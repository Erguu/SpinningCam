# -*- coding: utf-8 -*-
"""Reverse linear passes (#82, resolved by deletion 2026-08-30) and #81.

THE CONTRACT NOW: a reverse pass is the forward pass driven backwards. Nothing
selects between modes; every exit shape behaves the same in both directions.

WHAT THIS FILE USED TO ASSERT, and why it was wrong. #82 built a reverse pass
with swapped leg roles — the leg over the free blank forced straight, the bow
moved onto the outgoing arm. Check 3 claimed to prove the arm was bowed by
measuring `rev[3*n//4:]`, a slice containing the P2 corner. It reported
**5.6114 mm with exit_arc_angle at 25° and 5.6114 mm at 0°** — it never touched
the arm and would have passed with the feature entirely absent. Which it
effectively was: `path_generator.py:2514` collapses the arm to its two end
points, so the bow was built and then deleted, and a reverse pass ran straight
in and straight out no matter what was set.

The lesson worth keeping: a check that isolates a segment by index fraction is
measuring whatever happens to land there. Measure the thing itself.

Run:  runtest.bat _test_reverse_linear.py
"""
import numpy as np

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


def build(direction, exit_arc_op=None, exit_arc_global=0.0, **extra):
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
          "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": direction}
    if exit_arc_op is not None:
        op["exit_arc_angle"] = exit_arc_op
    op.update(extra)
    p = {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
         "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
         "exit_arc_angle": exit_arc_global}
    return pg.calculate_paths(p, {}, mgr)[0][0]


def arm_of(path, p2_z=30.0):
    """The positioning arm: everything from P2 down to P1. Named by GEOMETRY,
    not by index fraction — see the module docstring."""
    return np.array([q for q in path if q[2] <= p2_z + 1e-6])


def chord_dev(seg):
    if len(seg) < 3:
        return 0.0
    a, b = seg[0], seg[-1]
    ab = b - a
    L = np.linalg.norm(ab)
    if L < 1e-9:
        return 0.0
    return float(np.max(np.linalg.norm(np.cross(seg - a, ab / L), axis=1)))


# 1. The whole contract, in one line, for every shape.
for label, kw in (("no exit shape", {}),
                  ("exit_arc_angle=25", {"exit_arc_op": 25.0}),
                  ("exit_bow=12", {"exit_bow": 12.0}),
                  ("p2_radius=10", {"p2_radius": 10.0}),
                  ("exit_mid rotation", {"exit_mid_t": 0.6, "exit_mid_rotation": 20.0})):
    check(np.allclose(build("forward", **kw)[::-1], build("reverse", **kw), atol=1e-12),
          f"reverse == forward reversed: {label}")

# 2. The arm is the positioning leg in BOTH directions — it never carries a
#    shape now. This is the check the old #3 only appeared to make.
for d in ("forward", "reverse"):
    arm = arm_of(build(d, exit_arc_op=25.0))
    check(len(arm) == 2 and chord_dev(arm) < 1e-9,
          f"{d}: the arm stays a straight 2-point leg ({len(arm)} pts, "
          f"dev {chord_dev(arm):.4f} mm)")

# 3. And the arc now actually reaches the metal on a reverse pass — it used to
#    be silently discarded, which is the bug the swap's removal fixes.
check(not np.allclose(build("reverse", exit_arc_op=25.0),
                      build("reverse"), atol=1e-6),
      "exit_arc_angle changes a reverse pass (it was ignored before)")
check(np.allclose(build("reverse"), build("forward")[::-1], atol=1e-12),
      "with no arc set, a reverse pass is unchanged from before")

# 4. #81 — per-op exit_arc_angle wins over the global; empty falls back.
f_op = build("forward", exit_arc_op=25.0, exit_arc_global=0.0)
f_gl = build("forward", exit_arc_op=None, exit_arc_global=25.0)
check(np.allclose(f_op, f_gl, atol=1e-9), "op value == same value via global")
check(not np.allclose(build("forward", exit_arc_op=10.0, exit_arc_global=25.0),
                      f_gl, atol=1e-6), "op value WINS over a different global")
check(np.allclose(build("forward", exit_arc_op="", exit_arc_global=25.0), f_gl,
                  atol=1e-9), "empty op value falls back to global")

# 5. Forward passes are deterministic and untouched by any of this.
check(np.allclose(build("forward", exit_arc_op=25.0),
                  build("forward", exit_arc_op=25.0), atol=1e-12),
      "forward deterministic")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
