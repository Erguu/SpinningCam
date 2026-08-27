"""
TODO #100 — operator-authored exit tail: the points between P2 and the end of a pass.

Pure geometry + validation. No Tk, no OCC, no PathGenerator state, so the whole
thing is testable headless and the dialog and the engine can share one
implementation instead of mirroring each other (the trap `compute_pass_rows`
already has to work around).

THE DATA MODEL (decided with the user, 2026-08-26)

A pass carries a LIST of waypoints under `pass_edits[i]["exit_points"]`. Each is::

    {"anchor": "p2" | "prev", "dx": float, "dz": float, "feed": float|None}

* Positions are RELATIVE, never absolute — the operator cannot compute machine
  X/Z in his head, and P2 moves from pass to pass anyway.
* The anchor is chosen PER POINT:
    - ``"p2"``   → dx/dz are measured from the pass's contact point P2.
                   Moving this point moves only this point.
    - ``"prev"`` → dx/dz are measured from the previous waypoint (a step).
                   Moving it drags every later point with it.
  Both resolve to the same geometry; the anchor is an authoring convenience.
* dx/dz use the SAME sense as the existing `p3_x` / `p3_z` op params: dx is a
  plain +X offset, dz a +Z offset, in CAM space. Reusing that convention keeps
  the seeded values readable next to the fields they came from.
* ``feed`` is optional per point (None = inherit the pass feed). Parsed and
  carried here; G-code emission of it is NOT wired yet.

THERE IS NO P3. The last waypoint IS the end of the pass — this is why the
reach / pass-angle / P3 controls are greyed out on an op that carries waypoints.

TWO SHAPES (`exit_shape`, per pass, alongside `exit_points`):

* ``"straight"`` (**the default**, user 2026-08-27) — the waypoints ARE the
  path. N waypoints produce exactly N points after P2, joined by straight
  lines. This is what the S7-1200 wants: it has no velocity blending and a hard
  1000-line ceiling, so every extra point is a full stop and a spent line. The
  operator draws the route; the machine runs exactly it.
* ``"spline"`` — a centripetal Catmull-Rom through P2 and every waypoint. It
  passes THROUGH each point and, unlike the uniform variant, provably never
  forms a cusp or a self-intersecting loop. Smoother, but it turns 5 waypoints
  into ~100 emitted points, which is the opposite of what this machine needs.
  Kept for a controller that can blend — the geometry is sound, the point
  budget is what rules it out here.

The choice is per pass because it is a property of the shape the operator drew,
not of the machine — and a program may want a curved finishing tail alongside
straight roughing ones.
"""
import math

import numpy as np

# Curve sampling: points per Catmull-Rom span. The result is decimated later for
# the PLC anyway, so this only needs to be fine enough that the clearance check
# and the 3D view see the real shape.
SAMPLES_PER_SPAN = 24

VALID_ANCHORS = ("p2", "prev")

SHAPE_STRAIGHT = "straight"
SHAPE_SPLINE = "spline"
VALID_SHAPES = (SHAPE_STRAIGHT, SHAPE_SPLINE)

# Straight is the default EVERYWHERE, including tails authored before the option
# existed (user 2026-08-27). A tail drawn as 5 points should cost 5 lines; the
# spline silently cost ~100, which is what made the feature unusable on this PLC.
DEFAULT_SHAPE = SHAPE_STRAIGHT

# Clearance is checked along the emitted geometry, not just at its vertices: a
# straight chord between two clear waypoints can still cut through the part.
# 0.25 mm keeps the scan fine relative to anything the roller can hide behind.
CHECK_STEP = 0.25

# How far inside the clearance a sample may sit before it counts as a violation.
#
# Sitting EXACTLY on the clearance contour is legal and common: P2 is placed at
# exactly the op clearance by construction, and an exit tail that follows the
# part surface has every point on that contour by design. An exact comparison
# turns those legitimate shapes into a knife edge — the interpolating curve
# bows a few nanometres inside the chord between two points that are both
# precisely on the limit, and the operator gets "1.70 mm, needs 1.70 mm" with
# no number he can type to satisfy it.
#
# 1 µm: far below anything this machine can position or measure (and far below
# the mandrel-profile sampling error), while being orders of magnitude above
# float noise. A real gouge is tenths of a millimetre, never microns.
CLEARANCE_EPS = 1e-3


# ── data model ──────────────────────────────────────────────────────────────
def normalize(raw):
    """Coerce whatever is stored in the .ssp into a clean waypoint list.

    Tolerant on purpose: a hand-edited or older file must not crash a
    calculation. Anything unparseable is dropped rather than guessed at.
    Returns [] when there is nothing usable, which is the 'feature off' state.
    """
    if not raw:
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            dx = float(item.get("dx", 0.0))
            dz = float(item.get("dz", 0.0))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(dx) and math.isfinite(dz)):
            continue
        anchor = item.get("anchor", "p2")
        if anchor not in VALID_ANCHORS:
            anchor = "p2"
        feed = item.get("feed", None)
        try:
            feed = float(feed) if feed not in (None, "") else None
        except (TypeError, ValueError):
            feed = None
        if feed is not None and (not math.isfinite(feed) or feed <= 0):
            feed = None
        out.append({"anchor": anchor, "dx": dx, "dz": dz, "feed": feed})
    return out


def resolve(p2_x, p2_z, points):
    """Waypoints → absolute (x, z) in CAM space, applying each point's anchor.

    The first point is always measured from P2 whatever its anchor says: there is
    no previous point to step from, and silently treating it as 0,0 would put a
    waypoint exactly on the contact point.
    """
    out = []
    cx, cz = float(p2_x), float(p2_z)
    for k, w in enumerate(points):
        if w["anchor"] == "prev" and k > 0:
            bx, bz = out[-1]
        else:
            bx, bz = cx, cz
        out.append((bx + w["dx"], bz + w["dz"]))
    return out


# ── curve ───────────────────────────────────────────────────────────────────
def _centripetal_span(P0, P1, P2, P3, n, alpha=0.5):
    """One Catmull-Rom span P1→P2 (Barry-Goldman), sampled n times inclusive."""
    def _next_t(t, a, b):
        d = float(np.linalg.norm(b - a))
        return t + (d ** alpha if d > 1e-12 else 1e-6)

    t0 = 0.0
    t1 = _next_t(t0, P0, P1)
    t2 = _next_t(t1, P1, P2)
    t3 = _next_t(t2, P2, P3)

    t = np.linspace(t1, t2, n).reshape(-1, 1)
    A1 = (t1 - t) / (t1 - t0) * P0 + (t - t0) / (t1 - t0) * P1
    A2 = (t2 - t) / (t2 - t1) * P1 + (t - t1) / (t2 - t1) * P2
    A3 = (t3 - t) / (t3 - t2) * P2 + (t - t2) / (t3 - t2) * P3
    B1 = (t2 - t) / (t2 - t0) * A1 + (t - t0) / (t2 - t0) * A2
    B2 = (t3 - t) / (t3 - t1) * A2 + (t - t1) / (t3 - t1) * A3
    return (t2 - t) / (t2 - t1) * B1 + (t - t1) / (t2 - t1) * B2


def build_curve(p2_x, p2_z, points, samples_per_span=SAMPLES_PER_SPAN,
                start_xz=None, shape=DEFAULT_SHAPE):
    """Polyline P2 → … → last waypoint, as an (N,3) array of [x, 0, z].

    Returns an empty (0,3) array when there is nothing to build, so callers can
    treat 'no waypoints' as 'feature off' with one check.

    With ``shape="straight"`` (the default) the result IS the control polyline:
    one point per waypoint, nothing interpolated, so what the operator drew is
    exactly what gets emitted. With ``shape="spline"`` the same control points
    are run through a centripetal Catmull-Rom; ends are handled by REFLECTING
    the neighbouring point rather than duplicating it, because duplicating gives
    a zero-length span and centripetal parameterisation divides by that length.

    `start_xz` replaces the FIRST control point without touching how the
    waypoints are anchored. The engine passes the P2 fillet's tangent point T2
    there: the operator still measures his offsets from P2 (the frame he
    understands), but the tail has to begin where the fillet let go, or the two
    would overlap.
    """
    pts = resolve(p2_x, p2_z, points)
    if not pts:
        return np.empty((0, 3))

    _sx, _sz = (p2_x, p2_z) if start_xz is None else start_xz
    ctrl = [np.array([float(_sx), float(_sz)], dtype=float)]
    for x, z in pts:
        ctrl.append(np.array([float(x), float(z)], dtype=float))

    # Drop consecutive duplicates — they carry no shape and break the parameterisation.
    dedup = [ctrl[0]]
    for c in ctrl[1:]:
        if float(np.linalg.norm(c - dedup[-1])) > 1e-9:
            dedup.append(c)
    ctrl = dedup

    if len(ctrl) == 1:
        return np.empty((0, 3))

    if shape != SHAPE_SPLINE:
        # STRAIGHT: the waypoints are the path. No sampling, no smoothing — the
        # emitted point count equals what the operator can see in the table.
        xz = np.array(ctrl, dtype=float)
        return np.stack([xz[:, 0], np.zeros(len(xz)), xz[:, 1]], axis=1)

    if len(ctrl) == 2:                                  # single step → straight line
        n = max(2, int(samples_per_span))
        xs = np.linspace(ctrl[0][0], ctrl[1][0], n)
        zs = np.linspace(ctrl[0][1], ctrl[1][1], n)
        return np.stack([xs, np.zeros_like(xs), zs], axis=1)

    ext = [ctrl[0] + (ctrl[0] - ctrl[1])] + ctrl + [ctrl[-1] + (ctrl[-1] - ctrl[-2])]

    n = max(2, int(samples_per_span))
    xz = []
    for k in range(1, len(ext) - 2):
        span = _centripetal_span(ext[k - 1], ext[k], ext[k + 1], ext[k + 2], n)
        xz.append(span if not xz else span[1:])         # avoid duplicating the join
    xz = np.vstack(xz)
    return np.stack([xz[:, 0], np.zeros(len(xz)), xz[:, 1]], axis=1)


def normalize_shape(raw):
    """Whatever is stored → a valid shape token. Unknown/absent → DEFAULT_SHAPE."""
    return raw if raw in VALID_SHAPES else DEFAULT_SHAPE


def get_shape(op, pass_index):
    """The exit-tail shape for one pass (`straight` unless it says otherwise)."""
    edits = (op or {}).get("pass_edits") or {}
    pe = edits.get(str(pass_index)) or edits.get(pass_index) or {}
    return normalize_shape(pe.get("exit_shape"))


# ── safety ──────────────────────────────────────────────────────────────────
def densify(curve, step=CHECK_STEP):
    """Subdivide a polyline so no segment is longer than `step`.

    Needed because the clearance check looks at POINTS. In straight mode the
    emitted geometry is only a handful of vertices metres apart in the worst
    case, and a chord between two perfectly clear waypoints can pass straight
    through the part. Checking the vertices alone would miss exactly the gouge
    the operator is most likely to draw.
    """
    pts = np.asarray(curve, dtype=float)
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        d = float(np.linalg.norm(b - a))
        n = max(1, int(math.ceil(d / max(float(step), 1e-6))))
        for k in range(1, n + 1):
            out.append(a + (b - a) * (k / n))
    return np.array(out)


def check_clearance(curve, radius_at, center_x, base_offset, min_clearance):
    """Find where a waypoint tail comes closer to the part than it may.

    `radius_at(z)` returns the mandrel radius (None = unknown/outside), and
    `base_offset` is blank + shell + r_tool — the same decomposition the rest of
    the engine uses, passed in so this module stays free of engine state.

    Returns a list of {index, x, z, clearance} for the sampled points that
    violate, worst first. Empty list = the tail is clear. A sample is judged
    against `min_clearance - CLEARANCE_EPS`, so a tail lying exactly ON the
    clearance contour passes — see CLEARANCE_EPS for why that case is normal
    rather than marginal.

    ⚠️ Checks the GENERATED GEOMETRY, densified — not the typed waypoints, and
    not only the vertices. Two perfectly legal waypoints can still put the part
    between them: a spline bows through, a straight chord cuts across. Testing
    only the operator's numbers would miss exactly the case that matters.
    """
    if len(curve) == 0:
        return []
    bad = []
    for k, (x, _y, z) in enumerate(densify(curve)):
        r = radius_at(float(z))
        if r is None:
            continue
        clear = abs(float(x) - center_x) - (float(r) + base_offset)
        if clear < min_clearance - CLEARANCE_EPS:
            bad.append({"index": int(k), "x": float(x), "z": float(z),
                        "clearance": float(clear)})
    bad.sort(key=lambda d: d["clearance"])
    return bad


# The pass shapes whose exit leg the engine actually builds from waypoints.
# "spline" generates P1→P2→P3 as one curve (path_generator.py, the `else` branch
# after the linear shapes) and never looks at exit_points.
SHAPES_WITH_TAIL = ("linear_approach", "linear_full")


def excluded_reason(op):
    """Why this op may not carry waypoints — or None when it may.

    #100 D10 (user, 2026-08-26): reverse and back passes are OUT of scope for
    now. Back passes are built by a different route entirely and reverse passes
    deliberately keep the mandrel-entry leg straight, so each would need its own
    geometry, clearance handling and regression tests. Two refusals instead.

    2026-08-27, found by research: `pass_shape` belongs on the same list. A
    "spline" op ignores the tail geometry completely — but the tail was still
    being STORED and its per-point feeds still emitted, matched to whatever path
    point happened to be nearest (measured 6–14 mm away). Excluding the shape
    here fixes that at the source: no points, no feeds, no clearance report
    about a tail that is not running, and the editor button explains itself.

    Returns a short machine-readable token the UI turns into a message.
    """
    if not op:
        return None
    if op.get("direction", "forward") == "reverse":
        return "reverse"
    if op.get("back_pass_enabled", False):
        return "back_pass"
    if op.get("pass_shape", "spline") not in SHAPES_WITH_TAIL:
        return "pass_shape"
    return None


def stored_count(op, pass_index):
    """How many waypoints are STORED for this pass, ignoring the exclusions.

    `get_points` returns [] for an excluded op, which is what the engine needs —
    but it makes a tail the operator drew indistinguishable from no tail at all.
    This is what lets the UI say "you have 4 points here and they are not
    running" instead of silently dropping them.
    """
    edits = (op or {}).get("pass_edits") or {}
    pe = edits.get(str(pass_index)) or edits.get(pass_index) or {}
    return len(normalize(pe.get("exit_points")))


def get_points(op, pass_index):
    """The normalized waypoint list for one pass, or [] when it has none.

    Honours the #100 D10 exclusions: an op that may not carry waypoints reports
    none, so the engine can never build them for a reverse or back-pass op even
    if a hand-edited .ssp contains them.
    """
    if excluded_reason(op):
        return []
    edits = (op or {}).get("pass_edits") or {}
    pe = edits.get(str(pass_index)) or edits.get(pass_index) or {}
    return normalize(pe.get("exit_points"))
