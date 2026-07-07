import tkinter as tk
from tkinter import ttk

from i18n import t
from ui.helpers_ui import _fmt_num


class BatchEditDialog(tk.Toplevel):
    """Batch parameter edit (#67).

    One parameter + one operation (+= Δ / = value / ×= factor) applied to all
    target ops at once. A live old→new preview table updates as the value is
    typed; ops the parameter doesn't apply to are shown greyed as skipped.
    Nothing is written until Apply — which the owner (ProgramTab._apply_batch)
    wraps in a single #66 undo snapshot, so one Ctrl+Z reverts the whole batch.
    """

    def __init__(self, parent, program_tab, targets, options):
        super().__init__(parent)
        self.pt = program_tab
        self.targets = targets          # sorted op indices
        self.options = options          # [(key, label)]
        self._changes = {}

        self.title(t("dlg_batch_title").format(n=len(targets)))
        self.geometry("520x420")
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        self._create_widgets()
        self._refresh_preview()

    # ------------------------------------------------------------------
    def _create_widgets(self):
        f_top = ttk.Frame(self)
        f_top.pack(fill="x", padx=10, pady=(10, 4))

        ttk.Label(f_top, text=t("lbl_batch_param")).pack(side="left")
        self._labels = [lbl for _k, lbl in self.options]
        self.cmb_param = ttk.Combobox(f_top, values=self._labels,
                                      state="readonly", width=22)
        self.cmb_param.current(0)
        self.cmb_param.pack(side="left", padx=(4, 12))
        self.cmb_param.bind("<<ComboboxSelected>>", lambda e: self._refresh_preview())

        f_mode = ttk.Frame(self)
        f_mode.pack(fill="x", padx=10, pady=2)
        self.var_mode = tk.StringVar(value="add")
        for val, key in (("add", "rb_batch_add"),
                         ("set", "rb_batch_set"),
                         ("scale", "rb_batch_scale")):
            ttk.Radiobutton(f_mode, text=t(key), value=val, variable=self.var_mode,
                            command=self._refresh_preview).pack(side="left", padx=(0, 10))

        ttk.Label(f_mode, text=t("lbl_batch_value")).pack(side="left", padx=(12, 4))
        self.var_value = tk.StringVar(value="")
        ent = ttk.Entry(f_mode, textvariable=self.var_value, width=10)
        ent.pack(side="left")
        ent.bind("<KeyRelease>", lambda e: self._refresh_preview())
        ent.focus_set()

        # Preview: one row per target op, old -> new (or the skip reason).
        f_prev = ttk.Frame(self)
        f_prev.pack(fill="both", expand=True, padx=10, pady=(6, 4))
        cols = ("Op", "Type", "Old", "New")
        self.tree = ttk.Treeview(f_prev, columns=cols, show="headings", height=10)
        self.tree.heading("Op", text="#");             self.tree.column("Op", width=40, anchor="center")
        self.tree.heading("Type", text=t("col_type")); self.tree.column("Type", width=90)
        self.tree.heading("Old", text=t("col_batch_old")); self.tree.column("Old", width=110, anchor="center")
        self.tree.heading("New", text=t("col_batch_new")); self.tree.column("New", width=110, anchor="center")
        self.tree.tag_configure("skip", foreground="#9e9e9e")
        sb = ttk.Scrollbar(f_prev, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.lbl_status = ttk.Label(self, text="", foreground="#555")
        self.lbl_status.pack(fill="x", padx=10)

        f_btn = ttk.Frame(self)
        f_btn.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(f_btn, text=t("vc_close"), command=self.destroy).pack(side="right", padx=(4, 0))
        self.btn_apply = ttk.Button(f_btn, text=t("vc_apply"),
                                    command=self._apply, state="disabled")
        self.btn_apply.pack(side="right")

    # ------------------------------------------------------------------
    def _current_key(self):
        i = self.cmb_param.current()
        return self.options[i][0] if 0 <= i < len(self.options) else self.options[0][0]

    def _parse_value(self):
        raw = self.var_value.get().strip().replace(",", ".")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _refresh_preview(self):
        key = self._current_key()
        mode = self.var_mode.get()
        value = self._parse_value()
        ops = self.pt.app.params.get("operations", [])
        universe = {ot: self.pt._universe_for(ot)
                    for ot in ("roughing", "finishing", "cutting", "bending")}

        for item in self.tree.get_children():
            self.tree.delete(item)
        self._changes = {}

        if value is None:
            # No/invalid value yet: show the old values so the operator sees
            # what the batch would start from; Apply stays disabled.
            for i in self.targets:
                op = ops[i]
                old = op.get(key)
                old_s = _fmt_num(old) if isinstance(old, (int, float)) and not isinstance(old, bool) else "—"
                self.tree.insert("", "end", values=(i + 1, op.get("type", "?").upper(),
                                                    old_s, "—"))
            self.btn_apply.config(state="disabled")
            self.lbl_status.config(text=t("lbl_batch_novalue"))
            return

        changes, skipped = self.pt._batch_compute(ops, self.targets, key, mode,
                                                  value, universe)
        self._changes = changes
        for i in self.targets:
            op = ops[i]
            typ = op.get("type", "?").upper()
            if i in changes:
                old, new = changes[i]
                self.tree.insert("", "end", values=(
                    i + 1, typ,
                    _fmt_num(old) if old is not None else "—",
                    _fmt_num(new)))
            else:
                reason = t("lbl_batch_skip_na") if skipped.get(i) == "na" \
                         else t("lbl_batch_skip_nobase")
                self.tree.insert("", "end", tags=("skip",),
                                 values=(i + 1, typ, reason, "—"))
        self.btn_apply.config(state="normal" if changes else "disabled")
        self.lbl_status.config(
            text=t("lbl_batch_summary").format(n=len(changes), s=len(skipped)))

    def _apply(self):
        if not self._changes:
            return
        self.pt._apply_batch(self._current_key(), self._changes)
        self.destroy()
