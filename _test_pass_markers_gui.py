"""Widget smoke test for the "Emit pass markers" checkbox (2026-09-06).

_test_pass_markers.py proves the recipe is right. This proves the operator can
reach it: that the box is built into the PLC section, that ticking it writes
``plc_pass_markers`` through the normal param path, and that it follows PLC mode
the way the other PLC controls do (a marker option means nothing without a
recipe to put markers in).

Also pins the setting as a MACHINE key — it must survive opening someone else's
program, and .ssp files must not carry it back in.
"""
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

from i18n import set_language, t
from machine_adapter import StandardTwoAxisSpinningAdapter
from machine_loader import MACHINE_PROFILE_KEYS
from ui.tabs.machine_tab import MachineTab

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


set_language("EN")
root = tk.Tk()
root.withdraw()

written = {}

app = MagicMock()
app.params = {"plc_mode": True, "plc_auto_tune": False, "plc_target_lines": 1000,
              "plc_pass_markers": False, "plc_tolerance": 0.5,
              "plc_exit_tolerance": 0.5}
app.active_adapter = StandardTwoAxisSpinningAdapter()
app._calc_running = False
def _on_param_change(key, value, mode="none"):
    written[key] = value
    app.params[key] = value
app.on_param_change = _on_param_change

helper = MagicMock()
helper.bind_tooltip = lambda *a, **k: None
helper.register_param_var = lambda *a, **k: None

frame = ttk.Frame(root)
try:
    tab = MachineTab(frame, app, helper)
    built = True
except Exception as e:      # a broken widget block takes the whole tab with it
    built = False
    print("   tab build raised:", e)
check(built, "the Machine tab still builds with the checkbox in it")


def find_checkbutton(widget, needle):
    """The Checkbutton whose label contains `needle` (case-insensitive)."""
    hits = []
    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, (ttk.Checkbutton, tk.Checkbutton)):
                try:
                    if needle.lower() in str(c.cget("text")).lower():
                        hits.append(c)
                except tk.TclError:
                    pass
            walk(c)
    walk(widget)
    return hits


cb = find_checkbutton(frame, "pass marker")
check(len(cb) == 1, f"exactly one 'pass markers' checkbox exists (found {len(cb)})")

if cb:
    box = cb[0]
    check(str(box.cget("text")) == t("cb_plc_pass_markers"),
          "its label comes from i18n, not a hard-coded string")

    # It must be reachable while PLC mode is on — the state the option is for.
    check(str(box.cget("state")) != "disabled",
          "it is enabled while PLC mode is on")

    box.invoke()
    check(written.get("plc_pass_markers") is True,
          f"ticking it writes plc_pass_markers=True (wrote {written.get('plc_pass_markers')!r})")
    box.invoke()
    check(written.get("plc_pass_markers") is False,
          "un-ticking it writes False again")

# Off by default at BOTH ends: the contract with the PLC is that an unmarked
# recipe is the normal case, so neither a fresh machine profile nor a converter
# constructed without the flag may start emitting markers.
from recipe_to_scl import GCodeToSCLConverter
check(GCodeToSCLConverter().emit_pass_markers is False,
      "the converter defaults to markers OFF")
import re as _re, pathlib as _pl
_main_src = _pl.Path("main.py").read_text(encoding="utf-8")
_default = _re.search(r'"plc_pass_markers":\s*(\w+)', _main_src)
check(_default is not None and _default.group(1) == "False",
      f"the params default is False (found {_default.group(1) if _default else 'nothing'})")

# Machine-level, not program-level: opening another shop's .ssp must not flip it.
check("plc_pass_markers" in MACHINE_PROFILE_KEYS,
      "the setting lives in MACHINE_PROFILE_KEYS, so a .ssp cannot change it")

# Every string it needs must exist in all three languages, or the tab renders
# a raw key at the operator.
import i18n
for key in ("cb_plc_pass_markers", "msg_scl_markers_line", "msg_marker_range"):
    entry = i18n.STRINGS.get(key, {})
    check(all(entry.get(lang) for lang in ("EN", "TR", "ES")),
          f"{key} is translated in EN/TR/ES")

root.destroy()
print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURES")
raise SystemExit(1 if fails else 0)
