"""Start a forward pass where the previous stroke stopped (``start_from_last``).

THE SHAPE, in the user's words (2026-09-20): "a normal roughing pass that the
part below a specific X is removed. But that X, actually that point, is already
calculated in the previous back or reverse short-ended pass."

So this is NOT a new kind of pass. The engine builds an ordinary forward pass -
approach arm, P2 fillet, exit leg, with every one of its own settings - and then
the part before a given point is cut away. What survives starts out in the sheet
and runs to P3. Nothing about its shape is new, which is why it needs no
parameters of its own: one tickbox, and the point comes from the previous
toolpath's end.

"That X" turned out to be the wrong reading of it, corrected on the user's own
program (2026-09-20): matching the anchor's X left a 1.998 mm gap, because a
back pass is not the forward pass reversed. See `plan`.

Reading the previous toolpath's end is not a new idea here either: a Point op in
"relative" mode and a "relative" tool-change position both anchor on
``toolpaths[-1][-1]``, for the same reason - it is where the roller actually is.

Together with ``stop_short`` this makes the letter M:

    Op1  forward (normal)                out
         back pass, stopped short        in, partway     <- stop_short
    Op2  forward, cut at that point      out             <- this module
         back pass (normal)              in, all the way

FIRST PASS ONLY (user, 2026-09-20). An operation with three passes cuts only
pass 1; passes 2 and 3 begin at the mandrel as they always did. The stop point
belongs to the stroke that came before the OPERATION, not to each pass.

Pure module: no engine imports, no UI imports.
"""
import numpy as np

OP_KEY = "start_from_last"

# What must survive the cut. Below this there is no pass worth emitting.
MIN_REMAIN_MM = 1.0

REASONS = {
    "no_anchor": "nothing ran before this operation, so there is no point to start from",
    "not_reached": "this pass passes nowhere near where the previous stroke stopped",
    "too_short": "cutting there would leave almost nothing of the pass",
}


def enabled(op):
    """The tickbox. Absent = OFF."""
    return bool((op or {}).get(OP_KEY, False))


def op_can_use(op):
    """Whether the tickbox means anything on this op (editor visibility).

    A forming op with pass geometry to cut. Cutting, bending and Point ops have
    none. A REVERSE op is excluded on purpose: it is stored back-to-front and
    already ends at the mandrel, so "cut the beginning" would land on the far
    end of the approach arm - a different feature wearing the same name.
    """
    op = op or {}
    if op.get("type", "roughing") in ("cutting", "bending", "point"):
        return False
    return op.get("direction", "forward") != "reverse"


def plan(path, anchor, exit_start=0):
    """Where to cut ``path`` so it begins at ``anchor``.

    ``anchor`` is the POINT the previous stroke ended at, [x, y, z]. The cut
    lands on the path point CLOSEST to it - not merely where the path reaches
    the anchor's X.

    Why not X (the first attempt, corrected 2026-09-20 on the user's own test
    program): a back pass is NOT the forward pass reversed. A bow
    (``back_pass_arc_z``) and the clearance correction both move it off that
    line - measured 5.6 to 8.0 mm of X over most of its length on that file. So
    the X where the return stroke stopped sits somewhere quite different on the
    forward line, and matching X alone left a 1.998 mm gap in Z - exactly the
    2.0 mm bow the operator had set. Closest point cannot drift that way.

    ``exit_start`` is the index where the P2->P3 leg begins (the engine's
    ``last_render_split_idx``); the search starts there because the approach arm
    can pass close to the anchor too, and cutting inside the arm is never meant.
    0 means "search the whole path", which is what a shape with no recorded
    split gets.

    Returns ``None`` when there is nothing to do, else ``(i, t)``: the new path
    is one point interpolated ``t`` of the way from ``path[i]`` to
    ``path[i + 1]``, followed by ``path[i + 1:]``. The caller puts the anchor
    itself in front of that, so the pass starts exactly where the roller is and
    runs a short join onto its own line.

    Pure. Never mutates ``path``.
    """
    try:
        pts = np.asarray(path, dtype=float)
        a = np.asarray(anchor, dtype=float)
    except (TypeError, ValueError):
        return None
    if (pts.ndim != 2 or len(pts) < 2 or a.size < 3
            or not np.all(np.isfinite(pts)) or not np.all(np.isfinite(a))):
        return None
    lo = max(0, min(int(exit_start), len(pts) - 2))

    # Closest point on the polyline, segment by segment, in the XZ plane.
    best = None
    for i in range(lo, len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        d = p1 - p0
        den = float(d[0] * d[0] + d[2] * d[2])
        if den < 1e-18:
            t = 0.0
        else:
            t = float(((a[0] - p0[0]) * d[0] + (a[2] - p0[2]) * d[2]) / den)
            t = min(max(t, 0.0), 1.0)
        q = p0 + t * d
        dist = float(np.hypot(q[0] - a[0], q[2] - a[2]))
        if best is None or dist < best[0]:
            best = (dist, i, t)

    if best is None:
        return None
    _, i, t = best

    # Enough pass left after the cut to be worth emitting?
    tail = pts[i + 1:]
    cut_pt = pts[i] + t * (pts[i + 1] - pts[i])
    remain = float(np.linalg.norm(tail[0] - cut_pt)) if len(tail) else 0.0
    if len(tail) > 1:
        # dtype forced - see the same note in stop_short.plan: numpy takes its
        # object-array reduction path in a mocked environment and dies on its
        # own sentinel.
        remain += float(np.sum(np.linalg.norm(np.diff(tail, axis=0), axis=1),
                               dtype=float))
    if remain < MIN_REMAIN_MM:
        return None
    return (i, t)


def _closest(pts, a, lo):
    """(index, t, distance) of the closest point on the polyline, from ``lo`` on."""
    best = None
    for i in range(lo, len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        d = p1 - p0
        den = float(d[0] * d[0] + d[2] * d[2])
        t = 0.0 if den < 1e-18 else float(
            ((a[0] - p0[0]) * d[0] + (a[2] - p0[2]) * d[2]) / den)
        t = min(max(t, 0.0), 1.0)
        q = p0 + t * d
        dist = float(np.hypot(q[0] - a[0], q[2] - a[2]))
        if best is None or dist < best[2]:
            best = (i, t, dist)
    return best


def _cross(u, v):
    """2D cross product in the XZ plane."""
    return float(u[0] * v[2] - u[2] * v[0])


def shift_to_meet(path, anchor, move_dir, exit_start=0, max_shift_mm=25.0,
                  tol_mm=1e-3, iters=12):
    """How far to MOVE the whole pass so it runs through ``anchor``.

    The operator was doing this by hand: on his own program he raised Start Z
    from 10 to 12 and the pass met the previous stroke exactly. Measured there,
    the miss falls off a clean straight line - 1.866 mm at Start Z 10, 0.933 at
    11, 0.000 at 12 - so there is one answer and it can be solved for.

    ``move_dir`` is the direction the pass travels when Start Z changes: the
    mandrel surface tangent at the contact, [dr/dz, 0, 1]. Moving along it is
    what raising Start Z does, to first order, which is why the answer matches
    what he typed.

    SOLVED ON THE REAL POLYLINE, not on a straight line through it. The first
    attempt used the chord of the exit leg and overshot badly - 7.3 mm where the
    answer was 2.0 - because the leg is CURVED and the anchor sat 6.86 mm from
    the chord while being only 1.87 mm from the path itself. So each step
    measures the closest point on the path and its LOCAL tangent, and the loop
    absorbs whatever curvature is left.

    Returns the displacement as a 3-vector, or ``None`` when there is nothing to
    do or the answer is absurd (further than ``max_shift_mm`` - a pass that far
    from the anchor is not the one the operator meant to continue).

    Pure. Never mutates ``path``.
    """
    # A pure geometry helper must never take the program down - see the same
    # guard in stop_short.plan.
    try:
        pts = np.asarray(path, dtype=float)
        a = np.asarray(anchor, dtype=float)
        m = np.asarray(move_dir, dtype=float)
    except (TypeError, ValueError):
        return None
    if (pts.ndim != 2 or len(pts) < 2 or a.size < 3
            or not np.all(np.isfinite(pts)) or not np.all(np.isfinite(a))
            or not np.all(np.isfinite(m))):
        return None
    mn = float(np.hypot(m[0], m[2]))
    if mn < 1e-9:
        return None
    m = m / mn
    lo = max(0, min(int(exit_start), len(pts) - 2))

    cur = pts.copy()
    total = 0.0
    for _ in range(int(iters)):
        i, t, _ = _closest(cur, a, lo)
        q = cur[i] + t * (cur[i + 1] - cur[i])
        tan = cur[i + 1] - cur[i]
        tn = float(np.hypot(tan[0], tan[2]))
        if tn < 1e-12:
            break
        tan = tan / tn
        off = _cross(a - q, tan)          # signed miss, zero when on the line
        rate = _cross(m, tan)             # how fast it closes as the pass moves
        if abs(rate) < 1e-9:
            break                         # the pass moves along its own line
        step = off / rate
        if abs(total + step) > float(max_shift_mm):
            return None
        cur = cur + m * step
        total += step
        if abs(step) < float(tol_mm):
            break

    if abs(total) < 1e-9:
        return None
    return m * total


def apply(arr, cut):
    """Cut the front off one per-point array, the way ``plan`` says.

    Works for the path (N x 3), its projections (N x 3) and its deviations (N).
    The new first entry is interpolated - which is what a projection or a
    deviation is between two neighbouring samples anyway.
    """
    if cut is None:
        return arr
    i, t = cut
    a = np.asarray(arr)
    if len(a) <= i + 1:
        return arr
    if t <= 1e-9:
        return a[i:]
    if t >= 1.0 - 1e-9:
        return a[i + 1:]
    first = np.asarray(a[i] + t * (a[i + 1] - a[i]))
    return np.concatenate([first.reshape((1,) + a.shape[1:]), a[i + 1:]])


def join(path, anchor, max_join_mm=None):
    """Put ``anchor`` in front of ``path`` so the pass STARTS where the roller is.

    The cut lands on the pass's own line, which is generally not the anchor: the
    stroke before it was a different curve (see ``plan``). Rather than move the
    pass - which would carry its clearance, its P3 and the flange edge with it,
    by an amount that is really just the back pass's bow - the pass stays
    exactly where it was designed and one short move joins the two.

    Returns ``(path, join_mm)``. A zero-length join adds nothing.
    """
    pts = np.asarray(path, dtype=float)
    a = np.asarray(anchor, dtype=float)
    if len(pts) == 0:
        return path, 0.0
    d = float(np.hypot(pts[0][0] - a[0], pts[0][2] - a[2]))
    if d <= 1e-6:
        return pts, 0.0
    if max_join_mm is not None and d > float(max_join_mm):
        return pts, d               # caller decides what to do about it
    first = np.array([[a[0], pts[0][1], a[2]]], dtype=float)
    return np.concatenate([first, pts]), d


def apply_parallel(arr, cut, n_path_before):
    """Cut a per-point array only when it really tracks the path.

    Exact length is the normal case; the engine also produces projection lists
    one entry SHORT of their path on a linear_approach pass (measured
    2026-09-20, present with this feature off). Anything else is a mismatch this
    module does not understand and is returned untouched.
    """
    n = len(arr)
    if n == 0 or n not in (n_path_before, n_path_before - 1):
        return arr
    return apply(arr, cut)
