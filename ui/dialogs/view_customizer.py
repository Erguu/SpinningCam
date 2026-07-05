import tkinter as tk
from tkinter import ttk

from i18n import t
from ui.tabs.program_tab import _default_cfg

# Op types shown as tabs, with their display-label i18n keys.
_OP_TYPES = [
    ("roughing",  "op_type_roughing"),
    ("finishing", "op_type_finishing"),
    ("cutting",   "op_type_cutting"),
    ("bending",   "op_type_bending"),
]


class ViewCustomizerDialog(tk.Toplevel):
    """Customize View (Program tab).

    One tab per operation type. Each parameter that the type can render is
    listed with two checkboxes: 'Show as column' (adds a column to the ops
    table) and 'Advanced' (hidden from the property editor while the global
    Advanced toggle is off). Settings are saved per program (params
    ["op_view_config"]) and never touch operation values or the toolpath.
    """

    def __init__(self, parent, app, program_tab):
        super().__init__(parent)
        self.app = app
        self.pt = program_tab

        self.title(t("dlg_customize_view"))
        self.geometry("560x600")
        self.transient(parent)
        self.focus_force()

        # self._vars[op_type][key] = (col_var, adv_var); _order preserves layout.
        self._vars = {}
        self._order = {}

        self._create_widgets()

    # ------------------------------------------------------------------
    def _create_widgets(self):
        info = ttk.Label(self, text=t("vc_info"), foreground="#555",
                         wraplength=530, justify="left")
        info.pack(fill="x", padx=10, pady=(8, 4))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        for op_type, label_key in _OP_TYPES:
            tab = ttk.Frame(nb)
            nb.add(tab, text=t(label_key))
            self._build_type_tab(tab, op_type)

        # --- Buttons ---
        f_btn = ttk.Frame(self)
        f_btn.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(f_btn, text=t("vc_reset"), command=self._reset_defaults).pack(side="left")
        ttk.Button(f_btn, text=t("vc_close"), command=self.destroy).pack(side="right", padx=(4, 0))
        ttk.Button(f_btn, text=t("vc_apply"), command=self._apply).pack(side="right")

    def _build_type_tab(self, parent, op_type):
        # Header row
        f_hdr = ttk.Frame(parent)
        f_hdr.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(f_hdr, text=t("vc_col_param"), font=("Arial", 9, "bold")).pack(side="left")
        ttk.Label(f_hdr, text=t("vc_col_adv"), font=("Arial", 9, "bold"),
                  width=10, anchor="center").pack(side="right")
        ttk.Label(f_hdr, text=t("vc_col_show"), font=("Arial", 9, "bold"),
                  width=10, anchor="center").pack(side="right")
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=6)

        # Scrollable body
        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))

        def _mw(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _mw))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        keys = self.pt._universe_for(op_type)
        cfg = self.pt._view_cfg(op_type)
        col_set = set(cfg["columns"])
        adv_set = set(cfg["advanced"])

        self._vars[op_type] = {}
        self._order[op_type] = list(keys)

        for k in keys:
            row = ttk.Frame(body)
            row.pack(fill="x", padx=6, pady=1)
            ttk.Label(row, text=self.pt._param_label(k)).pack(side="left")

            adv_var = tk.BooleanVar(value=(k in adv_set))
            col_var = tk.BooleanVar(value=(k in col_set))
            ttk.Checkbutton(row, variable=adv_var, width=10).pack(side="right")
            ttk.Checkbutton(row, variable=col_var, width=10).pack(side="right")
            self._vars[op_type][k] = (col_var, adv_var)

    # ------------------------------------------------------------------
    def _reset_defaults(self):
        for op_type, _ in _OP_TYPES:
            d = _default_cfg(op_type)
            cols, adv = set(d["columns"]), set(d["advanced"])
            for k, (col_var, adv_var) in self._vars.get(op_type, {}).items():
                col_var.set(k in cols)
                adv_var.set(k in adv)

    def _apply(self):
        cfg = {}
        for op_type, _ in _OP_TYPES:
            order = self._order.get(op_type, [])
            vars_ = self._vars.get(op_type, {})
            cfg[op_type] = {
                "columns":  [k for k in order if vars_[k][0].get()],
                "advanced": [k for k in order if vars_[k][1].get()],
            }
        self.app.params["op_view_config"] = cfg
        self.pt.after_view_config_changed()
        self.destroy()
