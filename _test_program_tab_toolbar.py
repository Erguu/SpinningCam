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

# Tree has the On column and both rows enabled
assert "On" in tab.tree_ops["columns"], "On column missing"
assert tab.tree_ops.item("0")["values"][1] == "✓", "enabled mark missing"

# Toggle selected op -> disabled mark + gray tag, params updated
tab.tree_ops.selection_set("0")
tab.toggle_op_enabled()
assert app.params["operations"][0]["enabled"] is False, "toggle did not passivate op"
assert tab.tree_ops.item("0")["values"][1] == "—", "disabled mark missing"
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

root.destroy()
print("PROGRAM TAB TOOLBAR SMOKE TEST PASSED")
sys.exit(0)
