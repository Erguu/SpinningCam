# -*- coding: utf-8 -*-
"""Recipe check — "Why is my pass weird?" (Tools menu).

One list of every value in the program that did NOT come from the operation
panel: per-pass pins that override the operation setting, old-style hidden
overrides, negative clearances, gouge-risk roller reach, leftover data, and the
per-pass warnings the resolver already produces.

The point is discoverability. A stray pin on one field of one pass is invisible
in the editor panel and only row-level in the pass table, so operators (and the
people they ask for help) burn time hunting it. This window points straight at
it, in plain language, and jumps to the operation.

Read-only: nothing here writes params or touches a toolpath. All analysis lives
in recipe_explain.py (pure, headless-testable, shared with explain.py).
"""
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

from i18n import t
from logger_config import logger
from recipe_explain import audit_operations, format_report

# Row marker per severity — colour alone is not enough (projectors, colour
# blindness, and the copied text report has no colour at all).
SEV_MARK = {"error": "‼", "hidden": "◆", "warn": "!", "info": ""}


class RecipeAuditDialog(tk.Toplevel):
    def __init__(self, parent, app, program_tab=None):
        super().__init__(parent)
        self.app = app
        self.ptab = program_tab
        self.findings = []
        self.title(t("dlg_recipe_audit"))
        self.geometry("1000x560")
        self.transient(parent)

        tk.Label(self, text=t("rx_help"), anchor="w", justify="left",
                 fg="#446688", wraplength=960).pack(fill="x", padx=8, pady=(8, 2))

        cols = ("sev", "op", "pas", "msg")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, (label, w, stretch) in {
            "sev": (t("rx_col_sev"), 34, False),
            "op":  (t("rx_col_op"), 210, False),
            "pas": (t("rx_col_pass"), 52, False),
            "msg": (t("rx_col_msg"), 640, True),
        }.items():
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, stretch=stretch,
                             anchor="w" if c in ("op", "msg") else "center")
        # Severity styling. 'hidden' (a hand-set value that breaks the operation's
        # own pattern) is what people open this window to find, so it is red and
        # bold like a real error — the amber advisories must not compete with it.
        _base = tkfont.nametofont("TkDefaultFont")
        _bold = tkfont.Font(family=_base.cget("family"), size=_base.cget("size"),
                            weight="bold")
        self.tree.tag_configure("error", foreground="#a00000", background="#ffe0dc",
                                font=_bold)
        self.tree.tag_configure("hidden", foreground="#c01000", background="#ffecea",
                                font=_bold)
        self.tree.tag_configure("warn", foreground="#8a4b00", background="#fff6e0")
        self.tree.tag_configure("info", foreground="#667788")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="top", fill="both", expand=True, padx=(6, 0), pady=6)
        sb.place(relx=1.0, rely=0.0, anchor="ne")   # keeps the tree flush left
        self.tree.bind("<Double-1>", lambda e: self._goto())

        self.lbl_foot = tk.Label(self, anchor="w", justify="left", fg="#446688")
        self.lbl_foot.pack(fill="x", padx=8)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=6)
        ttk.Button(bar, text=t("btn_refresh"), command=self.refresh).pack(side="left", padx=2)
        ttk.Button(bar, text=t("rx_btn_goto"), command=self._goto).pack(side="left", padx=2)
        ttk.Button(bar, text=t("rx_btn_copy"), command=self._copy).pack(side="right", padx=2)

        self.refresh()

    def refresh(self):
        mgr = getattr(self.app, "mandrel_mgr", None)
        if mgr is not None and not getattr(mgr, "props", None):
            mgr = None
        try:
            self.findings = audit_operations(
                self.app.params, mgr,
                gui_overrides=getattr(self.app, "gui_pass_overrides", None),
                tools=getattr(self.app, "tool_library", None))
        except Exception as e:
            logger.error(f"recipe audit failed: {e}")
            self.findings = []
        self.tree.delete(*self.tree.get_children())
        for n, f in enumerate(self.findings):
            op_txt = "" if f.get("op") is None else \
                f"#{f['op'] + 1}  {f.get('op_name') or ''}".strip()
            self.tree.insert("", "end", iid=str(n), tags=(f["sev"],),
                             values=(SEV_MARK.get(f["sev"], ""), op_txt,
                                     f.get("pass") or "", f["msg"]))
        # Lead with the count that matters, not the total: a program full of
        # deliberate ramps produces many info lines and zero real problems.
        n_hot = sum(1 for f in self.findings if f["sev"] in ("error", "hidden"))
        if n_hot:
            foot = [t("rx_count_hot").format(n=n_hot, total=len(self.findings))]
            self.lbl_foot.config(fg="#c01000")
        elif self.findings:
            foot = [t("rx_count").format(n=len(self.findings))]
            self.lbl_foot.config(fg="#446688")
        else:
            foot = [t("rx_none")]
            self.lbl_foot.config(fg="#446688")
        if mgr is None:
            foot.append(t("rx_no_mandrel"))
        self.lbl_foot.config(text="   •   ".join(foot))
        # Put the first serious finding in view and selected.
        hot = next((str(n) for n, f in enumerate(self.findings)
                    if f["sev"] in ("error", "hidden")), None)
        if hot is not None:
            self.tree.selection_set(hot)
            self.tree.see(hot)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return self.findings[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _goto(self):
        """Select the offending operation in the program tab."""
        f = self._selected()
        if not f or f.get("op") is None or self.ptab is None:
            return
        try:
            iid = self.ptab.tree_ops.get_children()[f["op"]]
            self.ptab.tree_ops.selection_set(iid)
            self.ptab.tree_ops.see(iid)
            self.ptab.on_op_select(None)
        except Exception as e:
            logger.debug(f"audit goto skipped: {e}")

    def _copy(self):
        txt = format_report(self.findings)
        try:
            self.clipboard_clear()
            self.clipboard_append(txt)
            messagebox.showinfo(t("dlg_recipe_audit"), t("rx_copied"), parent=self)
        except Exception as e:
            logger.error(f"clipboard copy failed: {e}")
