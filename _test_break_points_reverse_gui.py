# -*- coding: utf-8 -*-
"""Real-widget tests for break points on a REVERSE pass (2026-08-30).

Two things the engine test next door cannot cover:

  1. `BreakPointsDialog._current_leg` on a reverse pass. The engine drops that
     pass's render split, and the dialog used to fall back to "the whole path is
     the leg" — so the clearance advisory measured the approach arm as well and
     re-bent an array that already carried the breaks. It must now find the real
     exit leg via `last_reverse_split_idx`, or find nothing at all.
  2. The Break Points BUTTON is enabled on a reverse op. That was the complaint
     this work came from, and both the toolbar state and the click handler are
     the single expression `exit_breaks.excluded_reason(op)`.

    runtest.bat _test_break_points_reverse_gui.py
"""
import tkinter as tk

import numpy as np

import i18n
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.dialogs.break_points_dialog import BreakPointsDialog

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


BREAKS = [{"t": 0.35, "angle": -15.0}, {"t": 0.70, "angle": -15.0}]


def make_op(**over):
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
          "clearance": 3.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": "forward",
          "pass_edits": {"0": {"exit_breaks": [dict(b) for b in BREAKS]}}}
    op.update(over)
    return op


class FakeApp:
    def __init__(self, op):
        self.mandrel_mgr = MandrelManager()
        self.mandrel_mgr.create_default_cone()
        self.mandrel_mgr.update_geometry(0, 0, 0, 0.0, 0.0)
        self.path_gen = PathGenerator()
        self.params = {
            "operations": [op],
            "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 0.0,
            "shell_thickness": 0.0,
            "auto_calc_angle": False,
            "min_safety_gap": -999.0,
            "roller_positive_x_side": True,
        }

    def calc(self):
        return self.path_gen.calculate_paths(self.params, {}, self.mandrel_mgr)[0]


root = tk.Tk()
root.withdraw()

# ── 1. forward: the baseline the reverse case must reproduce ───────────────
app_f = FakeApp(make_op())
paths_f = app_f.calc()
dlg_f = BreakPointsDialog(root, app_f, 0, 0, lambda per_pass: None)
leg_f = dlg_f._current_leg()
check(leg_f is not None and len(leg_f) >= 3, "forward: a leg is found")
check(leg_f is not None and len(leg_f) < len(paths_f[0]),
      f"forward: the leg is a subset ({len(leg_f)} of {len(paths_f[0])} pts)")
dlg_f.destroy()

# ── 2. reverse: same leg, found through the remapped split ────────────────
app_r = FakeApp(make_op(direction="reverse"))
paths_r = app_r.calc()
dlg_r = BreakPointsDialog(root, app_r, 0, 0, lambda per_pass: None)
leg_r = dlg_r._current_leg()
check(leg_r is not None and len(leg_r) >= 3, "reverse: a leg is found")
check(leg_r is not None and len(leg_r) < len(paths_r[0]),
      f"reverse: the leg is a subset, NOT the whole path "
      f"({len(leg_r) if leg_r is not None else 0} of {len(paths_r[0])} pts)")
check(leg_r is not None and leg_f is not None
      and leg_r.shape == leg_f.shape and np.allclose(leg_r, leg_f, atol=1e-12),
      "reverse: it is the SAME leg the forward pass hands over")
# T2 → P3, so the leg's last point is where the reverse pass STARTS.
check(leg_r is not None and np.allclose(leg_r[-1], paths_r[0][0], atol=1e-12),
      "reverse: the leg runs T2 -> P3 (ends at the pass start point)")
# The advisory must not throw, whatever it concludes.
try:
    dlg_r._clearance_warning()
    check(True, "reverse: the clearance advisory runs without raising")
except Exception as e:                                     # pragma: no cover
    check(False, f"reverse: clearance advisory raised {e!r}")
dlg_r.destroy()

# ── 3. reverse + a ticked back pass: still one clean pass to measure ──────
# A reverse op builds no back pass at all (#49) — it already IS the return
# stroke — so nothing downstream rebuilds the arrays and the editor can still
# find the leg.
app_b = FakeApp(make_op(direction="reverse", back_pass_enabled=True))
paths_b = app_b.calc()
check(len(paths_b) == 1, f"the ticked back pass is not built ({len(paths_b)} path)")
dlg_b = BreakPointsDialog(root, app_b, 0, 0, lambda per_pass: None)
leg_b = dlg_b._current_leg()
check(leg_b is not None and leg_r is not None
      and leg_b.shape == leg_r.shape and np.allclose(leg_b, leg_r, atol=1e-12),
      "reverse + back pass tick: the same leg is still found")
try:
    dlg_b._clearance_warning()
    check(True, "reverse + back pass tick: the advisory runs without raising")
except Exception as e:                                     # pragma: no cover
    check(False, f"reverse + back pass tick: advisory raised {e!r}")
dlg_b.destroy()

# ── 4. the Break Points BUTTON is enabled on a reverse op ────────────────
# The complaint that started this: "break points button is still disabled in the
# pass table of a reverse pass". pass_table._create_widgets disables it with
# exactly `if _eb.excluded_reason(op)`, and _edit_break_points refuses on the
# same call, so both gates are this one expression.
import exit_breaks as _eb

for _op, _want, _why in (
        (make_op(direction="reverse"), None, "plain reverse op"),
        (make_op(direction="forward"), None, "forward op"),
        (make_op(direction="reverse", pass_shape="spline"), "pass_shape", "spline"),
        (make_op(direction="reverse", exit_mid_radius=50.0), "curl", "curl set")):
    check(_eb.excluded_reason(_op) == _want,
          f"button gate on a {_why}: "
          f"{'enabled' if _want is None else 'disabled (' + _want + ')'}")


root.destroy()
print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
