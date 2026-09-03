import tkinter as tk
from tkinter import ttk

from i18n import t
from ui.tabs.program_tab import _default_cfg, _BATCH_ELIGIBLE, BORDER_COLORS
from ui import dialog_sizing

# Op types shown as tabs, with their display-label i18n keys.
_OP_TYPES = [
    ("roughing",  "op_type_roughing"),
    ("finishing", "op_type_finishing"),
    ("cutting",   "op_type_cutting"),
    ("bending",   "op_type_bending"),
    ("point",     "op_type_point"),
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
        dialog_sizing.fit(self, 720, 600)
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

        # Column order is a property of the single ops table, not of an op
        # type, so it gets its own tab rather than living in each type's tab.
        tab_ord = ttk.Frame(nb)
        nb.add(tab_ord, text=t("vc_tab_order"))
        self._build_order_tab(tab_ord)

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
    # Column order tab (#91) — display-only reordering of the ops table.
    # ------------------------------------------------------------------

    def _build_order_tab(self, parent):
        ttk.Label(parent, text=t("vc_order_info"), foreground="#555",
                  wraplength=640, justify="left").pack(fill="x", padx=10, pady=(10, 6))

        # Current live order straight off the tree, so this always mirrors what
        # the user is looking at. Columns ticked on in another tab but not yet
        # applied simply appear at the end after Apply (_display_order appends
        # ids the saved order doesn't know).
        tree = self.pt.tree_ops
        disp = tree.cget("displaycolumns")
        if isinstance(disp, str):
            disp = (disp,) if disp else ()
        cols = tree.cget("columns")
        if isinstance(cols, str):
            cols = tuple(cols.split())
        if not disp or "#all" in disp:
            disp = tuple(cols)
        self._order_list = [c for c in disp]
        self._order_sel = self._order_list[1] if len(self._order_list) > 1 else None

        # Horizontal strip of chips, left-to-right exactly like the real table.
        # Many configured columns overflow the dialog, hence the x-scrollbar.
        wrap = ttk.Frame(parent)
        wrap.pack(fill="x", padx=10)
        self._ord_canvas = tk.Canvas(wrap, height=44, highlightthickness=0)
        sbx = ttk.Scrollbar(wrap, orient="horizontal", command=self._ord_canvas.xview)
        self._ord_canvas.configure(xscrollcommand=sbx.set)
        self._ord_canvas.pack(fill="x")
        sbx.pack(fill="x")
        self._ord_strip = ttk.Frame(self._ord_canvas)
        self._ord_canvas.create_window((0, 0), window=self._ord_strip, anchor="nw")
        self._ord_strip.bind("<Configure>", lambda e: self._ord_canvas.configure(
            scrollregion=self._ord_canvas.bbox("all")))

        f_btn = ttk.Frame(parent)
        f_btn.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(f_btn, text="◀", width=4,
                   command=lambda: self._move_col(-1)).pack(side="left")
        ttk.Button(f_btn, text="▶", width=4,
                   command=lambda: self._move_col(1)).pack(side="left", padx=(6, 0))
        ttk.Button(f_btn, text=t("vc_order_reset"),
                   command=self._reset_order).pack(side="left", padx=(16, 0))

        ttk.Label(parent, text=t("vc_order_pinned"), foreground="#888",
                  wraplength=640, justify="left").pack(fill="x", padx=10, pady=(8, 0))
        self._redraw_order()

    def _redraw_order(self):
        for w in self._ord_strip.winfo_children():
            w.destroy()
        for cid in self._order_list:
            pinned = (cid == "Sel")
            selected = (cid == self._order_sel)
            lbl = tk.Label(self._ord_strip, text=self.pt._col_label(cid),
                           relief="raised", bd=1, padx=6, pady=4,
                           bg=("#1976d2" if selected else
                               "#e0e0e0" if pinned else "#f5f5f5"),
                           fg=("white" if selected else
                               "#9e9e9e" if pinned else "black"))
            lbl.pack(side="left", padx=2, pady=4)
            if not pinned:
                lbl.bind("<Button-1>", lambda e, c=cid: self._select_col(c))
        self._ord_strip.update_idletasks()
        self._ord_canvas.configure(scrollregion=self._ord_canvas.bbox("all"))

    def _select_col(self, cid):
        self._order_sel = cid
        self._redraw_order()

    def _move_col(self, delta):
        """Shift the selected column one slot left/right. Index 0 is Sel and is
        never a valid destination — the ☑ click handlers identify that cell by
        display position, so it stays pinned."""
        if self._order_sel is None or self._order_sel == "Sel":
            return      # Sel is pinned: it can neither be displaced nor moved
        try:
            i = self._order_list.index(self._order_sel)
        except ValueError:
            return
        j = i + delta
        if j < 1 or j >= len(self._order_list):
            return      # off the end, or into Sel's pinned slot
        self._order_list[i], self._order_list[j] = \
            self._order_list[j], self._order_list[i]
        self._redraw_order()

    def _reset_order(self):
        """Back to the natural order: base columns, then extras as configured."""
        cols = self.pt.tree_ops.cget("columns")
        if isinstance(cols, str):
            cols = tuple(cols.split())
        self._order_list = list(cols)
        self._order_sel = self._order_list[1] if len(self._order_list) > 1 else None
        self._redraw_order()

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
        self._reset_order()

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
        # Sel is pinned by _display_order and never stored, so the saved order
        # can't be edited into a state that moves it.
        self.app.params["op_view_col_order"] = [c for c in getattr(self, "_order_list", [])
                                                if c != "Sel"]
        self.pt.after_view_config_changed()
        self.destroy()
