# -*- coding: utf-8 -*-
"""Widget smoke test for the Compare-passes dialog (#104).

The model half is covered by _test_pass_compare.py; this checks the things only
a real widget can show:
  * the window builds, populates and filters ("Only differences");
  * the toolbar button and context-menu entry exist and open it;
  * [Apply] is disabled until something is staged, then writes ONE undo step to
    the destination the scope rules chose — and Ctrl+Z takes it back;
  * the same-operation case: an op-level stage shows on BOTH sides.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from i18n import t
from machine_adapter import StandardTwoAxisSpinningAdapter
from mandrel_analyzer import MandrelManager
from ui.tabs.program_tab import ProgramTab
from ui.dialogs.pass_compare_dialog import PassCompareDialog

root = tk.Tk()
root.withdraw()

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])

app = MagicMock()
app.mandrel_mgr = mgr
app.gui_pass_overrides = {}
app.tool_library = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0}]
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False
app.params = {
    "operations": [
        {"type": "roughing", "enabled": True, "name": "Rough fwd", "count": 4,
         "tool_id": "T0101", "direction": "forward", "pass_shape": "linear_approach",
         "r_tool": 25.0, "clearance": 1.5, "p1_x": 40.0, "p1_z": 50.0,
         "p3_x": 30.0, "p3_z": -25.0, "start_z": min_z + 10, "end_z": min_z + 40,
         "pass_angle": 120.0, "reach": 40.0, "feed": 300.0},
        {"type": "roughing", "enabled": True, "name": "Rough rev", "count": 3,
         "tool_id": "T0101", "direction": "reverse", "pass_shape": "spline",
         "r_tool": 25.0, "clearance": 2.5, "p1_x": 40.0, "p1_z": 50.0,
         "p3_x": 30.0, "p3_z": -25.0, "start_z": min_z + 40, "end_z": min_z + 10,
         "pass_angle": 110.0, "reach": 30.0, "feed": 500.0},
    ],
    "blank_radius": 0.0, "target_clearance": 0.0, "min_safety_gap": -999.0,
    "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
    "auto_calc_angle": False,
}

helper = MagicMock()
# Real values: the property editor feeds these straight to Tk, and a MagicMock
# there fails with 'unknown color name <id>' the moment an op is re-rendered.
helper.HINT_COLOR = "#9a9a9a"
helper.HINT_FONT = ("Arial", 7)

frame = ttk.Frame(root)
tab = ProgramTab(frame, app, MagicMock(), helper)
root.update_idletasks()

# --- Toolbar button + context-menu entry exist -----------------------------
btns = [w for w in tab.frame.winfo_children()[1].winfo_children()
        if isinstance(w, ttk.Button) and str(w["text"]) == t("btn_pass_compare")]
assert btns, "Compare toolbar button missing"
assert hasattr(tab, "open_pass_compare"), "ProgramTab.open_pass_compare missing"
print("Toolbar button + entry point OK")

# --- Dialog builds and populates ------------------------------------------
dlg = PassCompareDialog(root, app, tab, (0, 0), (1, 1))
root.update_idletasks()
rows_all = dlg.tree.get_children()
assert rows_all, "compare table is empty"
labels = [dlg.tree.item(i)["values"][0] for i in rows_all]
assert t("pc_sec_effective") in labels, "effective section header missing"
assert t("pc_sec_operation") in labels, "operation section header missing"
assert t("lbl_direction") in labels, "direction row missing (forward vs reverse)"
print(f"Dialog builds with {len(rows_all)} rows (both sections) OK")

# --- Two-step pickers (user 2026-09-02): operation, then pass --------------
for side, want in (("a", (0, 0)), ("b", (1, 1))):   # the seeds passed above
    assert dlg._sel(side) == want, f"seed {side} not honoured: {dlg._sel(side)}"
assert dlg._pick["a"]["pass"].get() == "1 / 4", dlg._pick["a"]["pass"].get()
assert dlg._pick["b"]["pass"].get() == "2 / 3", dlg._pick["b"]["pass"].get()
assert "Rough fwd" in dlg._pick["a"]["op"].get(), dlg._pick["a"]["op"].get()
assert t("pc_tag_reverse") in dlg._pick["b"]["op"].get(), \
    f"reverse op not tagged in the picker: {dlg._pick['b']['op'].get()}"
assert "4" in dlg._pick["a"]["op"].get(), "op label must carry its pass count"

# The pass list is scoped to the CHOSEN operation, not the whole program.
assert list(dlg._pick["a"]["cb_pass"]["values"]) == ["1 / 4", "2 / 4", "3 / 4", "4 / 4"]
assert list(dlg._pick["b"]["cb_pass"]["values"]) == ["1 / 3", "2 / 3", "3 / 3"]
print("Two-step pickers: op list tagged, pass list scoped to that op OK")

# Picking a pass inside the current operation moves only the pass index.
dlg._pick["a"]["pass"].set("1 / 4")
dlg._on_pass_pick("a")
assert dlg._sel("a") == (0, 0), dlg._sel("a")

# Switching operation KEEPS the pass number where it fits...
dlg._pick["a"]["pass"].set("3 / 4"); dlg._on_pass_pick("a")
dlg._pick["a"]["op"].set(dlg._ops[1]["label"]); dlg._on_op_pick("a")
assert dlg._sel("a") == (1, 2), f"pass number not carried across ops: {dlg._sel('a')}"
assert dlg._pick["a"]["pass"].get() == "3 / 3", dlg._pick["a"]["pass"].get()
assert list(dlg._pick["a"]["cb_pass"]["values"]) == ["1 / 3", "2 / 3", "3 / 3"], \
    "pass list did not follow the operation"
# ...and CLAMPS when the new operation is shorter.
dlg._pick["a"]["op"].set(dlg._ops[0]["label"]); dlg._on_op_pick("a")
dlg._pick["a"]["pass"].set("4 / 4"); dlg._on_pass_pick("a")
dlg._pick["a"]["op"].set(dlg._ops[1]["label"]); dlg._on_op_pick("a")
assert dlg._sel("a") == (1, 2), f"pass 4 not clamped onto a 3-pass op: {dlg._sel('a')}"
print("Op switch keeps the pass number, clamps onto shorter operations OK")

# Swap moves both selections AND both pairs of comboboxes.
dlg.sel_a, dlg.sel_b = (0, 2), (1, 1)          # known state: fwd op vs rev op
dlg._sync_pickers()
before = (dlg._sel("a"), dlg._sel("b"))
dlg._swap()
assert (dlg._sel("a"), dlg._sel("b")) == (before[1], before[0]), "swap did not swap"
assert "Rough fwd" in dlg._pick["b"]["op"].get(), "swap left the op picker stale"
assert dlg._pick["b"]["pass"].get() == "3 / 4", \
    f"swap left the pass picker stale: {dlg._pick['b']['pass'].get()}"
dlg._swap()
dlg.sel_a, dlg.sel_b = (0, 2), (1, 1)
dlg._sync_pickers()
dlg.refresh()
print("Swap keeps the pickers in step OK")

# --- Forward vs reverse difference is visible ------------------------------
dir_iid = next(i for i in rows_all if dlg.tree.item(i)["values"][0] == t("lbl_direction"))
vals = dlg.tree.item(dir_iid)["values"]
assert "forward" in str(vals[1]) and "reverse" in str(vals[2]), \
    f"direction cells wrong: {vals}"
assert "diff" in dlg.tree.item(dir_iid)["tags"], "differing row not tagged"
print("Forward vs reverse row flagged OK")

# --- Only-differences filter drops the identical rows AND empty headers ----
dlg.var_only_diff.set(True)
dlg.refresh()
rows_diff = dlg.tree.get_children()
assert 0 < len(rows_diff) < len(rows_all), \
    f"filter did nothing ({len(rows_diff)} vs {len(rows_all)})"
for i in rows_diff:
    if "header" in dlg.tree.item(i)["tags"]:
        continue
    assert dlg.tree.item(i)["values"][3], f"non-differing row survived: {dlg.tree.item(i)['values']}"
dlg.var_only_diff.set(False)
dlg.refresh()
print(f"Only-differences filter OK ({len(rows_diff)} of {len(rows_all)})")

# --- Apply gating + one undo step ------------------------------------------
assert str(dlg.btn_apply["state"]) == "disabled", "Apply enabled with nothing staged"
dlg.staged_pins[(0, 2)] = {"reach": 12.0}
dlg.staged_ops[1] = {"feed": 650.0}
dlg.refresh()
assert str(dlg.btn_apply["state"]) == "normal", "Apply not enabled by staging"
assert "pass_edits" not in app.params["operations"][0], "staging must not touch the op"
assert app.params["operations"][1]["feed"] == 500.0, "staging must not touch the op"
n_undo = len(tab._op_undo._undo)
dlg._apply()
assert app.params["operations"][0]["pass_edits"] == {"2": {"reach": 12.0}}, "pin not written"
assert app.params["operations"][1]["feed"] == 650.0, "op field not written"
assert len(tab._op_undo._undo) == n_undo + 1, "Apply must be exactly ONE undo step"
assert str(dlg.btn_apply["state"]) == "disabled", "Apply still enabled after commit"
tab.undo_op_action()
assert "pass_edits" not in app.params["operations"][0], "Ctrl+Z did not remove the pin"
assert app.params["operations"][1]["feed"] == 500.0, "Ctrl+Z did not restore the op field"
print("Staged apply -> one undo step -> undo restores both destinations OK")

# --- Same operation on both sides: an op-level stage shows on BOTH ---------
dlg.sel_a, dlg.sel_b = (0, 0), (0, 3)
dlg.staged_ops = {0: {"pass_shape": "spline"}}
dlg.staged_pins = {}
dlg.refresh()
sh = next(i for i in dlg.tree.get_children()
          if dlg.tree.item(i)["values"][0] == t("lbl_shape_mode"))
va, vb = str(dlg.tree.item(sh)["values"][1]), str(dlg.tree.item(sh)["values"][2])
assert "spline" in va and "spline" in vb, f"op stage not previewed on both sides: {va} / {vb}"
assert "staged" in dlg.tree.item(sh)["tags"], "staged row not tagged"
print("Op-level stage previews on both passes of the same op OK")

# --- Report -----------------------------------------------------------------
dlg.staged_ops = {}
dlg.sel_a, dlg.sel_b = (0, 0), (1, 1)
dlg.refresh()
import pass_compare as pc
rep = pc.format_report(dlg._rows, only_diff=True)
assert "forward" in rep and "reverse" in rep, "report missing the direction difference"
print("Report text OK")

dlg.staged_ops, dlg.staged_pins = {}, {}
dlg.destroy()
root.destroy()
print("\nALL PASS")
