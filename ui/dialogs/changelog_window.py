"""Startup 'What's New' dialog (TODO: changelog-on-version-change).

Shows the changelog entries for versions the operator hasn't seen yet, with a
'Don't show again' checkbox and a Confirm button. ``on_confirm(dont_show: bool)`` is
invoked when the user confirms so the caller can persist the seen version.
"""
import tkinter as tk
from i18n import t


class ChangelogWindow(tk.Toplevel):
    def __init__(self, master, current_version, sections, on_confirm):
        super().__init__(master)
        self.on_confirm = on_confirm
        self.title(t("changelog_title").format(v=current_version))
        self.configure(bg="#1b232e")
        self.resizable(False, False)
        self.transient(master)

        wrap = tk.Frame(self, bg="#1b232e")
        wrap.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(wrap, text=t("changelog_heading").format(v=current_version),
                 bg="#1b232e", fg="#eaeaea", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        # Text + scrollbar in their own frame: a release with many entries (or a
        # user who skipped several versions) overflows the box, and without a
        # visible bar the entries below the fold are simply never found.
        f_body = tk.Frame(wrap, bg="#1b232e")
        f_body.pack(fill="both", expand=True, pady=(8, 8))
        body = tk.Text(f_body, width=70, height=25, wrap="word", bg="#0e141b", fg="#dfe6ee",
                       relief="flat", padx=10, pady=8, font=("Segoe UI", 10))
        sb = tk.Scrollbar(f_body, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        body.pack(side="left", fill="both", expand=True)
        # The Text is disabled (read-only), which also stops it taking focus, so
        # bind the wheel on the window rather than relying on focus-follows.
        self.bind("<MouseWheel>", lambda e: body.yview_scroll(int(-e.delta / 120), "units"))
        # An entry is either a plain string (legacy — rendered as one bullet, the
        # way every version up to 1.010 was written) or a (title, body, where)
        # tuple, where the last two are optional. The tuple form is typeset in
        # three weights so the operator can skim the bold titles alone and read
        # the grey detail only for the change they care about.
        # lmargin2 gives every style a HANGING indent: wrapped lines line up
        # under the text instead of falling back to the left edge.
        body.tag_config("ver", foreground="#5cc8ff", font=("Segoe UI", 10, "bold"),
                        spacing1=4, spacing3=4)
        body.tag_config("title", foreground="#ffffff", font=("Segoe UI", 10, "bold"),
                        lmargin1=14, lmargin2=30, spacing1=8, spacing3=2)
        body.tag_config("detail", foreground="#c9d4e0", font=("Segoe UI", 10),
                        lmargin1=30, lmargin2=30, spacing3=2)
        body.tag_config("where", foreground="#8fa3b8", font=("Segoe UI", 9),
                        lmargin1=30, lmargin2=42, spacing3=2)
        body.tag_config("legacy", lmargin1=14, lmargin2=30, spacing3=3)
        for ver, lines in sections:
            body.insert("end", f"v{ver}\n", "ver")
            for ln in lines:
                if isinstance(ln, str):
                    body.insert("end", f"•  {ln}\n", "legacy")
                    continue
                title, detail, where = (list(ln) + ["", ""])[:3]
                body.insert("end", f"•  {title}\n", "title")
                if detail:
                    body.insert("end", f"{detail}\n", "detail")
                if where:
                    body.insert("end", f"▸ {where}\n", "where")
            body.insert("end", "\n")
        body.config(state="disabled")

        self._dont = tk.BooleanVar(value=False)
        row = tk.Frame(wrap, bg="#1b232e")
        row.pack(fill="x")
        tk.Checkbutton(row, text=t("changelog_dont_show"), variable=self._dont,
                       bg="#1b232e", fg="#cfd6de", selectcolor="#0e141b",
                       activebackground="#1b232e", activeforeground="#ffffff").pack(side="left")
        tk.Button(row, text=t("changelog_confirm"), command=self._confirm,
                  bg="#2d7d46", fg="white", relief="flat", padx=18, pady=4).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._confirm)
        self.after(50, self._center)
        try:
            self.grab_set()
        except Exception:
            pass

    def _center(self):
        self.update_idletasks()
        try:
            m = self.master
            x = m.winfo_rootx() + (m.winfo_width() - self.winfo_width()) // 2
            y = m.winfo_rooty() + (m.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

    def _confirm(self):
        dont = bool(self._dont.get())
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self.on_confirm:
            self.on_confirm(dont)
