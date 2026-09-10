# -*- coding: utf-8 -*-
"""Widget smoke test for single-pass mode in the pass table (#105).

single_pass_sync's own rules — and the proof that lifting a pin never moves the
machine — live in _test_single_pass_sync.py. This file checks the half only a
real widget can show:

  * with the setting OFF the dialog behaves exactly as it always did (this is
    the promise the whole feature rests on);
  * with it ON, opening the table lifts the pins into the operation, says so,
    and Ctrl+Z takes it back;
  * a new edit is staged against the OPERATION, not as a pin, so the two
    numbers cannot come back — and [Apply] writes it there;
  * the ✎ staged marker still lands on the column the operator typed into,
    even though the value is staged under a different key;
  * a refused field (Reach under follow-blank) still stages as a pin;
  * a multi-pass op is untouched by any of it.

Run:  runtest.bat _test_single_pass_sync_gui.py
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

import single_pass_sync as sps
from i18n import t
from machine_adapter import StandardTwoAxisSpinningAdapter
from mandrel_analyzer import MandrelManager
from ui.tabs.program_tab import ProgramTab
from ui.dialogs.pass_table import PassTableDialog

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


root = tk.Tk()
root.withdraw()

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])


def make_app(sync, extra_op0=None):
    app = MagicMock()
    app.mandrel_mgr = mgr
    app.gui_pass_overrides = {}
    app.tool_library = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0}]
    app.active_adapter = StandardTwoAxisSpinningAdapter()
    app._calc_running = False
    op0 = {"type": "roughing", "enabled": True, "name": "Single", "count": 1,
           "tool_id": "T0101", "direction": "forward", "pass_shape": "linear_approach",
           "r_tool": 25.0, "clearance": 1.0, "p1_x": 40.0, "p1_z": 50.0,
           "p3_x": 30.0, "p3_z": -25.0, "start_z": min_z + 10, "end_z": min_z + 40,
           "pass_angle": 20.0, "reach": 40.0, "feed": 300.0,
           "pass_edits": {"0": {"clearance": 0.5}}}
    op0.update(extra_op0 or {})
    app.params = {
        "operations": [
            op0,
            # A four-pass op, so "nothing happens to multi-pass ops" is checked
            # against a real neighbour rather than a hypothetical.
            {"type": "roughing", "enabled": True, "name": "Many", "count": 4,
             "tool_id": "T0101", "direction": "forward", "pass_shape": "linear_approach",
             "r_tool": 25.0, "clearance": 1.0, "p1_x": 40.0, "p1_z": 50.0,
             "p3_x": 30.0, "p3_z": -25.0, "start_z": min_z + 10, "end_z": min_z + 40,
             "pass_angle": 20.0, "reach": 40.0, "feed": 300.0,
             "pass_edits": {"0": {"clearance": 0.5}}},
        ],
        "single_pass_op_sync": sync,
        "blank_radius": 0.0, "target_clearance": 0.0, "min_safety_gap": -999.0,
        "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
        "auto_calc_angle": False,
    }
    helper = MagicMock()
    helper.HINT_COLOR = "#9a9a9a"
    helper.HINT_FONT = ("Arial", 7)
    frame = ttk.Frame(root)
    tab = ProgramTab(frame, app, MagicMock(), helper)
    root.update_idletasks()
    return app, tab


# ── 1. OFF = today's behaviour, exactly ─────────────────────────────────────
print("\n[1] setting OFF — nothing changes")
app, tab = make_app(sync=False)
dlg = PassTableDialog(root, app, tab, 0)
root.update_idletasks()
op = app.params["operations"][0]
check("dialog does not enter single-pass mode", dlg._sync is False)
check("the pin is left exactly where it was",
      sps.pass_slot(op) == {"clearance": 0.5}, str(sps.pass_slot(op)))
check("operation Clearance untouched", op["clearance"] == 1.0)
check("the old help text is shown", dlg._sync_notes == [])
dlg._stage(0, "clearance", 0.25)
check("an edit still stages as a PIN",
      dlg.staged == {0: {"clearance": 0.25}} and dlg.staged_op == {})
dlg.staged = {}
dlg.destroy()

# ── 2. ON — the lift happens at open, and undo takes it back ────────────────
print("\n[2] setting ON — the two numbers become one")
app, tab = make_app(sync=True)
op = app.params["operations"][0]
dlg = PassTableDialog(root, app, tab, 0)
root.update_idletasks()
check("dialog enters single-pass mode", dlg._sync is True)
check("the pass value moved into the operation", op["clearance"] == 0.5, str(op["clearance"]))
check("the pin is gone", "pass_edits" not in op, str(op.get("pass_edits")))
check("the footer says what happened",
      any(t("sps_note_merged").split("{")[0] in n for n in dlg._sync_notes),
      str(dlg._sync_notes))
check("[Apply] is still disabled (the lift is not a staged edit)",
      str(dlg.btn_apply["state"]) == "disabled")

# The lift went through the program tab's undo stack, so Ctrl+Z restores the
# pin — an automatic mutation the operator cannot reverse would be worse than
# the confusion it removes.
check("the lift pushed exactly one undo step", tab._op_undo.can_undo)
tab.undo_op_action()
root.update_idletasks()
op = app.params["operations"][0]
check("undo brings the pin back", sps.pass_slot(op) == {"clearance": 0.5},
      str(sps.pass_slot(op)))
check("undo restores the operation value", op["clearance"] == 1.0)
dlg.destroy()

# ── 3. ON — new edits go to the operation, not into a new pin ──────────────
print("\n[3] setting ON — a new edit cannot recreate the second number")
app, tab = make_app(sync=True)
op = app.params["operations"][0]
dlg = PassTableDialog(root, app, tab, 0)
root.update_idletasks()
dlg._stage(0, "clearance", 0.25)
check("clearance stages against the operation",
      dlg.staged_op == {"clearance": 0.25} and dlg.staged == {})
dlg._stage(0, "target_z", 44.0)
check("anchor Z stages against Zone Start Z",
      dlg.staged_op.get("start_z") == 44.0)
# The preview must show the staged numbers, or the operator is editing blind.
# refresh() is what every real edit path (double-click, Set all) calls once the
# value is staged, so the button state and the table are checked after it.
dlg.refresh()
check("[Apply] is enabled by a staged operation edit",
      str(dlg.btn_apply["state"]) == "normal")
row0 = dlg._last_rows[0]
check("the table previews the staged operation values",
      abs(float(row0["clr"]) - 0.25) < 1e-9 and abs(float(row0["anchor"]) - 44.0) < 1e-9,
      f"clr={row0['clr']} anchor={row0['anchor']}")
check("the ✎ marker lands on the column that was typed into",
      "✎" in str(dlg.tree.set("0", "clr")) and "✎" in str(dlg.tree.set("0", "anchor")),
      f"clr={dlg.tree.set('0', 'clr')!r} anchor={dlg.tree.set('0', 'anchor')!r}")

dlg._apply()
root.update_idletasks()
op = app.params["operations"][0]
check("Apply wrote the operation fields",
      op["clearance"] == 0.25 and op["start_z"] == 44.0,
      f"clr={op['clearance']} start_z={op['start_z']}")
check("Apply created NO pin", "pass_edits" not in op, str(op.get("pass_edits")))
check("staging is cleared", dlg.staged_op == {} and dlg.staged == {})
dlg.destroy()

# ── 4. ON — a refused field still becomes a pin ─────────────────────────────
print("\n[4] setting ON — the refusals still behave like pins")
app, tab = make_app(sync=True, extra_op0={"reach_follow_blank": True,
                                          "pass_edits": {}})
app.params["blank_radius"] = 220.0
op = app.params["operations"][0]
dlg = PassTableDialog(root, app, tab, 0)
root.update_idletasks()
dlg._stage(0, "reach", 61.0)
check("Reach under follow-blank stages as a PIN, not on the operation",
      dlg.staged == {0: {"reach": 61.0}} and "reach" not in dlg.staged_op)
check("...while Clearance beside it still goes to the operation",
      (dlg._stage(0, "clearance", 0.25), dlg.staged_op == {"clearance": 0.25})[1])
dlg.staged, dlg.staged_op = {}, {}
dlg.destroy()

# A refused pin already on the op is reported rather than silently left behind.
app, tab = make_app(sync=True, extra_op0={"reach_follow_blank": True,
                                          "pass_edits": {"0": {"reach": 61.0}}})
app.params["blank_radius"] = 220.0
dlg = PassTableDialog(root, app, tab, 0)
root.update_idletasks()
check("the refusal is explained in the footer",
      t("sps_block_follow") in "  ".join(dlg._sync_notes), str(dlg._sync_notes))
check("the refused pin is still on the pass",
      sps.pass_slot(app.params["operations"][0]) == {"reach": 61.0})
dlg.destroy()

# ── 5. ON — multi-pass ops are not touched ──────────────────────────────────
print("\n[5] setting ON — a multi-pass op is a normal pass table")
app, tab = make_app(sync=True)
dlg = PassTableDialog(root, app, tab, 1)      # the 4-pass op
root.update_idletasks()
op1 = app.params["operations"][1]
check("multi-pass op does not enter single-pass mode", dlg._sync is False)
check("its pin is untouched", sps.pass_slot(op1) == {"clearance": 0.5})
dlg._stage(2, "clearance", 0.25)
check("its edits still stage as pins",
      dlg.staged == {2: {"clearance": 0.25}} and dlg.staged_op == {})
dlg.staged = {}
dlg.destroy()


# ── 6. the Process-tab checkbox is really wired ─────────────────────────────
print("\n[6] the setting exists on the Process tab and writes the param")
import types

from ui.helpers_ui import UIHelper
from ui.tabs.process_tab import ProcessTab


def _walk_checkbuttons(w):
    for c in w.winfo_children():
        if isinstance(c, (tk.Checkbutton, ttk.Checkbutton)):
            yield c
        yield from _walk_checkbuttons(c)


written = {}
papp = types.SimpleNamespace()
papp.params = {"show_deformed_blank": True, "show_blank_edge": True,
               "deformed_blank_offset": 0.0, "shell_thickness": 0.0,
               "operations": [], "pass_colors": {}, "single_pass_op_sync": False}
noop = lambda *a, **k: None
papp.update_deformed_blank = noop
papp.update_blank_edge = noop
papp.save_settings_json = noop
papp.update_scene = noop
papp.on_param_change = lambda k, v, *a, **kw: written.__setitem__(k, v)
ui_root = types.SimpleNamespace(load_step_prompt=noop, run_sim=noop, stop_sim=noop,
                                ui_program=types.SimpleNamespace(refresh_ops_tree=noop))
ptab = ProcessTab(tk.Frame(root), papp, ui_root, UIHelper(tk.Label(root)))
root.update_idletasks()

boxes = [c for c in _walk_checkbuttons(ptab.content)
         if str(c.cget("text")) == t("cb_single_pass_sync")]
check("the checkbox is built on the Process tab", len(boxes) == 1, f"{len(boxes)} found")
if boxes:
    boxes[0].invoke()
    check("ticking it writes single_pass_op_sync=True",
          written.get("single_pass_op_sync") is True, str(written))
    boxes[0].invoke()
    check("unticking it writes False again",
          written.get("single_pass_op_sync") is False, str(written))


print(f"\n{'='*66}\n  {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for n in FAIL:
        print(f"    FAILED: {n}")
root.destroy()
raise SystemExit(1 if FAIL else 0)
