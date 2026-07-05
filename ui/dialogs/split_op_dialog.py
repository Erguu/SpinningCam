import tkinter as tk
from tkinter import ttk
from i18n import t


class SplitOpDialog(tk.Toplevel):
    """Visual operation splitter (TODO #64).

    Shows an operation's passes; the operator clicks the dividers BETWEEN passes to carve
    the op into contiguous chunks. ``previews`` is a list of ``{"z":.., "angle":..}`` per
    pass (for orientation). On OK, ``self.result`` is the list of chunk sizes (each >=1,
    summing to the pass count); it is ``None`` on Cancel or when no divider is set.
    """

    def __init__(self, parent, count, previews):
        super().__init__(parent)
        self.title(t("msg_split_title"))
        self.transient(parent)
        self.resizable(False, True)
        self.count = int(count)
        self.previews = previews or []
        self.splits = set()          # split-AFTER pass indices, subset of {0 .. count-2}
        self.result = None

        ttk.Label(self, text=t("split_help"), justify="left",
                  wraplength=340).pack(anchor="w", padx=12, pady=(12, 6))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=12)
        canvas = tk.Canvas(body, width=330, height=340, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        self.rows = ttk.Frame(canvas)
        self.rows.bind("<Configure>",
                       lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rows, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._div_btns = {}
        for i in range(self.count):
            pv = self.previews[i] if i < len(self.previews) else {}
            lbl = f"  Pass {i + 1}"
            if pv.get("z") is not None:
                lbl += f"     Z = {pv['z']:.1f}"
            if pv.get("angle") is not None:
                lbl += f"     ∠ {pv['angle']:.0f}°"
            tk.Label(self.rows, text=lbl, anchor="w", font=("Consolas", 9),
                     bg="#eef3fb").pack(fill="x", pady=(1, 0))
            if i < self.count - 1:
                b = tk.Button(self.rows, relief="flat", bd=0, anchor="w",
                              command=lambda k=i: self._toggle(k))
                b.pack(fill="x")
                self._div_btns[i] = b
                self._paint(i)

        self.summary = ttk.Label(self, text="", font=("Arial", 9, "bold"))
        self.summary.pack(anchor="w", padx=12, pady=(8, 2))

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(bar, text=t("btn_cancel"), command=self._cancel).pack(side="right")
        ttk.Button(bar, text=t("btn_ok"), command=self._ok).pack(side="right", padx=6)

        self._update_summary()
        self.grab_set()
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + 60
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _sizes(self):
        pts = sorted(self.splits)
        sizes, prev = [], 0
        for p in pts:
            sizes.append(p - prev + 1)
            prev = p + 1
        sizes.append(self.count - prev)
        return sizes

    def _toggle(self, k):
        self.splits.discard(k) if k in self.splits else self.splits.add(k)
        self._paint(k)
        self._update_summary()

    def _paint(self, k):
        b = self._div_btns[k]
        if k in self.splits:
            b.config(text="  ✂  ────  split here  ────",
                     fg="#c0392b", bg="#fdecea")
        else:
            b.config(text="  · · · · · · · · · · · · ·",
                     fg="#9aa4b2", bg="#f7f9fc")

    def _update_summary(self):
        sizes = self._sizes()
        self.summary.config(text=t("split_summary").format(
            n=len(sizes), sizes=" · ".join(map(str, sizes))))

    def _ok(self):
        self.result = self._sizes()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
