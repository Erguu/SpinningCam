"""Widget smoke test for the pass-retract axis-order dropdown.

The engine test proves the move is right. This proves the operator can reach it
on every op type that HAS a retract, that the Z-first warning actually appears
(warn-only is worthless if the warning never renders), and that the dropdown
stores the raw key rather than the translated label.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from i18n import set_language, t
from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import ProgramTab, OP_PARAM_UNIVERSE

root = tk.Tk()
root.withdraw()

app = MagicMock()
app.params = {
    "operations": [
        {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
         "retract_x": 50.0, "retract_z": 50.0},
        {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0202",
         "retract_x": 50.0, "retract_z": 50.0, "retract_motion": "z_first"},
        {"type": "cutting", "enabled": True, "count": 1, "tool_id": "T0303",
         "plunge_start_x": 100.0, "plunge_start_z": 0.0,
         "plunge_end_x": 50.0, "plunge_end_z": 0.0,
         "retract_x": 50.0, "retract_z": 50.0},
        {"type": "point", "enabled": True, "count": 1, "tool_id": "T0303",
         "point_x": 120.0, "point_z": 80.0},
    ],
    "home_x": 300.0, "home_z": 150.0, "roller_positive_x_side": False,
}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False

ui_root = MagicMock()
ui_root.tool_library = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0},
                        {"id": "T0202", "r_tool": 20.0, "radius": 18.0},
                        {"id": "T0303", "r_tool": 0.0, "radius": 10.0}]
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


def _labels():
    out = []
    def walk(w):
        if isinstance(w, (tk.Label, ttk.Label)):
            try:
                out.append(str(w.cget("text")))
            except Exception:
                pass
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return out


def _motion_combo():
    found = []
    def walk(w):
        if isinstance(w, ttk.Combobox) and getattr(w.master, "_pkey", "") == "retract_motion":
            found.append(w)
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return found[0] if found else None


# ── 1. Every op type that HAS a retract offers the order ──────────────────
for i, expect in ((0, True), (1, True), (2, True), (3, False)):
    tab.tree_ops.selection_set(str(i))
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()
    ot = app.params["operations"][i]["type"]
    has = "retract_motion" in _pkeys()
    assert has is expect, f"{ot}: retract_motion field present={has}, expected {expect}"
    # The universe must agree, or it becomes a pickable-but-uneditable column.
    assert ("retract_motion" in OP_PARAM_UNIVERSE[ot]) is expect, ot
print("Retract order shows on roughing/finishing/cutting, not on Point OK")

# ── 2. The Z-first warning actually renders ───────────────────────────────
tab.tree_ops.selection_set("1")          # finishing, retract_motion=z_first
tab.on_op_select(None, _flush=False)
root.update_idletasks()
assert any(t("lbl_retract_zfirst_warn") in l for l in _labels()), \
    "z_first selected but no warning label rendered"

tab.tree_ops.selection_set("0")          # roughing, default
tab.on_op_select(None, _flush=False)
root.update_idletasks()
assert not any(t("lbl_retract_zfirst_warn") in l for l in _labels()), \
    "warning shown for the default (synchronized) mode"
print("Z-first warning appears only for z_first OK")

# ── 3. Choosing z_first re-renders and brings the warning with it ─────────
# (_on_rm calls on_op_select so the operator sees the consequence immediately,
# rather than only after clicking away and back.)
# Done BEFORE the language loop and in a fixed language: a label rendered while
# TR was active keeps its Turkish text after set_language("EN"), so comparing it
# to the English string would fail for a reason that has nothing to do with the
# feature.
set_language("EN")
app.params["operations"][0]["retract_motion"] = "synchronized"
tab.tree_ops.selection_set("0")
tab.on_op_select(None, _flush=False)
root.update_idletasks()
assert not any(t("lbl_retract_zfirst_warn") in l for l in _labels())

cb = _motion_combo()
cb.set(t("opt_point_z_first"))
cb.event_generate("<<ComboboxSelected>>")
root.update_idletasks()
assert any(t("lbl_retract_zfirst_warn") in l for l in _labels()), \
    "picking z_first did not surface the warning without a reselect"
print("Picking z_first surfaces the warning immediately OK")

# ── 4. The dropdown stores the raw key in every language ──────────────────
for lang in ("EN", "TR", "ES"):
    set_language(lang)
    app.params["operations"][0]["retract_motion"] = "x_first"
    tab.tree_ops.selection_set("0")
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()

    cb = _motion_combo()
    assert cb is not None, f"[{lang}] retract motion combobox not found"
    assert cb.get() == t("opt_point_x_first"), (lang, cb.get())

    cb.set(t("opt_point_z_first"))
    cb.event_generate("<<ComboboxSelected>>")
    root.update_idletasks()
    stored = app.params["operations"][0]["retract_motion"]
    assert stored == "z_first", f"[{lang}] stored {stored!r}, expected 'z_first'"
set_language("EN")
print("Retract order stores the raw key in EN/TR/ES OK")

root.destroy()
print("\nAll retract-motion GUI checks passed.")
