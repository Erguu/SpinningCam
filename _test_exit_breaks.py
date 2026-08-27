# -*- coding: utf-8 -*-
"""#102 break points — headless tests for `exit_breaks`.

The one that matters is LEGACY EQUIVALENCE: an op saved before this feature
existed must produce the same exit leg, to the float, through the new code path.
Everything else is guard rails around it.

Run:  python _test_exit_breaks.py      (needs the spinning_cam env for the OCC
                                        rotation-parity test; the rest is pure)
"""
import math
import sys

import numpy as np

import exit_breaks as eb


PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


def a_leg(n=41, x0=100.0, z0=0.0, dx=40.0, dz=10.0):
    """A straight exit leg of n points, the shape the engine hands over."""
    t = np.linspace(0.0, 1.0, n).reshape(-1, 1)
    return np.hstack([x0 + dx * t, np.zeros_like(t), z0 + dz * t])


# ── 1. legacy equivalence ───────────────────────────────────────────────────
def legacy_reference(pts, t, deg):
    """The exact arithmetic path_generator.py used before #102, in numpy."""
    if abs(deg) <= 0.01 or len(pts) < 3:
        return np.asarray(pts, dtype=float)
    tt = min(max(float(t), 0.05), 0.95)
    k = int(round(tt * (len(pts) - 1)))
    k = min(max(k, 1), len(pts) - 2)
    piv = pts[k]
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    tail = pts[k + 1:]
    dx, dz = tail[:, 0] - piv[0], tail[:, 2] - piv[2]
    rot = np.stack([piv[0] + dx * c + dz * s, tail[:, 1], piv[2] - dx * s + dz * c], axis=1)
    return np.vstack([pts[:k + 1], rot])


def test_legacy_equivalence():
    print("\n[1] legacy single break → identical geometry")
    for t, deg in ((0.5, 12.0), (0.3, -8.0), (0.05, 45.0), (0.95, -30.0),
                   (0.5, 0.005), (0.72, 90.0)):
        legs = a_leg()
        op = {"exit_mid_t": t, "exit_mid_rotation": deg}
        got = eb.apply(legs, eb.get_breaks(op, 0))
        want = legacy_reference(legs, t, deg)
        same = got.shape == want.shape and np.allclose(got, want, atol=1e-12)
        check(f"t={t} rot={deg}", same,
              f"max diff {np.abs(got - want).max() if got.shape == want.shape else 'shape'}")

    # An op with no break at all must not touch the leg.
    legs = a_leg()
    check("no exit_mid → leg untouched",
          np.array_equal(eb.apply(legs, eb.get_breaks({}, 0)), legs))
    check("rotation below the 0.01 gate → leg untouched",
          np.array_equal(eb.apply(legs, eb.get_breaks(
              {"exit_mid_rotation": 0.004, "exit_mid_t": 0.4}, 0)), legs))


# ── 2. rotation parity with the OCC helper ──────────────────────────────────
def test_rotation_parity():
    print("\n[2] rotate_about == PathGenerator._apply_rotation (OCC)")
    try:
        from OCC.Core.gp import gp_Pnt
        from path_generator import PathGenerator
    except Exception as e:                                   # pragma: no cover
        print(f"  SKIP  OCC unavailable ({type(e).__name__}) — run in spinning_cam env")
        return
    pg = PathGenerator.__new__(PathGenerator)                # no __init__ needed
    pts = a_leg(9)
    piv = pts[4]
    for deg in (12.0, -35.0, 90.0, 179.0):
        mine = eb.rotate_about(pts[5:], deg, piv)
        theirs = pg._apply_rotation(pts[5:], deg, gp_Pnt(float(piv[0]), 0.0, float(piv[2])))
        check(f"{deg:+.0f}°", np.allclose(mine, theirs, atol=1e-9),
              f"max diff {np.abs(mine - theirs).max():.3e}")


# ── 3. multiple breaks ──────────────────────────────────────────────────────
def test_multiple():
    print("\n[3] several breaks")
    legs = a_leg()
    two = [{"t": 0.3, "angle": 10.0}, {"t": 0.7, "angle": 10.0}]
    got = eb.apply(legs, two)
    check("point count is preserved", len(got) == len(legs))
    check("everything before the first break is untouched",
          np.allclose(got[:eb.index_at(0.3, len(legs)) + 1],
                      legs[:eb.index_at(0.3, len(legs)) + 1]))

    # Two 10° bends must leave the last segment 20° off the original — that is
    # what "relative" means, and it is the whole point of the feature.
    def seg_dir(p, i):
        v = p[i + 1] - p[i]
        return math.degrees(math.atan2(v[2], v[0]))
    turn = seg_dir(legs, len(legs) - 2) - seg_dir(got, len(got) - 2)
    check("two 10° bends accumulate to 20°", abs(abs(turn) - 20.0) < 1e-6,
          f"got {turn:.4f}°")

    # Order of the rows in the file must not matter: they are sorted by t.
    rev = eb.apply(legs, list(reversed(two)))
    check("row order in the file is irrelevant", np.allclose(got, rev))

    # One break must equal the legacy result even when it arrives as a list.
    single = eb.apply(legs, [{"t": 0.4, "angle": -15.0}])
    check("a one-item list == the legacy block",
          np.allclose(single, legacy_reference(legs, 0.4, -15.0), atol=1e-12))

    # Two breaks at the same spot sum their angles.
    same_spot = eb.apply(legs, [{"t": 0.5, "angle": 7.0}, {"t": 0.5, "angle": 5.0}])
    one_sum = eb.apply(legs, [{"t": 0.5, "angle": 12.0}])
    check("two breaks at one t sum their angles", np.allclose(same_spot, one_sum, atol=1e-9))


# ── 4. normalize / storage ──────────────────────────────────────────────────
def test_normalize():
    print("\n[4] normalize + storage")
    check("junk rows are dropped, good ones kept",
          eb.normalize([{"t": 0.5, "angle": 3}, "nope", {"t": "x", "angle": 1},
                        {"t": float("nan"), "angle": 1}, None])
          == [{"t": 0.5, "angle": 3.0}])
    check("t is clamped, not dropped",
          eb.normalize([{"t": 0.0, "angle": 5}, {"t": 2.0, "angle": 5}])
          == [{"t": eb.T_MIN, "angle": 5.0}, {"t": eb.T_MAX, "angle": 5.0}])
    check("sorted by t",
          [r["t"] for r in eb.normalize([{"t": 0.8, "angle": 1}, {"t": 0.2, "angle": 1}])]
          == [0.2, 0.8])
    check("empty / None → []", eb.normalize(None) == [] and eb.normalize([]) == [])

    op = {"exit_mid_t": 0.5, "exit_mid_rotation": 20.0,
          "pass_edits": {"2": {"exit_breaks": [{"t": 0.4, "angle": -9.0}]}}}
    check("a pass with its own list ignores the legacy break",
          eb.get_breaks(op, 2) == [{"t": 0.4, "angle": -9.0}])
    check("a pass without one falls back to the legacy break",
          eb.get_breaks(op, 0) == [{"t": 0.5, "angle": 20.0}])
    check("int and str pass keys both resolve",
          eb.get_breaks({"pass_edits": {3: {"exit_breaks": [{"t": 0.6, "angle": 4}]}}}, 3)
          == [{"t": 0.6, "angle": 4.0}])
    check("stored() ignores the legacy fallback", eb.stored(op, 0) == [])


# ── 5. exclusions ───────────────────────────────────────────────────────────
def test_exclusions():
    print("\n[5] exclusions mirror the engine's branch order")
    base = {"pass_shape": "linear_approach"}
    check("linear_approach is allowed", eb.excluded_reason(base) is None)
    check("linear_full is excluded (earlier branch, never rotated)",
          eb.excluded_reason({"pass_shape": "linear_full"}) == "pass_shape")
    check("spline is excluded",
          eb.excluded_reason({"pass_shape": "spline"}) == "pass_shape")
    check("default shape (spline) is excluded", eb.excluded_reason({}) == "pass_shape")
    check("reverse without the legacy flip is excluded",
          eb.excluded_reason(dict(base, direction="reverse")) == "reverse")
    check("reverse WITH the legacy flip is allowed",
          eb.excluded_reason(dict(base, direction="reverse",
                                  reverse_legacy_flip=True)) is None)
    check("the curl wins", eb.excluded_reason(dict(base, exit_mid_radius=50.0)) == "curl")
    check("the end-radius alone also wins",
          eb.excluded_reason(dict(base, exit_mid_radius_end=50.0)) == "curl")
    check("an empty curl field is not a curl",
          eb.excluded_reason(dict(base, exit_mid_radius="")) is None)
    check("a back pass is NOT excluded (its main pass still exits normally)",
          eb.excluded_reason(dict(base, back_pass_enabled=True)) is None)


# ── 6. degenerate input ─────────────────────────────────────────────────────
def test_degenerate():
    print("\n[6] degenerate legs")
    two = a_leg(2)
    check("a 2-point leg has no interior pivot → untouched",
          np.array_equal(eb.apply(two, [{"t": 0.5, "angle": 30.0}]), two))
    three = a_leg(3)
    out = eb.apply(three, [{"t": 0.5, "angle": 30.0}])
    check("a 3-point leg rotates its last point only",
          np.allclose(out[:2], three[:2]) and not np.allclose(out[2], three[2]))
    check("empty break list → untouched",
          np.array_equal(eb.apply(a_leg(), []), a_leg()))
    check("index_at never picks an end", all(
        1 <= eb.index_at(t, 41) <= 39 for t in (0.0, 0.001, 0.5, 0.999, 1.0, 5.0)))


# ── 7. end to end, through calculate_paths ──────────────────────────────────
def test_end_to_end():
    """The unit tests prove the arithmetic; this proves the WIRING.

    Same harness as `_test_exit_mid_curve.py` — a one-pass roughing op with
    `p2_radius=0`, so the approach arm collapses to two points and everything
    from path[1] on is the exit leg.
    """
    print("\n[7] end to end through calculate_paths")
    try:
        from mandrel_analyzer import MandrelManager
        from path_generator import PathGenerator
    except Exception as e:                                   # pragma: no cover
        print(f"  SKIP  engine unavailable ({type(e).__name__})")
        return

    mgr = MandrelManager()
    mgr.create_default_cone()
    mgr.update_geometry(0, 0, 0, 0.0, 0.0)
    pg = PathGenerator()

    def build(**op_over):
        op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
              "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0,
              "p3_z": -25.0, "pass_shape": "linear_approach",
              "direction": "forward", "p2_radius": 0.0}
        op.update(op_over)
        params = {"operations": [op], "auto_calc_angle": False,
                  "min_safety_gap": -999.0, "final_part_thickness_on_mandrel": 0.0,
                  "shell_thickness": 0.0, "collision_resolution": 0.1,
                  "gcode_resolution": 0.05}
        return np.asarray(pg.calculate_paths(params, {}, mgr)[0][0])[1:]

    def total_turn(pts):
        d = np.diff(np.asarray(pts, dtype=float), axis=0)
        n = np.linalg.norm(d, axis=1)
        d = d[n > 1e-9] / n[n > 1e-9][:, None]
        if len(d) < 2:
            return 0.0
        dots = np.clip(np.einsum("ij,ij->i", d[:-1], d[1:]), -1.0, 1.0)
        return float(np.degrees(np.arccos(dots)).sum())

    straight = build()
    check("a leg with no breaks is straight", total_turn(straight) < 0.01,
          f"{total_turn(straight):.4f}°")

    # A per-pass list reaches the engine at all.
    two = build(pass_edits={"0": {"exit_breaks": [{"t": 0.3, "angle": 8.0},
                                                  {"t": 0.7, "angle": 8.0}]}})
    check("two per-pass breaks bend the leg by their sum",
          abs(total_turn(two) - 16.0) < 0.05, f"{total_turn(two):.4f}°")
    check("the leg still ends somewhere else than it started",
          not np.allclose(two[-1], straight[-1]))

    # A per-pass list must WIN over the op's legacy break.
    pinned = build(exit_mid_t=0.5, exit_mid_rotation=40.0,
                   pass_edits={"0": {"exit_breaks": [{"t": 0.5, "angle": 8.0}]}})
    check("a per-pass list overrides the legacy op break",
          abs(total_turn(pinned) - 8.0) < 0.05, f"{total_turn(pinned):.4f}°")

    # …and with no list, the legacy break must still run, unchanged.
    legacy = build(exit_mid_t=0.5, exit_mid_rotation=8.0)
    one_row = build(pass_edits={"0": {"exit_breaks": [{"t": 0.5, "angle": 8.0}]}})
    check("legacy op break == the identical one-row per-pass list",
          legacy.shape == one_row.shape and np.allclose(legacy, one_row, atol=1e-9))

    # The curl still wins over breaks, as the single rotation always lost to it.
    curled = build(exit_mid_radius=60.0,
                   pass_edits={"0": {"exit_breaks": [{"t": 0.5, "angle": 40.0}]}})
    curl_only = build(exit_mid_radius=60.0)
    check("the curl still wins over breaks",
          curled.shape == curl_only.shape and np.allclose(curled, curl_only, atol=1e-9))

    # linear_full never reached the rotation block and still must not.
    full = build(pass_shape="linear_full",
                 pass_edits={"0": {"exit_breaks": [{"t": 0.5, "angle": 20.0}]}})
    full_plain = build(pass_shape="linear_full")
    check("linear_full ignores breaks (matches excluded_reason)",
          full.shape == full_plain.shape and np.allclose(full, full_plain, atol=1e-9))


if __name__ == "__main__":
    test_legacy_equivalence()
    test_rotation_parity()
    test_multiple()
    test_normalize()
    test_exclusions()
    test_degenerate()
    test_end_to_end()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else 0)
