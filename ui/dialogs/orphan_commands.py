# -*- coding: utf-8 -*-
"""A custom command points at a pass this program does not have — now what?

A "pass" trigger is pinned to a global pass NUMBER, so editing the program list
can leave a command aimed past the end. The engine then just never fires it and
says nothing. For an actuator (a back support that never retracts) that silence
is the whole problem, so exporting stops here and asks.

The choice applies to the generated FILE only — the command table is never
edited behind the user's back.
"""
import tkinter as tk
from tkinter import ttk

from i18n import t
from recipe_explain import ORPHAN_LAST, ORPHAN_SKIP


class OrphanCommandsDialog(tk.Toplevel):
    """Modal. ``result`` is ORPHAN_LAST, ORPHAN_SKIP, or None for cancel."""

    def __init__(self, parent, orphans, total_passes):
        super().__init__(parent)
        self.title(t("orc_title"))
        self.resizable(False, False)
        self.result = None

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text=t("orc_heading"), font=("Arial", 10, "bold"),
                 anchor="w", justify="left").pack(anchor="w")
        tk.Label(frm, text=t("orc_explain").format(n=len(orphans), total=total_passes),
                 justify="left", wraplength=460, fg="#444").pack(anchor="w", pady=(4, 10))

        box = ttk.Frame(frm, relief="solid", borderwidth=1)
        box.pack(fill="x", pady=(0, 12))
        for o in orphans[:8]:
            note = f"  —  {o['note']}" if o.get("note") else ""
            tk.Label(box, text=f"   {o['cmd']}   →   {t('orc_wants').format(n=o['value'])}{note}",
                     anchor="w", justify="left", font=("Consolas", 9),
                     fg="#a00").pack(anchor="w", padx=6, pady=2)
        if len(orphans) > 8:
            tk.Label(box, text=f"   … +{len(orphans) - 8}", anchor="w",
                     fg="#777").pack(anchor="w", padx=6, pady=2)

        # Cancel first in code so it is the Escape/close default, but packed
        # right-to-left so the safe, non-destructive option reads first.
        btns = ttk.Frame(frm)
        btns.pack(fill="x")

        ttk.Button(btns, text=t("orc_btn_cancel"),
                   command=self._cancel).pack(side="right", padx=3)
        ttk.Button(btns, text=t("orc_btn_skip"),
                   command=lambda: self._choose(ORPHAN_SKIP)).pack(side="right", padx=3)
        ttk.Button(btns, text=t("orc_btn_last").format(n=total_passes),
                   command=lambda: self._choose(ORPHAN_LAST)).pack(side="right", padx=3)

        tk.Label(frm, text=t("orc_footer"), font=("Arial", 8, "italic"),
                 fg="gray", justify="left", wraplength=460).pack(anchor="w", pady=(10, 0))

        self.bind("<Escape>", lambda _e: self._cancel())
        self.update_idletasks()
        try:                       # centre on the parent window
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass
        self.grab_set()
        self.wait_window(self)

    def _choose(self, action):
        self.result = action
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
