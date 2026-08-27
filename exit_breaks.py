"""TODO #102 — break points: multi-break shaping of the exit leg.

The successor to the single `exit_mid_t` / `exit_mid_rotation` pair. Operators
already think in "at 40 % along the exit, turn 12°"; they simply want more than
one of them. Everything here is that one idea, in a list.

Pure geometry + validation. No Tk, no OCC, no PathGenerator state, so the dialog
and the engine share ONE implementation instead of mirroring each other.

DECIDED WITH THE USER (2026-08-27) — see PROPOSAL_break_points.md

* **Break points and #100 waypoints are separate features.** Waypoints are
  cartesian and frozen (dx/dz from P2); breaks are parametric and stay live — a
  percentage is still a percentage after reach, pass angle or progressive reach
  changes the leg's length. A pass that has waypoints ignores its breaks; that
  falls out of the engine's branch order and is logged, not silent.
* **Per pass**, stored beside `exit_points` under `pass_edits[i]["exit_breaks"]`,
  with an "apply to all passes" action in the editor — unlike dx/dz, the same
  40 % / −12° usually belongs on every pass of the op.
* **Angles are RELATIVE bends**: each row swings whatever is left of the tail by
  that many degrees relative to the direction it currently has. "Then turn
  another 10°". One break therefore behaves exactly as `exit_mid_rotation` did.
* **The legacy single break is replaced by fallback, not by migration.** A pass
  with no list of its own falls back to a one-item list built from the op's
  `exit_mid_t` / `exit_mid_rotation` (`legacy_break`), so every existing program
  produces byte-identical geometry and no .ssp is ever rewritten on load.

THE DATA MODEL::

    pass_edits["3"]["exit_breaks"] = [{"t": 0.40, "angle": -12.0}, ...]

`t` is a fraction of the exit leg, `angle` is degrees with the same sign
convention as `exit_mid_rotation` (rotation about +Y, i.e. in the XZ plane).

WHY THE INDICES ARE TAKEN ON THE ORIGINAL ARRAY

A rotation only touches points AFTER its own index and never changes how many
there are, so every break's index can be computed once, up front, against the
untouched leg. Applying them in ascending `t` then needs no re-parameterisation:
earlier breaks cannot slide later ones along the leg. The pivot POSITION, on the
other hand, must be read from the current array — break 2's pivot has already
been swung by break 1, and that is exactly what makes the bends accumulate.

POINT BUDGET. Each break is a corner, and RDP keeps corners by construction, so
K breaks cost at least K+2 lines on the leg. The S7-1200 stops at every point
and a recipe cannot exceed 1000 lines — `exit_max_points` (#101) still caps the
result. This is why MAX_BREAKS exists.
"""
import math

import numpy as np

# The pass shapes whose exit leg actually reaches the rotation block.
#
# NOT the same tuple as `exit_waypoints.SHAPES_WITH_TAIL`, and the difference is
# real rather than an oversight here: `linear_full` builds its exit leg in an
# EARLIER branch of `_create_and_store_pass` (path_generator.py:2177) and returns
# before the rotation is applied. The legacy single break has therefore never run
# on a linear_full pass. Listing it would make the editor promise a bend the
# engine does not make — worse than the inconsistency itself, which is #92-era
# behaviour and not something to change quietly under a new feature.
SHAPES_WITH_BREAKS = ("linear_approach",)

# Where a break may sit along the leg. The ends are excluded for the reason the
# single break always excluded them: a break AT P2 or AT the endpoint rotates
# either everything or nothing, and both are better expressed by the pass's own
# angle. Same numbers as the legacy clamp, so one break is unchanged.
T_MIN, T_MAX = 0.05, 0.95

# Below this the rotation is not worth a corner in the recipe. Matches the
# legacy `abs(_emid_rot) > 0.01` gate exactly.
ANGLE_EPS = 0.01

# Advisory only — the EDITOR stops offering Add beyond this. Deliberately NOT
# enforced in `normalize`: silently dropping breaks out of a hand-edited file
# would change the cut without saying so, which is the failure mode this project
# keeps running into. Geometry honours whatever is stored; the UI is what keeps
# the count sane.
MAX_BREAKS = 8


# ── data model ──────────────────────────────────────────────────────────────
def normalize(raw):
    """Coerce whatever is stored in the .ssp into a clean break list.

    Tolerant on purpose — a hand-edited or older file must not crash a
    calculation. Unparseable rows are dropped rather than guessed at. `t` is
    clamped rather than dropped: a break typed at 0 or 1 is a real instruction
    with an unreachable position, and the nearest legal one is what the operator
    meant. Sorted by `t`, which is the order the engine applies them in.
    """
    if not raw:
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            t = float(item.get("t", 0.5))
            angle = float(item.get("angle", 0.0))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(t) and math.isfinite(angle)):
            continue
        out.append({"t": min(max(t, T_MIN), T_MAX), "angle": angle})
    out.sort(key=lambda d: d["t"])
    return out


def legacy_break(op):
    """The op's single `exit_mid` break as a one-item list, or [].

    This is the whole of the "replace without migrating" plan: an op saved before
    break points existed answers `get_breaks` with exactly the rotation the old
    code applied, at exactly the same `t`, through exactly the same clamp — so
    the geometry it produces is unchanged to the last float.
    """
    if not op:
        return []
    try:
        rot = float(op.get("exit_mid_rotation", 0.0) or 0.0)
    except (TypeError, ValueError):
        return []
    if not math.isfinite(rot) or abs(rot) <= ANGLE_EPS:
        return []
    try:
        t = float(op.get("exit_mid_t", 0.5) or 0.5)
    except (TypeError, ValueError):
        t = 0.5
    if not math.isfinite(t):
        t = 0.5
    return [{"t": min(max(t, T_MIN), T_MAX), "angle": rot}]


def stored(op, pass_index):
    """This pass's OWN break list (no legacy fallback). [] when it has none."""
    edits = (op or {}).get("pass_edits") or {}
    pe = edits.get(str(pass_index)) or edits.get(pass_index) or {}
    return normalize(pe.get("exit_breaks"))


def get_breaks(op, pass_index):
    """The breaks the engine should apply to this pass.

    Its own list when it has one, otherwise the op's legacy single break. An
    empty list stored on the pass is NOT the same as no list: it means the
    operator deleted every row, and it correctly suppresses the legacy fallback
    only if the key is absent — so the editor removes the key entirely when the
    table is emptied (see the dialog's apply path).
    """
    own = stored(op, pass_index)
    return own if own else legacy_break(op)


def curl_active(op):
    """True when the #92 exit curl owns this leg, which disables breaks.

    Mirrors the engine's own parse of `exit_mid_radius` / `exit_mid_radius_end`.
    The engine keeps using its locally parsed values for the actual gate — this
    exists so the EDITOR can grey the button out for the same reason, instead of
    letting the operator author breaks that will not run.
    """
    for key in ("exit_mid_radius", "exit_mid_radius_end"):
        v = (op or {}).get(key, None)
        if v in (None, ""):
            continue
        try:
            if abs(float(v)) > 1e-4:
                return True
        except (TypeError, ValueError):
            continue
    return False


def excluded_reason(op):
    """Why this op cannot carry break points — or None when it can.

    Mirrors the conditions under which the engine's exit-leg rotation block is
    reached at all, so the editor can explain itself rather than accepting rows
    that quietly do nothing:

    * ``pass_shape``  — see SHAPES_WITH_BREAKS. A "spline" pass is one curve
      P1→P2→P3 with no separate exit leg to break; `linear_full` has one but
      builds it in a branch that never reaches the rotation.
    * ``reverse``     — a reverse pass without `reverse_legacy_flip` swaps its
      legs (#82), and the leg the breaks would bend is the one ENTERING the
      mandrel. The legacy single break was skipped there for the same reason.
      A reverse op that kept the legacy flip is fine and is NOT excluded.
    * ``curl``        — the #92 curl already shapes this leg and wins.

    A back pass is deliberately absent: `back_pass_enabled` adds an extra pass
    but the main pass still builds its exit leg normally, and the legacy break
    applied to it. Excluding it here would be a behaviour change, not a guard.
    """
    # `op is None` — not `not op` — on purpose, unlike the sibling guard in
    # exit_waypoints: None means "no op in hand, nothing to judge", but an EMPTY
    # dict is a real op that simply carries no keys, and its defaults (pass_shape
    # "spline") exclude it. Treating {} as permitted would have the editor offer
    # breaks on the one op shape that certainly ignores them.
    if op is None:
        return None
    if op.get("pass_shape", "spline") not in SHAPES_WITH_BREAKS:
        return "pass_shape"
    if (op.get("direction", "forward") == "reverse"
            and not op.get("reverse_legacy_flip", False)):
        return "reverse"
    if curl_active(op):
        return "curl"
    return None


# ── geometry ────────────────────────────────────────────────────────────────
def index_at(t, n):
    """Which point of an n-point leg a break at fraction `t` sits on.

    Clamped to [1, n-2]: the pivot must have something before it to stay put and
    something after it to swing. Identical arithmetic to the legacy block.
    """
    k = int(round(min(max(float(t), T_MIN), T_MAX) * (n - 1)))
    return min(max(k, 1), n - 2)


def rotate_about(points, deg, pivot):
    """Rotate (N,3) points about the +Y axis through `pivot`, in degrees.

    The numpy equivalent of `PathGenerator._apply_rotation` with
    ``gp_Dir(0, 1, 0)`` — same right-handed sense, same result, without dragging
    OCC into a module that wants to stay headless. `_test_exit_breaks.py` pins
    the two against each other so this cannot drift.
    """
    pts = np.asarray(points, dtype=float)
    if len(pts) == 0:
        return pts.reshape(0, 3)
    rad = math.radians(float(deg))
    c, s = math.cos(rad), math.sin(rad)
    dx = pts[:, 0] - float(pivot[0])
    dz = pts[:, 2] - float(pivot[2])
    return np.stack([float(pivot[0]) + dx * c + dz * s,
                     pts[:, 1],
                     float(pivot[2]) - dx * s + dz * c], axis=1)


def apply(points, breaks):
    """Apply every break to an exit leg, in order along the leg.

    `points` is the leg as built by whatever shape produced it (straight, bow,
    tangent-chord arc); breaks bend it afterwards, which is what the single
    `exit_mid_rotation` always did. Returns a NEW array of the same length —
    rotations move points, they never add or remove any.

    Legs shorter than 3 points are returned untouched: there is no interior
    point to pivot on. Same guard as the legacy block.
    """
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3 or not breaks:
        return pts
    out = pts
    n = len(pts)
    for b in sorted(breaks, key=lambda d: d["t"]):
        angle = float(b["angle"])
        if abs(angle) <= ANGLE_EPS:
            continue
        k = index_at(b["t"], n)
        # Pivot read from the CURRENT array, index from the original: see the
        # module docstring for why that pair is what makes the bends relative.
        out = np.vstack([out[:k + 1], rotate_about(out[k + 1:], angle, out[k])])
    return out
