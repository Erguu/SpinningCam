# -*- coding: utf-8 -*-
"""Headless test for per-pass pins (op['pass_edits'], #79/#80 P1) — the highest
priority in the engine's per-pass value chain: pin > follow > fan > reach > |p3|.
Also covers the split remap (pins stay on the same physical pass, #64/#79)."""
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from process_planner import estimate_flange_reach
import ui.tabs.program_tab as PT

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

def run(op):
    p = {"operations": [op], "blank_radius": blank_r, "auto_calc_angle": False,
         "min_safety_gap": -999.0, "final_part_thickness_on_mandrel": 0.0,
         "shell_thickness": 0.0, "target_clearance": 0.0}
    pg.calculate_paths(p, {}, mgr)
    return pg.last_op_reach.get(0), pg.last_op_end_angle.get(0)

BASE = {"type": "roughing", "pass_shape": "linear_approach", "r_tool": 25.0,
        "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
        "pass_angle": 120.0, "count": 3, "start_z": min_z + 10, "end_z": min_z + 30,
        "reach": 40.0, "progressive_angle_enabled": True, "progressive_angle_end": 170.0}

# Baseline: last pass = fan end (170°), reach 40.
r0, a0 = run(dict(BASE))
check(abs(a0 - 170.0) < 0.01 and abs(r0 - 40.0) < 0.01,
      f"baseline fan: last angle {a0}, reach {r0}")

# 1. Pin the LAST pass: both values override the fan.
op = dict(BASE, pass_edits={"2": {"pass_angle": 150.0, "reach": 33.0}})
r, a = run(op)
check(abs(a - 150.0) < 0.01, f"pinned angle beats the fan ({a})")
check(abs(r - 33.0) < 0.01, f"pinned reach beats the fan ({r})")

# 2. Pin only the MIDDLE pass: the last pass is untouched.
op = dict(BASE, pass_edits={"1": {"pass_angle": 90.0, "reach": 10.0}})
r, a = run(op)
check(abs(a - 170.0) < 0.01 and abs(r - 40.0) < 0.01,
      "pin on middle pass leaves the others on the fan")

# 3. Pin beats FOLLOW (highest priority).
op = dict(BASE, reach_follow_blank=True, pass_edits={"2": {"reach": 12.5}})
r, a = run(op)
check(abs(r - 12.5) < 0.01, f"pin beats follow ({r})")
op2 = dict(BASE, reach_follow_blank=True, pass_edits={"1": {"reach": 12.5}})
r2, _ = run(op2)
want_follow = estimate_flange_reach(mgr, blank_r, min_z + 30)
check(abs(r2 - want_follow) < 0.05, f"unpinned pass still follows ({r2:.2f})")

# 4. Junk/int-key tolerance: int keys work, junk values fall through safely.
op = dict(BASE, pass_edits={2: {"reach": 20.0}, "1": {"reach": "abc"}})
r, _ = run(op)
check(abs(r - 20.0) < 0.01, "int keys accepted; junk value ignored")

# (Anchoring for pinned reach shares the exact engine condition/branch with op
#  reach — covered by _test_reach.py / _test_reach_foldback.py; last_op_reach
#  records the COMMANDED magnitude pre-anchoring by design, so it can't be
#  used to assert the shift here.)

# 5. Split remap (#64): pins keep their physical pass across chunk boundaries.
op = dict(BASE, count=6, pass_edits={"0": {"reach": 11.0}, "4": {"reach": 15.0}})
chunks = PT.ProgramTab._split_op(op, [2, 4], min_z + 30)
check(chunks[0].get("pass_edits") == {"0": {"reach": 11.0}},
      f"chunk 1 keeps pass-0 pin ({chunks[0].get('pass_edits')})")
check(chunks[1].get("pass_edits") == {"2": {"reach": 15.0}},
      f"chunk 2 pin remapped 4→2 ({chunks[1].get('pass_edits')})")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
