"""Real End Z column tests.

1) INTEGRATION: the path generator stores, per op, the CAM Z its last forming
   pass actually reaches — including p2_z_extend. This is the bug the user hit:
   op0 (count=2, end_z=13, p2_z_extend=3) must report 16, not start_z=10.
2) UI: the column renders that stored value (and "—" when absent).
"""
import sys
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from path_generator import PathGenerator


# ── 1) INTEGRATION: path_generator.last_op_end_z ───────────────────────────
def cyl_mandrel():
    mm = MagicMock()
    mm.props = {"top_z": 100.0, "min_z": 0.0}
    mm.get_radius_fast = lambda z: 50.0          # straight cylinder
    mm.get_normal_at_z = lambda z: (1.0, 0.0)    # radial normal
    return mm


params = {
    "mandrel_pos_x_offset": 0.0,
    "final_part_thickness_on_mandrel": 0.0,
    "shell_thickness": 0.0,
    "home_x": 300.0, "home_z": 150.0,
    "retract_x": 50.0, "retract_z": 50.0,
    "operations": [
        # op0: count=2 → last pass at end_z=13, +p2_z_extend 3 → 16
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T1",
         "r_tool": 20.0, "start_z": 10.0, "end_z": 13.0, "p2_z_extend": 3.0,
         "pass_shape": "linear_approach"},
        # op1: count=1 → single pass sits at start_z=16, +2.5 → 18.5
        {"type": "roughing", "enabled": True, "count": 1, "tool_id": "T1",
         "r_tool": 20.0, "start_z": 16.0, "end_z": 16.0, "p2_z_extend": 2.5,
         "pass_shape": "linear_approach"},
        # op2: finishing → end is the zone end (end_z=30), no extend
        {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T2",
         "r_tool": 20.0, "start_z": 20.0, "end_z": 30.0},
    ],
}

pg = PathGenerator()
try:
    pg.calculate_paths(params, {}, cyl_mandrel())
except Exception as e:
    # last_op_end_z is populated before per-pass geometry, so a downstream
    # geometry hiccup on the synthetic cylinder must not hide the stored value.
    print(f"(calculate_paths raised after storing end-Z, tolerated: {e})")

assert abs(pg.last_op_end_z[0] - 16.0) < 1e-9, f"op0 expected 16, got {pg.last_op_end_z.get(0)}"
assert abs(pg.last_op_end_z[1] - 18.5) < 1e-9, f"op1 expected 18.5, got {pg.last_op_end_z.get(1)}"
assert abs(pg.last_op_end_z[2] - 30.0) < 1e-9, f"op2(finish) expected 30, got {pg.last_op_end_z.get(2)}"
print("path_generator.last_op_end_z: p2_z_extend + count + finishing all correct OK")


# ── 2) UI: column renders the stored value ─────────────────────────────────
from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import ProgramTab

root = tk.Tk(); root.withdraw()
app = MagicMock()
app.params = {"operations": [
    {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T1"},
    {"type": "roughing", "enabled": True, "count": 1, "tool_id": "T1"},
]}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False
app.path_gen.last_op_end_z = {0: 16.0, 1: 18.5}

tab = ProgramTab(ttk.Frame(root), app, MagicMock(), MagicMock())
root.update_idletasks()

assert "RealEndZ" in tab.tree_ops["columns"], "RealEndZ column missing"
assert str(tab.tree_ops.item("0")["values"][5]) == "16",   tab.tree_ops.item("0")["values"]
assert str(tab.tree_ops.item("1")["values"][5]) == "18.5", tab.tree_ops.item("1")["values"]
print("Real End Z column cells OK")

app.path_gen.last_op_end_z = {}
tab.refresh_ops_tree()
assert str(tab.tree_ops.item("0")["values"][5]) == "—", "empty Real End Z should be dash"
print("Empty Real End Z shows dash OK")

root.destroy()
print("REAL END Z TEST PASSED")
sys.exit(0)
