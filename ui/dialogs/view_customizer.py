import tkinter as tk
from tkinter import ttk

from i18n import t
from ui.tabs.program_tab import _default_cfg, _BATCH_ELIGIBLE, BORDER_COLORS

# Op types shown as tabs, with their display-label i18n keys.
_OP_TYPES = [
    ("roughing",  "op_type_roughing"),
    ("finishing", "op_type_finishing"),
    ("cutting",   "op_type_cutting"),
    ("bending",   "op_type_bending"),
]

# #84 — Border color choices for the highlight feature. Order matters (dropdown
# order). First entry ("") = no border. Each color name maps to a hex in
# program_tab.BORDER_COLORS; the label is shown translated in the dropdown.
_BORDER_CHOICES = [
    ("",       "vc_border_none"),
    ("red",    "vc_border_red"),
    ("green",  "vc_border_green"),
    ("blue",   "vc_border_blue"),
    ("orange", "vc_border_orange"),
    ("purple", "vc_border_purple"),
    ("yellow", "vc_border_yellow"),
]


class ViewCustomizerDialog(tk.Toplevel):
    """Customize View (Program tab).

    One tab per operation type. Each parameter that the type can render is
    listed with three checkboxes: 'Show as column' (adds a column to the ops
    table), 'Advanced' (hidden from the property editor while the global
    Advanced toggle is off) and 'Batch' (#67 — offered in the batch-edit
    dialog's parameter dropdown; numeric parameters only). Settings are saved
    per program (params["op_view_config"]) and never touch operation values
    or the toolpath.
    """

    def __init__(self, parent, app, program_tab):
        super().__init__(parent)
        self.app = app
        self.pt = program_tab

        self.title(t("dlg_customize_view"))
        self.geometry("720x600")
        self.transient(parent)
        self.focus_force()

        # self._vars[op_type][key] = (col_var, adv_var, bat_var or None, bdr_var);
        # _order preserves layout. bat_var is None for non-numeric params.
        # bdr_var (#84) is a StringVar holding the translated border-color label.
        self._vars = {}
        self._order = {}

        # #84 — translated dropdown label <-> internal color name, both ways.
        self._bdr_disp = {name: t(key) for name, key in _BORDER_CHOICES}
        self._bdr_rev = {disp: name for name, disp in self._bdr_disp.items()}
        self._bdr_values = [self._bdr_disp[name] for name, _ in _BORDER_CHOICES]

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

    # Fixed pixel width of the three checkbox columns — shared by the header
    # and the body rows so everything lines up in true columns.
    _COLW = 76
    _BORDERW = 96   # #84 — border-color dropdown column
    _SB_W = 18   # vertical-scrollbar width the header must skip over

    def _build_type_tab(self, parent, op_type):
        # Header row — grid with the same fixed column widths as the body,
        # plus a spacer column standing in for the body's scrollbar.
        f_hdr = ttk.Frame(parent)
        f_hdr.pack(fill="x", padx=6, pady=(6, 2))
        f_hdr.columnconfigure(0, weight=1)
        for c in (1, 2, 3):
            f_hdr.columnconfigure(c, minsize=self._COLW)
        f_hdr.columnconfigure(4, minsize=self._BORDERW)
        f_hdr.columnconfigure(5, minsize=self._SB_W)
        ttk.Label(f_hdr, text=t("vc_col_param"),
                  font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(f_hdr, text=t("vc_col_show"),
                  font=("Arial", 9, "bold")).grid(row=0, column=1)
        ttk.Label(f_hdr, text=t("vc_col_adv"),
                  font=("Arial", 9, "bold")).grid(row=0, column=2)
        ttk.Label(f_hdr, text=t("vc_col_batch"),
                  font=("Arial", 9, "bold")).grid(row=0, column=3)
        ttk.Label(f_hdr, text=t("vc_col_border"),
                  font=("Arial", 9, "bold")).grid(row=0, column=4)
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
        bat_set = set(cfg.get("batch", []))
        bdr_map = cfg.get("highlight", {})

        self._vars[op_type] = {}
        self._order[op_type] = list(keys)

        # One shared grid for all rows: label column stretches, the three
        # checkbox columns are fixed-width and centered — true columns, no
        # per-row drift from pack + character-based widths. Column 4 = border.
        body.columnconfigure(0, weight=1)
        for c in (1, 2, 3):
            body.columnconfigure(c, minsize=self._COLW)
        body.columnconfigure(4, minsize=self._BORDERW)

        for r, k in enumerate(keys):
            # Two grid rows per parameter: content on the even row, a thin
            # horizontal rule on the odd row so it's clear at a glance which
            # label lines up with which checkbox/dropdown across the width.
            gr = r * 2
            ttk.Label(body, text=self.pt._param_label(k)).grid(
                row=gr, column=0, sticky="w", padx=(6, 4), pady=3)

            adv_var = tk.BooleanVar(value=(k in adv_set))
            col_var = tk.BooleanVar(value=(k in col_set))
            ttk.Checkbutton(body, variable=col_var).grid(row=gr, column=1)
            ttk.Checkbutton(body, variable=adv_var).grid(row=gr, column=2)
            if k in _BATCH_ELIGIBLE:
                bat_var = tk.BooleanVar(value=(k in bat_set))
                ttk.Checkbutton(body, variable=bat_var).grid(row=gr, column=3)
            else:
                # Non-numeric param: batch modes (+=/=/×=) don't apply.
                bat_var = None
                ttk.Label(body, text="—").grid(row=gr, column=3)

            # #84 — border-color dropdown. Any param can be highlighted.
            cur_name = bdr_map.get(k, "")
            if cur_name not in self._bdr_disp:
                cur_name = ""   # stale/unknown color falls back to none
            bdr_var = tk.StringVar(value=self._bdr_disp[cur_name])
            cbb = ttk.Combobox(body, values=self._bdr_values, textvariable=bdr_var,
                               state="readonly", width=9)
            cbb.grid(row=gr, column=4, padx=(4, 6), pady=1)
            self._vars[op_type][k] = (col_var, adv_var, bat_var, bdr_var)

            # Row separator (skip after the last row).
            if r < len(keys) - 1:
                ttk.Separator(body, orient="horizontal").grid(
                    row=gr + 1, column=0, columnspan=5, sticky="ew")

    # ------------------------------------------------------------------
    def _reset_defaults(self):
        for op_type, _ in _OP_TYPES:
            d = _default_cfg(op_type)
            cols, adv, bat = set(d["columns"]), set(d["advanced"]), set(d["batch"])
            for k, (col_var, adv_var, bat_var, bdr_var) in self._vars.get(op_type, {}).items():
                col_var.set(k in cols)
                adv_var.set(k in adv)
                if bat_var is not None:
                    bat_var.set(k in bat)
                bdr_var.set(self._bdr_disp[""])   # #84 — no highlights by default

    def _apply(self):
        cfg = {}
        for op_type, _ in _OP_TYPES:
            order = self._order.get(op_type, [])
            vars_ = self._vars.get(op_type, {})
            cfg[op_type] = {
                "columns":  [k for k in order if vars_[k][0].get()],
                "advanced": [k for k in order if vars_[k][1].get()],
                "batch":    [k for k in order
                             if vars_[k][2] is not None and vars_[k][2].get()],
                # #84 — {key: color_name} for params with a border color set.
                "highlight": {k: self._bdr_rev[vars_[k][3].get()]
                              for k in order
                              if self._bdr_rev.get(vars_[k][3].get())},
            }
        self.app.params["op_view_config"] = cfg
        self.pt.after_view_config_changed()
        self.destroy()
