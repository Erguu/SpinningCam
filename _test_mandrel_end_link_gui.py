"""Widget smoke test for "No retract at mandrel end" (2026-09-16).

_test_mandrel_end_link.py proves the moves are right. This proves the operator
can reach the option ONLY where it means something (reverse roughing ops and
roughing ops with a back pass), that it is off until ticked, that ticking writes
the op key, and that the "Max link" field appears with it.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

import mandrel_end_link as mel
from i18n import set_language
from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import ProgramTab, OP_PARAM_UNIVERSE

set_language("EN")
root = tk.Tk()
root.withdraw()

app = MagicMock()
app.params = {
    "operations": [
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "direction": "reverse"},                                           # 0: eligible
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "back_pass_enabled": True},                                        # 1: eligible
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101"},   # 2: no
        {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0101",
         "direction": "reverse"},                                           # 3: no
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "direction": "reverse", "back_pass_enabled": True},                # 4: eligible (reverse)
    ],
    "home_x": 300.0, "home_z": 150.0, "auto_calculate_paths": False,
}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False

ui_root = MagicMock()
ui_root.tool_library = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0}]
helper = MagicMock()
helper.HINT_COLOR = "#888888"
helper.HINT_FONT = ("Arial", 7)

frame = ttk.Frame(root)
tab = ProgramTab(frame, app, ui_root, helper)
root.update_idletasks()


def _pkeys():
    out = set()

    def walk(w):
        if hasattr(w, "_pkey"):
            out.add(w._pkey)
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return out


def _flag_box():
    found = []

    def walk(w):
        if isinstance(w, ttk.Checkbutton) and getattr(w.master, "_pkey", "") == mel.OP_FLAG_KEY:
            found.append(w)
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return found[0] if found else None


def select(i):
    tab.tree_ops.selection_set(str(i))
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()


# ── 1. shown only where passes end at the mandrel ─────────────────────────
for i, expect in ((0, True), (1, True), (2, False), (3, False), (4, True)):
    select(i)
    has = mel.OP_FLAG_KEY in _pkeys()
    assert has is expect, f"op {i}: tickbox present={has}, expected {expect}"
print("Tickbox shows on reverse / back-pass roughing ops only OK")

# ── 2. both keys are in the roughing universe (columns, batch edit) ───────
assert mel.OP_FLAG_KEY in OP_PARAM_UNIVERSE["roughing"]
assert mel.OP_MAX_KEY in OP_PARAM_UNIVERSE["roughing"]
assert mel.OP_FLAG_KEY not in OP_PARAM_UNIVERSE["finishing"]
print("Both keys are roughing parameters OK")

# ── 3. off by default, max field hidden; ticking writes the key + shows max ─
select(0)
box = _flag_box()
assert box is not None, "tickbox not found"
assert mel.OP_FLAG_KEY not in app.params["operations"][0], "a default was written on open"
assert mel.OP_MAX_KEY not in _pkeys(), "max field shown while the option is off"
box.invoke()
root.update_idletasks()
assert app.params["operations"][0][mel.OP_FLAG_KEY] is True, "ticking did not write True"
assert mel.OP_MAX_KEY in _pkeys(), "max field did not appear after ticking"
box = _flag_box()
assert box is not None and box.instate(["selected"]), "tickbox not shown ticked after rebuild"
box.invoke()
root.update_idletasks()
assert app.params["operations"][0][mel.OP_FLAG_KEY] is False, "unticking did not write False"
assert mel.OP_MAX_KEY not in _pkeys(), "max field still shown after unticking"
print("Off by default; tick writes the key and shows Max link; untick hides it OK")

root.destroy()
print("\nAll mandrel-end link GUI checks passed.")
