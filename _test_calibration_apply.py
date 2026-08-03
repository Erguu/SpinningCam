"""Calibration ▸ Apply must reach the tab inputs, not just app.params.

BUG (2026-08-03): the five Apply buttons call app.on_param_change, which updates
params — but every tab input holds a Tk variable seeded ONCE at build time and
written back on <FocusOut>. So the box kept showing the pre-calibration number
(looking like the button did nothing) and the next focus-out silently wrote that
stale number back over the correction.

These checks drive real widgets through the exact sequence.
"""
import types
import tkinter as tk

from ui.helpers_ui import UIHelper
from ui.tabs.machine_tab import MachineTab

root = tk.Tk()
root.withdraw()

PARAMS = {
    "home_x": -396.0, "home_z": -175.0,
    "machine_gcode_offset_x": 0.0, "machine_gcode_offset_z": 0.0,
    "mandrel_pos_x_offset": 0.0, "final_part_thickness_on_mandrel": 2.0,
}

params = dict(PARAMS)
app = types.SimpleNamespace(params=params, active_machine_profile=None,
                            machine_adapter=None, factory_defaults={})
app.on_param_change = lambda k, v, m="none": params.__setitem__(
    k, v if isinstance(v, bool) else float(v))

helper = UIHelper(tk.Label(root))
tab = MachineTab(tk.Frame(root), app, helper)

# The two Process-tab Apply targets, built through the same shared helper the
# real app uses (main_window hands one UIHelper to every tab).
proc = tk.Frame(root)
helper.add_spinbox(proc, app, "final_part_thickness_on_mandrel", "Thickness",
                   0, 20, 0.1)
helper.add_scale(proc, app, "mandrel_pos_x_offset", "Mandrel X", -500, 500)


def widgets_for(key):
    return [(v, w) for k, v, w, _ in helper._param_vars if k == key]


def shown(key):
    out = []
    for var, _w in widgets_for(key):
        v = var.get()
        out.append(float(v) if not isinstance(v, bool) else v)
    return out


# ── every Apply target must own at least one registered input ────────────────
APPLY_TARGETS = {
    "home_x": -400.5,                      # _apply_home_x
    "home_z": -180.25,                     # _apply_home_z
    "machine_gcode_offset_z": 3.75,        # _apply_off_z
    "mandrel_pos_x_offset": 1.5,           # _apply_offset
    "final_part_thickness_on_mandrel": 2.4,  # _apply_blank
}
for key in APPLY_TARGETS:
    assert widgets_for(key), f"{key} has no registered input — Apply cannot reach it"
print("  1. all five Apply targets have registered inputs")

# ── apply each correction the way the dialog does, then fire the hook ────────
for key, new in APPLY_TARGETS.items():
    before = shown(key)
    app.on_param_change(key, new, "all")
    helper.refresh_from_params(app)          # what _show_applied now triggers
    after = shown(key)
    assert all(abs(v - new) < 1e-6 for v in after), \
        f"{key}: box shows {after}, expected {new} (was {before})"
print("  2. after Apply every box shows the corrected value:",
      {k: shown(k)[0] for k in APPLY_TARGETS})

# ── the silent-revert path: focus-out must not undo the correction ───────────
for key, new in APPLY_TARGETS.items():
    for _var, w in widgets_for(key):
        w.event_generate("<FocusOut>")
root.update_idletasks()
for key, new in APPLY_TARGETS.items():
    assert abs(float(params[key]) - new) < 1e-6, \
        f"{key} reverted to {params[key]} on focus-out (expected {new})"
print("  3. focus-out no longer writes the stale value back")

# ── Program End mirrors Program Start while unset ────────────────────────────
assert abs(shown("end_x")[0] - params["home_x"]) < 1e-6, shown("end_x")
assert abs(shown("end_z")[0] - params["home_z"]) < 1e-6, shown("end_z")
print("  4. Program End follows the corrected Program Start:",
      shown("end_x")[0], shown("end_z")[0])

# ── an explicit park point must NOT be dragged around by home_x ──────────────
params["end_use_home"] = False
params["end_x"] = 500.0
helper.refresh_from_params(app)
assert abs(shown("end_x")[0] - 500.0) < 1e-6, shown("end_x")
app.on_param_change("home_x", -410.0, "all")
helper.refresh_from_params(app)
assert abs(shown("end_x")[0] - 500.0) < 1e-6, \
    f"explicit park point moved with home_x: {shown('end_x')}"
print("  5. an explicit park point stays put when Program Start moves")

# ── destroyed widgets are dropped, not raised on ─────────────────────────────
n_before = len(helper._param_vars)
tab.content.destroy()
helper.refresh_from_params(app)
assert len(helper._param_vars) < n_before, "dead widgets were not pruned"
print(f"  6. rebuilt/destroyed widgets pruned ({n_before} -> {len(helper._param_vars)})")


# ── every Apply must be GLOBAL, never a per-pass override ────────────────────
# on_param_change diverts mode="paths" edits into gui_pass_overrides while
# "apply to this pass only" is on. A calibration correction sent down that path
# would land on one pass and leave the real parameter untouched. _apply_blank
# used mode="paths" until 2026-08-03.
import inspect

from ui.dialogs.touch_calibration import TouchCalibrationDialog as TCD

for name in ("_apply_home_x", "_apply_offset", "_apply_blank",
             "_apply_home_z", "_apply_off_z"):
    src = inspect.getsource(getattr(TCD, name))
    call = [l for l in src.splitlines()
            if "on_param_change" in l and not l.lstrip().startswith("#")]
    assert call, f"{name}: no on_param_change call found"
    assert '"paths"' not in call[0], \
        f'{name} passes mode="paths" — it would become a per-pass override'
    assert '"all"' in call[0], f"{name}: expected mode='all', got {call[0].strip()}"
print("  7. all five Apply calls use mode='all' (never a per-pass override)")

root.destroy()
print("\nALL CALIBRATION-APPLY CHECKS PASSED")
