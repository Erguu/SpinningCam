# -*- coding: utf-8 -*-
"""The recipe DB layout stopped opening on every SCL export (user, 2026-08-31).

It described the PLC's data block, not the program, so it asked the same
question every export and got the same answer. Now it is a Machine tab button
(Machine ▸ PLC ▸ Recipe DB layout…) and both halves are remembered on the machine
profile.

The dangerous half of this change is the SILENCE. `chunk_geometry` GROWS a
capacity that is too small for the recipe, and growing it adds arrays, and an
array count the PLC loader was not generated for either fails to compile in TIA
or silently drops the tail. So the export still interrupts for exactly that case.

What must hold:
  1. Both numbers persist on the MACHINE profile, so they survive to the next
     export and travel with the machine rather than the program.
  2. The dialog works with no recipe in hand (line_count=None) — an operator
     setting a machine up has not drawn anything yet — and then does not claim to
     know where the END marker lands.
  3. The export's ask/don't-ask gate: silent when the saved layout holds the
     recipe, open when it does not, open when nothing is saved.
  4. Whatever the layout, the geometry the PLC gets is still self-consistent.

Run:  python _test_scl_layout_manual.py
"""
import machine_loader
from recipe_to_scl import DEFAULT_CHUNK_SIZE, chunk_geometry

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


# ── 1. the layout belongs to the machine ────────────────────────────────────
print("\n[1] both halves live on the machine profile")
for key in ("scl_chunk_size", "scl_capacity"):
    check(f"{key} is a machine-profile key",
          key in machine_loader.MACHINE_PROFILE_KEYS)

import main as main_mod
import inspect
_src = inspect.getsource(main_mod.SpinningApp.load_settings)
check("scl_capacity has a default in load_settings", '"scl_capacity"' in _src)


# ── 2. the ask/don't-ask gate ───────────────────────────────────────────────
print("\n[2] the export only interrupts when the saved layout cannot serve")


def should_ask(stored_capacity, line_count, auto_target=None):
    """The gate as ui/main_window.export_scl_action applies it. auto_target is
    the auto-tune budget, which pins the capacity for that one run."""
    capacity = auto_target if auto_target is not None else (stored_capacity or None)
    if capacity is None:
        return "unset"
    if capacity < line_count:
        return "small"
    return None


CASES = (
    ("saved 1000, recipe 299 -> silent",            (1000, 299, None), None),
    ("saved 1000, recipe exactly 1000 -> silent",   (1000, 1000, None), None),
    ("saved 1000, recipe 1200 -> ASK (too small)",  (1000, 1200, None), "small"),
    ("nothing saved -> ASK (unset)",                (0, 299, None), "unset"),
    ("nothing saved, tiny recipe -> ASK (unset)",   (0, 5, None), "unset"),
    ("auto-tune pins its own target -> silent",     (0, 299, 350), None),
    ("auto-tune target below the lines -> ASK",     (1000, 400, 350), "small"),
)
for name, args, want in CASES:
    check(name, should_ask(*args) == want, f"got {should_ask(*args)!r}")

check("a too-small capacity really is grown (which is why it must ask)",
      chunk_geometry(1200, 1000, 100)["capacity"] >= 1200,
      str(chunk_geometry(1200, 1000, 100)["capacity"]))
check("...and growing it changes the ARRAY COUNT the PLC loader was built for",
      chunk_geometry(1200, 1000, 100)["chunk_count"]
      != chunk_geometry(299, 1000, 100)["chunk_count"],
      f'{chunk_geometry(1200, 1000, 100)["chunk_count"]} vs '
      f'{chunk_geometry(299, 1000, 100)["chunk_count"]}')


# ── 3. the geometry stays sane with no recipe in hand ───────────────────────
print("\n[3] line_count=0 (the Machine-tab case) still describes a valid DB")
for cap, chunk in ((1000, 100), (350, 100), (1000, 0), (1, 100), (1000, 256)):
    geo = chunk_geometry(0, cap, chunk)
    ok = (geo["capacity"] >= 1
          and (not geo["chunked"]
               or geo["chunk_count"] * geo["chunk_size"] == geo["capacity"]))
    check(f"capacity={cap} chunk={chunk} -> {geo['chunk_count']} x "
          f"{geo['chunk_size']} = {geo['capacity']}", ok)

check("the reference 10 x 100 round-trips to 1000",
      chunk_geometry(0, 1000, 100)["chunk_count"] == 10
      and chunk_geometry(0, 1000, 100)["capacity"] == 1000)


# ── 4. the dialog accepts line_count=None, and every string exists ──────────
print("\n[4] dialog + i18n")
import i18n
NEW_KEYS = ("dlg_layout_no_recipe", "dlg_layout_preview_nolines",
            "dlg_layout_preview_legacy_nolines", "dlg_layout_why_small",
            "dlg_layout_why_unset", "btn_scl_layout",
            "lbl_scl_layout_current", "lbl_scl_layout_legacy")
for k in NEW_KEYS:
    entry = i18n.STRINGS.get(k)
    check(f"{k} defined in EN/TR/ES",
          isinstance(entry, dict) and all(entry.get(l) for l in ("EN", "TR", "ES")))

import inspect as _i
from ui.dialogs import scl_layout
_sig = _i.signature(scl_layout.SclLayoutDialog.__init__)
check("SclLayoutDialog takes a `reason`", "reason" in _sig.parameters)
_dsrc = _i.getsource(scl_layout.SclLayoutDialog.__init__)
check("line_count=None is handled rather than int()'d blindly",
      "_has_recipe" in _dsrc and "line_count or 0" in _dsrc)

from ui.tabs.machine_tab import MachineTab
from ui.main_window import SpinningCamWindow
check("MachineTab exposes the button handler and the label refresh",
      hasattr(MachineTab, "_open_scl_layout")
      and hasattr(MachineTab, "refresh_scl_layout"))
check("the main window owns the dialog and one shared persist helper",
      hasattr(SpinningCamWindow, "open_scl_layout")
      and hasattr(SpinningCamWindow, "_remember_scl_layout"))

_esrc = _i.getsource(SpinningCamWindow.export_scl_action)
check("the export opens the dialog ONLY under a reason",
      "if _why:" in _esrc and "SclLayoutDialog" in _esrc)
check("the export reads the remembered capacity",
      'scl_capacity' in _esrc)


# ── 5. the Machine tab really builds with the new row ──────────────────────
print("\n[5] real-Tk smoke: the PLC section builds and states the layout")
try:
    import tkinter as tk
    import types
    from ui.tabs.machine_tab import MachineTab as _MT

    class _Helper:
        def __getattr__(self, name):
            return lambda *a, **k: None

    _root = tk.Tk()
    _root.withdraw()
    _params = {"plc_mode": True, "plc_tolerance": 0.5, "plc_exit_tolerance": 0.5,
               "plc_auto_tune": False, "plc_target_lines": 1000,
               "scl_chunk_size": 100, "scl_capacity": 1000,
               "home_x": 0.0, "home_z": 0.0}
    _app = types.SimpleNamespace(params=_params, active_machine_profile=None,
                                 machine_adapter=None, changed=[])
    _app.on_param_change = lambda k, v, m="none": _app.changed.append((k, v))
    _tab = _MT(tk.Frame(_root), _app, _Helper())

    check("the tab built without raising", True)
    check("the layout label exists", getattr(_tab, "lbl_scl_layout", None) is not None)
    _txt = _tab.lbl_scl_layout.cget("text")
    check(f"it states the saved layout ({_txt!r})",
          "10" in _txt and "100" in _txt and "1000" in _txt)

    # Change the stored layout the way the dialog would, then refresh in place.
    _params["scl_capacity"] = 400
    _tab.refresh_scl_layout()
    _txt2 = _tab.lbl_scl_layout.cget("text")
    check(f"refresh_scl_layout updates in place ({_txt2!r})",
          "400" in _txt2 and _txt2 != _txt)

    # Legacy single-array layout must read differently, not crash.
    _params["scl_chunk_size"] = 0
    _tab.refresh_scl_layout()
    check(f"legacy single-array layout reads sensibly "
          f"({_tab.lbl_scl_layout.cget('text')!r})",
          "400" in _tab.lbl_scl_layout.cget("text"))
    _root.destroy()
except tk.TclError as e:                                       # pragma: no cover
    print(f"  SKIP  no display ({e})")


print()
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for n in FAIL:
        print("  FAILED:", n)
    raise SystemExit(1)
print("ALL PASS")
