"""Real-Tk smoke test for the Program End section and the touch-calibration note.

Builds the actual MachineTab against a stub app and drives the checkbox, so the
enable/disable wiring and the label text are exercised rather than assumed.
"""
import types
import tkinter as tk

from i18n import t
from ui.tabs.machine_tab import MachineTab


class Helper:
    """No-op UI helper — the sections under test build their own widgets."""
    def __getattr__(self, name):
        return lambda *a, **k: None


def build(params):
    root = tk.Tk()
    root.withdraw()
    app = types.SimpleNamespace(
        params=params,
        active_machine_profile=None,
        machine_adapter=None,
        changed=[],
    )
    app.on_param_change = lambda k, v, m="none": app.changed.append((k, v))
    tab = MachineTab(tk.Frame(root), app, Helper())
    return root, app, tab


def labels(widget, out=None):
    out = [] if out is None else out
    for w in widget.winfo_children():
        if isinstance(w, tk.Label):
            try: out.append(w.cget("text"))
            except tk.TclError: pass
        labels(w, out)
    return out


BASE = {
    "home_x": -396.0, "home_z": -175.0,
    "calibration_last_session": {
        "entry_x": "270", "entry_z": "190",
        "tool_var": "T0102", "saved_at": "2026-08-01  09:12",
    },
}

# ── 1. calibration note appears, verbatim, twice (Program Start + Program End) ──
root, app, tab = build(dict(BASE))
txt = [l for l in labels(tab.content) if l.startswith(t("lbl_cal_touch"))]
assert len(txt) == 2, f"expected a note under Start and End, got {len(txt)}"
assert "DRO X 270" in txt[0] and "Z 190" in txt[0], txt[0]
assert "T0102" in txt[0] and "2026-08-01" in txt[0], txt[0]
print("  1. note echoes DRO verbatim + tool/date, under both sections:", txt[0])

# ── 2. the numbers are NOT converted (that was the explicit design choice) ─────
assert "-396" not in txt[0] and "-300" not in txt[0], "note must not do CAM math"
print("  2. no conversion applied — raw reading only")

# ── 3. no calibration yet -> honest placeholder, no crash ─────────────────────
root2, _, tab2 = build({"home_x": -396.0, "home_z": -175.0})
assert t("lbl_cal_none") in labels(tab2.content)
print("  3. uncalibrated machine shows placeholder, no crash")

# ── 4. Program End entries seed from Program Start and start disabled ─────────
def find_by_class(w, cls, out=None):
    out = [] if out is None else out
    for c in w.winfo_children():
        if c.winfo_class() == cls:
            out.append(c)
        find_by_class(c, cls, out)
    return out


f_end = [f for f in find_by_class(tab.content, "TLabelframe")
         if str(f.cget("text")) == t("frm_program_end")]
assert len(f_end) == 1, "Program End section not found"
f_end = f_end[0]

entries = find_by_class(f_end, "TEntry")
assert len(entries) == 2, f"expected End X and End Z, got {len(entries)}"
assert all(str(e.cget("state")) == "disabled" for e in entries), \
    "fields must start locked while 'same as start' is ticked"
seeded = sorted(float(tab.content.getvar(e.cget("textvariable"))) for e in entries)
assert seeded == [-396.0, -175.0], seeded
print("  4. End X/Z disabled and pre-filled from Program Start:", seeded)

# ── 5. unticking enables them and records the flag ───────────────────────────
cbs = [c for c in find_by_class(f_end, "TCheckbutton")
       if str(c.cget("text")) == t("chk_end_use_home")]
assert len(cbs) == 1, cbs
cbs[0].invoke()
assert ("end_use_home", False) in app.changed, app.changed
assert all(str(e.cget("state")) == "normal" for e in entries), "fields stayed locked"
print("  5. untick -> end_use_home=False recorded, fields unlocked")

cbs[0].invoke()
assert ("end_use_home", True) in app.changed
assert all(str(e.cget("state")) == "disabled" for e in entries)
print("  6. re-tick -> back to 'same as start' and re-locked")

# ── 7. refresh helper survives destroyed labels ──────────────────────────────
tab._cal_notes[0].destroy()
tab._refresh_cal_notes()
assert len(tab._cal_notes) == 1, tab._cal_notes
print("  7. _refresh_cal_notes drops dead labels instead of raising")

root.destroy(); root2.destroy()
print("\nALL PROGRAM-END GUI CHECKS PASSED")
