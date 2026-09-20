"""Stop a stroke short of the mandrel (op field ``stop_short_mm``).

THE RULE, in the user's words (2026-09-20): the number only affects movement
TOWARDS the mandrel. So a forward pass is never touched - it travels outward,
to the blank edge, and where it ends there is already settled by reach and the
blank factor. What it does touch is the stroke that comes back:

* a BACK PASS, which runs P3 -> exit leg -> P2 fillet -> T1, ending on the
  mandrel wall;
* a REVERSE pass, which is the forward pass driven backwards and ends at the
  far end of the straight approach arm.

With ``back_pass_swapped`` the two strokes trade places, and the rule still
picks the right one: the trimmed stroke is whichever runs INWARD, not whichever
runs second. In the engine that is always the array called ``bck_path`` (and,
for a reverse op, the pass itself).

Why this is not just ``p1_z``. On a reverse op you CAN already end the pass
earlier by shortening the approach arm - but the arm length also caps the P2
fillet (``_arc_fillet_at_p2``: ``max_len = min(leg1, leg2) * 0.9``), so past a
point it quietly shrinks the corner radius as well. Trimming the end leaves the
corner alone.

The trim is measured ALONG the stroke, not as a straight line to its end, so it
stays honest when the exit leg is bowed or curled.

Pure module: no engine imports, no UI imports.
"""
import numpy as np

OP_KEY = "stop_short_mm"

# What must be left of a stroke after trimming. Below this there is no pass
# worth emitting, and the decimator/PLC caps downstream assume a real polyline.
# Refusing (and REPORTING) beats shipping a stub.
MIN_REMAIN_MM = 1.0

REASONS = {
    "too_long": "the trim is longer than the stroke it is cutting",
}


def distance_mm(op):
    """The op's trim in mm, or 0.0 when it is off.

    Off is the default and the safe answer: absent, empty, unreadable, not
    finite, or <= 0 all mean "do nothing", never "guess a number".
    """
    raw = (op or {}).get(OP_KEY, None)
    if raw in (None, ""):
        return 0.0
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(v) or v <= 0:
        return 0.0
    return v


def enabled(op):
    return distance_mm(op) > 0.0


def op_can_use(op, builds_back_pass):
    """Whether the field means anything on this op (editor visibility).

    An op has an inward stroke when it runs reverse, or when it builds a back
    pass. ``builds_back_pass`` is ``path_generator.op_builds_back_pass(op)``,
    passed in so this module stays import-free.

    Deliberately NOT restricted to roughing, unlike the mandrel-end link: a
    reverse FINISHING pass is a reverse pass and travels inward like any other.
    Cutting, bending and Point ops have no pass geometry at all, so they are out.
    """
    op = op or {}
    if op.get("type", "roughing") in ("cutting", "bending", "point"):
        return False
    return op.get("direction", "forward") == "reverse" or bool(builds_back_pass)


def plan(path, mm):
    """Where to cut ``mm`` off the END of a polyline, measured along it.

    Returns ``None`` when nothing should happen - the trim is off, the path is
    too short to measure, or the cut would not leave ``MIN_REMAIN_MM``. The
    caller reports that last case rather than shipping a stub.

    Otherwise returns ``(keep, t)``:
      * points ``0 .. keep`` of the original survive;
      * when ``t > 0`` ONE more point is added, interpolated ``t`` of the way
        from ``path[keep]`` to ``path[keep + 1]``.

    Pure. Never mutates ``path``.
    """
    if mm <= 0:
        return None
    # A pure geometry helper must never take the program down. Anything it
    # cannot measure - a path that will not convert, a NaN from a degenerate
    # build - means "do nothing", which is this feature's safe answer anyway.
    try:
        pts = np.asarray(path, dtype=float)
    except (TypeError, ValueError):
        return None
    if pts.ndim != 2 or len(pts) < 2 or not np.all(np.isfinite(pts)):
        return None
    segs = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    # dtype forced: without it numpy takes its object-array reduction path in a
    # mocked environment and dies on its own sentinel (test_app_structure).
    try:
        total = float(np.sum(segs, dtype=float))
    except (TypeError, ValueError):
        return None
    if total <= 0:
        return None
    target = total - float(mm)
    if target < MIN_REMAIN_MM:
        return None

    acc = 0.0
    for i, seg in enumerate(segs):
        if seg <= 0:
            continue
        if acc + seg >= target:
            t = (target - acc) / seg
            if t <= 1e-9:
                # The cut lands ON path[i]. Keep up to it, add nothing.
                return (i, 0.0) if i >= 1 else None
            if t >= 1.0 - 1e-9:
                return (i + 1, 0.0)
            return (i, float(t))
        acc += seg
    return None                                   # target beyond the last point


def apply_parallel(arr, cut, n_path_before):
    """Trim a per-point array, but only when it really does track the path.

    Exact length is the normal case. The engine ALSO produces projection lists
    that are one entry SHORT of their path on a linear_approach pass - measured
    2026-09-20, present with this feature switched off and unrelated to it. Those
    are trimmed too: leaving them alone would let the projection end up LONGER
    than the trimmed path, which is worse than the off-by-one it started with.

    Anything else is a mismatch this module does not understand, so it is
    returned untouched rather than cut at an index that means nothing in it.
    """
    n = len(arr)
    if n == 0 or n not in (n_path_before, n_path_before - 1):
        return arr
    return apply(arr, cut)


def apply(arr, cut):
    """Trim one per-point array the same way ``plan`` trims the path.

    Works for the path itself (N x 3), its projections (N x 3) and its
    deviations (N). The extra point, when there is one, is interpolated
    linearly - which is what the projection and the deviation are between two
    neighbouring samples anyway.

    An array whose length does not match the path is returned UNCHANGED: an
    empty projections/deviations list is normal here, and silently reshaping it
    would be worse than leaving it alone.
    """
    if cut is None:
        return arr
    keep, t = cut
    a = np.asarray(arr)
    if len(a) <= keep + 1:
        return arr
    head = a[:keep + 1]
    if t <= 1e-9:
        return head
    extra = np.asarray(a[keep] + t * (a[keep + 1] - a[keep]))
    return np.concatenate([head, extra.reshape((1,) + a.shape[1:])])
