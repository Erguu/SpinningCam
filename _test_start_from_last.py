"""Start from last - cut a forward pass's beginning off (start_from_last.py).

THE SHAPE, from the user (2026-09-20): "a normal roughing pass that the part
below a specific X is removed. But that X, actually that point, is already
calculated in the previous back or reverse short-ended pass."

Together with stop_short this draws the letter M:

    Op1  forward (normal)             out
         back pass, stopped short     in, partway
    Op2  forward, cut at that X       out
         back pass (normal)           in, all the way

What must hold, most important first:

1. OFF = nothing changes, point for point.
2. FIRST PASS ONLY. A 3-pass operation cuts pass 1; passes 2 and 3 begin at the
   mandrel exactly as before.
3. The cut lands on the X the previous stroke ENDED at - not near it.
4. The END of the pass never moves. Only its beginning is removed.
5. Op2's BACK pass stays FULL. The cut happens after it is built; cutting first
   would shorten the return stroke, which is the whole point of the shape.
6. The search runs on the EXIT LEG only. The approach arm sits at nearly
   constant X, so a whole-path search would cut inside the arm instead.
7. Exit Max Points still governs the point count: a cut pass is all exit leg,
   and that cap used to die silently on paths with no split (it did exactly
   that on reverse passes until 2026-08-30).
8. Anything it cannot do is REPORTED, never silently skipped.

Run:  python _test_start_from_last.py
"""
import copy
import sys

import numpy as np

import start_from_last as sfl
import stop_short as ss
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILED.append(name)


# == A. the pure geometry ===================================================
print("A. plan / apply / join")

# X climbs 0 -> 100 along Z, like an exit leg heading out.
LEG = np.array([[float(x), 0.0, float(x) * 0.5] for x in range(0, 101, 10)])


def pt(x, z):
    return np.array([float(x), 0.0, float(z)])


# CLOSEST POINT, not "where the path reaches this X". The stroke that ran before
# is a different curve - a back pass carries a bow and its own clearance shift -
# so its end does not sit on this path at all.
cut = sfl.plan(LEG, pt(25.0, 12.5))          # exactly on the line
out = sfl.apply(LEG, cut)
check("an anchor ON the line cuts exactly there",
      abs(out[0][0] - 25.0) < 1e-9 and abs(out[0][2] - 12.5) < 1e-9, out[0])
check("the END is untouched", np.allclose(out[-1], LEG[-1]))
check("the points before it are gone", len(out) == 9, len(out))

# An anchor 2 mm OFF the line - the case the user's file actually hit.
off = pt(25.0, 14.5)
cut_off = sfl.plan(LEG, off)
near = sfl.apply(LEG, cut_off)
check("an anchor OFF the line cuts at the nearest point, not at its X",
      abs(near[0][0] - 25.0) > 1e-6, near[0])
joined, d = sfl.join(near, off)
check("join puts the anchor first, so the pass STARTS on the roller",
      abs(joined[0][0] - off[0]) < 1e-9 and abs(joined[0][2] - off[2]) < 1e-9,
      joined[0])
check("join reports the distance it bridged", 0.0 < d < 3.0, d)
check("join adds exactly one point", len(joined) == len(near) + 1)
check("join on a point already there adds nothing",
      sfl.join(near, near[0])[0].shape == near.shape)

# Landing exactly on a sample point must not duplicate it.
on_pt = sfl.apply(LEG, sfl.plan(LEG, pt(30.0, 15.0)))
check("a cut landing on a point leaves no duplicate",
      len(on_pt) == 8 and abs(on_pt[0][0] - 30.0) < 1e-9,
      f"{len(on_pt)} pts, {on_pt[0][0]}")

check("a cut leaving almost nothing is refused",
      sfl.plan(LEG, pt(100.0, 50.0)) is None)

# exit_start: the arm sits at constant X and can be the closest thing of all.
ARM = np.array([[10.0, 0.0, float(z)] for z in range(0, 40, 10)])
PATH = np.vstack([ARM, LEG[1:]])
A = pt(10.5, 20.0)                            # right beside the ARM
naive = sfl.plan(PATH, A, exit_start=0)
guided = sfl.plan(PATH, A, exit_start=len(ARM))
check("searching from 0 finds the ARM (the trap)",
      naive is not None and naive[0] < len(ARM), naive)
check("searching from the exit leg skips the arm",
      guided is not None and guided[0] >= len(ARM) - 1, guided)

# parallel arrays
devs = np.arange(len(LEG), dtype=float)
t_devs = sfl.apply_parallel(devs, cut, len(LEG))
check("a parallel array cuts to the same length",
      len(t_devs) == len(out), f"{len(t_devs)} vs {len(out)}")
check("a mismatched array is left alone",
      len(sfl.apply_parallel(np.arange(3.0), cut, len(LEG))) == 3)

# the tickbox
check("absent = off", not sfl.enabled({}))
check("false = off", not sfl.enabled({sfl.OP_KEY: False}))
check("true = on", sfl.enabled({sfl.OP_KEY: True}))

# who may use it
check("a forward roughing op may", sfl.op_can_use({"type": "roughing"}))
check("a finishing op may", sfl.op_can_use({"type": "finishing"}))
check("a REVERSE op may not",
      not sfl.op_can_use({"type": "roughing", "direction": "reverse"}))
check("cutting / bending / point may not",
      not any(sfl.op_can_use({"type": k}) for k in ("cutting", "bending", "point")))


# == B. the engine ==========================================================
print()
print("B. the engine")

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
MIN_Z = float(mgr.props["min_z"])

PARAMS = {
    "auto_calc_angle": False, "min_safety_gap": 0.0,
    "final_part_thickness_on_mandrel": 2.0, "shell_thickness": 0.0,
    "blank_radius": float(mgr.props["br"]) * 1.5,
    "collision_resolution": 0.5, "gcode_resolution": 2.0,
    "home_x": 300.0, "home_z": 150.0, "retract_x": 50.0, "retract_z": 50.0,
    "surface_speed_m_min": 100.0, "feed_rate_mm_min": 300.0, "max_spin_rpm": 2550.0,
}

OP = {
    "type": "roughing", "enabled": True, "count": 1, "tool_id": "T0101",
    "r_tool": 25.0, "direction": "forward",
    "speed_mode": "RPM", "speed": 200, "feed_mode": "mm_min", "feed": 300,
    "start_z": MIN_Z + 10, "end_z": MIN_Z + 30,
    "retract_x": 50.0, "retract_z": 50.0,
    "pass_shape": "linear_approach", "p2_radius": 3.0,
    "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0, "reach": 40.0,
    "pass_angle": 120.0, "clearance": 5.0,
}


def run(ops, plc=False):
    """(generator, paths). With plc=True the paths are the DECIMATED ones the
    recipe would carry - calculate_paths always returns full resolution, and the
    point caps only bite during decimation."""
    p = copy.deepcopy(PARAMS)
    if plc:
        p["plc_mode"] = True
    p["operations"] = copy.deepcopy(ops)
    pg = PathGenerator()
    tp = pg.calculate_paths(p, {}, mgr)[0]
    if plc:
        pg.generate_gcode(params=p, for_recipe=True)
        tp = pg.last_plc_paths
    return pg, tp


# A lead whose LAST stroke ends out in the sheet, so there is an X to cut at.
LEAD = dict(OP, name="lead", reach=12.0)


def pair(on, probe_over=None):
    probe = dict(OP, name="probe", **(probe_over or {}))
    if on:
        probe[sfl.OP_KEY] = True
    return [dict(LEAD), probe]


# -- B1. off changes nothing --
pg_off, tp_off = run(pair(False))
pg_on, tp_on = run(pair(True))
check("the same number of toolpaths", len(tp_off) == len(tp_on))
check("the LEAD is point-for-point unchanged", np.allclose(tp_off[0], tp_on[0]))

# -- B2. the cut lands on the lead's end X --
anchor_x = float(np.asarray(tp_off[0], float)[-1][0])
start_x = float(np.asarray(tp_on[1], float)[0][0])
check("the cut pass begins at the X the lead ended at",
      abs(start_x - anchor_x) < 1e-6, f"{start_x} vs {anchor_x}")
check("it really did lose points",
      len(tp_on[1]) < len(tp_off[1]), f"{len(tp_on[1])} vs {len(tp_off[1])}")
check("the END of the pass did not move",
      np.allclose(np.asarray(tp_on[1], float)[-1],
                  np.asarray(tp_off[1], float)[-1]))
check("nothing was refused", pg_on.last_start_from_last_ignored == [])

# -- B3. FIRST PASS ONLY --
pg3_off, tp3_off = run(pair(False, {"count": 3}))
pg3_on, tp3_on = run(pair(True, {"count": 3}))
check("3 passes: the first one is cut",
      len(tp3_on[1]) < len(tp3_off[1]), f"{len(tp3_on[1])} vs {len(tp3_off[1])}")
check("3 passes: passes 2 and 3 are point-for-point unchanged",
      all(np.allclose(tp3_off[i], tp3_on[i]) for i in (2, 3)))

# -- B4. the back pass stays FULL (the M) --
def leng(p):
    a = np.asarray(p, float)
    return float(np.linalg.norm(np.diff(a, axis=0), axis=1).sum())


m_off, m_tpoff = run(pair(False, {"back_pass_enabled": True}))
m_on, m_tpon = run(pair(True, {"back_pass_enabled": True}))
# layout: [0] lead fwd, [1] probe fwd, [2] probe back
check("the M: the forward is cut",
      leng(m_tpon[1]) < leng(m_tpoff[1]) - 1.0,
      f"{leng(m_tpon[1]):.3f} vs {leng(m_tpoff[1]):.3f}")
check("the M: the BACK pass is still FULL",
      abs(leng(m_tpon[2]) - leng(m_tpoff[2])) < 1e-6,
      f"{leng(m_tpon[2]):.4f} vs {leng(m_tpoff[2]):.4f}")

# -- B5. the cut does not land in the approach arm --
arm_x = float(np.asarray(tp_off[1], float)[0][0])
check("the cut is OUTBOARD of where the arm starts",
      start_x > arm_x + 1.0, f"cut {start_x:.3f}, arm {arm_x:.3f}")

# -- B6. refusals are reported --
# A lead that ends at a big X the probe never reaches.
far = [dict(OP, name="lead", reach=400.0), dict(OP, name="probe", **{sfl.OP_KEY: True})]
pg_far, tp_far = run(far)
check("an unreachable X is refused AND reported",
      len(pg_far.last_start_from_last_ignored) == 1 and
      pg_far.last_start_from_last_ignored[0]["reason"] in ("not_reached", "too_short"),
      pg_far.last_start_from_last_ignored)

# Nothing before it at all.
alone = [dict(OP, name="probe", **{sfl.OP_KEY: True})]
pg_alone, _ = run(alone)
check("no previous stroke is refused AND reported",
      len(pg_alone.last_start_from_last_ignored) == 1 and
      pg_alone.last_start_from_last_ignored[0]["reason"] == "no_anchor",
      pg_alone.last_start_from_last_ignored)

# -- B7. Exit Max Points still governs a cut pass --
# A BOWED leg, deliberately: a straight cut pass decimates to two points and a
# cap has nothing left to remove, which would pass this check for the wrong
# reason. linear_full is the shape that routes through the bow.
CAP = 3
CURVED = {"pass_shape": "linear_full", "exit_bow": 12.0, "exit_mid_radius": ""}
check("a cut pass is marked exit-only",
      1 in run(pair(True, CURVED))[0].last_exit_only_paths,
      run(pair(True, CURVED))[0].last_exit_only_paths)
_, tp_nocap = run(pair(True, CURVED), plc=True)
_, tp_cap = run(pair(True, dict(CURVED, exit_max_points=CAP)), plc=True)
check("the uncapped cut pass really has points to lose",
      len(tp_nocap[1]) > CAP, len(tp_nocap[1]))
check(f"Exit Max Points ({CAP}) reaches the cut pass",
      len(tp_cap[1]) <= CAP and len(tp_cap[1]) < len(tp_nocap[1]),
      f"capped {len(tp_cap[1])}, uncapped {len(tp_nocap[1])}")


# -- B8. Exit Max Points reaches BACK passes too (user report, 2026-09-20) ----
# "point number modifiers doesn't effect back passes at all". Measured on his
# own program: a back pass of 293 points came out at 49 under a cap of 10. Same
# cause as the cut pass - a back pass is the FORMING part driven backwards, so
# it is all exit leg and carries no split, and a path with no split reads its
# cap as zero. The cap uses the NORMAL tolerance, not plc_exit_tolerance:
# applying the exit tolerance to a whole stroke took that back pass to 3 points,
# which changes the shape rather than the point count.
print()
print("B8. the back-pass point cap")

BOWED = {"back_pass_enabled": True, "pass_shape": "linear_full",
         "exit_bow": 12.0, "exit_mid_radius": ""}
_, tp_plain = run(pair(False, BOWED), plc=True)
_, tp_cap = run(pair(False, dict(BOWED, exit_max_points=3)), plc=True)
# layout: [0] lead fwd, [1] probe fwd, [2] probe BACK
check("the uncapped back pass has points to lose",
      len(tp_plain[2]) > 3, len(tp_plain[2]))
check("Exit Max Points reaches the BACK pass",
      len(tp_cap[2]) <= 3 and len(tp_cap[2]) < len(tp_plain[2]),
      f"capped {len(tp_cap[2])}, uncapped {len(tp_plain[2])}")
check("a back pass is marked exit-only",
      2 in run(pair(False, BOWED))[0].last_exit_only_paths,
      run(pair(False, BOWED))[0].last_exit_only_paths)

print()
if FAILED:
    print(f"{len(FAILED)} check(s) FAILED: {FAILED}")
    sys.exit(1)
print("All start-from-last checks passed.")
