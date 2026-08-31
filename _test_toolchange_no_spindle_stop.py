"""A tool change must NOT stop the spindle (user decision 2026-08-31).

The turret is fully automatic and the roller is already retracted when it
indexes, so the M5/M1 pair that shipped in the initial commit only cost a
spin-down and spin-up per change. M1 was worse than useless: the recipe protocol
has no such command, so it came out as CMD=1 (LINEAR) with F=0.

What must stay true:
  * the retract to the tool-change point is untouched — that IS the clearance,
  * the new op's speed is still commanded after M6,
  * SPINDLE_OFF now appears ONLY at the end of the program,
  * no CMD=1 line carries F=0.

Run: pyrun.bat _test_toolchange_no_spindle_stop.py   (conda env spinning_cam)
"""
import sys

import numpy as np

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
import recipe_to_scl as R

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        fails.append(name)


def op(tool, speed, z0, z1):
    return {"type": "roughing", "enabled": True, "count": 1, "tool_id": tool,
            "r_tool": 20.0, "speed": speed, "speed_mode": "RPM",
            "feed": 300.0, "feed_mode": "mm_min", "start_z": z0, "end_z": z1}


mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0, 0)

params = {
    "operations": [op("T0101", 800, 0.0, 20.0),
                   op("T0202", 500, 20.0, 40.0),     # tool change #1
                   op("T0101", 800, 40.0, 60.0)],    # tool change #2
    "blank_radius": 100.0, "final_part_thickness_on_mandrel": 2.0,
    "num_sweeping_passes": 1,
}

pg = PathGenerator()
pg.calculate_paths(params, {}, mgr)
gcode = pg.generate_gcode(params=params, for_recipe=True)
lines = gcode.splitlines()

print("1) the G-code")
body = [l.strip() for l in lines]
tc_idx = [i for i, l in enumerate(body) if l.startswith("M6 ")]
check("two mid-program tool changes plus the initial one", len(tc_idx) == 3,
      f"got {len(tc_idx)}")
check("no M5 before a tool change",
      not any(body[i - 1] == "M5" or body[i - 2] == "M5" for i in tc_idx if i >= 2))
check("no M1 line anywhere",
      not any(l == "M1" or l.startswith("M1 ") for l in body))
# The footer still stops the spindle at the end.
check("footer still has M5", body.count("M5") == 1, f"count={body.count('M5')}")
check("retract before the change survives",
      any("Tool Change" in l or "Retract X" in l for l in body))
# Speed is commanded BEFORE the turret indexes, so the spindle has the whole
# index plus the approach to reach it — except for the very first op, which has
# no tool-change block and must start the spindle after M6.
first_m6, later_m6 = tc_idx[0], tc_idx[1:]
check("first op: S..M3 right after M6 (spindle starts here)",
      body[first_m6 + 1].endswith("M3"), body[first_m6 + 1])
for i in later_m6:
    check(f"tool change at line {i}: S..M3 comes BEFORE M6",
          body[i - 1].endswith("M3"), body[i - 1])
    check(f"tool change at line {i}: no second S..M3 after M6",
          not body[i + 1].endswith("M3"), body[i + 1])
# The speed set before the change is the INCOMING op's, not the outgoing one's.
check("incoming speed is commanded at the change",
      "S500" in body[later_m6[0] - 1], body[later_m6[0] - 1])
check("and 800 again coming back", "S800" in body[later_m6[1] - 1],
      body[later_m6[1] - 1])

print("2) the recipe")
rec = R.GCodeToSCLConverter().parse_gcode(gcode)
offs = [i for i, l in enumerate(rec) if l.cmd == R.CMD_SPINDLE_OFF]
ons = [i for i, l in enumerate(rec) if l.cmd == R.CMD_SPINDLE_ON]
tcs = [i for i, l in enumerate(rec) if l.cmd == R.CMD_TOOL_CHANGE]
end = [i for i, l in enumerate(rec) if l.cmd == R.CMD_PROGRAM_END]

check("SPINDLE_OFF only at the end of the program",
      all(i > tcs[-1] for i in offs), f"offs={offs} last tool change={tcs[-1]}")
check("the last OFF is immediately before PROGRAM_END",
      offs and end and offs[-1] == end[0] - 1, f"offs={offs} end={end}")
check("one SPINDLE_ON per operation still", len(ons) == 3, f"got {len(ons)}")
check("three tool changes in the recipe", len(tcs) == 3, f"got {len(tcs)}")
# In the recipe the speed must land immediately before the turret command.
for t in tcs[1:]:
    check(f"CMD=20 immediately precedes CMD=10 at {t}",
          rec[t - 1].cmd == R.CMD_SPINDLE_ON, f"got CMD={rec[t - 1].cmd}")
check("the 500 RPM op is set before its tool change",
      rec[tcs[1] - 1].param == 50, f"got {rec[tcs[1] - 1].param}")
# The M1 artifact is gone: no LINEAR line may carry F=0.
bad = [i for i, l in enumerate(rec) if l.cmd == R.CMD_LINEAR and l.f == 0]
check("no LINEAR line with F=0 (the old M1 artifact)", not bad, f"at {bad}")

# The spindle is never commanded off between two tool changes.
between = [i for i in offs if tcs[0] < i < tcs[-1]]
check("spindle never stops between the first and last tool change", not between,
      f"stops at {between}")

print()
if fails:
    print(f"FAILED: {len(fails)} -> {fails}")
    sys.exit(1)
print("ALL PASS")
