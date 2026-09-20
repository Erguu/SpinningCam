"""Widget smoke test for "Start from last" (2026-09-20).

_test_start_from_last.py proves the cut is right. This proves the operator can
FIND it and is TOLD what it does - the bug class that hid "No retract at mandrel
end" behind a 15-character label column until 2026-09-16.

The note matters more here than usual: the box cuts only the FIRST pass, and
someone with a 3-pass operation would reasonably expect all three to move.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

import start_from_last as sfl
from i18n import set_language, t, STRINGS
from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import ProgramTab, OP_PARAM_UNIVERSE

set_language("EN")
root = tk.Tk()
root.withdraw()

app = MagicMock()
app.params = {
    "operations": [
        {"type": "roughing", "enabled": True, "count": 3, "tool_id": "T0101"},  # 0: yes
        {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0101"}, # 1: yes
        # Reverse is excluded: it is stored back-to-front and already ends at
        # the mandrel, so "cut the beginning" would mean something else there.
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "direction": "reverse"},                                              # 2: no
        {"type": "cutting", "enabled": True, "tool_id": "T0101"},              # 3: no
        {"type": "point", "enabled": True, "tool_id": "T0101",
         "point_mode": "absolute"},                                            # 4: no
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


def _box():
    found = []

    def walk(w):
        if (isinstance(w, ttk.Checkbutton)
                and getattr(w.master, "_pkey", "") == sfl.OP_KEY):
            found.append(w)
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return found[0] if found else None


def select(i):
    tab.tree_ops.selection_set(str(i))
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()


# -- 1. shown only where a pass beginning exists to cut -------------------
for i, expect in ((0, True), (1, True), (2, False), (3, False), (4, False)):
    select(i)
    has = sfl.OP_KEY in _pkeys()
    assert has is expect, f"op {i}: box present={has}, expected {expect}"
print("Box shows on forward forming ops only OK")

# -- 2. registered so it is columnable and batch-editable ------------------
assert sfl.OP_KEY in OP_PARAM_UNIVERSE["roughing"]
assert sfl.OP_KEY in OP_PARAM_UNIVERSE["finishing"]
for k in ("cutting", "bending", "point"):
    assert sfl.OP_KEY not in OP_PARAM_UNIVERSE[k], k
print("Registered for roughing and finishing only OK")

# -- 3. off until ticked, and ticking writes the key ----------------------
select(0)
assert sfl.OP_KEY not in app.params["operations"][0], "a default was written on open"
box = _box()
assert box is not None, "tickbox not found"
box.invoke()
root.update_idletasks()
assert app.params["operations"][0][sfl.OP_KEY] is True, "ticking did not write True"
box.invoke()
root.update_idletasks()
assert app.params["operations"][0][sfl.OP_KEY] is False, "unticking did not write False"
print("Off by default; tick writes the key OK")

# -- 4. the FIRST PASS ONLY note is really on screen ----------------------
for lang in ("EN", "TR", "ES"):
    set_language(lang)
    select(0)
    assert t("note_start_from_last") in _texts(), f"{lang}: the note is not on screen"
    assert t("lbl_start_from_last") in _texts(), f"{lang}: the label is not on screen"
set_language("EN")
print("The 'first pass only' note is shown OK")

# -- 5. the 15-character column ------------------------------------------
COL = 15
for lang in ("EN", "TR", "ES"):
    lbl = STRINGS["lbl_start_from_last"][lang]
    assert len(lbl) <= COL, f"{lang} label '{lbl}' is {len(lbl)} chars, column is {COL}"
print("Label fits the 15-character column in every language OK")

root.destroy()
print("All start-from-last widget checks passed.")
