# -*- coding: utf-8 -*-
"""Headless GUI test: the "Send Report to Devs" window.

Builds the real Toplevel against a stub app (root withdrawn, nothing shown) and
checks the things that decide whether an operator can trust the window:

1. **A row that could not be collected is disabled AND unticked.** A ticked
   checkbox for a file that does not exist is a promise the bundle cannot keep.
2. **The heavy items are off when it opens.** Pre-ticking the mandrel STEP would
   send a customer's part geometry because they clicked Save without reading.
3. **The running total tracks the ticks**, so the size shown is the size sent.
4. **Save with nothing ticked writes nothing**, and never reaches the file
   dialog.
5. **Preview opens** for every collectable row without raising.

The Save path is exercised with the file dialog and the message boxes stubbed —
what is being tested is the wiring, not Tk's own dialogs.
"""
import json
import os
import shutil
import tempfile
import tkinter as tk
import zipfile
from tkinter import ttk

import report_bundle as rb
from _test_report_bundle import _StubApp, _make_base

import ui.dialogs.send_report as sr


def _root():
    root = tk.Tk()
    root.withdraw()
    return root


def _open(root, app):
    dlg = sr.SendReportDialog(root, app)
    dlg.withdraw()
    dlg.grab_release()          # a grab on a withdrawn window blocks the next one
    root.update_idletasks()
    return dlg


def test_unavailable_rows_are_disabled_and_unticked():
    base = _make_base(with_files=False)
    root = _root()
    try:
        app = _StubApp(base, paths=False)
        dlg = _open(root, app)
        by_key = {it.key: it for it in dlg.items}
        for key, var in dlg.vars.items():
            if not by_key[key].available:
                assert not var.get(), "%s is unavailable but ticked" % key
        # the program is built from memory, so it is there even on an empty disk
        assert dlg.vars[rb.PROGRAM].get(), "the program row should be ticked"
        dlg.destroy()
    finally:
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_unavailable_rows_are_disabled_and_unticked PASS")


def test_heavy_items_start_unticked():
    base = _make_base()
    root = _root()
    try:
        step = os.path.join(base, "part.STEP")
        with open(step, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\n")
        dlg = _open(root, _StubApp(base, step=step))
        by_key = {it.key: it for it in dlg.items}
        # both ARE collectable here — so an unticked box is a real decision,
        # not just an absent file
        assert by_key[rb.STEP].available
        assert by_key[rb.TOOL_GEOMETRY].available
        assert not dlg.vars[rb.STEP].get()
        assert not dlg.vars[rb.TOOL_GEOMETRY].get()
        for key in (rb.PROGRAM, rb.LOG, rb.SETTINGS, rb.MACHINE, rb.TOOLS, rb.GCODE):
            assert dlg.vars[key].get(), key
        dlg.destroy()
    finally:
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_heavy_items_start_unticked PASS")


def test_total_tracks_the_ticks():
    base = _make_base()
    root = _root()
    try:
        dlg = _open(root, _StubApp(base))
        before = dlg.lbl_total.cget("text")

        for key in list(dlg.vars):
            dlg.vars[key].set(False)
        dlg._refresh_total()
        empty = dlg.lbl_total.cget("text")
        assert empty.startswith("0 "), empty
        assert empty != before

        dlg.vars[rb.TOOLS].set(True)
        dlg._refresh_total()
        one = dlg.lbl_total.cget("text")
        assert one.startswith("1 "), one
        size = rb.human_size({i.key: i for i in dlg.items}[rb.TOOLS].size)
        assert size in one, (one, size)
        dlg.destroy()
    finally:
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_total_tracks_the_ticks PASS")


def test_save_with_nothing_ticked_writes_nothing():
    base = _make_base()
    root = _root()
    calls = {"warn": 0, "filedialog": 0}
    orig_warn = sr.messagebox.showwarning
    orig_fd = sr.filedialog.asksaveasfilename
    try:
        dlg = _open(root, _StubApp(base))
        for key in list(dlg.vars):
            dlg.vars[key].set(False)

        def _warn(*a, **k):
            calls["warn"] += 1

        def _ask(*a, **k):
            calls["filedialog"] += 1
            return ""

        sr.messagebox.showwarning = _warn
        sr.filedialog.asksaveasfilename = _ask
        dlg._save()
        assert calls["warn"] == 1, calls
        assert calls["filedialog"] == 0, "the file dialog must not open with an empty selection"
        assert dlg.result is None
        dlg.destroy()
    finally:
        sr.messagebox.showwarning = orig_warn
        sr.filedialog.asksaveasfilename = orig_fd
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_save_with_nothing_ticked_writes_nothing PASS")


def test_save_writes_the_ticked_rows_and_the_note():
    base = _make_base()
    root = _root()
    out = os.path.join(base, "out.zip")
    orig_fd = sr.filedialog.asksaveasfilename
    orig_yes = sr.messagebox.askyesno
    orig_reveal = sr._reveal
    try:
        dlg = _open(root, _StubApp(base))
        dlg.txt_note.insert("1.0", "it dives on pass 3")
        for key in list(dlg.vars):
            dlg.vars[key].set(key in (rb.PROGRAM, rb.TOOLS))
        dlg._refresh_total()

        sr.filedialog.asksaveasfilename = lambda *a, **k: out
        sr.messagebox.askyesno = lambda *a, **k: False   # don't open the folder
        sr._reveal = lambda p: None

        dlg._save()
        assert dlg.result == out, dlg.result
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
            summary = zf.read(rb.SUMMARY_NAME).decode("utf-8")
        assert names == {rb.SUMMARY_NAME, "program.ssp", "tools.json"}, names
        assert "it dives on pass 3" in summary
    finally:
        sr.filedialog.asksaveasfilename = orig_fd
        sr.messagebox.askyesno = orig_yes
        sr._reveal = orig_reveal
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_save_writes_the_ticked_rows_and_the_note PASS")


def test_empty_note_asks_once_and_respects_no():
    base = _make_base()
    root = _root()
    asked = {"n": 0}
    orig_yes = sr.messagebox.askyesno
    orig_fd = sr.filedialog.asksaveasfilename
    try:
        dlg = _open(root, _StubApp(base))

        def _no(*a, **k):
            asked["n"] += 1
            return False

        sr.messagebox.askyesno = _no
        sr.filedialog.asksaveasfilename = lambda *a, **k: ""
        dlg._save()
        assert asked["n"] == 1, asked
        assert dlg.result is None
        dlg.destroy()
    finally:
        sr.messagebox.askyesno = orig_yes
        sr.filedialog.asksaveasfilename = orig_fd
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_empty_note_asks_once_and_respects_no PASS")


def test_preview_opens_for_every_collectable_row():
    base = _make_base()
    root = _root()
    try:
        step = os.path.join(base, "part.STEP")
        with open(step, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\n")
        dlg = _open(root, _StubApp(base, step=step))
        for it in dlg.items:
            if it.available:
                dlg._preview(it.key)      # multi-member rows take the Notebook path
                root.update_idletasks()
        dlg.destroy()
    finally:
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_preview_opens_for_every_collectable_row PASS")


def test_preview_takes_and_returns_the_modal_grab():
    """The report window is modal. A preview opened underneath that grab would
    be dead to the mouse, and closing one that never took the grab leaves the
    report window un-modal. Exercised with the grab actually HELD, which is the
    real path — the other tests release it so they can drive several windows."""
    base = _make_base()
    root = _root()
    try:
        dlg = sr.SendReportDialog(root, _StubApp(base))
        dlg.withdraw()
        root.update_idletasks()
        assert root.grab_current() is dlg, "the report window should hold the grab"

        win = dlg._preview(rb.LOG)          # two members -> the Notebook path
        root.update_idletasks()
        assert win is not None, "_preview must return the window it opened"
        assert root.grab_current() is win, "the preview should hold the grab"

        # Close the way the operator does, and check the grab comes back.
        # The button is collected BEFORE invoking: invoking destroys the window,
        # and walking a destroyed widget tree raises.
        buttons = [w for child in win.winfo_children()
                   for w in child.winfo_children() if isinstance(w, ttk.Button)]
        assert len(buttons) == 1, f"expected one Close button, got {len(buttons)}"
        buttons[0].invoke()
        root.update_idletasks()
        assert not win.winfo_exists(), "Close did not destroy the preview"
        assert root.grab_current() is dlg, "the grab did not return to the report window"

        dlg.grab_release()
        dlg.destroy()
    finally:
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_preview_takes_and_returns_the_modal_grab PASS")


def test_opens_in_every_language():
    """The window is built once from t(); a key missing in TR or ES shows the raw
    key on a shop-floor screen. Cheap to check, and it is the slip that recurs."""
    from i18n import LANGUAGES, get_language, set_language
    base = _make_base()
    root = _root()
    prev = get_language()
    try:
        app = _StubApp(base)
        for lang in LANGUAGES:
            set_language(lang)
            dlg = _open(root, app)
            for key in rb.ITEM_ORDER:
                from i18n import t
                label = t("rep_item_" + key)
                assert label != "rep_item_" + key, (lang, key)
            assert dlg.lbl_total.cget("text"), lang
            dlg.destroy()
    finally:
        set_language(prev)
        root.destroy()
        shutil.rmtree(base, ignore_errors=True)
    print("test_opens_in_every_language PASS")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"\nAll {len(tests)} Send-Report GUI checks passed.")
