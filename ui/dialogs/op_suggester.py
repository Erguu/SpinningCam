import tkinter as tk
from tkinter import ttk, messagebox

from i18n import t, get_language
from process_planner import (load_materials, analyze_profile,
                             suggest_operations, save_default_materials)
from logger_config import logger


class OpSuggesterDialog(tk.Toplevel):
    """Advisory operation suggester (Program tab → Suggest).

    Shows a rule-based roughing+finishing proposal computed from the loaded
    mandrel profile and a material heuristic table. Nothing touches
    params["operations"] until the user presses Apply — review-first by design.
    """

    def __init__(self, parent, app, tool_library, on_apply):
        super().__init__(parent)
        self.app = app
        self.tool_library = tool_library
        self.on_apply = on_apply
        save_default_materials()  # give the operator a tunable file on first use
        self.materials = load_materials()
        self.result = None

        self.title(t("sug_title"))
        self.geometry("620x560")
        self.transient(parent)
        self.focus_force()

        self._create_widgets()
        self._recalculate()

    # ------------------------------------------------------------------
    def _mat_display(self, mat):
        name = mat.get("name", {})
        if isinstance(name, dict):
            return name.get(get_language(), name.get("EN", mat.get("id", "?")))
        return str(name)

    def _create_widgets(self):
        f_in = ttk.LabelFrame(self, text=t("sug_inputs"))
        f_in.pack(fill="x", padx=8, pady=6)

        ttk.Label(f_in, text=t("sug_material")).grid(row=0, column=0, sticky="w", padx=4, pady=3)
        self.cmb_material = ttk.Combobox(f_in, state="readonly", width=34,
                                         values=[self._mat_display(m) for m in self.materials])
        self.cmb_material.current(0)
        self.cmb_material.grid(row=0, column=1, sticky="w", padx=4, pady=3)
        self.cmb_material.bind("<<ComboboxSelected>>", lambda e: self._recalculate())

        ttk.Label(f_in, text=t("sug_blank_thick")).grid(row=1, column=0, sticky="w", padx=4, pady=3)
        self.ent_thick = ttk.Entry(f_in, width=10)
        self.ent_thick.insert(0, f"{float(self.app.params.get('final_part_thickness_on_mandrel', 2.0)):g}")
        self.ent_thick.grid(row=1, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(f_in, text=t("sug_blank_diam")).grid(row=2, column=0, sticky="w", padx=4, pady=3)
        self.ent_diam = ttk.Entry(f_in, width=10)
        try:
            _suggested = 2.0 * analyze_profile(self.app.mandrel_mgr)["blank_radius_suggested"]
            self.ent_diam.insert(0, f"{_suggested:.1f}")
        except Exception:
            self.ent_diam.insert(0, "0")
        self.ent_diam.grid(row=2, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(f_in, text=t("sug_diam_hint"), foreground="#666").grid(
            row=2, column=2, sticky="w", padx=4)

        btn_calc = ttk.Button(f_in, text=t("sug_calc"), command=self._recalculate)
        btn_calc.grid(row=3, column=1, sticky="w", padx=4, pady=5)

        # Bottom bar FIRST (side="bottom") so the Insert button can never be
        # clipped away when the window is resized small — the preview takes
        # whatever space remains.
        f_btn = ttk.Frame(self)
        f_btn.pack(side="bottom", fill="x", padx=8, pady=6)
        self.btn_apply = tk.Button(f_btn, text=t("sug_apply"),
                                   bg="#c8e6c9", activebackground="#a5d6a7",
                                   relief="raised", bd=1, padx=10,
                                   command=self._apply)
        self.btn_apply.pack(side="left", padx=4)
        ttk.Button(f_btn, text=t("sug_close"), command=self.destroy).pack(side="right", padx=4)

        ttk.Label(self, text=t("sug_disclaimer"), foreground="#b26500",
                  wraplength=580, justify="left").pack(side="bottom", fill="x", padx=8, pady=2)

        # Preview
        f_prev = ttk.LabelFrame(self, text=t("sug_preview"))
        f_prev.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt = tk.Text(f_prev, font=("Consolas", 9), state="disabled", wrap="word")
        _sb = ttk.Scrollbar(f_prev, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=_sb.set)
        _sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        self.txt.tag_config("head", font=("Consolas", 9, "bold"))
        self.txt.tag_config("warn", foreground="#b71c1c")
        self.txt.tag_config("dim", foreground="#666666")

    # ------------------------------------------------------------------
    def _read_inputs(self):
        try:
            thick = float(self.ent_thick.get().replace(",", "."))
        except ValueError:
            thick = None
        try:
            diam = float(self.ent_diam.get().replace(",", "."))
        except ValueError:
            diam = None
        mat = self.materials[self.cmb_material.current()]
        return mat, thick, diam

    def _recalculate(self):
        mat, thick, diam = self._read_inputs()
        try:
            self.result = suggest_operations(
                self.app.mandrel_mgr, self.app.params, mat,
                self.tool_library, blank_diameter=diam, blank_thickness=thick)
        except Exception as e:
            logger.error(f"Op suggestion failed: {e}")
            self.result = None
            self._set_text([(t("sug_err_profile"), "warn")])
            self.btn_apply.config(state="disabled")
            return
        self.btn_apply.config(state="normal")
        self._render_result()

    def _render_result(self):
        a = self.result["analysis"]
        lines = []
        lines.append((t("sug_h_analysis"), "head"))
        lines.append((f"  {t('sug_i_height')}: {a['height']:.1f} mm   "
                      f"Ø max: {2*a['r_max']:.1f} mm   Ø min: {2*a['r_min']:.1f} mm", None))
        lines.append((f"  {t('sug_i_bend')}: {a['max_bend_deg']:.1f}°", None))
        lines.append((f"  {t('sug_i_blank')}: Ø {a['blank_diameter']:.1f} mm × {a['blank_thickness']:g} mm   "
                      f"({t('sug_i_ratio')}: {a['spinning_ratio']:.2f})", None))
        lines.append(("", None))
        lines.append((t("sug_h_ops"), "head"))
        for i, op in enumerate(self.result["ops"]):
            lines.append((f"  {i+1}. {op['type'].upper()}  —  {t('col_tool')}: {op['tool_id']}", None))
            if op["type"] == "roughing":
                _fan_end = op.get("progressive_angle_end", 180.0)
                lines.append((f"       {t('sug_i_passes')}: {op['count']}   "
                              f"{t('sug_i_passangle')}: {op['pass_angle']}° → {_fan_end:.0f}°", None))
            lines.append((f"       Z: {op['start_z']:.1f} → {op['end_z']:.1f} mm   "
                          f"{t('sug_i_clearance')}: {op['clearance']:g} mm", None))
            _bp = t("sug_i_on") if op.get("back_pass_enabled") else t("sug_i_off")
            lines.append((f"       S: {op['speed']:.0f} RPM   F: {op['feed']:.0f} mm/min   "
                          f"{t('sug_i_backpass')}: {_bp}   {t('lbl_direction')}: {t('opt_forward')}", None))
        notes = self.result.get("notes", [])
        if notes:
            lines.append(("", None))
            lines.append((t("sug_h_why"), "head"))
            for key, kw in notes:
                try:
                    msg = t(key).format(**kw)
                except (KeyError, IndexError):
                    msg = t(key)
                lines.append((f"  • {msg}", "dim"))
        warns = self.result["warnings"]
        cur_thick = float(self.app.params.get("final_part_thickness_on_mandrel", 2.0))
        if abs(a["blank_thickness"] - cur_thick) > 1e-9:
            warns = warns + [("sug_warn_thickness", {"val": a["blank_thickness"]})]
        if warns:
            lines.append(("", None))
            lines.append((t("sug_h_warnings"), "head"))
            for key, kw in warns:
                try:
                    msg = t(key).format(**kw)
                except (KeyError, IndexError):
                    msg = t(key)
                lines.append((f"  ⚠ {msg}", "warn"))
        self._set_text(lines)

    def _set_text(self, lines):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        for text, tag in lines:
            self.txt.insert("end", text + "\n", tag or ())
        self.txt.config(state="disabled")

    # ------------------------------------------------------------------
    def _apply(self):
        if not self.result:
            return
        n = len(self.result["ops"])
        if not messagebox.askyesno(t("sug_title"), t("sug_confirm").format(n=n), parent=self):
            return
        a = self.result["analysis"]
        self.on_apply(self.result["ops"], a["blank_thickness"])
        self.destroy()
