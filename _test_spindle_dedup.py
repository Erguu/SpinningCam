"""An operation only commands the spindle when the speed actually changes.

CMD=20 sets the speed target (CAM_INTERFACE_SPEC §5), so re-sending the target
the spindle is already turning at does nothing — but it still costs one of the
1000 recipe lines. DB_RecipeProgram1.scl spent 25 of its 205 lines that way, and
DB_RecipeProgram3.scl spent 15 while sitting at 999 against the cap.

The two carve-outs are the whole safety story and each has a test below:
  * a TOOL CHANGE always re-commands, even at an unchanged speed,
  * any custom M3/M5 command forgets the tracked state, so the next op
    re-commands rather than trusting a number the emitter no longer owns.

Run: pyrun.bat _test_spindle_dedup.py   (conda env spinning_cam)
"""
import sys

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


mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0, 0)


def op(tool, speed, z0, z1):
    return {"type": "roughing", "enabled": True, "count": 1, "tool_id": tool,
            "r_tool": 20.0, "speed": speed, "speed_mode": "RPM",
            "feed": 300.0, "feed_mode": "mm_min", "start_z": z0, "end_z": z1}


def recipe(ops, **extra):
    p = {"operations": ops, "blank_radius": 100.0,
         "final_part_thickness_on_mandrel": 2.0, "num_sweeping_passes": 1}
    p.update(extra)
    pg = PathGenerator()
    pg.calculate_paths(p, {}, mgr)
    g = pg.generate_gcode(params=p, for_recipe=True)
    return g, R.GCodeToSCLConverter().parse_gcode(g)


def ons(rec):
    return [l.param for l in rec if l.cmd == R.CMD_SPINDLE_ON]


print("1) same tool, same speed — one command for the lot")
_, rec = recipe([op("T0101", 800, i * 10.0, i * 10.0 + 10.0) for i in range(6)])
check("six ops collapse to one SPINDLE_ON", ons(rec) == [80], ons(rec))

print("2) same tool, speed changes — every change is commanded")
_, rec = recipe([op("T0101", 800, 0, 10), op("T0101", 800, 10, 20),
                 op("T0101", 1000, 20, 30), op("T0101", 1000, 30, 40),
                 op("T0101", 600, 40, 50)])
check("800, 1000, 600 — repeats dropped, changes kept",
      ons(rec) == [80, 100, 60], ons(rec))

print("3) a float that writes the same S word is not a change")
_, rec = recipe([op("T0101", 800.0, 0, 10), op("T0101", 800.4, 10, 20),
                 op("T0101", 800.9, 20, 30)])
check("800.0 / 800.4 / 800.9 all write S800 -> one command",
      ons(rec) == [80], ons(rec))

print("4) CARVE-OUT: a tool change re-commands even at the same speed")
_, rec = recipe([op("T0101", 800, 0, 10), op("T0202", 800, 10, 20),
                 op("T0202", 800, 20, 30)])
check("two ONs: the start and the tool change (not the third op)",
      ons(rec) == [80, 80], ons(rec))
tcs = [i for i, l in enumerate(rec) if l.cmd == R.CMD_TOOL_CHANGE]
check("the second ON sits immediately before the turret command",
      rec[tcs[1] - 1].cmd == R.CMD_SPINDLE_ON, f"CMD={rec[tcs[1] - 1].cmd}")

print("5) CARVE-OUT: a custom M5 forgets the tracked speed")
# A pass-triggered command fires INSIDE that pass, i.e. AFTER the op header that
# decides whether to command the spindle. So the reset matters when the M5 lands
# on an EARLIER op's pass (pass 1 here) — that is the ordering that would
# otherwise leave the tracker claiming a speed the spindle no longer has.
base = [op("T0101", 800, 0, 10), op("T0101", 800, 10, 20)]
_, rec_plain = recipe(base)
check("without the custom command, the repeat is dropped",
      ons(rec_plain) == [80], ons(rec_plain))
_, rec_m5 = recipe(base, custom_commands=[
    {"cmd": "M5", "trigger": "pass", "value": "1"}])
check("with an M5 on pass 1, op2 re-commands instead of trusting the tracker",
      ons(rec_m5) == [80, 80], ons(rec_m5))
check("and the M5 really is in the recipe as SPINDLE_OFF",
      sum(1 for l in rec_m5 if l.cmd == R.CMD_SPINDLE_OFF) == 3,
      sum(1 for l in rec_m5 if l.cmd == R.CMD_SPINDLE_OFF))
# An M5 on the op's OWN pass fires after that op's header, so no tracker can
# save it — the operator has asked for the spindle to stop mid-operation and it
# stops. Recorded here so the behaviour is known, not discovered on a machine.
# This is pre-existing: before dedup the M3 was emitted and then cancelled by
# the same M5, so the op ran with the spindle off either way.
_, rec_own = recipe(base, custom_commands=[
    {"cmd": "M5", "trigger": "pass", "value": "2"}])
check("M5 on the op's own pass still stops it (unchanged, operator's choice)",
      ons(rec_own) == [80], ons(rec_own))
check("a custom M3 also resets the tracker",
      ons(recipe(base, custom_commands=[
          {"cmd": "M3 S900", "trigger": "pass", "value": "1"}])[1]) == [80, 90, 80],
      ons(recipe(base, custom_commands=[
          {"cmd": "M3 S900", "trigger": "pass", "value": "1"}])[1]))

print("6) M30 / M40 / M41 must NOT be mistaken for a spindle command")
for code in ("M30", "M40 P1", "M41 P2", "M35", "M53"):
    _, r = recipe(base, custom_commands=[
        {"cmd": code, "trigger": "pass", "value": "2"}])
    check(f"{code:8} does not reset the tracker", ons(r) == [80], ons(r))

print("7) the skipped line leaves a comment in the .nc, not a silent gap")
g, _ = recipe([op("T0101", 800, 0, 10), op("T0101", 800, 10, 20)])
check("'(Spindle already at' comment present", "(Spindle already at" in g)
check("the comment produces no recipe line",
      not any(l.cmd not in (0, 1) for l in
              R.GCodeToSCLConverter().parse_gcode("(Spindle already at G97 S800)")
              if l.cmd == R.CMD_SPINDLE_ON))

print("8) the first op always starts the spindle")
_, rec = recipe([op("T0101", 800, 0, 10)])
check("one SPINDLE_ON for a single-op program", ons(rec) == [80], ons(rec))

print()
if fails:
    print(f"FAILED: {len(fails)} -> {fails}")
    sys.exit(1)
print("ALL PASS")
