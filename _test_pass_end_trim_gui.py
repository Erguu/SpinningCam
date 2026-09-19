"""Widget smoke test for "Stop short (mm)" (2026-09-20).

_test_pass_end_trim.py proves the trim is right. This proves the operator can
FIND it - the bug class that hid "No retract at mandrel end" behind a
15-character label column until 2026-09-16.

So: the field is reachable exactly where it can act (reverse ops and ops with a
back pass, roughing OR finishing), it is absent everywhere else, the grey
"only on back passes and reverse passes" note is really on screen next to it,
and no label in any language is long enough to be cut.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

import stop_short as ss
from i18n import set_language, t, STRINGS
from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import ProgramTab, OP_PARAM_UNIVERSE, OP_PARAM_DEFAULTS

set_language("EN")
root = tk.Tk()
root.withdraw()

app = MagicMock()
app.params = {
    "operations": [
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "direction": "reverse"},                                          # 0: yes
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "back_pass_enabled": True},                                       # 1: yes
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101"},  # 2: no
        {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0101",
         "direction": "reverse"},                                          # 3: yes
        {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0101"}, # 4: no
        # A reverse op with the back-pass box ticked builds NO back pass (#49),
        # but it is still a reverse pass, so the field belongs there.
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "direction": "reverse", "back_pass_enabled": True},               # 5: yes
        {"type": "cutting", "enabled": True, "tool_id": "T0101",
         "direction": "reverse"},                                          # 6: no
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


def _texts():
    out = []

    def walk(w):
        try:
            txt = w.cget("text")
        except Exception:
            txt = None
        if txt:
            out.append(str(txt))
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return out


def select(i):
    tab.tree_ops.selection_set(str(i))
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()


# -- 1. shown only where there IS an inward stroke -------------------------
for i, expect in ((0, True), (1, True), (2, False), (3, True),
                  (4, False), (5, True), (6, False)):
    select(i)
    has = ss.OP_KEY in _pkeys()
    assert has is expect, f"op {i}: field present={has}, expected {expect}"
print("Field shows on reverse ops and back-pass ops only OK")

# -- 2. in both universes, so it is columnable and batch-editable ----------
assert ss.OP_KEY in OP_PARAM_UNIVERSE["roughing"]
assert ss.OP_KEY in OP_PARAM_UNIVERSE["finishing"]
for k in ("cutting", "bending", "point"):
    assert ss.OP_KEY not in OP_PARAM_UNIVERSE[k], k
assert ss.OP_KEY in OP_PARAM_DEFAULTS, "no faded default hint"
print("Registered for roughing and finishing only OK")

# -- 3. nothing is written just by opening the editor ---------------------
select(0)
assert ss.OP_KEY not in app.params["operations"][0], "a default was written on open"
print("Off until typed OK")

# -- 4. the grey scope note is really on screen beside it -----------------
for lang in ("EN", "TR", "ES"):
    set_language(lang)
    select(0)
    note = t("note_stop_short")
    assert note in _texts(), f"{lang}: the scope note is not on screen"
    assert t("lbl_stop_short") in _texts(), f"{lang}: the label is not on screen"
set_language("EN")
print("The 'only on back passes and reverse passes' note is shown OK")

# -- 5. the 15-character column (the bug that hid No end retract) ----------
COL = 15
for lang in ("EN", "TR", "ES"):
    lbl = STRINGS["lbl_stop_short"][lang]
    assert len(lbl) <= COL, f"{lang} label '{lbl}' is {len(lbl)} chars, column is {COL}"
print("Label fits the 15-character column in every language OK")

root.destroy()
print("All stop-short widget checks passed.")
