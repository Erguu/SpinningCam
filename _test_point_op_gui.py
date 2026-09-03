"""Widget smoke test for the Point operation editor.

The engine tests (_test_point_op.py) prove the move is right. This one proves
the operator can actually reach it: that "+ Point" is in the Add menu, that
selecting a Point op builds an editor instead of raising, that the fields
present are the Point ones (and the retract fields are NOT), and that the
motion dropdown stores the raw key rather than the translated label — which is
what would silently break a program saved in one language and opened in another.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from i18n import set_language, t
from machine_adapter import StandardTwoAxisSpinningAdapter
from ui.tabs.program_tab import (ProgramTab, OP_PARAM_UNIVERSE,
                                 _DEFAULT_BASIC, _NO_PASS_OP_TYPES)

root = tk.Tk()
root.withdraw()

app = MagicMock()
app.params = {
    "operations": [
        {"type": "roughing", "enabled": True, "count": 3, "tool_id": "T0101"},
        {"type": "point", "enabled": True, "count": 1, "tool_id": "T0303",
         "point_x": 120.0, "point_z": 80.0, "point_motion": "x_first",
         "point_rapid": True},
    ],
    "home_x": 300.0, "home_z": 150.0,
    "roller_positive_x_side": False,
}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False

ui_root = MagicMock()
ui_root.tool_library = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0},
                        {"id": "T0303", "r_tool": 0.0, "radius": 10.0}]
helper = MagicMock()
# Real values, not MagicMocks: the property editor passes these straight to Tk
# as a colour and a font, and Tk rejects a mock's repr with an obscure
# "unknown color name <id>". The toolbar smoke test never opens an editor, so
# it never needed them.
helper.HINT_COLOR = "#888888"
helper.HINT_FONT = ("Arial", 7)

frame = ttk.Frame(root)
tab = ProgramTab(frame, app, ui_root, helper)
root.update_idletasks()

# ── 1. "point" is offered by the adapter and reaches the Add menu ──────────
assert "point" in app.active_adapter.get_available_op_types()
menubuttons = [w for w in tab.frame.winfo_children()[1].winfo_children()
               if isinstance(w, ttk.Menubutton)]
menu = menubuttons[0].nametowidget(menubuttons[0]["menu"])
labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
          if menu.type(i) == "command"]
assert any("Point" in l or "Nokta" in l or "Punto" in l for l in labels), labels
print("Point is in the +Add dropdown OK")

# ── 2. Selecting a Point op builds an editor without raising ───────────────
tab.tree_ops.selection_set("1")
tab.on_op_select(None, _flush=False)
root.update_idletasks()

def _pkeys():
    """Every parameter key the property editor is currently rendering."""
    out = set()
    def walk(w):
        if hasattr(w, "_pkey"):
            out.add(w._pkey)
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return out


pkeys = _pkeys()
for k in ("point_x", "point_z", "point_motion", "point_rapid", "tool_id"):
    assert k in pkeys, f"{k} field missing from the Point editor; got {sorted(pkeys)}"
# No retract, on purpose — it would undo the position the op exists to reach.
assert "retract_x" not in pkeys and "retract_z" not in pkeys, sorted(pkeys)
print("Point editor renders its fields, and no retract fields OK")

# ── 3. The universe matches what the editor actually renders ──────────────
# The standing contract in this file: a key in OP_PARAM_UNIVERSE that the
# editor never renders becomes a column you can pick but cannot edit.
uni = set(OP_PARAM_UNIVERSE["point"])
for k in ("point_x", "point_z", "point_motion", "point_rapid"):
    assert k in uni, f"{k} rendered but missing from OP_PARAM_UNIVERSE['point']"
assert "retract_x" not in uni and "retract_z" not in uni, uni
assert _DEFAULT_BASIC["point"] <= uni, _DEFAULT_BASIC["point"] - uni
print("OP_PARAM_UNIVERSE['point'] agrees with the editor OK")

# ── 4. A Point contributes no pass ────────────────────────────────────────
assert "point" in _NO_PASS_OP_TYPES
assert tab._op_logical_count(app.params["operations"][1]) == 0
assert tab._op_logical_count(app.params["operations"][0]) == 3
print("Point counts as zero passes OK")

# ── 5. The motion dropdown stores the KEY, not the translated label ───────
# A program saved in Turkish must still run when opened in English.
for lang in ("EN", "TR", "ES"):
    set_language(lang)
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()

    combos = []
    def _find(w):
        if isinstance(w, ttk.Combobox) and getattr(w.master, "_pkey", "") == "point_motion":
            combos.append(w)
        for c in w.winfo_children():
            _find(c)
    _find(tab.f_prop_editor)
    assert combos, f"[{lang}] motion combobox not found"

    cb = combos[0]
    # The box shows the translated label for the STORED key...
    assert cb.get() == t("opt_point_x_first"), (lang, cb.get())
    # ...and picking a label writes the raw key back.
    cb.set(t("opt_point_z_first"))
    cb.event_generate("<<ComboboxSelected>>")
    root.update_idletasks()
    stored = app.params["operations"][1]["point_motion"]
    assert stored == "z_first", f"[{lang}] stored {stored!r}, expected 'z_first'"
    app.params["operations"][1]["point_motion"] = "x_first"   # reset for next lang
set_language("EN")
print("Motion dropdown stores the raw key in EN/TR/ES OK")

# ── 6. Adding a Point from the factory gives a usable op ──────────────────
tab.add_op("point", factory=True)
fresh = app.params["operations"][-1]
assert fresh["type"] == "point"
assert fresh["point_x"] == 300.0 and fresh["point_z"] == 150.0, fresh
assert fresh["point_motion"] == "synchronized" and fresh["point_rapid"] is True
print("Factory Point op defaults to Program Start OK")


# ── 7. Reference modes reveal the right fields ────────────────────────────
# Each mode shows a DIFFERENT set of position fields. A mode that leaves a
# stale field on screen invites the operator to fill in a number nothing reads.
set_language("EN")
_MODE_FIELDS = {
    "absolute": {"point_x", "point_z"},
    "surface":  {"point_z", "point_standoff"},
    "relative": {"point_dx", "point_dz"},
    "home":     {"point_dx", "point_dz"},
}
_ALL_POS = {"point_x", "point_z", "point_standoff", "point_dx", "point_dz"}

for mode, expected in _MODE_FIELDS.items():
    app.params["operations"][1]["point_mode"] = mode
    tab.tree_ops.selection_set("1")
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()
    shown = _pkeys() & _ALL_POS
    assert shown == expected, f"{mode}: shows {sorted(shown)}, expected {sorted(expected)}"
    # The mode picker itself is always there, and the universe must cover
    # every field or it becomes a pickable-but-uneditable column.
    assert "point_mode" in _pkeys(), mode
    assert expected <= set(OP_PARAM_UNIVERSE["point"]), mode
print("Each Point mode reveals only its own fields OK")

# ── 8. The mode dropdown stores the raw key, and re-renders on change ─────
def _mode_combo():
    found = []
    def walk(w):
        if isinstance(w, ttk.Combobox) and getattr(w.master, "_pkey", "") == "point_mode":
            found.append(w)
        for c in w.winfo_children():
            walk(c)
    walk(tab.f_prop_editor)
    return found[0] if found else None

for lang in ("EN", "TR", "ES"):
    set_language(lang)
    app.params["operations"][1]["point_mode"] = "absolute"
    tab.tree_ops.selection_set("1")
    tab.on_op_select(None, _flush=False)
    root.update_idletasks()

    cb = _mode_combo()
    assert cb is not None, f"[{lang}] point_mode combobox not found"
    assert cb.get() == t("opt_point_absolute"), (lang, cb.get())

    cb.set(t("opt_point_surface"))
    cb.event_generate("<<ComboboxSelected>>")
    root.update_idletasks()
    stored = app.params["operations"][1]["point_mode"]
    assert stored == "surface", f"[{lang}] stored {stored!r}, expected 'surface'"
    # Picking a mode re-renders immediately: the standoff field is now present.
    assert "point_standoff" in _pkeys(), f"[{lang}] switching mode did not re-render"
set_language("EN")
print("Point mode stores the raw key and re-renders in EN/TR/ES OK")

root.destroy()
print("\nAll Point-op GUI checks passed.")
