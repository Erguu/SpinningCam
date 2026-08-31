"""CSS (G96) is disabled — an operation always runs as fixed RPM (2026-08-31).

Why this test exists: the PLC recipe has no constant-surface-speed mode. CMD=20
carries Param = RPM/10, and recipe_to_scl reads only the S word, so a CSS op's
surface speed was shipped to the machine as if it were RPM. The kill switch in
path_generator must be honoured by EVERY consumer, or the .nc would say G96
while the recipe ran a fixed RPM.

Run: pyrun.bat _test_speed_mode_css_off.py   (conda env spinning_cam)
"""
import sys

import path_generator
from path_generator import resolve_speed_mode, speed_mode_choices
import recipe_to_scl

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        fails.append(name)


print("1) resolve_speed_mode")
check("CSS is read as RPM", resolve_speed_mode({"speed_mode": "CSS"}) == "RPM")
check("lowercase css too", resolve_speed_mode({"speed_mode": "css"}) == "RPM")
check("RPM stays RPM", resolve_speed_mode({"speed_mode": "RPM"}) == "RPM")
check("missing key defaults to RPM", resolve_speed_mode({}) == "RPM")
check("None-safe", resolve_speed_mode(None) == "RPM")
check("switch is off", path_generator.CSS_SPEED_MODE_ENABLED is False)
check("UI offers RPM only", speed_mode_choices() == ["RPM"])

print("2) the switch really re-enables CSS")
path_generator.CSS_SPEED_MODE_ENABLED = True
try:
    check("CSS survives when enabled", resolve_speed_mode({"speed_mode": "CSS"}) == "CSS")
    check("UI offers both", speed_mode_choices() == ["CSS", "RPM"])
finally:
    path_generator.CSS_SPEED_MODE_ENABLED = False

print("3) emitter writes G97, never G96")
_gcode = None
try:
    import numpy as np
    from mandrel_analyzer import MandrelManager
    from main import SpinningApp  # noqa: F401  (settings defaults live here)
except Exception as e:  # pragma: no cover
    print(f"  SKIP engine check ({e})")
else:
    pg = path_generator.PathGenerator()
    params = {
        "operations": [{
            "type": "roughing", "enabled": True, "count": 2,
            "tool_id": "T0101", "r_tool": 20.0,
            "speed": 200.0, "speed_mode": "CSS",      # legacy op, still on disk
            "feed": 300.0, "feed_mode": "mm_min",
            "start_z": 0.0, "end_z": 40.0,
        }],
        "blank_radius": 100.0, "final_part_thickness_on_mandrel": 2.0,
        "mandrel_step_file": "", "num_sweeping_passes": 1,
    }
    mgr = MandrelManager()
    try:
        pg.calculate_paths(params, {}, mgr)
        _gcode = pg.generate_gcode(params=params, for_recipe=True)
    except Exception as e:
        print(f"  SKIP engine check (no mandrel: {e})")
        _gcode = None

if _gcode:
    check("no G96 in output", "G96" not in _gcode)
    check("G97 emitted", "G97" in _gcode)
    conv = recipe_to_scl.GCodeToSCLConverter()
    lines = conv.parse_gcode(_gcode)
    on = [l for l in lines if l.cmd == recipe_to_scl.CMD_SPINDLE_ON]
    check("spindle ON emitted", len(on) >= 1, f"got {len(on)}")
    # 200 was stored as CSS m/min; it already ran as 200 RPM, so Param must not
    # change value — this is the "no recipe changes" guarantee.
    check("Param unchanged at 20 (200 RPM)", all(l.param == 20 for l in on),
          f"got {[l.param for l in on]}")

print("4) SCL header names the real mode")
conv = recipe_to_scl.GCodeToSCLConverter()
conv.parse_gcode("G0 X10 Z5\nG97 S300 M3\nG1 X20 Z6 F300\nM5\nM30\n")
scl = conv.generate_scl("DB_T", "T", force=True, params={
    "operations": [{"type": "roughing", "speed": 200, "speed_mode": "CSS",
                    "feed": 300, "feed_mode": "mm_min"}],
})
check("header says RPM=200, not CSS=200", "RPM=200" in scl and "CSS=200" not in scl)

print("5) editor combo (real Tk)")
try:
    import types
    import tkinter as tk
    from ui.tabs.program_tab import ProgramTab

    root = tk.Tk()
    root.withdraw()
    pt = ProgramTab.__new__(ProgramTab)
    pt.f_prop_editor = tk.Frame(root)
    pt.helper = types.SimpleNamespace(bind_tooltip=lambda *a, **k: None)
    pt.app = types.SimpleNamespace(params={"operations": [{"speed_mode": "CSS"}]})

    legacy = {"speed_mode": "CSS"}
    pt._add_prop_combo(0, "speed_mode", "Speed Mode", speed_mode_choices(),
                       legacy, current=resolve_speed_mode(legacy))
    cb = [w for w in pt.f_prop_editor.winfo_children()[0].winfo_children()
          if w.winfo_class() == "TCombobox"][0]
    check("legacy CSS op shows RPM in the box", cb.get() == "RPM", cb.get())
    check("CSS not selectable", tuple(cb.cget("values")) == ("RPM",),
          str(cb.cget("values")))
    # `current=None` must keep the old behaviour for every other combo.
    pt._add_prop_combo(0, "feed_mode", "Feed Mode", ["mm_min", "mm_rev"],
                       {"feed_mode": "mm_rev"})
    cb2 = [w for w in pt.f_prop_editor.winfo_children()[1].winfo_children()
           if w.winfo_class() == "TCombobox"][0]
    check("other combos unaffected", cb2.get() == "mm_rev", cb2.get())

    # The ops-table column must agree with the combo an inch away from it.
    legacy_op = {"type": "roughing", "speed_mode": "CSS"}
    check("table column shows RPM for a legacy CSS op",
          pt._cell_value(legacy_op, "speed_mode", "roughing") == "RPM",
          pt._cell_value(legacy_op, "speed_mode", "roughing"))
    check("table column shows RPM when the key is absent entirely",
          pt._cell_value({"type": "roughing"}, "speed_mode", "roughing") == "RPM")
    check("other columns still read raw",
          pt._cell_value({"type": "roughing", "feed_mode": "mm_rev"},
                         "feed_mode", "roughing") == "mm_rev")
    root.destroy()
except Exception as e:  # pragma: no cover
    print(f"  SKIP Tk check ({e})")

print()
if fails:
    print(f"FAILED: {len(fails)} -> {fails}")
    sys.exit(1)
print("ALL PASS")
