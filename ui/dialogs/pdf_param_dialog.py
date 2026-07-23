# -*- coding: utf-8 -*-
"""Export-time PDF parameter picker (#88).

Shown when the user exports a PDF: a flat checkbox list of every parameter used
by the program's operations, so they choose what the PDF's "Operation Parameters"
section lists. The last selection is remembered by the caller (a global setting),
so a repeat export is just OK. ``result`` is the chosen list of keys, or None if
the user cancelled (export should be aborted).
"""
import tkinter as tk
from tkinter import ttk

from i18n import t


class PdfParamDialog(tk.Toplevel):
    def __init__(self, parent, all_keys, selected):
        super().__init__(parent)
        self.result = None
        self._vars = {}
        self.title(t("pdfsel_title"))
        self.transient(parent)

        # None or empty saved selection -> everything ticked (first-run default).
        sel = set(selected) if selected else set(all_keys)

        ttk.Label(self, text=t("pdfsel_info"), wraplength=340, justify="left",
                  foreground="#555").pack(fill="x", padx=10, pady=(10, 6))

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(outer, highlightthickness=0, width=320, height=320)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))

        def _mw(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _mw))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        for k in all_keys:
            v = tk.BooleanVar(value=(k in sel))
            self._vars[k] = v
            ttk.Checkbutton(body, text=k, variable=v).pack(anchor="w", padx=4, pady=1)

        fbtn = ttk.Frame(self)
        fbtn.pack(fill="x", padx=10, pady=(6, 0))
        ttk.Button(fbtn, text=t("pdfsel_all"), command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(fbtn, text=t("pdfsel_none"), command=lambda: self._set_all(False)).pack(side="left", padx=4)

        fok = ttk.Frame(self)
        fok.pack(fill="x", padx=10, pady=10)
        ttk.Button(fok, text=t("pdfsel_cancel"), command=self._cancel).pack(side="right")
        ttk.Button(fok, text=t("pdfsel_ok"), command=self._ok).pack(side="right", padx=(0, 4))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.geometry("380x470")
        try:
            self.grab_set()
        except Exception:
            pass
        self.wait_window(self)

    def _set_all(self, val):
        for v in self._vars.values():
            v.set(val)

    def _ok(self):
        self.result = [k for k, v in self._vars.items() if v.get()]
        self._close()

    def _cancel(self):
        self.result = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
