# -*- coding: utf-8 -*-
"""Per-pass table (PROPOSAL_REACH_ANGLE_PRIORITY P1, TODO #80/#79).

One row per pass of an operation: contact Z, effective angle, effective reach,
exit endpoint, value SOURCE (manual / fan / follow / pin / legacy override) and
warnings (clearance-guard flip, near-duplicate pass, reach→0 fallback). The
compute half is pure (no Tk) and mirrors the engine formulas in
path_generator.calculate_paths — keep the two in sync.

Editing model (user decision 2026-07-07): staged. Double-click an editable cell
(angle / reach) stages a value; nothing touches the op until [Apply], which
writes ONE undo snapshot + op["pass_edits"]; [Cancel] discards the staging.
Pinned passes are engine-authoritative (see pass_edits in path_generator).
"""

import math
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from i18n import t
from logger_config import logger


# ──────────────────────────────────────────────────────────────────────────
# Pure computation (headless-testable)
# ──────────────────────────────────────────────────────────────────────────

def _f(v, default=None):
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def compute_pass_rows(op, params, mgr, gui_overrides=None, base_fwd_idx=0,
                      staged=None):
    """Effective per-pass values for ``op`` — mirrors the engine exactly.

    Returns a list of dicts: {i, z, angle, reach, p3x, p3z, end_x, end_z,
    source, pinned, legacy_override, warnings:[str]}. ``staged`` (dict
    {i: {"pass_angle":v, "reach":v}}) previews unapplied table edits.
    ``angle`` is None in RAW mode. Purely advisory — never mutates the op.
    """
    count = int(op.get("count", 1))
    if op.get("type") in ("cutting", "bending"):
        return []
    is_finish = op.get("type") == "finishing"
    staged = staged or {}
    gui_overrides = gui_overrides or {}

    top_z = float(mgr.props.get("top_z", 100.0))
    start_h = float(op.get("start_z", 10.0))
    end_h = float(op["end_z"]) if op.get("end_z") is not None else top_z

    p1_x = abs(_f(op.get("p1_x"), 40.0))
    p1_z = abs(_f(op.get("p1_z"), 50.0))
    def_p3_x = _f(op.get("p3_x"), p1_x)
    def_p3_z = abs(_f(op.get("p3_z"), -20.0) or 0.0)

    _rv = _f(op.get("reach"))
    reach_v = _rv if (_rv is not None and _rv > 0) else None
    pa_deg = _f(op.get("pass_angle"))
    prog_a = pa_deg is not None and bool(op.get("progressive_angle_enabled", False)) and count > 1
    prog_a_end = _f(op.get("progressive_angle_end"), 180.0) if prog_a else None
    prog_r = pa_deg is not None and bool(op.get("progressive_reach_enabled", False)) and count > 1
    follow = bool(op.get("reach_follow_blank", False)) and not is_finish
    fb_fac = _f(op.get("reach_blank_factor"), 1.0) or 1.0
    fb_off = _f(op.get("reach_blank_offset"), 0.0) or 0.0

    # Clearance (same resolution chain as the engine)
    op_clearance = op.get("clearance")
    if op_clearance is None:
        if is_finish:
            op_clearance = (_f(op.get("finish_allowance"), 0.0) or 0.0) + \
                           (_f(params.get("safety_clearance_roller_to_part"), 0.0) or 0.0)
        else:
            op_clearance = _f(params.get("target_clearance"), 0.0) or 0.0
    op_clearance = float(op_clearance)
    conformal = op.get("conformal_clearance_operation_specific",
                       params.get("conformal_clearance_all_operations", False))

    shape = op.get("pass_shape", "spline")
    if shape in ("linear_approach", "linear_full"):
        theta_A = -math.pi / 2
    else:
        theta_A = math.atan2(-p1_z, p1_x) if p1_x > 0.001 else -math.pi / 2

    pe_all = op.get("pass_edits") or {}
    R_blank = _f(params.get("blank_radius"), 0.0) or 0.0
    # Flange-edge model: needed for follow mode AND for the "exit beyond blank
    # edge" advisory (which applies in every mode when a blank is defined).
    est_flange = None
    if R_blank > 0:
        try:
            from process_planner import estimate_flange_reach
            est_flange = lambda z: estimate_flange_reach(mgr, R_blank, z)
        except Exception:
            est_flange = None
    # Roughing P2 sits p2_z_extend ABOVE the contact target (engine contact_z =
    # target_z + p2_z_extend); finishing forces it to 0.
    p2_ext = 0.0 if is_finish else (_f(op.get("p2_z_extend"), 0.0) or 0.0)

    r_tool = _f(op.get("r_tool"), 25.0) or 25.0
    blank_thick = _f(params.get("final_part_thickness_on_mandrel"), 2.0) or 0.0
    shell_off = _f(params.get("shell_thickness"), 0.0) or 0.0
    center_x = _f(params.get("mandrel_pos_x_offset"), 0.0) or 0.0
    rows = []
    prev_end = None
    for i in range(count):
        warnings = []
        pe = pe_all.get(str(i)) or pe_all.get(i) or {}
        st = staged.get(i) or staged.get(str(i)) or {}
        edit_angle = _f(st.get("pass_angle", pe.get("pass_angle")))
        edit_reach = _f(st.get("reach", pe.get("reach")))
        pinned = bool(pe) or bool(st)
        # #89 Phase 2 — per-pass pins (roughing): anchor (target_z), extend
        # (p2_z_extend), clearance. Mirrors the engine exactly.
        edit_clr = None if is_finish else _f(st.get("clearance", pe.get("clearance")))
        edit_tz  = None if is_finish else _f(st.get("target_z", pe.get("target_z")))
        edit_ext = None if is_finish else _f(st.get("p2_z_extend", pe.get("p2_z_extend")))
        eff_clr = edit_clr if edit_clr is not None else op_clearance
        if count <= 1:
            target_z = start_h
        else:
            target_z = start_h + (i / (count - 1)) * (end_h - start_h)
        if edit_tz is not None:
            target_z = edit_tz
        eff_ext = edit_ext if edit_ext is not None else p2_ext
        contact_z = target_z + eff_ext          # engine: contact_z = target_z + p2_z_extend
        total_off = r_tool + blank_thick + eff_clr

        follow_reach = None
        if follow and est_flange is not None:
            try:
                fr = est_flange(target_z)
            except Exception:
                fr = 0.0
            if fr > 0:
                follow_reach = max(fr * fb_fac + fb_off, 0.0)

        p3_x, p3_z = def_p3_x, def_p3_z
        eff_angle = None
        if pa_deg is not None:
            eff_angle = pa_deg
            if prog_a:
                eff_angle += i * (prog_a_end - eff_angle) / (count - 1)
            if edit_angle is not None:
                eff_angle = edit_angle
            L3 = reach_v if reach_v is not None else math.hypot(p3_x, p3_z)
            if prog_r:
                r_end = _f(op.get("progressive_reach_end"), L3)
                r_end = L3 if r_end is None else r_end
                L3 = max(L3 + i * (r_end - L3) / (count - 1), 0.0)
            if follow_reach is not None:
                L3 = follow_reach
            if edit_reach is not None:
                L3 = edit_reach
            if L3 > 0.001:
                theta_B = theta_A + math.radians(eff_angle)
                p3_x = L3 * math.cos(theta_B)
                p3_z = L3 * math.sin(theta_B)
            else:
                warnings.append(t("pt_warn_reach_zero"))
            eff_reach = L3
        else:
            raw_len = reach_v
            if follow_reach is not None:
                raw_len = follow_reach
            if edit_reach is not None:
                raw_len = edit_reach
            cur = math.hypot(p3_x, p3_z)
            if raw_len is not None and cur > 1e-6:
                s = raw_len / cur
                p3_x *= s
                p3_z *= s
            eff_reach = math.hypot(p3_x, p3_z)

        # Clearance anchoring + fold-back guard (engine lines mirror)
        anchored = (reach_v is not None or follow_reach is not None
                    or edit_reach is not None)
        if anchored:
            if conformal:
                try:
                    nx, nz = mgr.get_normal_at_z(contact_z)
                except Exception:
                    nx, nz = 1.0, 0.0
                gx = p3_x - eff_clr * nx >= 0.0
                gz = p3_z - eff_clr * nz >= 0.0
                if gx:
                    p3_x -= eff_clr * nx
                if gz:
                    p3_z -= eff_clr * nz
                if not (gx and gz):
                    warnings.append(t("pt_warn_guard").format(c=round(eff_clr, 2)))
            else:
                if p3_x - eff_clr >= 0.0:
                    p3_x -= eff_clr
                else:
                    warnings.append(t("pt_warn_guard").format(c=round(eff_clr, 2)))

        # "Exit beyond blank edge": the commanded stroke overshoots where material
        # still exists (est. unformed flange at this Z) → the tail of the pass is
        # an air move. Advisory only; skipped when the blank is already fully
        # formed at this Z (flange ≈ 0 — riding the formed wall is normal there).
        if est_flange is not None and not is_finish:
            try:
                _fl = est_flange(target_z)
            except Exception:
                _fl = 0.0
            if _fl > 0.5 and eff_reach > _fl + 3.0:
                warnings.append(t("pt_warn_beyond_blank").format(
                    mm=round(eff_reach - _fl, 1)))

        # Absolute endpoint estimate (non-conformal P2 placement, display only).
        try:
            r_contact = mgr.get_radius_fast(contact_z) + shell_off
        except Exception:
            r_contact = 0.0
        p2_x_abs = center_x + r_contact + total_off
        end_x = p2_x_abs + p3_x
        end_z = contact_z + p3_z

        # "Nearly the same pass": consecutive exit endpoints closer than the
        # roller-contact scale (~2.5 mm) do no distinguishable extra work.
        if prev_end is not None:
            if math.hypot(end_x - prev_end[0], end_z - prev_end[1]) < 2.5:
                warnings.append(t("pt_warn_duplicate"))
        prev_end = (end_x, end_z)

        # Source tag (priority order, matches the engine)
        if bool(st):
            source = t("pt_src_staged")
        elif bool(pe):
            source = t("pt_src_pin")
        elif follow_reach is not None:
            source = t("pt_src_follow")
        elif prog_r or prog_a:
            source = t("pt_src_fan")
        else:
            source = t("pt_src_manual")

        legacy = bool(gui_overrides.get(base_fwd_idx + i))
        if legacy:
            warnings.append(t("pt_warn_legacy"))

        rows.append({"i": i, "z": round(contact_z, 2),
                     "anchor": round(target_z, 2), "extend": round(eff_ext, 2),
                     "clr": round(eff_clr, 2),
                     "angle": None if eff_angle is None else round(eff_angle, 2),
                     "reach": round(eff_reach, 2),
                     "p3x": round(p3_x, 2), "p3z": round(p3_z, 2),
                     "end_x": round(end_x, 2), "end_z": round(end_z, 2),
                     # Absolute control points for the 2D preview (schematic; P1 drawn
                     # at the P1_Z anchor so it matches the columns).
                     "p1x": round(p2_x_abs + p1_x, 2), "p1z": round(target_z, 2),
                     "p2x": round(p2_x_abs, 2),
                     "source": source, "pinned": pinned,
                     "legacy_override": legacy, "warnings": warnings})
    return rows


# ──────────────────────────────────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────────────────────────────────

class PassTableDialog(tk.Toplevel):
    """Popup per-pass table with staged pin edits (Apply / Cancel)."""

    def __init__(self, parent, app, program_tab, op_index):
        super().__init__(parent)
        self.app = app
        self.ptab = program_tab
        self.op_index = op_index
        self.staged = {}          # {pass_i: {"pass_angle": v, "reach": v}}
        op = app.params["operations"][op_index]
        self.title(t("pt_title").format(name=op.get("name") or op.get("type", "?"),
                                        n=int(op.get("count", 1))))
        self.geometry("900x640")
        self.transient(parent)

        # Plain-language helper: how to edit one pass vs. fill many (#89).
        tk.Label(self, text=t("pt_help"), anchor="w", justify="left", fg="#446688",
                 wraplength=860).pack(fill="x", padx=8, pady=(8, 2))

        self._last_rows = None
        cols = ("pas", "anchor", "extend", "z", "clr", "angle", "reach", "endz", "src", "warn")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        heads = {"pas": ("№", 34),
                 "anchor": (t("pt_col_anchor"), 74), "extend": (t("pt_col_extend"), 66),
                 "z": (t("pt_col_z"), 70), "clr": (t("pt_col_clr"), 60),
                 "angle": (t("pt_col_angle"), 66), "reach": (t("pt_col_reach"), 66),
                 "endz": (t("pt_col_endz"), 66),
                 "src": (t("pt_col_src"), 80), "warn": (t("pt_col_warn"), 210)}
        for c in cols:
            self.tree.heading(c, text=heads[c][0])
            self.tree.column(c, width=heads[c][1], anchor="center", stretch=(c == "warn"))
        self.tree.tag_configure("pin", background="#fff3d0")
        self.tree.tag_configure("staged", background="#ffe0b0")
        self.tree.tag_configure("warn", foreground="#aa3300")
        self.tree.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

        # #89 — live 2D side view (X-Z): each pass drawn P1→P2→P3 (schematic), the
        # mandrel faint, the selected pass highlighted. Redraws from the CURRENT rows
        # (staged edits included) so you watch the sweep form before Apply.
        self.preview = tk.Canvas(self, height=150, bg="#0e141b", highlightthickness=0)
        self.preview.pack(fill="x", padx=6, pady=(4, 0))
        self.preview.bind("<Configure>", lambda e: self._draw_preview())

        self.lbl_foot = tk.Label(self, anchor="w", justify="left", fg="#446688")
        self.lbl_foot.pack(fill="x", padx=8, pady=(2, 0))

        # #89 — bulk fill helpers: put one value on every pass (Set all) or a linear
        # first→last ramp (Progressive) for the selected field. Both stage like manual
        # edits, so [Apply] / undo / [Cancel] work the same. Set-all Anchor Z + a
        # Progressive Extend = an anchored sweep built by hand.
        fill = ttk.Frame(self)
        fill.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(fill, text=t("pt_fill_field")).pack(side="left")
        self._fill_map = {t("pt_col_anchor"): "target_z", t("pt_col_extend"): "p2_z_extend",
                          t("pt_col_clr"): "clearance", t("pt_col_angle"): "pass_angle",
                          t("pt_col_reach"): "reach"}
        self._fill_var = tk.StringVar(value=t("pt_col_extend"))
        ttk.Combobox(fill, values=list(self._fill_map.keys()), textvariable=self._fill_var,
                     state="readonly", width=12).pack(side="left", padx=4)
        ttk.Button(fill, text=t("pt_fill_setall"), command=self._fill_set_all).pack(side="left", padx=2)
        ttk.Button(fill, text=t("pt_fill_progressive"), command=self._fill_progressive).pack(side="left", padx=2)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=6)
        self.btn_apply = ttk.Button(bar, text=t("pt_btn_apply"), command=self._apply)
        self.btn_apply.pack(side="right", padx=2)
        ttk.Button(bar, text=t("pt_btn_cancel"), command=self._cancel).pack(side="right", padx=2)
        ttk.Button(bar, text=t("pt_btn_unpin"), command=self._unpin_selected).pack(side="left", padx=2)
        ttk.Button(bar, text=t("pt_btn_refresh"), command=self.refresh).pack(side="left", padx=2)

        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ── data ──────────────────────────────────────────────────────────
    def _op(self):
        ops = self.app.params.get("operations", [])
        return ops[self.op_index] if self.op_index < len(ops) else None

    def _base_fwd_idx(self):
        """Global forward-pass index of this op's first pass (legacy overrides)."""
        base = 0
        for j, o in enumerate(self.app.params.get("operations", [])):
            if j == self.op_index:
                break
            if o.get("enabled", True):
                base += 1 if o.get("type") in ("cutting", "bending") else int(o.get("count", 1))
        return base

    def refresh(self):
        op = self._op()
        if op is None:
            self.destroy()
            return
        rows = compute_pass_rows(op, self.app.params, self.app.mandrel_mgr,
                                 gui_overrides=getattr(self.app, "gui_pass_overrides", {}),
                                 base_fwd_idx=self._base_fwd_idx(),
                                 staged=self.staged)
        self._last_rows = rows
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            tags = []
            if str(r["i"]) in {str(k) for k in self.staged}:
                tags.append("staged")
            elif r["pinned"]:
                tags.append("pin")
            if r["warnings"]:
                tags.append("warn")
            # ✎ prefix directly ON the staged cell — user feedback 2026-07-08:
            # the row tint alone was not noticed as "pending edit".
            st = self.staged.get(r["i"]) or self.staged.get(str(r["i"])) or {}
            def _mark(key, val):
                return f"✎ {val}" if key in st else val
            a_txt = _mark("pass_angle", "—" if r["angle"] is None else r["angle"])
            r_txt = _mark("reach", r["reach"])
            an_txt = _mark("target_z", r["anchor"])
            ex_txt = _mark("p2_z_extend", r["extend"])
            c_txt = _mark("clearance", r["clr"])
            self.tree.insert("", "end", iid=str(r["i"]), tags=tuple(tags), values=(
                r["i"] + 1, an_txt, ex_txt, r["z"], c_txt, a_txt, r_txt,
                r["end_z"], r["source"],
                "  |  ".join(r["warnings"])))
        # Footer: follow-mode flange line + staged count
        foot = []
        if op.get("reach_follow_blank"):
            vals = self.ptab._blank_reach_values(op)
            if vals:
                foot.append(t("pt_foot_flange").format(a=vals[0], b=vals[1]))
            else:
                foot.append(t("lbl_reach_auto_blocked"))
        if self.staged:
            foot.append(t("pt_foot_staged").format(n=len(self.staged)))
        self.lbl_foot.config(text="   •   ".join(foot))
        self.btn_apply.config(state="normal" if self.staged else "disabled")
        self._draw_preview()

    # ── 2D preview (#89) ───────────────────────────────────────────────
    def _draw_preview(self):
        c = getattr(self, "preview", None)
        rows = getattr(self, "_last_rows", None)
        if c is None:
            return
        c.delete("all")
        op = self._op()
        if not rows or op is None:
            return
        W = c.winfo_width() or 860
        H = c.winfo_height() or 150
        if W < 40 or H < 40:
            return
        mL, mR, mT, mB = 34, 12, 8, 16

        # Match the 3D-sim orientation: rows are computed in the canonical +X frame,
        # but a negative-X-side roller is mirrored around the mandrel center there —
        # so mirror X the same way here (2·cx − x) to compare side-by-side (#89, user).
        cx = float(self.app.params.get("mandrel_pos_x_offset", 0.0) or 0.0)
        _pos_side = self.app.params.get("roller_positive_x_side", True)

        def mx(x):
            return x if _pos_side else (2.0 * cx - x)

        # Points: each pass P1→P2→P3 (schematic) + the mandrel profile (roller side).
        pts = []
        for r in rows:
            pts += [(mx(r["p1x"]), r["p1z"]), (mx(r["p2x"]), r["z"]), (mx(r["end_x"]), r["end_z"])]
        mgr = self.app.mandrel_mgr
        prof = []
        if mgr is not None and getattr(mgr, "profile_z", None) is not None \
                and len(mgr.profile_z) > 1:
            prof = [(mx(cx + float(rr)), float(z))
                    for z, rr in zip(mgr.profile_z, mgr.profile_r)]
        allpts = pts + prof
        if not allpts:
            return
        xs = [p[0] for p in allpts]
        zs = [p[1] for p in allpts]
        xmin, xmax, zmin, zmax = min(xs), max(xs), min(zs), max(zs)
        xr = max(xmax - xmin, 1.0)
        zr = max(zmax - zmin, 1.0)
        xmin -= xr * 0.06; xmax += xr * 0.06
        zmin -= zr * 0.06; zmax += zr * 0.06
        xr, zr = xmax - xmin, zmax - zmin
        dW, dH = W - mL - mR, H - mT - mB

        def to_c(x, z):
            return (mL + (z - zmin) / zr * dW,        # Z → horizontal
                    mT + (xmax - x) / xr * dH)        # X → vertical (larger X up)

        if len(prof) > 1:
            coords = []
            for x, z in prof:
                coords += list(to_c(x, z))
            c.create_line(*coords, fill="#3a4658", width=1)

        sel = None
        s = self.tree.selection()
        if s:
            try:
                sel = int(s[0])
            except (ValueError, TypeError):
                sel = None

        pal = ["#5cc8ff", "#ffb060", "#7ee787", "#ff7b72", "#c39bff", "#79c0d0"]
        for r in rows:
            col = pal[r["i"] % len(pal)]
            wdt = 3 if r["i"] == sel else 1
            p1 = to_c(mx(r["p1x"]), r["p1z"])
            p2 = to_c(mx(r["p2x"]), r["z"])
            p3 = to_c(mx(r["end_x"]), r["end_z"])
            c.create_line(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1], fill=col, width=wdt)
            c.create_oval(p2[0] - 2, p2[1] - 2, p2[0] + 2, p2[1] + 2, fill=col, outline="")
        c.create_text(mL, H - 5, text="Z →   (X ↑)", fill="#6a7686",
                      anchor="w", font=("Segoe UI", 7))

    # ── interactions ──────────────────────────────────────────────────
    def _on_row_select(self, _e=None):
        """Highlight the clicked pass in the 3D view (same machinery as
        pass-stepping: active index = op base + within-op offset × stride)."""
        self._draw_preview()   # highlight the selected pass in the 2D view too
        sel = self.tree.selection()
        if not sel:
            return
        try:
            i = int(sel[0])
            base = 0
            for j, o in enumerate(self.app.params.get("operations", [])):
                if j == self.op_index:
                    break
                if o.get("enabled", True):
                    base += self.ptab._op_logical_count(o) * self.ptab._op_toolpath_stride(o)
            op = self._op()
            stride = self.ptab._op_toolpath_stride(op)
            self.app.active_editing_pass_idx = base + i * stride
            self.app.recolor_paths()
        except Exception as e:
            logger.debug(f"pass-table highlight skipped: {e}")

    def _on_double_click(self, event):
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row:
            return
        i = int(row)
        op = self._op()
        _is_finish = op.get("type") == "finishing"
        if col in ("#2", "#3", "#5"):   # anchor / extend / clearance — roughing only
            if _is_finish:
                messagebox.showinfo(t("pt_title_short"), t("pt_edit_rough_only"), parent=self)
                return
            key, label = {"#2": ("target_z", t("pt_col_anchor")),
                          "#3": ("p2_z_extend", t("pt_col_extend")),
                          "#5": ("clearance", t("pt_col_clr"))}[col]
        elif col == "#6":   # angle — only meaningful in polar mode
            if op.get("pass_angle") in (None, ""):
                messagebox.showinfo(t("pt_title_short"), t("pt_no_angle_raw"), parent=self)
                return
            key, label = "pass_angle", t("pt_col_angle")
        elif col == "#7":   # reach
            key, label = "reach", t("pt_col_reach")
        else:
            return
        cur = self.tree.set(row, {"target_z": "anchor", "p2_z_extend": "extend",
                                  "clearance": "clr", "pass_angle": "angle",
                                  "reach": "reach"}[key])
        cur = cur.replace("✎", "").strip()   # strip the staged marker
        val = simpledialog.askstring(t("pt_title_short"),
                                     t("pt_edit_prompt").format(p=i + 1, label=label),
                                     initialvalue=cur if cur != "—" else "",
                                     parent=self)
        if val is None:
            return
        val = val.strip().replace(",", ".")
        if val == "":
            # empty = drop this staged key (and stage removal of an existing pin key)
            st = self.staged.setdefault(i, {})
            st[key] = None
        else:
            try:
                fval = float(val)
            except ValueError:
                messagebox.showerror(t("pt_title_short"), t("pt_bad_number"), parent=self)
                return
            self.staged.setdefault(i, {})[key] = fval
        # prune empty staging entries ({} or all-None with no existing pin)
        if all(v is None for v in self.staged[i].values()):
            pe = (self._op().get("pass_edits") or {})
            if not (pe.get(str(i)) or pe.get(i)):
                self.staged.pop(i, None)
        self.refresh()

    # ── bulk fill helpers (#89) ────────────────────────────────────────
    def _parse_num(self, s):
        try:
            return float(s.strip().replace(",", "."))
        except (ValueError, AttributeError):
            messagebox.showerror(t("pt_title_short"), t("pt_bad_number"), parent=self)
            return None

    def _fill_guard(self, key):
        """False (with an info popup) if the selected field can't be filled for this op."""
        op = self._op()
        if op is None:
            return False
        if op.get("type") == "finishing" and key in ("target_z", "p2_z_extend", "clearance"):
            messagebox.showinfo(t("pt_title_short"), t("pt_edit_rough_only"), parent=self)
            return False
        if key == "pass_angle" and op.get("pass_angle") in (None, ""):
            messagebox.showinfo(t("pt_title_short"), t("pt_no_angle_raw"), parent=self)
            return False
        return True

    def _fill_set_all(self):
        key = self._fill_map.get(self._fill_var.get())
        if not key or not self._fill_guard(key):
            return
        val = simpledialog.askstring(
            t("pt_title_short"), t("pt_fill_setall_prompt").format(f=self._fill_var.get()),
            parent=self)
        if val is None:
            return
        v = self._parse_num(val)
        if v is None:
            return
        for i in range(int(self._op().get("count", 1))):
            self.staged.setdefault(i, {})[key] = v
        self.refresh()

    def _fill_progressive(self):
        key = self._fill_map.get(self._fill_var.get())
        if not key or not self._fill_guard(key):
            return
        n = int(self._op().get("count", 1))
        if n < 2:
            messagebox.showinfo(t("pt_title_short"), t("pt_fill_need2"), parent=self)
            return
        first = simpledialog.askstring(
            t("pt_title_short"), t("pt_fill_prog_first").format(f=self._fill_var.get()),
            parent=self)
        if first is None:
            return
        last = simpledialog.askstring(
            t("pt_title_short"), t("pt_fill_prog_last").format(f=self._fill_var.get()),
            parent=self)
        if last is None:
            return
        a, b = self._parse_num(first), self._parse_num(last)
        if a is None or b is None:
            return
        for i in range(n):
            self.staged.setdefault(i, {})[key] = round(a + (b - a) * i / (n - 1), 4)
        self.refresh()

    def _apply(self):
        """ONE undo snapshot; staged values → op['pass_edits']; recalc."""
        op = self._op()
        if op is None or not self.staged:
            return
        self.ptab._push_undo(t("pt_undo_label"))
        pe = dict(op.get("pass_edits") or {})
        for i, ed in self.staged.items():
            k = str(i)
            cur = dict(pe.get(k) or {})
            for key, v in ed.items():
                if v is None:
                    cur.pop(key, None)
                else:
                    cur[key] = v
            if cur:
                pe[k] = cur
            else:
                pe.pop(k, None)
        if pe:
            op["pass_edits"] = pe
        else:
            op.pop("pass_edits", None)
        self.staged = {}
        self.ptab.refresh_ops_tree()
        self.ptab._schedule_auto_calc()
        self.refresh()

    def _cancel(self):
        if self.staged and not messagebox.askyesno(
                t("pt_title_short"), t("pt_discard_confirm"), parent=self):
            return
        self.staged = {}
        self.destroy()

    def _unpin_selected(self):
        """Remove pins (pass_edits) AND legacy hidden overrides for the selected
        passes. Immediate (button action) with its own undo snapshot."""
        sel = self.tree.selection()
        if not sel:
            return
        op = self._op()
        self.ptab._push_undo(t("pt_btn_unpin"))
        pe = dict(op.get("pass_edits") or {})
        base = self._base_fwd_idx()
        cleared_legacy = 0
        for row in sel:
            i = int(row)
            pe.pop(str(i), None)
            pe.pop(i, None)
            self.staged.pop(i, None)
            gpo = getattr(self.app, "gui_pass_overrides", None)
            if gpo is not None and gpo.pop(base + i, None) is not None:
                cleared_legacy += 1
        if pe:
            op["pass_edits"] = pe
        else:
            op.pop("pass_edits", None)
        if cleared_legacy:
            messagebox.showinfo(t("pt_title_short"),
                                t("pt_legacy_cleared").format(n=cleared_legacy),
                                parent=self)
        self.ptab.refresh_ops_tree()
        self.ptab._schedule_auto_calc()
        self.refresh()
