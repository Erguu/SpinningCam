# -*- coding: utf-8 -*-
"""Help ▸ Send Report to Devs — build a troubleshooting .zip the operator can send.

The collecting and zipping live in ``report_bundle``; this file is only the
window. Two rules shaped it:

**Nothing leaves without being seen.** Every row shows what it is and how big it
is, and any row can be opened with Preview before it is packed. An operator who
does not trust a support tool will not use it, and one that ships their folder
paths without saying so has earned that.

**The description is the point.** The note box is at the top, focused when the
window opens, and the Save button reminds them once if it is empty. Every file in
the bundle can be reconstructed from other files; the sentence "it dives into the
part on the third pass" cannot.

There is no Send button yet — the bundle is saved to disk and the operator sends
it the way they already talk to the factory (user decision, 2026-09-10). That is
also the only route that works behind a factory firewall, so it stays the primary
one whatever gets added later.
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import report_bundle as rb
from i18n import t
from logger_config import logger
from ui import dialog_sizing

# Why a row is greyed out. Kept short — these are read at a glance, not studied.
_REASON_KEYS = {
    "not_found":       "rep_why_not_found",
    "not_loaded":      "rep_why_not_loaded",
    "no_paths":        "rep_why_no_paths",
    "no_machine_id":   "rep_why_no_machine",
    "save_failed":     "rep_why_failed",
    "generate_failed": "rep_why_failed",
    "empty":           "rep_why_failed",
    "failed":          "rep_why_failed",
}


class SendReportDialog(tk.Toplevel):
    """``result`` is the path written, or None if nothing was saved."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.result = None
        self.title(t("rep_title"))
        self.transient(parent)

        # Button bar first, packed to the bottom (#103) — see dialog_sizing.
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=8, pady=8)

        ttk.Label(self, text=t("rep_intro"), wraplength=560,
                  justify="left", foreground="#446688").pack(
            fill="x", padx=10, pady=(10, 6))

        # --- the note ------------------------------------------------------
        nf = ttk.LabelFrame(self, text=t("rep_note_label"))
        nf.pack(fill="x", padx=10, pady=(0, 8))
        self.txt_note = tk.Text(nf, height=4, wrap="word")
        self.txt_note.pack(fill="x", padx=6, pady=6)
        ttk.Label(nf, text=t("rep_note_hint"), foreground="#777",
                  wraplength=540, justify="left").pack(
            anchor="w", padx=6, pady=(0, 6))

        # --- the file list -------------------------------------------------
        lf = ttk.LabelFrame(self, text=t("rep_items_label"))
        lf.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.items = rb.collect_items(app)
        self.vars = {}
        self._by_key = {it.key: it for it in self.items}

        for it in self.items:
            row = ttk.Frame(lf)
            row.pack(fill="x", padx=6, pady=2)
            var = tk.BooleanVar(value=(it.key in rb.DEFAULT_ON and it.available))
            self.vars[it.key] = var

            cb = ttk.Checkbutton(row, variable=var, command=self._refresh_total,
                                 text=t("rep_item_" + it.key))
            cb.pack(side="left")
            if not it.available:
                cb.state(["disabled"])

            if it.available:
                ttk.Label(row, text=rb.human_size(it.size),
                          foreground="#555", width=9, anchor="e").pack(side="left", padx=(8, 0))
                ttk.Button(row, text=t("rep_preview"), width=10,
                           command=lambda k=it.key: self._preview(k)).pack(side="right")
            else:
                why = t(_REASON_KEYS.get(it.error, "rep_why_failed"))
                ttk.Label(row, text=why, foreground="#aa6600").pack(side="left", padx=(8, 0))

            ttk.Label(row, text=t("rep_hint_" + it.key), foreground="#888",
                      wraplength=300, justify="left").pack(
                side="left", padx=(12, 0))

        # --- always included ------------------------------------------------
        ttk.Label(self, text=t("rep_always"), foreground="#777",
                  wraplength=560, justify="left").pack(
            fill="x", padx=12, pady=(0, 4))

        # --- buttons --------------------------------------------------------
        self.lbl_total = ttk.Label(bar, text="")
        self.lbl_total.pack(side="left")
        ttk.Button(bar, text=t("btn_cancel"), command=self.destroy).pack(side="right")
        ttk.Button(bar, text=t("rep_save"), command=self._save).pack(side="right", padx=6)

        self._refresh_total()
        dialog_sizing.fit(self, 640, 620, parent)
        self.txt_note.focus_set()
        self.grab_set()

    # -- helpers ------------------------------------------------------------

    def _selected_keys(self):
        return [k for k, v in self.vars.items() if v.get()]

    def _selection(self):
        return rb.selected_items(self.items, self._selected_keys())

    def _refresh_total(self):
        sel = self._selection()
        self.lbl_total.config(text=t("rep_total").format(
            n=len(sel), size=rb.human_size(rb.total_size(sel))))

    def _preview(self, key):
        item = self._by_key.get(key)
        if not item or not item.available:
            return
        win = tk.Toplevel(self)
        win.title(t("rep_preview_title").format(name=t("rep_item_" + key)))
        win.transient(self)

        bar = ttk.Frame(win)
        bar.pack(side="bottom", fill="x", padx=6, pady=6)

        # This dialog holds a modal grab, so the preview has to take the grab
        # while it is up and hand it back on close. Without that hand-back the
        # report window is left un-modal behind it, and a second Preview can
        # open on top of the first. Same nesting the pass table uses for its
        # own sub-dialogs (pass_table.py:1019).
        def _close():
            try:
                win.grab_release()
            except tk.TclError:
                pass
            win.destroy()
            try:
                if self.winfo_exists():
                    self.grab_set()
            except tk.TclError:
                pass

        ttk.Button(bar, text=t("btn_close"), command=_close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", _close)

        # One tab per file when an item carries several (the log has two, the
        # machine profile has the live one and the factory template).
        if len(item.members) > 1:
            nb = ttk.Notebook(win)
            nb.pack(fill="both", expand=True, padx=6, pady=6)
            for arc, _ in item.members:
                frm = ttk.Frame(nb)
                nb.add(frm, text=os.path.basename(arc))
                self._fill_text(frm, rb.preview_text(item, arc))
        else:
            self._fill_text(win, rb.preview_text(item))

        dialog_sizing.fit(win, 760, 520, self)
        win.grab_set()
        return win

    @staticmethod
    def _fill_text(master, content):
        frm = ttk.Frame(master)
        frm.pack(fill="both", expand=True, padx=6, pady=6)
        sb = ttk.Scrollbar(frm, orient="vertical")
        sb.pack(side="right", fill="y")
        txt = tk.Text(frm, wrap="none", yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0", content)
        txt.config(state="disabled")

    # -- save ---------------------------------------------------------------

    def _save(self):
        sel = self._selection()
        if not sel:
            messagebox.showwarning(t("rep_title"), t("rep_nothing_selected"), parent=self)
            return

        note = self.txt_note.get("1.0", "end").strip()
        if not note and not messagebox.askyesno(
                t("rep_title"), t("rep_no_note_confirm"), parent=self):
            self.txt_note.focus_set()
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title=t("rep_save_title"),
            defaultextension=".zip",
            initialfile=rb.default_filename(self.app),
            initialdir=_desktop(),
            filetypes=[(t("rep_zip_files"), "*.zip"), (t("fd_all_files"), "*.*")])
        if not path:
            return

        summary = rb.summary_text(self.app, note=note, items=sel)
        try:
            n, size = rb.write_bundle(path, sel, summary)
        except Exception as e:
            logger.error("report bundle failed: %s", e, exc_info=True)
            messagebox.showerror(t("rep_title"),
                                 t("rep_save_failed").format(err=e), parent=self)
            return

        self.result = path
        # Open the containing folder: the next step is attaching this file to a
        # message, and hunting for it is where a support tool loses people.
        if messagebox.askyesno(
                t("rep_saved_title"),
                t("rep_saved").format(name=os.path.basename(path),
                                      n=n, size=rb.human_size(size)),
                parent=self):
            _reveal(path)
        self.destroy()


def _desktop():
    """Where to put it by default. The Desktop is the one folder every operator
    can find again without being told a path."""
    for cand in (os.path.join(os.path.expanduser("~"), "Desktop"),
                 os.path.expanduser("~")):
        if os.path.isdir(cand):
            return cand
    return os.getcwd()


def _reveal(path):
    try:
        os.startfile(os.path.dirname(os.path.abspath(path)))   # noqa: S606
    except Exception as e:
        logger.debug("could not open the report folder: %s", e)
