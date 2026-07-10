import tkinter as tk
from tkinter import ttk
from i18n import t


class UniteResolveDialog(tk.Toplevel):
    """Interactive conflict resolver for Unite (#85).

    When the operations being united carry conflicting field values, this dialog lists
    each conflict and lets the operator pick how it is resolved (First / Last / Average,
    or Ramp for the fields that vary across passes). ``conflicts`` is the list built by
    ``ProgramTab._unite_conflicts`` — each item is ``{"key", "label", "options":[{"label",
    "patch"}...]}`` with options[0] the default. On OK, ``self.result`` is a dict mapping
    each conflict key to the chosen option index; it is ``None`` on Cancel.

    ``reorder_count`` > 0 warns that intervening operations will be moved; ``span`` is the
    (start_z, end_z) of the united op for an orientation line; ``approx`` shows a note when
    the merge is not exact but no per-field choices were surfaced.
    """

    def __init__(self, parent, conflicts, reorder_count, span, approx):
        super().__init__(parent)
        self.title(t("msg_unite_title"))
        self.transient(parent)
        self.resizable(False, True)
        self.conflicts = conflicts or []
        self.result = None
        self._combos = {}

        ttk.Label(self, text=t("unite_resolve_help"), justify="left",
                  wraplength=420).pack(anchor="w", padx=12, pady=(12, 6))

        if reorder_count and reorder_count > 0:
            tk.Label(self, text=t("unite_resolve_reorder").format(k=reorder_count),
                     justify="left", wraplength=420, fg="#c0392b", bg="#fdecea",
                     anchor="w").pack(fill="x", padx=12, pady=(0, 6))

        try:
            a, b = span
            ttk.Label(self, text=t("unite_resolve_span").format(
                a=_fmt(a), b=_fmt(b)), font=("Arial", 9, "bold")).pack(
                anchor="w", padx=12, pady=(0, 6))
        except Exception:
            pass

        if self.conflicts:
            body = ttk.Frame(self)
            body.pack(fill="both", expand=True, padx=12)
            canvas = tk.Canvas(body, width=430, height=260, highlightthickness=0)
            vsb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
            rows = ttk.Frame(canvas)
            rows.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=rows, anchor="nw")
            canvas.configure(yscrollcommand=vsb.set)
            canvas.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")

            hdr = ttk.Frame(rows)
            hdr.pack(fill="x", pady=(2, 4))
            ttk.Label(hdr, text=t("unite_col_field"), width=20,
                      font=("Arial", 9, "bold")).pack(side="left")
            ttk.Label(hdr, text=t("unite_col_resolution"),
                      font=("Arial", 9, "bold")).pack(side="left")

            for c in self.conflicts:
                row = ttk.Frame(rows)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=c["label"], width=20, anchor="w").pack(side="left")
                labels = [o["label"] for o in c["options"]]
                cb = ttk.Combobox(row, values=labels, state="readonly", width=28)
                cb.current(0)
                cb.pack(side="left", fill="x", expand=True)
                self._combos[c["key"]] = cb
        elif approx:
            ttk.Label(self, text=t("unite_resolve_noconf_approx"), justify="left",
                      wraplength=420, foreground="#8a6d3b").pack(anchor="w", padx=12, pady=6)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=12, pady=(8, 12))
        ttk.Button(bar, text=t("btn_cancel"), command=self._cancel).pack(side="right")
        ttk.Button(bar, text=t("btn_ok"), command=self._ok).pack(side="right", padx=6)

        self.grab_set()
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + 60
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _ok(self):
        self.result = {k: cb.current() for k, cb in self._combos.items()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def _fmt(v):
    try:
        s = f"{float(v):.3f}".rstrip("0").rstrip(".")
        return "0" if s in ("", "-0") else s
    except (TypeError, ValueError):
        return "—" if v is None else str(v)
