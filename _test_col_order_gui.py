"""#91 — real-Tk check of the Column Order tab against a live Treeview.

Builds an actual ops-table-shaped Treeview + the order editor, moves a column
with the ◀ / ▶ handlers and confirms displaycolumns follows, that Sel cannot be
displaced, and that the ☑ cell stays at display position #1.
"""
import types
import tkinter as tk
from tkinter import ttk

from ui.tabs.program_tab import ProgramTab

COLS = ("Sel", "Idx", "On", "Type", "Count", "Tool", "RealEndZ",
        "EndReach", "EndAngle", "x_clearance", "x_feed_rate")

root = tk.Tk()
root.withdraw()

pt = ProgramTab.__new__(ProgramTab)
pt.app = types.SimpleNamespace(params={})
pt.tree_ops = ttk.Treeview(root, columns=COLS, show="headings")
for c in COLS:
    pt.tree_ops.heading(c, text=c)
pt.tree_ops.configure(displaycolumns=pt._display_order(COLS))
pt.tree_ops.insert("", "end", iid="0", values=("☐", 1, "✓", "ROUGH", 3, "T001",
                                               "12.0", "40.0", "30.0°", "2.5", "800"))

# Build the dialog's order tab without the full app (only _build_order_tab and
# the movement handlers are exercised).
from ui.dialogs.view_customizer import ViewCustomizerDialog as VC

dlg = VC.__new__(VC)
dlg.pt = pt
dlg.app = pt.app
frame = tk.Frame(root)
VC._build_order_tab(dlg, frame)
print(f"  strip built, {len(dlg._order_list)} chips: {dlg._order_list[:4]}...")
assert dlg._order_list[0] == "Sel"

# Move clearance from index 9 to the front (index 1), one ◀ press at a time.
dlg._select_col("x_clearance")
for _ in range(20):
    VC._move_col(dlg, -1)
assert dlg._order_list[1] == "x_clearance", dlg._order_list
assert dlg._order_list[0] == "Sel", "Sel displaced by repeated left moves"
print("  OK  clearance walks to position 2, stops at pinned Sel")

# Sel itself has no chip binding, but force the handler anyway.
dlg._order_sel = "Sel"
VC._move_col(dlg, 1)
assert dlg._order_list[0] == "Sel", "Sel moved via direct handler call"
print("  OK  Sel immovable even by direct handler call")

# Apply the order to the live tree the way after_view_config_changed does.
dlg._order_sel = "x_clearance"
pt.app.params["op_view_col_order"] = [c for c in dlg._order_list if c != "Sel"]
order = pt._display_order(COLS)
pt.tree_ops.configure(displaycolumns=order)
shown = pt.tree_ops.cget("displaycolumns")
shown = tuple(shown.split()) if isinstance(shown, str) else tuple(str(c) for c in shown)
assert shown == order, f"{shown} != {order}"
assert shown[1] == "x_clearance", shown
print(f"  OK  tree displaycolumns applied: {shown[:3]}...")

# The critical invariant: values still land under the right headings, and the
# ☑ cell is still display column #1 (what the tick handlers test).
assert pt.tree_ops.set("0", "x_clearance") == "2.5", "value/column misaligned"
assert pt.tree_ops.set("0", "Sel") == "☐"
root.update_idletasks()
first = pt.tree_ops.column("#1", "id")
assert first == "Sel", f"display column #1 is {first!r}, tick handlers would break"
print("  OK  values stay aligned; display column #1 is still Sel")

# Reset returns the natural order.
VC._reset_order(dlg)
assert tuple(dlg._order_list) == COLS, dlg._order_list
print("  OK  Reset Order restores natural order")

root.destroy()
print("\nALL PASS")
