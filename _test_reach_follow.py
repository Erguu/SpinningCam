# -*- coding: utf-8 -*-
"""Headless test for ENGINE-SIDE follow-blank reach (2026-07-07 rework,
PROPOSAL_REACH_ANGLE_PRIORITY R2/R3).

Follow mode now lives inside path_generator.calculate_paths: each pass's reach
is computed from the flange model at THAT pass's Z (robust edge), modified by
the user-owned factor (×) and offset (mm). The op dict must NEVER be
auto-rewritten. Replaces the old UI-side _refresh_auto_reach test (removed)."""
import math

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from process_planner import estimate_flange_reach

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])
blank_r = float(mgr.props["br"]) * 1.5

pg = PathGenerator()

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

def run(op, blank=blank_r):
    p = {"operations": [op], "blank_radius": blank, "auto_calc_angle": False,
         "min_safety_gap": -999.0, "final_part_thickness_on_mandrel": 0.0,
         "shell_thickness": 0.0, "target_clearance": 0.0}
    pg.calculate_paths(p, {}, mgr)
    return pg.last_op_reach.get(0), pg.last_op_end_angle.get(0)

BASE = {"type": "roughing", "pass_shape": "linear_approach", "r_tool": 25.0,
        "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
        "pass_angle": 100.0}

# 1. Per-pass exactness: single-pass follow ops at several Z — engine reach must
#    equal the flange estimate AT THAT Z (not a lerp between two endpoints).
ok = True
for dz in (10, 20, 35, 50):
    z = min_z + dz
    op = dict(BASE, count=1, start_z=z, end_z=z + 1, reach_follow_blank=True)
    r, _ = run(op)
    want = estimate_flange_reach(mgr, blank_r, z)
    if want <= 0:
        continue
    if abs(r - want) > 0.05:
        ok = False
        print(f"   z={z}: engine {r} vs flange {want}")
check(ok, "follow reach == flange estimate at each pass Z (per-pass, engine-side)")

# 2. Multi-pass: LAST pass follows the flange at end_z exactly.
op = dict(BASE, count=4, start_z=min_z + 10, end_z=min_z + 40, reach_follow_blank=True)
r_last, _ = run(op)
want_last = estimate_flange_reach(mgr, blank_r, min_z + 40)
check(abs(r_last - want_last) < 0.05,
      f"multi-pass last reach {r_last:.2f} == flange(end_z) {want_last:.2f}")

# 3. R2 — the op dict is NEVER auto-rewritten by follow mode.
check("reach" not in op, "op['reach'] not written by follow")
check("progressive_reach_end" not in op, "op['progressive_reach_end'] not written")
check(not op.get("progressive_reach_enabled", False),
      "fan flag NOT flipped by follow (user owns it)")

# 4. Modifiers: factor (×) then offset (mm) — reach = flange × factor + offset.
op = dict(BASE, count=1, start_z=min_z + 20, end_z=min_z + 21,
          reach_follow_blank=True, reach_blank_factor=0.9, reach_blank_offset=-5.0)
r_mod, _ = run(op)
want_mod = estimate_flange_reach(mgr, blank_r, min_z + 20) * 0.9 - 5.0
check(abs(r_mod - want_mod) < 0.05,
      f"modifiers: flange×0.9−5 → {r_mod:.2f} (want {want_mod:.2f})")

# 5. Follow supersedes the reach fan; a manual reach underneath is ignored but preserved.
op = dict(BASE, count=3, start_z=min_z + 10, end_z=min_z + 30, reach_follow_blank=True,
          reach=999.0, progressive_reach_enabled=True, progressive_reach_end=1.0)
r_f, _ = run(op)
want_f = estimate_flange_reach(mgr, blank_r, min_z + 30)
check(abs(r_f - want_f) < 0.05, f"follow supersedes fan+manual ({r_f:.2f})")
check(op["reach"] == 999.0 and op["progressive_reach_end"] == 1.0,
      "manual values preserved untouched underneath")

# 6. RAW mode (no pass_angle): follow rescales the p3 vector, ratio preserved.
op = dict(BASE, count=1, start_z=min_z + 20, end_z=min_z + 21, reach_follow_blank=True)
op.pop("pass_angle")
r_raw, ang_raw = run(op)
want_raw = estimate_flange_reach(mgr, blank_r, min_z + 20)
check(abs(r_raw - want_raw) < 0.05, f"RAW mode follow length {r_raw:.2f}")
want_dir = math.degrees(math.atan2(25.0, 30.0))  # |p3_z|/p3_x ratio preserved
check(abs(ang_raw - want_dir) < 0.5, f"RAW mode direction preserved ({ang_raw:.1f}°)")

# 7. No blank radius → follow silently inert (engine guard), op untouched.
op = dict(BASE, count=1, start_z=min_z + 20, end_z=min_z + 21,
          reach_follow_blank=True, reach=40.0)
r_nb, _ = run(op, blank=0.0)
check(abs(r_nb - 40.0) < 0.05, f"no blank radius → manual reach used ({r_nb:.2f})")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
