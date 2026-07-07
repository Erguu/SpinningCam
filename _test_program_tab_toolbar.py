"""Widget smoke test for the reworked ProgramTab toolbar: +Add dropdown,
Suggest button, On/Off toggle, On column + gray rows, double-click toggle."""
import sys
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import ProgramTab

root = tk.Tk()
root.withdraw()

app = MagicMock()
app.params = {"operations": [
    {"type": "roughing", "enabled": True, "count": 3, "tool_id": "T0101"},
    {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0202"},
]}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False

ui_root = MagicMock()
ui_root.tool_library = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0}]
helper = MagicMock()

frame = ttk.Frame(root)
tab = ProgramTab(frame, app, ui_root, helper)
root.update_idletasks()

# Tree has the On column and both rows enabled (values: Sel, Idx, On, ... — #67
# added the ☑ batch-tick column in front)
assert "On" in tab.tree_ops["columns"], "On column missing"
assert "Sel" in tab.tree_ops["columns"], "Sel (batch tick) column missing"
assert tab.tree_ops.item("0")["values"][2] == "✓", "enabled mark missing"
assert tab.tree_ops.item("0")["values"][0] == "☐", "batch tick should start unticked"

# Toggle selected op -> disabled mark + gray tag, params updated
tab.tree_ops.selection_set("0")
tab.toggle_op_enabled()
assert app.params["operations"][0]["enabled"] is False, "toggle did not passivate op"
assert tab.tree_ops.item("0")["values"][2] == "—", "disabled mark missing"
assert "op_disabled" in tab.tree_ops.item("0")["tags"], "gray tag missing"
tab.toggle_op_enabled()
assert app.params["operations"][0]["enabled"] is True, "re-toggle did not reactivate"
print("On/Off toggle + tree marks OK")

# +Add dropdown exists with the adapter's op types as menu entries
menubuttons = [w for w in tab.frame.winfo_children()[1].winfo_children()
               if isinstance(w, ttk.Menubutton)]
assert len(menubuttons) == 1, "Add dropdown missing"
menu = menubuttons[0].nametowidget(menubuttons[0]["menu"])
n_entries = menu.index("end") + 1
assert n_entries == 4, f"expected 4 op types in dropdown, got {n_entries}"
# selecting an entry adds an op
menu.invoke(0)  # roughing
assert len(app.params["operations"]) == 3, "dropdown add_op did not append"
assert app.params["operations"][-1]["type"] == "roughing"
print("+Add dropdown adds operations OK")

# Suggest button present (tk.Button with the i18n label)
from i18n import t
suggest_btns = [w for w in tab.frame.winfo_children()[1].winfo_children()
                if isinstance(w, tk.Button) and w["text"] == t("btn_suggest_ops")]
assert len(suggest_btns) == 1, "Suggest button missing"
print("Suggest button present OK")

# The full property-editor rebuild needs real app/tool objects the mocks can't
# provide; undo/batch correctness is asserted on params, so stub it out here.
tab.on_op_select = lambda *a, **k: None

# --- #66 Undo/Redo buttons: toggling pushed history -> undo enabled ---
assert str(tab.btn_undo["state"]) == "normal", "undo should be enabled after actions"
n_before = len(app.params["operations"])
tab.tree_ops.selection_set("0")
tab.toggle_op_enabled()          # one more tracked action
was_enabled = app.params["operations"][0]["enabled"]
tab.undo_op_action()
assert app.params["operations"][0]["enabled"] != was_enabled, "undo did not revert toggle"
assert str(tab.btn_redo["state"]) == "normal", "redo should be enabled after undo"
tab.redo_op_action()
assert app.params["operations"][0]["enabled"] == was_enabled, "redo did not re-apply"
assert len(app.params["operations"]) == n_before, "undo/redo changed op count"
print("Undo/Redo buttons + revert/reapply OK")

# --- #67 Batch button: disabled at <2 targets, enabled via ticks or selection ---
assert str(tab.btn_batch["state"]) == "disabled", "batch should start disabled"
tab.tree_ops.selection_set(("0", "1"))           # extended selection of 2 ops
tab._update_batch_button()
assert str(tab.btn_batch["state"]) == "normal", "batch should enable at 2 selected"
assert "(2)" in tab.btn_batch["text"], "batch label should show target count"
tab.tree_ops.selection_set("0")                   # back to single
tab._update_batch_button()
assert str(tab.btn_batch["state"]) == "disabled", "batch should disable at 1 selected"
tab._batch_checked.update({0, 1, 2})              # ☑ ticks override selection
tab._update_batch_button()
assert "(3)" in tab.btn_batch["text"], "ticked targets should win over selection"
changes, skipped = tab._batch_compute(app.params["operations"], tab._batch_targets(),
                                      "count", "add", 1.0,
                                      {ot: tab._universe_for(ot)
                                       for ot in ("roughing", "finishing", "cutting", "bending")})
assert changes, "batch compute produced no changes"
tab._apply_batch("count", changes)                # writes + one undo snapshot
for i, (_old, new) in changes.items():
    assert app.params["operations"][i]["count"] == new, "batch write missing"
tab.undo_op_action()                              # single Ctrl+Z reverts the batch
for i, (old, _new) in changes.items():
    assert app.params["operations"][i].get("count", 1) == old, "batch undo failed"
print("Batch targets/compute/apply + single-step undo OK")

# --- #69 Copy: multi-target duplicate as a block after the last target ---
tab._batch_checked.clear()
n0 = len(app.params["operations"])
app.params["operations"][0]["name"] = "my rough"     # named op -> suffixed copy
tab.refresh_ops_tree()
tab._batch_checked.update({0, 1})
tab.copy_ops()
assert len(app.params["operations"]) == n0 + 2, "copy did not add 2 clones"
assert app.params["operations"][2] == {**app.params["operations"][0],
                                       "name": app.params["operations"][2]["name"]}, \
    "first clone content differs"
assert app.params["operations"][2]["name"].startswith("my rough ("), \
    "named copy not suffixed"
assert not tab._batch_checked, "ticks must clear after copy (indices shifted)"
tab.undo_op_action()
assert len(app.params["operations"]) == n0, "undo did not remove the copies"
print("Copy (multi, block insert, name suffix, undo) OK")

# --- #70 Name shown in Type column ---
tab.refresh_ops_tree()
assert tab.tree_ops.item("0")["values"][3] == "my rough", "custom name not shown"
assert str(tab.tree_ops.item("1")["values"][3]).startswith("FINISH"), \
    "unnamed op must show its type"
print("Name display in Type column OK")

# --- #71 Library insert: fresh op after anchor + r_tool re-sync called ---
import ops_library as ol
entry_ops = []
ol.add_entry(entry_ops, "lib rough", {"type": "roughing", "count": 4,
                                      "tool_id": "T0101", "r_tool": 999.0})
n1 = len(app.params["operations"])
tab.tree_ops.selection_set("0")
tab._insert_from_library(entry_ops[0])
assert len(app.params["operations"]) == n1 + 1, "library insert missing"
ins = app.params["operations"][1]
assert ins["name"] == "lib rough" and ins["count"] == 4 and ins["enabled"] is True
app.sync_operation_r_tools.assert_called()   # stale-reach guard invoked
tab.undo_op_action()
assert len(app.params["operations"]) == n1, "undo did not remove library insert"
print("Library insert (position, content, r_tool sync, undo) OK")

# --- #68 Reach source: follow overwrites reach, release unlocks cleanly ---
op0 = app.params["operations"][0]
op0["reach"] = 42.0
op0["reach_follow_blank"] = True
tab._blank_reach_values = lambda op: (10.0, 5.0, False)   # stub the flange model
tab._refresh_auto_reach()
assert op0["reach"] == 10.0, "follow mode did not refresh reach"
# Release (#68 reversibility guarantee): back to Elle — the auto refresh must
# stop touching the op and a manual edit must survive the next refresh.
op0["reach_follow_blank"] = False
op0["reach"] = 33.0
tab._refresh_auto_reach()
assert op0["reach"] == 33.0, "released op still auto-refreshed"
# Live read-out var gets the fresh value when registered for the op (#68 P1).
op0["reach_follow_blank"] = True
class _FakeVar:
    def __init__(self): self.v = None
    def set(self, x): self.v = x
tab._reach_live_var = _FakeVar()
tab._reach_live_idx = 0
tab._refresh_auto_reach()
assert tab._reach_live_var.v == str(op0["reach"]), "live var not updated"
op0["reach_follow_blank"] = False
print("Reach source follow/release + live read-out (#68) OK")

root.destroy()
print("PROGRAM TAB TOOLBAR SMOKE TEST PASSED")
sys.exit(0)
