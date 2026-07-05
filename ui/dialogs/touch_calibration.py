import tkinter as tk
from tkinter import ttk, messagebox
import math
import numpy as np


class TouchCalibrationDialog(tk.Toplevel):
    """Calibration dialog with live XZ cross-section canvas.

    X-axis: jog roller radially to mandrel/blank surface, enter DRO X.
    Z-axis: jog to a known axial reference, enter DRO Z.
    Canvas shows mandrel profile, blank, roller, machine origins, and delta arrows.
    """

    # ── Colour palette (matches pass-diagram dark theme) ──────────────────
    C_BG    = "#1a1a2e"
    C_AX    = "#445566"
    C_MAND  = "#6688aa"
    C_MFILL = "#1e3048"
    C_BLANK = "#2a3a2a"
    C_BLINE = "#557755"
    C_ROLLER= "#88aacc"
    C_RFILL = "#1e2a38"
    C_PATH  = "#55aaff"
    C_TOUCH = "#ffdd44"
    C_GOOD  = "#44cc77"
    C_WARN  = "#ffaa33"
    C_ERR   = "#ff5544"
    C_HDIM  = "#7799ff"
    C_VDIM  = "#ff99bb"
    C_HOME  = "#88ffaa"
    C_HOMEZ = "#ff88cc"
    C_LBL   = "#cce0ff"
    C_GHOST = "#334455"

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Touch Point Calibration")
        self.geometry("1060x680")
        self.minsize(820, 520)
        self.resizable(True, True)
        self.grab_set()

        # Computed calibration state
        self._x_delta     = None
        self._x_surface   = None   # surface used in the first calculate ("mandrel"/"blank")
        self._z_delta     = None
        self._x_dir_x     = None
        self._x_side      = None
        self._z_dir_z     = None
        self._new_home_x  = None
        self._new_cx      = None
        self._new_blank   = None
        self._new_home_z  = None
        self._new_off_z   = None

        # Canvas zoom / pan
        self._zoom = [1.0]
        self._pan  = [0.0, 0.0]
        self._drag = [None, None]

        # Canvas orientation — persisted in settings
        cal_cfg = self.app.params.get("calibration_view", {})
        self._flip_z = [bool(cal_cfg.get("flip_z", False))]
        self._flip_x = [bool(cal_cfg.get("flip_x", False))]

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.canvas.bind("<Configure>", lambda e: self.after(10, self._redraw))
        self.after(80, self._redraw)

    # ═════════════════════════════════════════════════════════════════════
    # Layout
    # ═════════════════════════════════════════════════════════════════════

    def _build_layout(self):
        # ── Top banner ──────────────────────────────────────────────────
        top = tk.Frame(self, bg="#0d1520")
        top.pack(fill="x")
        tk.Label(top, text="Touch Point Calibration",
                 bg="#0d1520", fg="#aaccff",
                 font=("Arial", 13, "bold")).pack(side="left", padx=12, pady=(8, 2))

        self.lbl_mode = tk.Label(top, text="", bg="#0d1520", fg="#7799aa",
                                 font=("Consolas", 8, "italic"))
        self.lbl_mode.pack(side="left", padx=12, pady=(8, 2))
        self._update_mode_label()

        # ── Main body: canvas (left) + right panel ───────────────────────
        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=6, pady=4)

        # Canvas column: orientation toolbar on top, canvas below
        frm_canvas_col = tk.Frame(body, bg="#0d1520")
        frm_canvas_col.pack(side="left", fill="both", expand=True)

        # ── Orientation toolbar ──────────────────────────────────────────
        frm_orient = tk.Frame(frm_canvas_col, bg="#0d1520")
        frm_orient.pack(fill="x", pady=(2, 0))
        tk.Label(frm_orient, text="View:", bg="#0d1520", fg="#556677",
                 font=("Consolas", 7)).pack(side="left", padx=(6, 2))
        self._btn_fz = tk.Button(
            frm_orient, text="Flip Z ↔", width=7,
            bg="#1e2a3a", fg="#99bbdd", relief="flat",
            font=("Consolas", 7), activebackground="#2a3f55",
            command=self._toggle_flip_z)
        self._btn_fz.pack(side="left", padx=2)
        self._btn_fx = tk.Button(
            frm_orient, text="Flip X ↕", width=7,
            bg="#1e2a3a", fg="#99bbdd", relief="flat",
            font=("Consolas", 7), activebackground="#2a3f55",
            command=self._toggle_flip_x)
        self._btn_fx.pack(side="left", padx=2)
        tk.Label(frm_orient, text="(match your 3D view)", bg="#0d1520", fg="#334455",
                 font=("Consolas", 7, "italic")).pack(side="left", padx=6)
        self._update_orient_buttons()

        self.canvas = tk.Canvas(frm_canvas_col, bg=self.C_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        frm_right = tk.Frame(body, bg="#0d1520", width=370)
        frm_right.pack(side="right", fill="y")
        frm_right.pack_propagate(False)
        self._build_right_panel(frm_right)

        # ── Bottom bar ───────────────────────────────────────────────────
        bot = tk.Frame(self, bg="#0d1520")
        bot.pack(fill="x")
        tk.Button(bot, text="Close", command=self._on_close,
                  width=10, bg="#334455", fg="white").pack(pady=5)

        # Canvas mouse bindings
        c = self.canvas
        c.bind("<MouseWheel>",      self._on_scroll)
        c.bind("<Button-4>",        self._on_scroll)
        c.bind("<Button-5>",        self._on_scroll)
        c.bind("<ButtonPress-1>",   self._on_drag_start)
        c.bind("<B1-Motion>",       self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_drag_end)
        c.bind("<Double-Button-1>",
               lambda e: (self._zoom.__setitem__(0, 1.0),
                          self._pan.__setitem__(0, 0.0),
                          self._pan.__setitem__(1, 0.0),
                          self._redraw()))

    # ─────────────────────────────────────────────────────────────────────
    # Right panel
    # ─────────────────────────────────────────────────────────────────────

    def _build_right_panel(self, parent):
        # Scrollable inner
        outer = tk.Frame(parent, bg="#0d1520")
        outer.pack(fill="both", expand=True)
        cv = tk.Canvas(outer, bg="#0d1520", highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg="#0d1520")
        _wid = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",    lambda e: cv.itemconfig(_wid, width=e.width))
        def _mw(e): cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
        cv.bind("<Enter>", lambda e: cv.bind_all("<MouseWheel>", _mw))
        cv.bind("<Leave>", lambda e: cv.unbind_all("<MouseWheel>"))

        # Last-session banner (hidden until data is loaded)
        self.lbl_last_session = tk.Label(
            inner, text="", bg="#0d1520", fg="#5566aa",
            font=("Consolas", 7, "italic"), wraplength=340, anchor="w")
        self.lbl_last_session.pack(fill="x", padx=8, pady=(3, 0))

        def hdr(txt, color="#7799cc"):
            tk.Label(inner, text=txt, bg="#0d1520", fg=color,
                     font=("Consolas", 9, "bold")).pack(anchor="w", padx=8, pady=(8, 1))

        def sep():
            tk.Frame(inner, bg="#223355", height=1).pack(fill="x", padx=6, pady=2)

        def hint(txt):
            tk.Label(inner, text=txt, bg="#0d1520", fg="#556677",
                     font=("Consolas", 7, "italic"), wraplength=330,
                     justify="left").pack(anchor="w", padx=14, pady=(0, 3))

        # ── X-Axis section ──────────────────────────────────────────────
        hdr("X-AXIS  Radial Touch", "#7799cc")
        sep()
        tk.Label(inner,
                 text="Jog the roller until it just grazes the surface.\nRead the DRO X and enter it below.",
                 bg="#0d1520", fg="#778899", font=("Consolas", 8),
                 justify="left").pack(anchor="w", padx=10, pady=(2, 4))

        # Tool selector
        import json, os as _os
        _tools_path = _os.path.join(_os.path.dirname(_os.path.dirname(
            _os.path.dirname(_os.path.abspath(__file__)))), "tools.json")
        try:
            _tools = json.load(open(_tools_path, encoding="utf-8")) if _os.path.exists(_tools_path) else []
        except Exception:
            _tools = []
        self._tools_data = {t["id"]: t for t in _tools if "id" in t}

        f_tool = tk.Frame(inner, bg="#0d1520")
        f_tool.pack(fill="x", padx=10, pady=(2, 0))
        tk.Label(f_tool, text="Roller (tool):", bg="#0d1520", fg=self.C_LBL,
                 font=("Consolas", 8), width=20, anchor="w").pack(side="left")
        _tool_choices = ["(manual)"] + [f"{t['id']}  {t.get('name','')}" for t in _tools if "id" in t]
        self.tool_var = tk.StringVar(value=_tool_choices[0])
        _cb = ttk.Combobox(f_tool, textvariable=self.tool_var,
                           values=_tool_choices, state="readonly", width=18)
        _cb.pack(side="left")
        _cb.bind("<<ComboboxSelected>>", self._on_tool_selected)
        self._btn_view_roller = tk.Button(
            f_tool, text="View ▸", command=self._show_roller_preview,
            bg="#2a3f55", fg="#88aacc", font=("Consolas", 7), width=5,
            relief="flat", activebackground="#3a5570")
        self._btn_view_roller.pack(side="left", padx=(4, 0))
        hint("Pick the roller tool used for this touch.\n"
             "Selects the correct edge radius (Rr) and disc angle automatically.\n"
             "'View ▸' opens a 2D cross-section from the tool STEP file.")

        # r_tool override row (editable, pre-filled from ops)
        _rt0 = float(self.app.params.get("r_tool",
               self.app.params.get("operations", [{}])[0].get("r_tool", 15.0)
               if self.app.params.get("operations") else 15.0))
        self.entry_rt = self._frow(inner, "Roller edge radius Rr (mm):")
        self.entry_rt.insert(0, f"{_rt0:.2f}")
        self.entry_rt.bind("<KeyRelease>", self._redraw)
        hint("Effective radial reach: distance from machine X reference to roller contact.\n"
             "Auto-filled from r_tool in Operations (already accounts for disc tilt/mounting).\n"
             "Do NOT use the disc outer radius — that is a larger, uncorrected value.")

        # ── CHALLENGER reach (axis-fit) — opt-in A/B test, does not change defaults ──
        f_chal = tk.Frame(inner, bg="#0d1520")
        f_chal.pack(fill="x", padx=10, pady=(0, 2))
        tk.Label(f_chal, text="Challenger Rr (axis):", bg="#0d1520", fg=self.C_LBL,
                 font=("Consolas", 8), width=20, anchor="w").pack(side="left")
        self.lbl_challenger = tk.Label(f_chal, text="—", bg="#0d1520", fg="#c8a24a",
                                       font=("Consolas", 8), anchor="w")
        self.lbl_challenger.pack(side="left")
        self._btn_use_challenger = tk.Button(
            f_chal, text="Use ▸", command=self._use_challenger_rt,
            bg="#2a3f55", fg="#88aacc", font=("Consolas", 7), width=5,
            relief="flat", activebackground="#3a5570", state="disabled")
        self._btn_use_challenger.pack(side="left", padx=(6, 0))
        self._challenger_rt = None
        hint("A SECOND way to measure this tool's reach (Rr), read from its STEP file.\n"
             "\n"
             "Why it exists: if you calibrate with one tool and then run a DIFFERENT\n"
             "tool, a small gap can appear. That is because the normal Rr is measured\n"
             "slightly differently for each tool. This value measures every tool the\n"
             "same way, so tools stay consistent with each other.\n"
             "\n"
             "'Use ▸' just types this number into the Rr box above so you can test it\n"
             "on the machine. It saves NOTHING and does NOT change the tool library.")

        # Approach angle
        self.entry_angle = self._frow(inner, "Contact angle (°):")
        self.entry_angle.insert(0, "0.0")
        self.entry_angle.bind("<KeyRelease>", self._redraw)
        hint("Angle between the roller approach direction and the machine X-axis.\n"
             "0 = roller approaches purely radially (most accurate for calibration).\n"
             "Non-zero: effective radial offset = Rr × cos(angle).\n"
             "Check your tool's disc tilt or approach angle in the tool setup.")

        self.entry_z = self._frow(inner, "Machine Z at touch (mm):")
        hint("The Z value shown on your machine DRO/controller at the moment of contact.\n"
             "Same as Machine X — just read it directly from the DRO.")

        self.entry_x = self._frow(inner, "Machine X at touch (mm):")
        hint("The X value shown on the machine DRO or controller\n"
             "at the exact moment the roller touched the surface.")

        f_surf = tk.Frame(inner, bg="#0d1520")
        f_surf.pack(fill="x", padx=10, pady=(2, 2))
        tk.Label(f_surf, text="Surface touched:", bg="#0d1520", fg=self.C_LBL,
                 font=("Consolas", 8), width=20, anchor="w").pack(side="left")
        self.surface_var = tk.StringVar(value="mandrel")
        for val, lbl in (("mandrel", "Mandrel"), ("blank", "Blank")):
            ttk.Radiobutton(f_surf, text=lbl, variable=self.surface_var,
                            value=val, command=self._redraw).pack(side="left", padx=(0, 10))
        hint("Mandrel = bare mandrel surface (no sheet metal on it).\n"
             "Blank = metal sheet already placed on the mandrel.\n"
             "Choosing wrong will give an incorrect blank-thickness correction.")

        p0 = self.app.params
        _blank_default = float(p0.get("final_part_thickness_on_mandrel", p0.get("shell_thickness", 0.0)))
        self.entry_blank_t = self._frow(inner, "Blank thickness (mm):")
        self.entry_blank_t.insert(0, f"{_blank_default:.2f}")
        self.entry_blank_t.bind("<KeyRelease>", self._redraw)
        hint("Sheet metal thickness. Only used when 'Blank' surface is selected above.\n"
             "Defaults to final_part_thickness_on_mandrel from project settings.")

        # ── Z-Axis section ──────────────────────────────────────────────
        hdr("Z-AXIS  Axial Touch", "#cc99ff")
        sep()
        tk.Label(inner,
                 text="Jog the roller to a known axial position.\nRead the DRO Z and enter it below.",
                 bg="#0d1520", fg="#778899", font=("Consolas", 8),
                 justify="left").pack(anchor="w", padx=10, pady=(2, 4))

        f_zref = tk.Frame(inner, bg="#0d1520")
        f_zref.pack(fill="x", padx=10, pady=(0, 2))
        tk.Label(f_zref, text="Reference point:", bg="#0d1520", fg=self.C_LBL,
                 font=("Consolas", 8)).pack(anchor="w")
        self.zref_var = tk.StringVar(value="mandrel_root")
        for val, lbl in (("mandrel_root", "Mandrel root face  (Z = 0 in CAM)"),
                         ("mandrel_top",  "Mandrel top  (auto-detect from STEP)"),
                         ("custom",       "Custom CAM Z  (enter below)")):
            ttk.Radiobutton(f_zref, text=lbl, variable=self.zref_var,
                            value=val, command=self._on_zref_change).pack(anchor="w", padx=12)
        hint("Choose a feature you can physically jog to.\n"
             "Mandrel root = the flat face at the chuck end (Z = 0 in CAM).\n"
             "Mandrel top = the tip/flange edge (Z auto-read from STEP).\n"
             "Custom = any other point where you know the exact CAM Z.")

        self.entry_cam_z = self._frow(inner, "Known CAM Z (mm):")
        hint("The Z value this physical feature corresponds to in the program.\n"
             "Auto-filled for root (0) and top (from STEP). Enter manually for Custom.")

        self.entry_mach_z = self._frow(inner, "Machine Z at touch (mm):")
        hint("The Z value shown on the machine DRO or controller\n"
             "when the roller is at the reference feature.")

        self._on_zref_change()   # pre-fill CAM Z

        # ── Calculate ───────────────────────────────────────────────────
        sep()
        f_calc_row = tk.Frame(inner, bg="#0d1520")
        f_calc_row.pack(fill="x", padx=10, pady=(6, 4))
        tk.Button(f_calc_row, text="  Calculate  ", command=self._calculate,
                  bg="#1e4a7a", fg="white",
                  font=("Arial", 9, "bold"), width=16).pack(side="left")
        tk.Button(f_calc_row, text="How it works?", command=self._show_formula_reference,
                  bg="#1a3a1a", fg="#88cc88",
                  font=("Arial", 8), width=15).pack(side="left", padx=(8, 0))
        hint("Computes the error (Delta) between where the machine\n"
             "thinks it is vs. where the STEP model expects it to be.\n"
             "'How it works?' explains every formula and parameter.")

        self.txt_results = tk.Text(inner, height=15, font=("Consolas", 8),
                                   bg="#0a0f1a", fg=self.C_LBL,
                                   relief="sunken", bd=1,
                                   state="disabled", wrap="none",
                                   highlightthickness=0)
        self.txt_results.pack(fill="x", padx=8, pady=(0, 4))
        self._set_results("  — enter values and click Calculate —")

        # ── Apply section ────────────────────────────────────────────────
        hdr("Apply Correction")
        sep()

        self.lbl_rec = tk.Label(inner, text="", bg="#0d1520", fg="#7799aa",
                                font=("Consolas", 7, "italic"), wraplength=340, justify="left")
        self.lbl_rec.pack(anchor="w", padx=10, pady=(2, 4))

        tk.Label(inner, text="X corrections:", bg="#0d1520", fg="#7799cc",
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=10)
        self.btn_home_x = self._abtn(inner, "Program Start X", self._apply_home_x)
        hint("Shifts home_x — the position the machine goes to at program start.\n"
             "Best when Origin = Safe Home is ON. Moves ALL passes equally.")
        self.btn_offset = self._abtn(inner, "Mandrel Offset", self._apply_offset)
        hint("Shifts mandrel_pos_x_offset — the CAM model's radial centre.\n"
             "Best when the mandrel is physically off-centre from the expected position.")
        self.btn_blank = self._abtn(inner, "Blank Thickness", self._apply_blank)
        hint("Adjusts final_part_thickness_on_mandrel — the sheet metal thickness.\n"
             "Only meaningful if you touched the blank surface (not the bare mandrel).")

        tk.Label(inner, text="Z corrections:", bg="#0d1520", fg="#cc99ff",
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
        self.btn_home_z = self._abtn(inner, "Program Start Z", self._apply_home_z)
        hint("Shifts home_z — the axial safe-home position.\n"
             "Best when Origin = Safe Home is ON. Moves ALL passes equally in Z.")
        self.btn_off_z = self._abtn(inner, "G-code Z Offset", self._apply_off_z)
        hint("Shifts machine_gcode_offset_z — added to every Z coordinate in the output.\n"
             "Like adjusting a G54 work offset. Use in Fixed-Origin mode.")

        self.lbl_apply = tk.Label(inner, text="", bg="#0d1520", fg="lime",
                                  font=("Arial", 8), wraplength=340, justify="left")
        self.lbl_apply.pack(anchor="w", padx=10, pady=(4, 2))

        # ── Optional second touch ────────────────────────────────────────
        hdr("Optional — Second Touch  (STEP consistency check)", "#778899")
        sep()
        tk.Label(inner,
                 text="Touch a second Z location using the same surface as the first touch.\n"
                      "Both deltas should be nearly equal — verifies the STEP profile.",
                 bg="#0d1520", fg="#556677", font=("Consolas", 7, "italic"),
                 justify="left").pack(anchor="w", padx=10, pady=(2, 4))
        self.entry_z2 = self._frow(inner, "Machine Z at touch 2 (mm):")
        self.entry_x2 = self._frow(inner, "Machine X 2 (mm):")
        f_chk = tk.Frame(inner, bg="#0d1520")
        f_chk.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(f_chk, text="Check Consistency", command=self._check_consistency,
                  bg="#3a4a2a", fg="white", font=("Arial", 8), width=18).pack(side="left")
        self.lbl_consist = tk.Label(f_chk, text="", bg="#0d1520",
                                    font=("Consolas", 8))
        self.lbl_consist.pack(side="left", padx=8)

        # Restore last session after all fields exist
        self._load_last_session()

    def _frow(self, parent, label):
        f = tk.Frame(parent, bg="#0d1520")
        f.pack(fill="x", padx=10, pady=2)
        tk.Label(f, text=label, bg="#0d1520", fg=self.C_LBL,
                 font=("Consolas", 8), width=26, anchor="w").pack(side="left")
        e = ttk.Entry(f, width=12)
        e.pack(side="left")
        e.bind("<Return>",   lambda _: self._redraw())
        e.bind("<FocusOut>", lambda _: self._redraw())
        return e

    def _abtn(self, parent, label, cmd):
        b = tk.Button(parent, text=label, command=cmd,
                      bg="#445566", fg="#aabbcc", state="disabled",
                      font=("Consolas", 8), anchor="w", width=42)
        b.pack(padx=10, pady=2, anchor="w")
        return b

    # ═════════════════════════════════════════════════════════════════════
    # Canvas mouse
    # ═════════════════════════════════════════════════════════════════════

    def _on_scroll(self, event):
        factor = 1.1 if (getattr(event, "delta", 0) > 0 or event.num == 4) else 1/1.1
        self._zoom[0] = max(0.2, min(self._zoom[0] * factor, 8.0))
        self._redraw()

    def _on_drag_start(self, event):
        self._drag[0] = event.x;  self._drag[1] = event.y

    def _on_drag(self, event):
        if self._drag[0] is not None:
            self._pan[0] += event.x - self._drag[0]
            self._pan[1] += event.y - self._drag[1]
            self._drag[0] = event.x;  self._drag[1] = event.y
            self._redraw()

    def _on_drag_end(self, _event):
        self._drag[0] = None

    def _redraw(self, _=None):
        c = self.canvas
        c.delete("all")
        W = c.winfo_width()  or 600
        H = c.winfo_height() or 500
        if W < 20 or H < 20:
            return
        self._draw_scene(c, W, H, self._zoom[0], self._pan)

    # ═════════════════════════════════════════════════════════════════════
    # Coordinate helpers
    # ═════════════════════════════════════════════════════════════════════

    def _machine_params(self):
        p = self.app.params
        dir_x  = -1.0 if p.get("machine_invert_x", False) else 1.0
        dir_z  = -1.0 if p.get("machine_invert_z", False) else 1.0
        off_x  = float(p.get("machine_gcode_offset_x", 0.0))
        off_z  = float(p.get("machine_gcode_offset_z", 0.0))
        if p.get("origin_use_home", False):
            ox = float(p.get("home_x", 0.0))
            oz = float(p.get("home_z", 0.0))
        else:
            ox = float(p.get("machine_origin_x", 0.0))
            oz = float(p.get("machine_origin_z", 0.0))
        return ox, oz, dir_x, dir_z, off_x, off_z

    def _cam_to_mach_x(self, cam_x):
        ox, _, dx, _, ofx, _ = self._machine_params()
        return (cam_x - ox) * dx + ofx

    def _cam_to_mach_z(self, cam_z):
        _, oz, _, dz, _, ofz = self._machine_params()
        return (cam_z - oz) * dz + ofz

    def _mach_to_cam_x(self, mx):
        ox, _, dx, _, ofx, _ = self._machine_params()
        return (mx - ofx) / dx + ox

    def _mach_to_cam_z(self, mz):
        _, oz, _, dz, _, ofz = self._machine_params()
        return (mz - ofz) / dz + oz

    def _mandrel_r(self, z):
        mgr = getattr(self.app, "mandrel_mgr", None)
        if mgr is None or getattr(mgr, "profile_z", None) is None:
            return None
        return float(mgr.get_radius_fast(float(z)))

    def _mandrel_top_z(self):
        mgr = getattr(self.app, "mandrel_mgr", None)
        if mgr is None or getattr(mgr, "profile_z", None) is None:
            return None
        pz = list(mgr.profile_z)
        return float(max(pz)) if pz else None

    def _mandrel_profile(self):
        """Return (prof_z, prof_r) lists. Synthesise a cylinder if no STEP loaded."""
        mgr = getattr(self.app, "mandrel_mgr", None)
        if mgr is not None and getattr(mgr, "profile_z", None) is not None:
            pz = list(mgr.profile_z)
            pr = [float(mgr.get_radius_fast(z)) for z in pz]
            return pz, pr
        return [0.0, 150.0], [75.0, 75.0]

    def _roller_r(self):
        p = self.app.params
        ops = p.get("operations", [])
        if ops:
            rv = ops[0].get("r_tool", None)
            if rv is not None:
                return float(rv)
        return float(p.get("r_tool", 15.0))

    def _compute_x_delta(self, touch_z, mach_x, surface):
        r = self._mandrel_r(touch_z)
        if r is None:
            return None, None, None, None
        p  = self.app.params
        cx    = float(p.get("mandrel_pos_x_offset", 0.0))
        try:
            blank = max(0.0, float(self.entry_blank_t.get()))
        except (ValueError, tk.TclError):
            blank = float(p.get("final_part_thickness_on_mandrel", p.get("shell_thickness", 0.0)))
        try:
            r_t = max(0.1, float(self.entry_rt.get()))
        except (ValueError, tk.TclError):
            r_t = self._roller_r()
        try:
            _ang = float(self.entry_angle.get())
            r_t = r_t * math.cos(math.radians(_ang))
        except (ValueError, tk.TclError):
            pass
        r_t = max(0.1, r_t)
        side  = 1.0 if p.get("roller_positive_x_side", True) else -1.0
        if surface == "mandrel":
            cam_x_contact = cx + side * (r + r_t)
        else:
            cam_x_contact = cx + side * (r + blank + r_t)
        exp_mach = self._cam_to_mach_x(cam_x_contact)
        _, _, dx, _, _, _ = self._machine_params()
        return exp_mach, mach_x - exp_mach, side, dx

    def _compute_z_delta(self, cam_z_ref, mach_z):
        _, _, _, dz, _, _ = self._machine_params()
        exp_mach = self._cam_to_mach_z(cam_z_ref)
        return exp_mach, mach_z - exp_mach, dz

    # ═════════════════════════════════════════════════════════════════════
    # Z reference helper
    # ═════════════════════════════════════════════════════════════════════

    def _on_zref_change(self, *_):
        ref = self.zref_var.get()
        e = self.entry_cam_z
        e.config(state="normal")
        e.delete(0, "end")
        if ref == "mandrel_root":
            e.insert(0, "0.0")
            e.config(state="disabled")
        elif ref == "mandrel_top":
            top = self._mandrel_top_z()
            e.insert(0, f"{top:.3f}" if top is not None else "")
            e.config(state="disabled")
        # custom: leave editable
        self._redraw()

    # ═════════════════════════════════════════════════════════════════════
    # Mode label
    # ═════════════════════════════════════════════════════════════════════

    def _update_mode_label(self):
        p = self.app.params
        use_home = bool(p.get("origin_use_home", False))
        ix = bool(p.get("machine_invert_x", False))
        iz = bool(p.get("machine_invert_z", False))
        if use_home:
            hx = float(p.get("home_x", 0.0))
            hz = float(p.get("home_z", 0.0))
            txt = (f"Origin = Safe Home  |  home_x={hx:.3f}  home_z={hz:.3f}  |  "
                   f"X={'inv' if ix else 'norm'}  Z={'inv' if iz else 'norm'}")
        else:
            ox = float(p.get("machine_origin_x", 0.0))
            oz = float(p.get("machine_origin_z", 0.0))
            txt = (f"Fixed Origin  |  origin_x={ox:.3f}  origin_z={oz:.3f}  |  "
                   f"X={'inv' if ix else 'norm'}  Z={'inv' if iz else 'norm'}")
        self.lbl_mode.config(text=txt)

    def _on_tool_selected(self, _=None):
        sel = self.tool_var.get()
        if sel.startswith("(manual)"):
            self._refresh_challenger(None)
            self._redraw()
            return
        tid = sel.split()[0]
        tool = self._tools_data.get(tid, {})
        self._refresh_challenger(tool)
        # r_tool: tool library is the primary source (set once in Tool Manager).
        # Fall back to operations for backwards compatibility.
        # The disc outer radius (tool["radius"]) is NOT used here.
        r_t = tool.get("r_tool")  # from tool library
        if r_t is None:
            for op in self.app.params.get("operations", []):
                if op.get("tool_id") == tid:
                    r_t = op.get("r_tool")
                    break
        self.entry_rt.delete(0, "end")
        if r_t is not None:
            self.entry_rt.insert(0, f"{float(r_t):.2f}")
        # Contact angle stays 0° — r_tool is already the effective radial reach
        # (it already accounts for disc tilt and mounting geometry).
        # step_rotation is 3D visualisation data, not a calibration parameter.
        self.entry_angle.delete(0, "end")
        self.entry_angle.insert(0, "0.0")
        self._redraw()

    def _refresh_challenger(self, tool):
        """Compute the axis-fit challenger reach for the selected tool and show it.
        Read-only display + enables the 'Use ▸' button; never changes Rr on its own."""
        self._challenger_rt = None
        loader = getattr(self.app, "tool_step_loader", None)
        val = None
        if tool and loader is not None:
            try:
                val = loader.get_contact_radius_axis(tool)
            except Exception:
                val = None
        if val is None:
            self._challenger_rt = None
            self.lbl_challenger.config(text="—  (no STEP / current default)")
            self._btn_use_challenger.config(state="disabled")
            return
        self._challenger_rt = float(val)
        try:
            cur = float(self.entry_rt.get())
            delta = f"   Δ {self._challenger_rt - cur:+.2f} vs current"
        except (ValueError, tk.TclError):
            delta = ""
        self.lbl_challenger.config(text=f"{self._challenger_rt:.2f} mm{delta}")
        self._btn_use_challenger.config(state="normal")

    def _use_challenger_rt(self):
        """Copy the challenger reach into the editable Rr field (opt-in A/B test)."""
        if self._challenger_rt is None:
            return
        self.entry_rt.delete(0, "end")
        self.entry_rt.insert(0, f"{self._challenger_rt:.2f}")
        self._refresh_challenger(  # refresh Δ read-out against the new value
            self._tools_data.get(self.tool_var.get().split()[0], {})
            if not self.tool_var.get().startswith("(manual)") else None)
        self._redraw()

    # ═════════════════════════════════════════════════════════════════════
    # Session persistence
    # ═════════════════════════════════════════════════════════════════════

    def _on_close(self):
        self._save_last_session()
        self.destroy()

    def _save_last_session(self):
        import json, os, datetime
        data = {
            "saved_at": datetime.datetime.now().strftime("%Y-%m-%d  %H:%M"),
            "entry_z":        self.entry_z.get(),
            "entry_x":        self.entry_x.get(),
            "surface":        self.surface_var.get(),
            "entry_blank_t":  self.entry_blank_t.get(),
            "tool_var":       self.tool_var.get(),
            "entry_rt":       self.entry_rt.get(),
            "entry_angle":    self.entry_angle.get(),
            "zref":           self.zref_var.get(),
            "entry_cam_z":    self.entry_cam_z.get(),
            "entry_mach_z":   self.entry_mach_z.get(),
            "entry_z2":       self.entry_z2.get(),
            "entry_x2":       self.entry_x2.get(),
        }
        self.app.params["calibration_last_session"] = data
        try:
            cfg_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), "settings.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, encoding="utf-8") as f:
                    file_data = json.load(f)
                file_data["calibration_last_session"] = data
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(file_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _load_last_session(self):
        last = self.app.params.get("calibration_last_session", {})
        if not last:
            return

        def _fill(entry, key):
            val = last.get(key, "")
            if val == "":
                return
            try:
                cur_state = str(entry.cget("state"))
                entry.config(state="normal")
                entry.delete(0, "end")
                entry.insert(0, str(val))
                if cur_state == "disabled":
                    entry.config(state="disabled")
            except tk.TclError:
                pass

        _fill(self.entry_z,       "entry_z")
        _fill(self.entry_x,       "entry_x")
        _fill(self.entry_blank_t, "entry_blank_t")

        if last.get("surface"):
            self.surface_var.set(last["surface"])

        if last.get("tool_var"):
            self.tool_var.set(last["tool_var"])
            if not last["tool_var"].startswith("(manual)"):
                self._on_tool_selected()   # auto-fills Rr and angle from library

        # Restore last-used Rr override (operator may have hand-edited it)
        _fill(self.entry_rt, "entry_rt")
        # Re-sync the challenger Δ read-out against the restored Rr override
        if last.get("tool_var") and not last["tool_var"].startswith("(manual)"):
            self._refresh_challenger(self._tools_data.get(last["tool_var"].split()[0], {}))
        # Do NOT restore contact angle — always keep 0° (r_tool is already
        # the effective reach; restoring a stale 45° causes a double-correction)

        if last.get("zref"):
            self.zref_var.set(last["zref"])
            self._on_zref_change()   # sets entry_cam_z state
            if last["zref"] == "custom":
                _fill(self.entry_cam_z, "entry_cam_z")

        _fill(self.entry_mach_z, "entry_mach_z")
        _fill(self.entry_z2,     "entry_z2")
        _fill(self.entry_x2,     "entry_x2")

        saved_at = last.get("saved_at", "")
        suffix = f"  ({saved_at})" if saved_at else ""
        self.lbl_last_session.config(
            text=f"⏮  Values from last session{suffix}  —  verify before calculating")
        self._redraw()

    def _show_roller_preview(self):
        sel = self.tool_var.get()
        if sel.startswith("(manual)"):
            tool = {"id": "manual", "name": "Manual entry",
                    "radius": 150.0, "step_rotation": [0.0, 0.0, 0.0]}
        else:
            tid  = sel.split()[0]
            tool = self._tools_data.get(tid, {})
        try:
            r_t = max(0.1, float(self.entry_rt.get()))
        except (ValueError, tk.TclError):
            r_t = self._roller_r()
        try:
            angle_deg = float(self.entry_angle.get())
        except (ValueError, tk.TclError):
            angle_deg = 0.0
        from ui.dialogs.roller_preview import RollerPreviewDialog
        RollerPreviewDialog(self, tool, r_t, angle_deg)

    def _toggle_flip_z(self):
        self._flip_z[0] = not self._flip_z[0]
        self._save_view_prefs()
        self._update_orient_buttons()
        self._redraw()

    def _toggle_flip_x(self):
        self._flip_x[0] = not self._flip_x[0]
        self._save_view_prefs()
        self._update_orient_buttons()
        self._redraw()

    def _update_orient_buttons(self):
        active_bg   = "#2255aa"
        inactive_bg = "#1e2a3a"
        self._btn_fz.config(bg=active_bg if self._flip_z[0] else inactive_bg)
        self._btn_fx.config(bg=active_bg if self._flip_x[0] else inactive_bg)

    def _save_view_prefs(self):
        if "calibration_view" not in self.app.params:
            self.app.params["calibration_view"] = {}
        self.app.params["calibration_view"]["flip_z"] = self._flip_z[0]
        self.app.params["calibration_view"]["flip_x"] = self._flip_x[0]
        try:
            import json, os
            cfg_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))), "settings.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, encoding="utf-8") as f:
                    data = json.load(f)
                data["calibration_view"] = self.app.params["calibration_view"]
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════════
    # Formula reference popup
    # ═════════════════════════════════════════════════════════════════════

    def _show_formula_reference(self):
        win = tk.Toplevel(self)
        win.title("Calibration — Formula Reference")
        win.geometry("720x700")
        win.configure(bg="#0d1520")
        win.resizable(True, True)

        frm = tk.Frame(win, bg="#0d1520")
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        sb = tk.Scrollbar(frm)
        sb.pack(side="right", fill="y")

        txt = tk.Text(frm, font=("Consolas", 9), bg="#060d18", fg="#aabbcc",
                      relief="flat", bd=0, wrap="word",
                      yscrollcommand=sb.set, state="normal",
                      highlightthickness=0, padx=10, pady=8)
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)

        txt.tag_config("h1",  font=("Consolas", 11, "bold"), foreground="#ffffff")
        txt.tag_config("h2",  font=("Consolas",  9, "bold"), foreground="#88aaff")
        txt.tag_config("sep", foreground="#2a4060")
        txt.tag_config("key", foreground="#ffcc44")
        txt.tag_config("val", foreground="#88ffaa")
        txt.tag_config("cmt", foreground="#6688aa", font=("Consolas", 8))
        txt.tag_config("ok",  foreground="#44ff88")
        txt.tag_config("err", foreground="#ff6644")
        txt.tag_config("hi",  foreground="#ffffff", font=("Consolas", 9, "bold"))

        def h1(s):  txt.insert("end", s + "\n", "h1")
        def h2(s):  txt.insert("end", s + "\n", "h2")
        def sep():  txt.insert("end", "─" * 72 + "\n", "sep")
        def ln(s=""):  txt.insert("end", s + "\n")
        def cmt(s): txt.insert("end", "  " + s + "\n", "cmt")
        def kv(k, v, comment=""):
            txt.insert("end", f"  {k:<32}", "key")
            txt.insert("end", f"{v}", "val")
            if comment:
                txt.insert("end", f"   ← {comment}", "cmt")
            txt.insert("end", "\n")

        h1("CALIBRATION FORMULA REFERENCE")
        sep()
        ln()

        # ── Overview ──────────────────────────────────────────────────────
        h2("OVERVIEW")
        sep()
        ln("  Calibration checks whether the machine's coordinate system agrees with")
        ln("  the physical reality of where the roller actually touches a surface.")
        ln()
        ln("  You manually jog the roller to touch a known surface (mandrel or blank),")
        ln("  read the DRO X and Z, and enter them here. The tool calculates where")
        ln("  the machine *should* have been according to the STEP model and current")
        ln("  settings, then reports the difference (Delta).")
        ln()
        txt.insert("end", "  Delta ≈ 0  →  calibrated — model and machine agree\n", "ok")
        txt.insert("end", "  Delta ≠ 0  →  a setting is wrong — the tool tells you which one\n", "err")
        ln()

        # ── Origin mode ────────────────────────────────────────────────────
        h2("ORIGIN MODE  (most important concept)")
        sep()
        ln("  Every formula needs an 'origin' — the CAM reference point that maps to")
        ln("  the machine coordinate system. There are two modes (Machine Tab toggle):")
        ln()
        txt.insert("end", "  ★ Use Home as Origin  (your current mode)\n", "hi")
        ln("    origin_x = Program Start X   (the X value the G-code sends on startup)")
        ln("    origin_z = Program Start Z   (the Z value the G-code sends on startup)")
        ln()
        cmt("Program Start X/Z = home_x / home_z in settings. This is the machine's")
        cmt("retract / safe position. When you adjust 'Program Start X' in Machine Tab,")
        cmt("you are shifting the entire coordinate system. This is the most common")
        cmt("calibration correction — you were doing this manually before.")
        ln()
        txt.insert("end", "  ○ Use Machine Origin  (alternative mode)\n", "key")
        ln("    origin_x = Machine Origin X  (a fixed machine-zero reference)")
        ln("    origin_z = Machine Origin Z")
        cmt("Used when the machine has a fixed absolute origin separate from home.")
        ln()

        # ── Manual inputs ─────────────────────────────────────────────────
        h2("WHAT YOU ENTER MANUALLY")
        sep()
        kv("Machine Z at touch",    "DRO Z reading",    "Z on controller display at the moment of contact")
        kv("Machine X at touch",    "DRO X reading",    "X on controller display at the moment of contact")
        kv("Surface touched",       "Mandrel / Blank",  "mandrel = bare mandrel surface  |  blank = sheet on mandrel")
        kv("Blank thickness (mm)",  "e.g. 1.0",         "only used when Surface = Blank; ignored for mandrel touch")
        ln()

        # ── Automatic inputs ──────────────────────────────────────────────
        h2("WHAT COMES FROM THE SYSTEM (automatic)")
        sep()
        kv("Mandrel R at Z",        "from STEP model",   "your Machine Z → CAM Z → STEP model radius lookup")
        kv("Roller Rr  (r_tool)",   "from Tool Library", "effective radial reach — NOT the disc outer radius")
        ln()
        cmt("r_tool is the real distance from the machine's X reference to the roller")
        cmt("contact point, already accounting for disc tilt and mounting geometry.")
        cmt("It must be measured on the real machine — the STEP file cannot give you this.")
        cmt("Set it once per tool in the Tool Manager → Rr / r_tool field.")
        ln()
        kv("Contact angle",         "always 0°",         "r_tool already includes tilt; no cos() correction applied")
        ln()

        # ── X formula ─────────────────────────────────────────────────────
        h2("X-AXIS CALIBRATION — STEP BY STEP")
        sep()
        ln()
        txt.insert("end", "  Step 1 — Convert Machine Z (DRO) → CAM Z:\n", "h2")
        txt.insert("end", "    CAM Z = (Machine Z − gcode_offset_z) / dir_z + Program Start Z\n\n", "val")

        txt.insert("end", "  Step 2 — Look up mandrel radius at that CAM Z from STEP model:\n", "h2")
        txt.insert("end", "    mandrel_R = STEP_model.radius(CAM Z)\n\n", "val")

        txt.insert("end", "  Step 3 — Compute where the roller centre should be (CAM space):\n", "h2")
        txt.insert("end", "    Mandrel touch:  cam_X = mandrel_offset + side × (mandrel_R + r_tool)\n", "val")
        txt.insert("end", "    Blank touch:    cam_X = mandrel_offset + side × (mandrel_R + blank_t + r_tool)\n\n", "val")
        cmt("The roller centre must be r_tool beyond the surface so the roller edge")
        cmt("just touches it. That is the geometric meaning of r_tool.")
        ln()

        txt.insert("end", "  Step 4 — Convert CAM roller position → Expected machine DRO X:\n", "h2")
        txt.insert("end", "    Expected X = (cam_X − Program Start X) × dir_x + gcode_offset_x\n\n", "val")
        cmt("Program Start X is the origin. When cam_X = Program Start X, machine X = 0.")
        cmt("Shifting Program Start X shifts everything — that is why it is the main")
        cmt("calibration knob.")
        ln()

        txt.insert("end", "  Step 5 — Compare with what the DRO actually showed:\n", "h2")
        txt.insert("end", "    Delta X = Actual DRO X − Expected X\n\n", "val")
        txt.insert("end", "    ", ""); txt.insert("end", "Delta ≈ 0  →  CALIBRATED\n", "ok")
        txt.insert("end", "    Delta > 0  →  roller was further from spindle than model predicts\n", "err")
        txt.insert("end", "    Delta < 0  →  roller was closer to spindle than model predicts\n", "err")
        ln()

        # ── X parameters ──────────────────────────────────────────────────
        h2("PARAMETERS INVOLVED IN X-AXIS")
        sep()
        kv("Program Start X  (home_x)",  "Machine Tab",        "★ most important — shifts entire X coordinate system")
        cmt("This is origin_x in the formula. Adjusting this is what you were")
        cmt("doing manually before using this calibration tool.")
        kv("dir_x",                      "+1 or −1",           "machine_invert_x in Machine Tab")
        cmt("+1: increasing DRO X = roller moves away from spindle")
        cmt("−1: increasing DRO X = roller moves toward spindle")
        kv("gcode_offset_x",             "usually 0",          "machine_gcode_offset_x — fixed offset added to all X outputs")
        kv("mandrel_offset",             "usually 0",          "mandrel_pos_x_offset — only non-zero if mandrel is off-centre")
        kv("side",                       "+1 or −1",           "roller_positive_x_side — which side of spindle roller is on")
        kv("r_tool  (Rr)",               "Tool Library",       "effective radial reach per tool — measured on machine")
        kv("blank_t",                    "entered in dialog",   "also saved as final_part_thickness_on_mandrel in Process Tab")
        ln()

        # ── Corrections ───────────────────────────────────────────────────
        h2("SUGGESTED CORRECTIONS  (apply only ONE per measurement)")
        sep()
        ln()
        txt.insert("end", "  ★ New Program Start X  =  Program Start X − Delta / dir_x\n", "hi")
        cmt("This is what you were adjusting manually before. Use this when the")
        cmt("machine's home/retract position reference is off.")
        cmt("Most common correction. Affects every X move in the program.")
        ln()
        txt.insert("end", "  New Mandrel Offset  =  mandrel_offset + Delta / dir_x\n", "val")
        cmt("Use when the mandrel is physically not centred on the spindle axis.")
        cmt("Does not change Program Start X — only shifts where the mandrel is in CAM.")
        ln()
        txt.insert("end", "  New Blank Thickness  =  blank_t + Delta × side / dir_x\n", "val")
        cmt("Use only when Program Start X is known correct and the blank thickness")
        cmt("entered does not match the real sheet metal thickness.")
        ln()

        # ── Z formula ─────────────────────────────────────────────────────
        h2("Z-AXIS CALIBRATION — STEP BY STEP")
        sep()
        ln()
        ln("  Jog the roller to a known axial position (mandrel root or tip).")
        ln("  Enter the known CAM Z reference and the actual DRO Z.")
        ln()
        txt.insert("end", "  Expected Z = (CAM Z ref − Program Start Z) × dir_z + gcode_offset_z\n", "val")
        txt.insert("end", "  Delta Z    = Actual DRO Z − Expected Z\n\n", "val")
        kv("Program Start Z  (home_z)",  "Machine Tab",  "★ Z origin — same role as Program Start X but for Z axis")
        kv("dir_z",                      "+1 or −1",     "machine_invert_z in Machine Tab")
        kv("gcode_offset_z",             "usually 0",    "machine_gcode_offset_z")
        ln()
        txt.insert("end", "  ★ New Program Start Z  =  Program Start Z − Delta / dir_z\n", "hi")
        cmt("Apply this correction if Z is off. Same logic as X.")
        ln()

        # ── Settings map ──────────────────────────────────────────────────
        h2("QUICK SETTINGS REFERENCE")
        sep()
        kv("Program Start X / Z",         "Machine Tab → Program Start X / Z",   "= home_x / home_z")
        kv("Invert X / Z",                "Machine Tab → Invert X / Invert Z",    "= dir_x / dir_z")
        kv("G-code Offset X / Z",         "Machine Tab → G-code Offset X / Z",   "= gcode_offset_x / z")
        kv("Use Home as Origin",           "Machine Tab → origin mode toggle",     "if ON: origin = Program Start X/Z")
        kv("Machine Origin X / Z",        "Machine Tab → Machine Origin X / Z",   "used only when Use Home as Origin = OFF")
        kv("Roller Side",                  "Machine Tab → Roller Side toggle",     "= roller_positive_x_side → side +1 or −1")
        kv("Mandrel Offset X",             "Machine Tab → Mandrel Offset X",       "= mandrel_pos_x_offset")
        kv("Blank Thickness",              "Process Tab → Blank Thickness",        "= final_part_thickness_on_mandrel")
        kv("Rr / r_tool  (per tool)",      "Tool Manager → Rr / r_tool field",     "set once; auto-fills in calibration dialog")
        ln()

        txt.config(state="disabled")
        tk.Button(win, text="Close", command=win.destroy,
                  bg="#1e2a3a", fg="#88aacc", font=("Arial", 8)).pack(pady=6)

    # ═════════════════════════════════════════════════════════════════════
    # Calculate
    # ═════════════════════════════════════════════════════════════════════

    def _calculate(self):
        self.lbl_apply.config(text="")
        self.lbl_consist.config(text="")
        self._clear_state()
        self._update_mode_label()

        p      = self.app.params
        lines  = []
        worst  = 0.0   # for result text colour

        # ── X axis ───────────────────────────────────────────────────────
        x_ok = False
        try:
            tz_mach = float(self.entry_z.get())   # machine DRO Z
            tz      = self._mach_to_cam_z(tz_mach)  # CAM Z for mandrel lookup
            mx = float(self.entry_x.get())
            x_ok = True
        except ValueError:
            lines.append("  X: enter valid numbers for Machine Z at touch and Machine X.")

        if x_ok and self._mandrel_r(tz) is None:
            lines.append("  X: no mandrel profile — load a STEP file first.")
            x_ok = False

        if x_ok:
            surface = self.surface_var.get()
            exp_x, dx, side, dir_x = self._compute_x_delta(tz, mx, surface)
            if exp_x is not None:
                r   = self._mandrel_r(tz)
                cx  = float(p.get("mandrel_pos_x_offset", 0.0))
                hx  = float(p.get("home_x", 0.0))

                # Read display values from entry fields (same source as _compute_x_delta)
                try:
                    r_t_disc = max(0.1, float(self.entry_rt.get()))
                except (ValueError, tk.TclError):
                    r_t_disc = self._roller_r()
                try:
                    _ang_disp = float(self.entry_angle.get())
                    r_t_eff   = r_t_disc * math.cos(math.radians(_ang_disp))
                except (ValueError, tk.TclError):
                    _ang_disp = 0.0
                    r_t_eff   = r_t_disc
                r_t_eff = max(0.1, r_t_eff)
                try:
                    blank = max(0.0, float(self.entry_blank_t.get()))
                except (ValueError, tk.TclError):
                    blank = float(p.get("final_part_thickness_on_mandrel", p.get("shell_thickness", 0.0)))

                nhx  = round(hx - dx / dir_x, 4)
                ncx  = round(cx + dx / dir_x, 4)
                nblk = round(blank + (dx / dir_x) * side, 4)

                self._x_delta = dx;  self._x_side = side;  self._x_dir_x = dir_x
                self._x_surface = surface
                self._new_home_x  = nhx
                self._new_cx      = ncx
                self._new_blank   = nblk if nblk >= 0 else None  # suppress if nonsensical
                worst = max(worst, abs(dx))
                surf_s = "Mandrel" if surface == "mandrel" else "Blank"

                ang_line = (f"  Roller angle:        {_ang_disp:>9.1f} °"
                            f"  → eff. R = {r_t_eff:.3f} mm")
                blk_line = (f"  Blank thickness:     {blank:>9.3f} mm" if surface == "blank"
                            else f"  Blank thickness:          (mandrel touch — not used)")
                lines += [
                    f"  ── X-AXIS  ({surf_s} touch at Z={tz:.1f} mm) ──────────────",
                    f"  Mandrel R at Z:      {r:>9.3f} mm",
                    f"  Roller R (disc):     {r_t_disc:>9.3f} mm",
                    ang_line,
                    blk_line,
                    f"  Expected machine X:  {exp_x:>9.3f} mm",
                    f"  Machine X (DRO):     {mx:>9.3f} mm",
                    f"  Delta X:             {dx:>+9.3f} mm  {'OK' if abs(dx)<0.5 else '← CHECK'}",
                    f"  {'─'*48}",
                    f"  Program Start X:  {hx:>9.3f}  →  {nhx:>9.3f} mm",
                    f"  Mandrel Offset:   {cx:>9.3f}  →  {ncx:>9.3f} mm",
                ] + (
                    [f"  Blank Thickness:  {blank:>9.3f}  →  {nblk:>9.3f} mm"]
                    if nblk >= 0 else
                    [f"  Blank Thickness:  (would be {nblk:.3f} mm — not applicable)"]
                )

        lines.append("")

        # ── Z axis ───────────────────────────────────────────────────────
        z_ok = False
        try:
            cam_z_ref = float(self.entry_cam_z.get())
            mz        = float(self.entry_mach_z.get())
            z_ok = True
        except ValueError:
            lines.append("  Z: enter valid numbers for CAM Z and Machine Z.")

        if z_ok:
            exp_z, dz, dir_z = self._compute_z_delta(cam_z_ref, mz)
            _, _, _, _, _, off_z = self._machine_params()
            hz     = float(p.get("home_z", 0.0))
            nhz    = round(hz    - dz / dir_z, 4)
            noffz  = round(off_z - dz,          4)
            self._z_delta = dz;  self._z_dir_z = dir_z
            self._new_home_z = nhz;  self._new_off_z = noffz
            worst = max(worst, abs(dz))
            lines += [
                f"  ── Z-AXIS  (reference CAM Z = {cam_z_ref:.1f} mm) ───────────────",
                f"  Expected machine Z:  {exp_z:>9.3f} mm",
                f"  Machine Z (DRO):     {mz:>9.3f} mm",
                f"  Delta Z:             {dz:>+9.3f} mm  {'OK' if abs(dz)<0.5 else '← CHECK'}",
                f"  {'─'*48}",
                f"  Program Start Z:  {hz:>9.3f}  →  {nhz:>9.3f} mm",
                f"  G-code Z Offset:  {off_z:>9.3f}  →  {noffz:>9.3f} mm",
            ]

        col = self.C_ERR if worst > 2.0 else (self.C_WARN if worst > 0.5 else self.C_GOOD)
        self._set_results("\n".join(lines), col)
        self._refresh_apply_buttons()
        self._redraw()

    def _clear_state(self):
        for attr in ("_x_delta","_z_delta","_x_dir_x","_x_side","_z_dir_z",
                     "_new_home_x","_new_cx","_new_blank","_new_home_z","_new_off_z"):
            setattr(self, attr, None)

    # ═════════════════════════════════════════════════════════════════════
    # Apply buttons
    # ═════════════════════════════════════════════════════════════════════

    def _refresh_apply_buttons(self):
        use_home = bool(self.app.params.get("origin_use_home", False))

        def cfg(btn, value, label_base, recommended=False):
            if value is not None:
                bg  = "#44aa55" if recommended else "#2a5a3a"
                fg  = "white"   if recommended else "#aaccaa"
                txt = f"{'★ ' if recommended else '  '}{label_base}  →  {value:.3f} mm"
                btn.config(state="normal", bg=bg, fg=fg, text=txt)
            else:
                btn.config(state="disabled", bg="#445566", fg="#7799aa",
                           text=label_base)

        nhx = self._new_home_x;  ncx = self._new_cx;  nblk = self._new_blank
        nhz = self._new_home_z;  noz = self._new_off_z

        cfg(self.btn_home_x, nhx, "Program Start X", recommended=use_home)
        cfg(self.btn_offset,  ncx, "Mandrel Offset",  recommended=not use_home)
        cfg(self.btn_blank,  nblk, "Blank Thickness")
        cfg(self.btn_home_z, nhz,  "Program Start Z", recommended=use_home)
        cfg(self.btn_off_z,  noz,  "G-code Z Offset",  recommended=not use_home)

        if use_home:
            self.lbl_rec.config(
                text="Origin = Safe Home ON  →  ★ apply to Program Start X/Z (recommended)")
        else:
            self.lbl_rec.config(
                text="Fixed Origin mode  →  ★ Mandrel Offset (X) · G-code Z Offset (Z) recommended")

    def _apply_home_x(self):
        if self._new_home_x is None: return
        old = float(self.app.params.get("home_x", 0.0))
        self.app.on_param_change("home_x", self._new_home_x, "all")
        self._show_applied(f"Program Start X:  {old:.3f}  →  {self._new_home_x:.3f} mm")
        self._update_mode_label();  self._kill_x();  self._redraw()

    def _apply_offset(self):
        if self._new_cx is None: return
        old = float(self.app.params.get("mandrel_pos_x_offset", 0.0))
        self.app.on_param_change("mandrel_pos_x_offset", self._new_cx, "all")
        self._show_applied(f"Mandrel Offset:  {old:.3f}  →  {self._new_cx:.3f} mm")
        self._kill_x();  self._redraw()

    def _apply_blank(self):
        if self._new_blank is None: return
        if self._new_blank < 0:
            messagebox.showwarning("Invalid",
                f"Blank thickness ({self._new_blank:.3f} mm) is negative.\n"
                "Check the surface type selection.", parent=self)
            return
        old = float(self.app.params.get("final_part_thickness_on_mandrel", 2.0))
        self.app.on_param_change("final_part_thickness_on_mandrel", self._new_blank, "paths")
        self._show_applied(f"Blank Thickness:  {old:.3f}  →  {self._new_blank:.3f} mm")
        self._kill_x();  self._redraw()

    def _apply_home_z(self):
        if self._new_home_z is None: return
        old = float(self.app.params.get("home_z", 0.0))
        self.app.on_param_change("home_z", self._new_home_z, "all")
        self._show_applied(f"Program Start Z:  {old:.3f}  →  {self._new_home_z:.3f} mm")
        self._update_mode_label();  self._kill_z();  self._redraw()

    def _apply_off_z(self):
        if self._new_off_z is None: return
        old = float(self.app.params.get("machine_gcode_offset_z", 0.0))
        self.app.on_param_change("machine_gcode_offset_z", self._new_off_z, "all")
        self._show_applied(f"G-code Z Offset:  {old:.3f}  →  {self._new_off_z:.3f} mm")
        self._kill_z();  self._redraw()

    def _show_applied(self, msg):
        self.lbl_apply.config(text="✓  " + msg, fg="lime")

    def _kill_x(self):
        for b in (self.btn_home_x, self.btn_offset, self.btn_blank):
            b.config(state="disabled", bg="#445566", fg="#7799aa")
        self._x_delta = None

    def _kill_z(self):
        for b in (self.btn_home_z, self.btn_off_z):
            b.config(state="disabled", bg="#445566", fg="#7799aa")
        self._z_delta = None

    # ═════════════════════════════════════════════════════════════════════
    # Results text
    # ═════════════════════════════════════════════════════════════════════

    def _set_results(self, text, color=None):
        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", "end")
        self.txt_results.insert("1.0", text)
        if color:
            self.txt_results.config(fg=color)
        self.txt_results.config(state="disabled")

    # ═════════════════════════════════════════════════════════════════════
    # Second touch
    # ═════════════════════════════════════════════════════════════════════

    def _check_consistency(self):
        if self._x_delta is None:
            messagebox.showinfo("Calculate first",
                                "Complete Calculate before checking consistency.", parent=self)
            return
        try:
            z2_mach = float(self.entry_z2.get())
            z2      = self._mach_to_cam_z(z2_mach)  # CAM Z
            x2 = float(self.entry_x2.get())
        except ValueError:
            messagebox.showwarning("Input Error",
                                   "Enter valid numbers for the second touch point.", parent=self)
            return
        if self._mandrel_r(z2) is None:
            messagebox.showwarning("No Mandrel", "No mandrel profile loaded.", parent=self)
            return
        surface2 = self._x_surface or "mandrel"   # match surface used in first calculate
        _, d2, _, _ = self._compute_x_delta(z2, x2, surface2)
        if d2 is None: return
        diff = abs(d2 - self._x_delta)
        surf_lbl = "blank" if surface2 == "blank" else "mandrel"
        if diff < 0.3:
            msg = f"✓ Consistent ({surf_lbl})   Δ1={self._x_delta:+.3f}  Δ2={d2:+.3f}  diff={diff:.3f} mm"
            col = "lime"
        else:
            msg = (f"⚠ Inconsistent ({surf_lbl})  Δ1={self._x_delta:+.3f}  Δ2={d2:+.3f}  "
                   f"diff={diff:.3f} mm  → STEP may not match real mandrel")
            col = "#ff6633"
        self.lbl_consist.config(text=msg, fg=col)

    # ═════════════════════════════════════════════════════════════════════
    # Canvas — main drawing
    # ═════════════════════════════════════════════════════════════════════

    def _get_tool_profile_pts(self, tid, side):
        """Return ordered (x_can, z_can) convex-hull points of the tool XZ silhouette.
        Delegates to ToolStepLoader.get_2d_profile which applies step_rotation WITHOUT
        the shaft→Y correction, so the disc appears at its true physical tilt in XZ."""
        cache_key = (tid, int(side))
        if not hasattr(self, "_profile_cache"):
            self._profile_cache = {}
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]
        tool_data = self._tools_data.get(tid, {})
        loader    = getattr(self.app, "tool_step_loader", None)
        result    = None
        if loader is not None:
            try:
                result = loader.get_2d_profile(tool_data, side)
            except Exception:
                result = None
        self._profile_cache[cache_key] = result
        return result

    def _draw_scene(self, C, W, H, zoom, pan):
        """XZ cross-section — orientation matches the 3D view:
          Z runs left→right (left = root/start, right = tip/end).
          Radial direction runs top→bottom (top = spindle axis, bottom = outward/roller).
        So the mandrel body fills from the axis downward, and the roller sits below it.
        """
        p      = self.app.params
        cx_man = float(p.get("mandrel_pos_x_offset", 0.0))
        try:
            blank = max(0.0, float(self.entry_blank_t.get()))
        except (ValueError, tk.TclError):
            blank = float(p.get("final_part_thickness_on_mandrel", p.get("shell_thickness", 0.0)))
        try:
            r_t = max(0.1, float(self.entry_rt.get()))
        except (ValueError, tk.TclError):
            r_t = self._roller_r()
        try:
            _ang = float(self.entry_angle.get())
            r_t = r_t * math.cos(math.radians(_ang))  # effective radial offset
        except (ValueError, tk.TclError):
            pass
        r_t = max(0.1, r_t)
        side   = 1.0 if p.get("roller_positive_x_side", True) else -1.0
        prof_z, prof_r = self._mandrel_profile()

        z_min = min(prof_z);  z_max = max(prof_z)
        r_max = max(prof_r)

        # ── Scene extents ─────────────────────────────────────────────────
        zm   = (z_max - z_min) * 0.18
        zlo  = z_min - zm;  zhi = z_max + zm
        zrng = max(zhi - zlo, 1.0)

        # x_top  → canvas TOP  (axis side, away from roller)
        # x_bot  → canvas BOTTOM (roller side)
        # Show the full mandrel diameter on both sides so the roller looks
        # proportionally correct (was 0.25*r_max = only a sliver above axis).
        x_top = cx_man - side * r_max * 1.15       # axis side — full mandrel + margin
        x_bot = cx_man + side * (r_max + blank + r_t * 2.6)  # roller side
        # Signed span: positive when side>0, negative when side<0.
        # _base() uses division by signed span so the direction is always correct.
        x_signed_span = x_bot - x_top
        if abs(x_signed_span) < 1.0:
            x_signed_span = 1.0 if x_signed_span >= 0 else -1.0

        ML, MR, MT, MB = 24, 18, 30, 36

        zcx, zcy = W / 2, H / 2

        flip_z = self._flip_z[0]
        flip_x = self._flip_x[0]

        def _base(cam_z, cam_x):
            tz = (zhi - cam_z) if flip_z else (cam_z - zlo)
            bx = ML + tz / zrng * (W - ML - MR)
            frac = (cam_x - x_top) / x_signed_span  # 0 = axis/top, 1 = roller/bottom
            if flip_x:
                frac = 1.0 - frac
            by = MT + frac * (H - MT - MB)
            return bx, by

        def zp(cam_z, cam_x):
            bx, by = _base(cam_z, cam_x)
            return zcx + (bx - zcx) * zoom + pan[0], zcy + (by - zcy) * zoom + pan[1]

        def zlw(b):  return max(1, int(b * zoom))
        def zsz(b):  return max(7, int(b * zoom))   # font size, scales with zoom
        def zoff(b): return max(2, int(b * zoom))   # pixel offset, scales with zoom

        px_per_cam = (W - ML - MR) / zrng * zoom   # pixels per CAM mm (horizontal)

        # ── Drawing primitives ────────────────────────────────────────────

        def _line(*pts_cam, color, width=1, dash=()):
            flat = []
            for cz, cx_ in pts_cam:
                flat += list(zp(cz, cx_))
            kw = dict(fill=color, width=zlw(width))
            if dash: kw["dash"] = dash
            C.create_line(*flat, **kw)

        def _poly(pts_cam, fill, outline, width=1):
            flat = []
            for cz, cx_ in pts_cam:
                flat += list(zp(cz, cx_))
            C.create_polygon(*flat, fill=fill, outline=outline, width=zlw(width))

        def _text(cam_z, cam_x, txt, color, anchor="center", sz=8, bold=False):
            bx, by = zp(cam_z, cam_x)
            C.create_text(bx, by, text=txt, fill=color,
                         font=("Consolas", zsz(sz), "bold" if bold else "normal"),
                         anchor=anchor)

        def _vline(cam_z, color, width=1, dash=()):
            bx, y_top_px = zp(cam_z, x_top)
            _,  y_bot_px = zp(cam_z, x_bot)
            kw = dict(fill=color, width=zlw(width))
            if dash: kw["dash"] = dash
            C.create_line(bx, y_top_px, bx, y_bot_px, **kw)

        def _hline(cam_x, color, width=1, dash=()):
            x0, by = zp(zlo, cam_x)
            x1, _  = zp(zhi, cam_x)
            kw = dict(fill=color, width=zlw(width))
            if dash: kw["dash"] = dash
            C.create_line(x0, by, x1, by, **kw)

        def canvas_top_y(cam_z):
            _, y = zp(cam_z, x_top);  return y

        def canvas_bot_y(cam_z):
            _, y = zp(cam_z, x_bot);  return y

        def dim_v(cam_z, cam_x1, cam_x2, label, color, right=True):
            """Dimension bracket between two X values at fixed Z."""
            px1, py1 = zp(cam_z, cam_x1)
            px2, py2 = zp(cam_z, cam_x2)
            off = zoff(18) if right else -zoff(18)
            tk  = zoff(4)
            for py in (py1, py2):
                C.create_line(px1-tk, py, px1+tk, py, fill=color, width=1)
            C.create_line(px1, py1, px1, py2, fill=color, width=1, dash=(3, 3))
            C.create_text(px1 + off, (py1+py2)/2, text=label, fill=color,
                         font=("Consolas", zsz(7)), anchor="w" if right else "e")

        # ── Fixed axis labels (pixel space — not affected by zoom/pan) ────
        # Z arrow along the bottom margin
        C.create_line(ML, H - 12, W - MR, H - 12,
                     fill=self.C_AX, width=1, arrow=tk.LAST)
        C.create_text(W - MR + 4, H - 12, text="Z →",
                     fill=self.C_LBL, font=("Consolas", 9, "bold"), anchor="w")
        # Z tick marks and grid hints
        for i in range(5):
            tz = zlo + i / 4 * zrng
            bx, _ = _base(tz, x_top)
            bx_s = zcx + (bx - zcx) * zoom + pan[0]
            C.create_line(bx_s, H - 16, bx_s, H - 8, fill=self.C_AX, width=1)
            C.create_text(bx_s, H - 6, text=f"{tz:.0f}",
                         fill=self.C_AX, font=("Consolas", max(6, int(6*zoom))), anchor="n")

        # X arrow along the left margin (points DOWN = outward)
        C.create_line(14, MT, 14, H - MB,
                     fill=self.C_AX, width=1, arrow=tk.LAST)
        C.create_text(7, MT - 6, text="axis",
                     fill=self.C_AX, font=("Consolas", 7), anchor="sw")
        C.create_text(7, H - MB + 4, text="out\n↓",
                     fill=self.C_AX, font=("Consolas", 7), anchor="nw")

        # ── Spindle axis horizontal line ───────────────────────────────────
        _hline(cx_man, self.C_AX, width=1, dash=(6, 4))
        bx_axlbl, by_axlbl = zp(zlo + zrng * 0.01, cx_man)
        C.create_text(bx_axlbl, by_axlbl - zoff(5), text="spindle axis",
                     fill=self.C_AX, font=("Consolas", zsz(7)), anchor="sw")

        # ── Mandrel polygon ───────────────────────────────────────────────
        surf_x  = [cx_man + side * r for r in prof_r]
        top_pts = list(zip(prof_z, surf_x))               # outer surface curve (roller side)
        bot_pts = [(z, cx_man) for z in reversed(prof_z)] # back along axis

        # Roller-side half
        _poly(top_pts + bot_pts, fill=self.C_MFILL, outline=self.C_MAND, width=2)

        # Mirror half (opposite side of axis) — same profile, flipped
        mir_surf = [(z, cx_man - side * r) for z, r in zip(prof_z, prof_r)]
        mir_axis = [(z, cx_man) for z in reversed(prof_z)]
        _poly(mir_surf + mir_axis, fill=self.C_MFILL, outline=self.C_MAND, width=1)

        # hatch lines (roller side only)
        hatch_n = max(8, int((W + H) / max(8, int(12 * zoom))))
        for i in range(hatch_n):
            hz_ = zlo + i / max(hatch_n - 1, 1) * zrng
            r_hz = (float(self._mandrel_r(hz_))
                    if self._mandrel_r(hz_) is not None else prof_r[0])
            ax_, ay_ = zp(hz_, cx_man + side * r_hz)
            bx_, by_ = zp(hz_, cx_man)
            if abs(ay_ - by_) > 3:
                C.create_line(ax_, ay_, bx_, by_, fill="#2a4060", width=1)

        _line(*top_pts, color=self.C_MAND, width=2)
        mid_i = len(prof_z) // 2
        _text(prof_z[mid_i], cx_man + side * r_max * 0.5,
              "MANDREL", self.C_MAND, sz=9, bold=True)

        # ── Blank ring ────────────────────────────────────────────────────
        if blank > 0.2:
            bk_outer = [(z, cx_man + side * (r + blank)) for z, r in zip(prof_z, prof_r)]
            _poly(bk_outer + list(reversed(top_pts)),
                  fill=self.C_BLANK, outline=self.C_BLINE, width=1)
            _line(*bk_outer, color=self.C_BLINE, width=1)
            _text(prof_z[mid_i], cx_man + side * (prof_r[mid_i] + blank / 2),
                  f"blank {blank:.1f} mm", self.C_BLINE, sz=7)

        # ── Machine origin reference lines ────────────────────────────────
        ox, oz, _, _, _, _ = self._machine_params()

        # Machine Z-origin: vertical dashed line + label at top
        bx_oz, _ = zp(oz, x_top)
        C.create_line(bx_oz, canvas_top_y(oz), bx_oz, canvas_bot_y(oz),
                     fill=self.C_HOMEZ, width=1, dash=(4, 4))
        C.create_text(bx_oz, canvas_top_y(oz) - zoff(4),
                     text=f"Z-origin {oz:.1f}", fill=self.C_HOMEZ,
                     font=("Consolas", zsz(7)), anchor="s")

        # Machine X-origin: horizontal dashed line + label at left
        _hline(ox, self.C_HOME, width=1, dash=(4, 4))
        bx_home0, bhy_home = zp(zlo, ox)
        C.create_text(bx_home0 - zoff(4), bhy_home, text=f"X-origin {ox:.1f}",
                     fill=self.C_HOME, font=("Consolas", zsz(7)), anchor="e")

        # ── Mandrel root / tip DRO labels ────────────────────────────────
        prof_z_list = list(prof_z)
        if len(prof_z_list) >= 2:
            root_cam_z = min(prof_z_list)
            tip_cam_z  = max(prof_z_list)
            root_mach_z = self._cam_to_mach_z(root_cam_z)
            tip_mach_z  = self._cam_to_mach_z(tip_cam_z)
            # draw small end-markers with machine-DRO Z so user knows what to type
            for cz, lbl in (
                    (root_cam_z, f"root\nDRO Z={root_mach_z:.1f}"),
                    (tip_cam_z,  f"tip\nDRO Z={tip_mach_z:.1f}")):
                bx_end, _ = zp(cz, x_top)
                C.create_line(bx_end, canvas_top_y(cz), bx_end, canvas_top_y(cz) - zoff(6),
                             fill=self.C_MAND, width=1)
                C.create_text(bx_end, canvas_top_y(cz) - zoff(7),
                             text=lbl, fill=self.C_MAND,
                             font=("Consolas", zsz(7)), anchor="s")

        # ── Parse live user inputs (independent: each can be None on its own) ─
        try:
            touch_mach_z = float(self.entry_z.get())
            touch_z      = self._mach_to_cam_z(touch_mach_z)
        except (ValueError, tk.TclError):
            touch_mach_z = touch_z = None

        try:
            touch_mx = float(self.entry_x.get())
        except (ValueError, tk.TclError):
            touch_mx = None

        try:
            cam_z_ref = float(self.entry_cam_z.get())
            touch_mz  = float(self.entry_mach_z.get())
        except (ValueError, tk.TclError):
            cam_z_ref = touch_mz = None

        # ── X-touch visualisation ─────────────────────────────────────────
        if touch_z is not None:
            r_at_z = self._mandrel_r(touch_z)
            if r_at_z is not None:
                surface    = self.surface_var.get()
                extra      = blank if surface == "blank" else 0.0
                cam_x_surf = cx_man + side * (r_at_z + extra)   # surface contact point
                cam_x_exp  = cx_man + side * (r_at_z + extra + r_t)  # roller centre

                py_per_cam = (H - MT - MB) / max(abs(x_signed_span), 1.0) * zoom
                r_px  = max(4, int(r_t * py_per_cam))
                r_px2 = max(2, int(3 * zoom))

                # Load tool profile from STEP (canonical: tip at origin, side already applied)
                _tid = None
                _sel = self.tool_var.get()
                if not _sel.startswith("(manual)"):
                    _tid = _sel.split()[0]
                _profile = self._get_tool_profile_pts(_tid, side) if _tid else None

                def _profile_flat(x_tip_cam, z_tip_cam):
                    """Canonical profile → flat canvas coords list. tip at (x_tip_cam, z_tip_cam)."""
                    flat = []
                    for px, pz in _profile:
                        cpx, cpy = zp(z_tip_cam + pz, x_tip_cam + px)
                        flat += [cpx, cpy]
                    return flat

                # Touch-Z vertical marker
                _vline(touch_z, self.C_TOUCH, width=1, dash=(2, 5))
                bx_tz, _ = zp(touch_z, x_top)
                C.create_text(bx_tz, canvas_bot_y(touch_z) + zoff(8),
                             text=f"Z touch\nDRO={touch_mach_z:.1f}" if touch_mach_z is not None else "Z touch",
                             fill=self.C_TOUCH, font=("Consolas", zsz(7)), anchor="n")

                # Mandrel surface contact point (small dot)
                bxs, bys = zp(touch_z, cam_x_surf)
                C.create_oval(bxs-r_px2, bys-r_px2, bxs+r_px2, bys+r_px2,
                             fill=self.C_MAND, outline="")

                # Expected roller — STEP profile (dashed green) or circle fallback
                bxe, bye = zp(touch_z, cam_x_exp)
                if _profile:
                    flat_exp = _profile_flat(cam_x_surf, touch_z)
                    C.create_polygon(flat_exp, fill="", outline=self.C_GOOD,
                                     width=zlw(2), dash=(4, 3))
                    lbl_y_exp = min(flat_exp[1::2]) - zoff(5)
                else:
                    C.create_oval(bxe-r_px, bye-r_px, bxe+r_px, bye+r_px,
                                 fill="", outline=self.C_GOOD, width=zlw(2), dash=(4, 3))
                    lbl_y_exp = bye - r_px - zoff(5)
                C.create_line(bxs, bys, bxe, bye, fill=self.C_GHOST, width=1, dash=(2, 4))
                C.create_text(bxe, lbl_y_exp,
                             text=f"expected\n(Rr {r_t:.1f} mm)", fill=self.C_GOOD,
                             font=("Consolas", zsz(7)), anchor="s")

                # Dimension brackets: mandrel R, blank, roller Rr
                z_ann = prof_z[0] + (z_max - z_min) * 0.06
                dim_v(z_ann, cx_man, cx_man + side * r_at_z,
                      f"R={r_at_z:.1f}", self.C_HDIM, right=(side > 0))
                if blank > 0.2:
                    dim_v(z_ann + (z_max - z_min) * 0.09,
                          cx_man + side * r_at_z,
                          cx_man + side * (r_at_z + blank),
                          f"blank {blank:.1f}", self.C_BLINE, right=(side > 0))
                dim_v(z_ann + (z_max - z_min) * 0.18,
                      cam_x_surf, cam_x_exp,
                      f"Rr={r_t:.1f}", self.C_ROLLER, right=(side > 0))

                if touch_mx is not None:
                    cam_x_actual = self._mach_to_cam_x(touch_mx)
                    bxa, bya = zp(touch_z, cam_x_actual)
                    # Measured tip = expected tip shifted by the delta
                    cam_delta   = cam_x_actual - cam_x_exp
                    x_tip_meas  = cam_x_surf + cam_delta

                    # Measured roller — STEP profile (yellow filled) or circle fallback
                    if _profile:
                        flat_meas = _profile_flat(x_tip_meas, touch_z)
                        C.create_polygon(flat_meas, fill=self.C_RFILL,
                                         outline=self.C_TOUCH, width=zlw(2))
                        lbl_y_meas = max(flat_meas[1::2]) + zoff(5)
                    else:
                        C.create_oval(bxa-r_px, bya-r_px, bxa+r_px, bya+r_px,
                                     fill=self.C_RFILL, outline=self.C_TOUCH, width=zlw(2))
                        lbl_y_meas = bya + r_px + zoff(5)
                    C.create_text(bxa, lbl_y_meas,
                                 text="measured", fill=self.C_TOUCH,
                                 font=("Consolas", zsz(7)), anchor="n")

                    # Delta error arrow: expected centre → measured centre
                    delta_x = touch_mx - self._cam_to_mach_x(cam_x_exp)
                    if abs(delta_x) > 0.05:
                        dc = self.C_ERR if abs(delta_x) > 2.0 else self.C_WARN
                        C.create_line(bxe, bye, bxa, bya,
                                     fill=dc, width=zlw(2), arrow=tk.LAST)
                        C.create_text((bxe+bxa)/2 + zoff(6), (bye+bya)/2,
                                     text=f"ΔX = {delta_x:+.2f} mm",
                                     fill=dc,
                                     font=("Consolas", zsz(8), "bold"), anchor="w")

        # ── Z-touch visualisation ──────────────────────────────────────────
        if cam_z_ref is not None:
            # Reference Z: green vertical, label at canvas top
            _vline(cam_z_ref, self.C_GOOD, width=2, dash=(5, 3))
            bx_ref, _ = zp(cam_z_ref, x_top)
            C.create_text(bx_ref, canvas_top_y(cam_z_ref) - zoff(8),
                         text=f"Ref Z\n{cam_z_ref:.1f} mm",
                         fill=self.C_GOOD, font=("Consolas", zsz(7)), anchor="s")

            if touch_mz is not None:
                cam_z_actual = self._mach_to_cam_z(touch_mz)
                # Measured Z: yellow vertical, label at canvas top
                _vline(cam_z_actual, self.C_TOUCH, width=2)
                bx_za, _ = zp(cam_z_actual, x_top)
                C.create_text(bx_za, canvas_top_y(cam_z_actual) - zoff(8),
                             text=f"Measured Z\n{cam_z_actual:.1f} mm",
                             fill=self.C_TOUCH, font=("Consolas", zsz(7)), anchor="s")

                # Delta Z arrow at mid-mandrel height
                delta_z = touch_mz - self._cam_to_mach_z(cam_z_ref)
                if abs(delta_z) > 0.05:
                    dc = self.C_ERR if abs(delta_z) > 2.0 else self.C_WARN
                    _, mid_y = zp(cam_z_ref, cx_man + side * r_max * 0.5)
                    bx_r, _ = zp(cam_z_ref,    cx_man + side * r_max * 0.5)
                    bx_a, _ = zp(cam_z_actual, cx_man + side * r_max * 0.5)
                    C.create_line(bx_r, mid_y, bx_a, mid_y,
                                 fill=dc, width=zlw(2), arrow=tk.LAST)
                    C.create_text((bx_r+bx_a)/2, mid_y - zoff(8),
                                 text=f"ΔZ = {delta_z:+.2f} mm",
                                 fill=dc,
                                 font=("Consolas", zsz(8), "bold"), anchor="s")

        # ── Legend ────────────────────────────────────────────────────────
        leg_entries = [
            (self.C_GOOD,   "Expected position (STEP)"),
            (self.C_TOUCH,  "Measured position (DRO)"),
            (self.C_ERR,    "Error > 2 mm"),
            (self.C_WARN,   "Caution 0.5–2 mm"),
            (self.C_HOMEZ,  "Machine Z-origin"),
            (self.C_HOME,   "Machine X-origin"),
        ]
        leg_sz  = max(6, int(7 * zoom))
        row_h   = max(12, int(14 * zoom))
        sw      = max(8,  int(10 * zoom))
        lx, ly  = W - 8, MT + 4
        for i, (col, txt) in enumerate(leg_entries):
            ey = ly + i * row_h
            C.create_rectangle(lx-152, ey, lx-152+sw, ey+int(sw*0.75),
                               fill=col, outline="")
            C.create_text(lx-152+sw+4, ey+int(sw*0.375), text=txt,
                         fill=self.C_LBL, font=("Consolas", leg_sz), anchor="w")

        # Hint at bottom
        C.create_text(W / 2, H - 20,
                     text="scroll = zoom  ·  drag = pan  ·  double-click = reset",
                     fill="#334455", font=("Consolas", 7), anchor="s")
