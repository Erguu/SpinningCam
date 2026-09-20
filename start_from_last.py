"""Start a forward pass where the previous stroke stopped (``start_from_last``).

THE SHAPE, in the user's words (2026-09-20): "a normal roughing pass that the
part below a specific X is removed. But that X, actually that point, is already
calculated in the previous back or reverse short-ended pass."

So this is NOT a new kind of pass. The engine builds an ordinary forward pass -
approach arm, P2 fillet, exit leg, with every one of its own settings - and then
the part before a given X is cut away. What survives starts out in the sheet and
runs to P3. Nothing about its shape is new, which is why it needs no parameters
of its own: one tickbox, and the X comes from the previous toolpath's end.

Reading the previous toolpath's end is not a new idea here either: a Point op in
"relative" mode and a "relative" tool-change position both anchor on
``toolpaths[-1][-1]``, for the same reason - it is where the roller actually is.

Together with ``stop_short`` this makes the letter M:

    Op1  forward (normal)                out
         back pass, stopped short        in, partway     <- stop_short
    Op2  forward, cut at that X          out             <- this module
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
    "not_reached": "this pass never reaches the X the previous stroke stopped at",
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


def plan(path, x_value, exit_start=0):
    """Where to cut ``path`` so it begins at ``x_value``.

    ``exit_start`` is the index where the P2->P3 leg begins (the engine's
    ``last_render_split_idx``); the search starts there because X is NOT unique
    over a whole pass - the approach arm runs at nearly constant X and a naive
    search would cut in the arm instead of the exit leg. 0 means "search the
    whole path", which is what a shape with no recorded split gets.

    Coordinates here are CANONICAL (+X outward), which is what calculate_paths
    works in until it mirrors at the very end - so X grows along the exit leg
    and the first crossing is the one wanted.

    Returns ``None`` when there is nothing to do, else ``(i, t)``: the new path
    is one point interpolated ``t`` of the way from ``path[i]`` to
    ``path[i + 1]``, followed by ``path[i + 1:]``.

    Pure. Never mutates ``path``.
    """
    pts = np.asarray(path, dtype=float)
    if pts.ndim != 2 or len(pts) < 2:
        return None
    lo = max(0, min(int(exit_start), len(pts) - 2))

    for i in range(lo, len(pts) - 1):
        x0, x1 = pts[i][0], pts[i + 1][0]
        if x0 <= x_value <= x1 or x1 <= x_value <= x0:
            span = x1 - x0
            t = 0.0 if abs(span) < 1e-12 else (x_value - x0) / span
            t = float(min(max(t, 0.0), 1.0))
            # Enough pass left after the cut to be worth emitting?
            tail = pts[i + 1:]
            cut_pt = pts[i] + t * (pts[i + 1] - pts[i])
            remain = float(np.linalg.norm(tail[0] - cut_pt))
            if len(tail) > 1:
                remain += float(np.linalg.norm(np.diff(tail, axis=0), axis=1).sum())
            if remain < MIN_REMAIN_MM:
                return None
            return (i, t)
    return None


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
