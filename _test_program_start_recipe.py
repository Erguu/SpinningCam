# -*- coding: utf-8 -*-
"""The two Program Start rapids must not reach a PLC recipe (2026-08-17).

generate_gcode opens with a staged "G0 Z<home>" + "G0 X<home>" pair. That is a
G-code homing convention and it stays in the .nc: the first move into a pass is
a coordinated diagonal, so a G-code control needs the known start point.

A PLC recipe does not. Every recipe line carries absolute X AND Z, the machine
homes before every run, and with origin_use_home the pair transforms to X0 Z0 —
two identical CMD=0 rows that drag the roller BACK to zero whenever it is not
already sitting there (operator jogged in, start cylinder moved it).

Pins the part that is easy to get wrong: the strip follows for_recipe (the
output path), NOT params["plc_mode"]. plc_mode only asks for decimation, and
ID112-1 is a PLC machine that ships with plc_mode 0.0 — gating on it would
leave exactly that machine with the zero rows.
"""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from recipe_to_scl import GCodeToSCLConverter, CMD_RAPID

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)


def make_params(plc=False):
    op = {"type": "roughing", "count": 3, "start_z": 10.0, "end_z": 50.0,
          "r_tool": 25.0, "clearance": 0.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": "forward", "p2_radius": 2.0,
          "exit_mid_t": 0.5, "exit_mid_radius": -60.0}
    return {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "collision_resolution": 0.5, "gcode_resolution": 2.0,
            "plc_mode": plc, "plc_tolerance": 0.01, "plc_exit_tolerance": 0.01,
            # ID112-1's real frame: origin follows home, so home prints as X0 Z0.
            "home_x": -400.0, "home_z": -150.0, "origin_use_home": 1.0}


def gen(params, for_recipe):
    pg = PathGenerator()
    pg.calculate_paths(params, {}, mgr)
    return pg.generate_gcode(params=params, for_recipe=for_recipe)


def start_lines(txt):
    return [l for l in txt.splitlines() if "(Program Start Z)" in l or "(Program Start X)" in l]


# ── 1. .nc output keeps the staged home, unchanged ────────────────────────
p_off = make_params(plc=False)
nc = gen(p_off, for_recipe=False)
sl = start_lines(nc)
check(len(sl) == 2 and sl[0].startswith("G0 Z") and sl[1].startswith("G0 X"),
      f"G-code output still opens with the staged home ({' | '.join(sl)})")
check("G0 Z0.000 (Program Start Z)" in nc and "G0 X0.000 (Program Start X)" in nc,
      "origin_use_home really does make the pair X0 Z0 (the duplicate rows)")

# ── 2. Recipe output drops exactly those two lines, nothing else ──────────
rec = gen(p_off, for_recipe=True)
check(start_lines(rec) == [], "recipe output emits neither Program Start line")
removed = [l for l in nc.splitlines() if l not in rec.splitlines()]
check(len(nc.splitlines()) - len(rec.splitlines()) == 2,
      f"exactly 2 lines fewer ({len(nc.splitlines())} → {len(rec.splitlines())})")
check(all("Program Start" in l for l in removed),
      f"the ONLY lines dropped are the two home moves (dropped: {removed})")
check("(Program Start: X=-400.0, Z=-150.0)" in rec,
      "the header comment still documents Program Start (comments are not motion)")

# ── 3. plc_mode must NOT be the switch — the ID112-1 trap ─────────────────
check(start_lines(gen(make_params(plc=True), for_recipe=False)) != [],
      "plc_mode ON alone does not strip them (it only asks for decimation)")
check(start_lines(gen(make_params(plc=True), for_recipe=True)) == [],
      "for_recipe strips them with plc_mode ON too")
check(start_lines(gen(make_params(plc=False), for_recipe=True)) == [],
      "for_recipe strips them with plc_mode OFF (ID112-1 ships plc_mode 0.0)")

# ── 4. The recipe no longer opens with a move to zero ─────────────────────
def to_recipe(txt):
    conv = GCodeToSCLConverter()
    return conv.parse_gcode(txt)

r_nc, r_rec = to_recipe(nc), to_recipe(rec)
check(len(r_nc) - len(r_rec) == 2,
      f"two recipe rows saved ({len(r_nc)} → {len(r_rec)} lines)")
def leading_zero_rapids(rows):
    """(0,0) rapids BEFORE the first move that actually goes somewhere."""
    out = []
    for l in rows:
        if l.cmd == CMD_RAPID:
            if abs(l.x) < 1e-9 and abs(l.z) < 1e-9:
                out.append(l)
            else:
                break
    return out

check(len(leading_zero_rapids(r_nc)) == 2,
      "before: the recipe DID open with two identical (0,0) rapids")
check(leading_zero_rapids(r_rec) == [],
      "after: the recipe opens with no move to zero at all")

# The Program End park is a DIFFERENT pair (path_generator ~2958): staged Z-then-X
# from wherever the last pass ended, so both rows are real motion. for_recipe must
# not touch it — the program still has to get the roller out of the way.
end_rapids = [l for l in r_rec if l.cmd == CMD_RAPID][-2:]
check(abs(end_rapids[-1].x) < 1e-9 and abs(end_rapids[-1].z) < 1e-9
      and abs(end_rapids[-2].x) > 1e-9,
      f"Program End park survives, still staged Z-then-X "
      f"(X{end_rapids[-2].x:.1f} Z{end_rapids[-2].z:.1f} → "
      f"X{end_rapids[-1].x:.1f} Z{end_rapids[-1].z:.1f})")

# ── 5. The first pass still positions correctly (absolute X+Z, not modal) ─
first_rapid_nc = next(l for l in r_nc if l.cmd == CMD_RAPID and (abs(l.x) > 1e-9 or abs(l.z) > 1e-9))
first_rapid_rec = next(l for l in r_rec if l.cmd == CMD_RAPID)
check(abs(first_rapid_nc.x - first_rapid_rec.x) < 1e-9
      and abs(first_rapid_nc.z - first_rapid_rec.z) < 1e-9,
      f"first real positioning move is unchanged "
      f"(X{first_rapid_rec.x:.3f} Z{first_rapid_rec.z:.3f})")

print()
print("FAILURES:" if fails else "ALL PASS", fails if fails else "")
raise SystemExit(1 if fails else 0)
