"""
Headless tests for TODO #100 core — exit_waypoints.py (pure geometry + safety).

Covers:
  1. normalize(): tolerant parsing, bad input dropped not guessed.
  2. resolve(): per-point anchor ("p2" vs "prev"), first point always from P2.
  3. build_curve(): passes THROUGH every waypoint, ends at the last one,
     no cusp/loop, degenerate inputs handled.
  3b. STRAIGHT is the default and emits exactly one point per waypoint — the
     waypoints ARE the path (user 2026-08-27); the spline is opt-in.
  4. check_clearance(): catches a bow BETWEEN two legal waypoints AND a straight
     chord that cuts across the part between two clear ones (the cases that
     testing only the typed numbers, or only the vertices, would miss).
  5. excluded_reason()/get_points(): reverse + back-pass ops carry no waypoints
     even if a hand-edited file says otherwise (#100 D10).

No OCC / Tk needed, but run it in the env anyway for numpy parity:
    runtest.bat _test_exit_waypoints.py
"""
import math

import numpy as np

import exit_waypoints as ew


def _near(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_normalize():
    assert ew.normalize(None) == []
    assert ew.normalize([]) == []

    out = ew.normalize([
        {"dx": 5, "dz": 2},                              # defaults to p2 anchor
        {"anchor": "prev", "dx": "3", "dz": "1.5", "feed": "200"},
        {"anchor": "nonsense", "dx": 1, "dz": 1},        # unknown anchor -> p2
        {"dx": "abc", "dz": 1},                          # unparseable -> dropped
        {"anchor": "p2", "dx": float("inf"), "dz": 0},   # non-finite -> dropped
        "not a dict",                                    # junk -> dropped
        {"dx": 1, "dz": 1, "feed": -5},                  # bad feed -> None
    ])
    assert len(out) == 4, f"expected 4 survivors, got {out}"
    assert out[0] == {"anchor": "p2", "dx": 5.0, "dz": 2.0, "feed": None}
    assert out[1] == {"anchor": "prev", "dx": 3.0, "dz": 1.5, "feed": 200.0}
    assert out[2]["anchor"] == "p2", "unknown anchor must fall back to p2"
    assert out[3]["feed"] is None, "non-positive feed must become None"
    print("[OK] normalize: junk dropped, anchors and feeds coerced")


def test_resolve_anchors():
    pts = ew.normalize([
        {"anchor": "p2",   "dx": 10, "dz": 0},
        {"anchor": "prev", "dx": 5,  "dz": 5},
        {"anchor": "p2",   "dx": 30, "dz": 1},
        {"anchor": "prev", "dx": 0,  "dz": 4},
    ])
    got = ew.resolve(100.0, 50.0, pts)
    assert got[0] == (110.0, 50.0), got[0]          # from P2
    assert got[1] == (115.0, 55.0), got[1]          # step from previous
    assert got[2] == (130.0, 51.0), got[2]          # back to P2-relative
    assert got[3] == (130.0, 55.0), got[3]          # step from previous

    # a leading "prev" has nothing to step from -> measured from P2
    lead = ew.normalize([{"anchor": "prev", "dx": 7, "dz": 3}])
    assert ew.resolve(100.0, 50.0, lead)[0] == (107.0, 53.0)
    print("[OK] resolve: per-point anchors, leading 'prev' falls back to P2")


def test_curve_passes_through_points():
    pts = ew.normalize([
        {"dx": 10, "dz": 4},
        {"dx": 22, "dz": 12},
        {"dx": 28, "dz": 26},
    ])
    p2 = (100.0, 50.0)
    curve = ew.build_curve(*p2, pts, shape=ew.SHAPE_SPLINE)
    assert len(curve) > 10, "the SPLINE shape should be densely sampled"

    # starts at P2, ends at the LAST waypoint (there is no P3)
    assert _near(curve[0][0], 100.0) and _near(curve[0][2], 50.0), curve[0]
    last = ew.resolve(*p2, pts)[-1]
    assert _near(curve[-1][0], last[0], 1e-6) and _near(curve[-1][2], last[1], 1e-6), (
        f"curve must END at the last waypoint {last}, got {curve[-1]}")

    # every waypoint is actually ON the curve (interpolating, not control points)
    for wx, wz in ew.resolve(*p2, pts):
        d = np.min(np.hypot(curve[:, 0] - wx, curve[:, 2] - wz))
        assert d < 1e-6, f"waypoint ({wx},{wz}) is {d:.4f} off the curve"

    # monotone-ish input must not produce a cusp: no reversal in arc direction
    seg = np.diff(curve[:, [0, 2]], axis=0)
    lens = np.hypot(seg[:, 0], seg[:, 1])
    assert np.all(lens > 0), "curve must not stall"
    dots = np.sum(seg[:-1] * seg[1:], axis=1) / (lens[:-1] * lens[1:])
    assert np.all(dots > 0.0), f"direction reversal (cusp) detected, min={dots.min():.3f}"
    print(f"[OK] build_curve(spline): {len(curve)} pts, through every waypoint, no cusp")


def test_straight_is_the_default_and_costs_nothing_extra():
    """#100, user 2026-08-27: the waypoints ARE the path.

    N waypoints must produce exactly N emitted points after P2 — no sampling.
    This is the whole point on a controller that stops at every point and has a
    1000-line ceiling; the spline turned 5 points into ~100.
    """
    assert ew.DEFAULT_SHAPE == ew.SHAPE_STRAIGHT, "straight is the default (user decision)"

    pts = ew.normalize([{"dx": 5, "dz": 1}, {"dx": 11, "dz": 2},
                        {"dx": 17, "dz": 3}, {"dx": 23, "dz": 4}])
    p2 = (100.0, 50.0)

    straight = ew.build_curve(*p2, pts)                       # default
    assert len(straight) == len(pts) + 1, (
        f"{len(pts)} waypoints + P2 must emit {len(pts) + 1} points, got {len(straight)}")

    # the emitted points ARE the waypoints, in order, exactly
    for k, (wx, wz) in enumerate(ew.resolve(*p2, pts), start=1):
        assert _near(straight[k][0], wx, 1e-9) and _near(straight[k][2], wz, 1e-9), (
            f"point {k} is {straight[k]} not ({wx},{wz})")

    # ...and it really is cheaper than the curve it replaced
    spline = ew.build_curve(*p2, pts, shape=ew.SHAPE_SPLINE)
    assert len(spline) > 5 * len(straight), (
        f"spline {len(spline)} should dwarf straight {len(straight)}")

    # an unknown/absent token falls back to straight rather than to the old curve
    assert ew.normalize_shape(None) == ew.SHAPE_STRAIGHT
    assert ew.normalize_shape("wobbly") == ew.SHAPE_STRAIGHT
    assert ew.normalize_shape("spline") == ew.SHAPE_SPLINE
    assert ew.get_shape({}, 0) == ew.SHAPE_STRAIGHT
    assert ew.get_shape({"pass_edits": {"0": {"exit_shape": "spline"}}}, 0) == ew.SHAPE_SPLINE
    assert ew.get_shape({"pass_edits": {"0": {"exit_shape": "spline"}}}, 1) == ew.SHAPE_STRAIGHT
    print(f"[OK] straight: {len(pts)} waypoints -> {len(straight)} pts "
          f"(spline would be {len(spline)})")


def test_straight_chord_through_the_part_is_caught():
    """Two waypoints can both be clear while the LINE between them is not.

    Straight mode makes this the likely failure, not an exotic one: the operator
    places a point above the shoulder and one below it, and the chord cuts the
    corner. check_clearance must densify, not just look at the vertices.
    """
    # A part whose radius bulges in the middle of the span.
    def radius_at(z):
        return 50.0 + 12.0 * math.exp(-((z - 25.0) ** 2) / 8.0)

    p2 = (60.0, 10.0)          # clear of the 50 mm shank
    pts = ew.normalize([{"dx": 0.0, "dz": 30.0}])   # straight up, past the bulge

    curve = ew.build_curve(*p2, pts)
    assert len(curve) == 2, "straight mode emits just the two ends here"

    # both ENDS are clear...
    for x, _y, z in curve:
        assert abs(x) - radius_at(z) > 1.0

    # ...but the chord passes through the bulge, and that must be caught
    bad = ew.check_clearance(curve, radius_at, 0.0, 0.0, 1.0)
    assert bad, "a chord straight through the bulge was NOT caught"
    assert bad[0]["clearance"] < 0, f"worst point should be inside the part: {bad[0]}"
    print(f"[OK] densified check: chord through the part caught "
          f"({len(bad)} samples, worst {bad[0]['clearance']:.2f} mm)")


def test_curve_degenerate_inputs():
    assert len(ew.build_curve(100.0, 50.0, [])) == 0, "no points -> empty"

    one = ew.normalize([{"dx": 10, "dz": 10}])
    line = ew.build_curve(100.0, 50.0, one)
    assert len(line) >= 2
    assert _near(line[-1][0], 110.0) and _near(line[-1][2], 60.0)
    mid = line[len(line) // 2]
    assert _near(mid[0] - 100.0, mid[2] - 50.0, 1e-6), "single step should be straight"

    # a waypoint sitting exactly on P2 is dropped rather than dividing by zero
    dup = ew.normalize([{"dx": 0, "dz": 0}, {"dx": 10, "dz": 10}])
    assert len(ew.build_curve(100.0, 50.0, dup)) >= 2
    print("[OK] build_curve: empty / single-step / duplicate-point inputs safe")


def test_clearance_catches_bow_between_legal_points():
    # Convex bump peaking at z=5; clearance = x - R(z) with base 0.
    def radius_at(z):
        if z < 0 or z > 10:
            return 100.0
        return 100.0 + 8.0 * np.sin(np.pi * z / 10.0)

    # Two waypoints that are each individually clear (at z=0 and z=10, R=100),
    # but the tail between them runs straight across the 108 bump.
    pts = ew.normalize([{"dx": 2.0, "dz": 0.0}, {"dx": 2.0, "dz": 10.0}])
    curve = ew.build_curve(100.0, 0.0, pts)

    for wx, wz in ew.resolve(100.0, 0.0, pts):
        # center_x = 0 below, so clearance is |x| - R(z)
        assert abs(wx) - radius_at(wz) >= 1.9, (
            f"the typed points must be legal: ({wx},{wz}) -> "
            f"{abs(wx) - radius_at(wz):.2f}mm")

    bad = ew.check_clearance(curve, radius_at, center_x=0.0,
                             base_offset=0.0, min_clearance=1.0)
    assert bad, "a bow between two legal waypoints must be caught"
    assert bad[0]["clearance"] < 0, f"worst point should gouge, got {bad[0]}"
    assert 2.0 < bad[0]["z"] < 8.0, f"violation should sit mid-span, got z={bad[0]['z']}"
    print(f"[OK] check_clearance: caught {len(bad)} pts, worst "
          f"{bad[0]['clearance']:.2f}mm at z={bad[0]['z']:.1f}")

    # same tail, generous mandrel -> clean
    assert ew.check_clearance(curve, lambda z: 10.0, 0.0, 0.0, 1.0) == []
    print("[OK] check_clearance: clear tail reports nothing")


def test_reverse_and_back_pass_excluded():
    wp = [{"dx": 10, "dz": 5}]
    base = {"pass_edits": {"0": {"exit_points": wp}}}

    assert ew.excluded_reason({}) is None
    assert ew.excluded_reason({"direction": "reverse"}) == "reverse"
    assert ew.excluded_reason({"back_pass_enabled": True}) == "back_pass"

    assert len(ew.get_points(dict(base), 0)) == 1, "a normal forward op keeps its points"

    rev = dict(base, direction="reverse")
    assert ew.get_points(rev, 0) == [], "reverse op must never build waypoints"

    bp = dict(base, back_pass_enabled=True)
    assert ew.get_points(bp, 0) == [], "back-pass op must never build waypoints"

    assert ew.get_points(dict(base), 7) == [], "a pass with no edits has none"
    assert ew.get_points({}, 0) == []
    print("[OK] D10 exclusions: reverse + back-pass ops carry no waypoints")


if __name__ == "__main__":
    test_normalize()
    test_resolve_anchors()
    test_curve_passes_through_points()
    test_straight_is_the_default_and_costs_nothing_extra()
    test_straight_chord_through_the_part_is_caught()
    test_curve_degenerate_inputs()
    test_clearance_catches_bow_between_legal_points()
    test_reverse_and_back_pass_excluded()
    print("\nALL PASS")
