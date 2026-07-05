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

        body = tk.Text(wrap, width=70, height=16, wrap="word", bg="#0e141b", fg="#dfe6ee",
                       relief="flat", padx=10, pady=8, font=("Segoe UI", 10))
        body.pack(fill="both", expand=True, pady=(8, 8))
        body.tag_config("ver", foreground="#5cc8ff", font=("Segoe UI", 10, "bold"))
        for ver, lines in sections:
            body.insert("end", f"v{ver}\n", "ver")
            for ln in lines:
                body.insert("end", f"   •  {ln}\n")
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
