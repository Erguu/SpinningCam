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

import numpy as np

import exit_breaks
import exit_waypoints
from i18n import t
from logger_config import logger
from ui import preview_orient
from ui import dialog_sizing

# How finely the schematic exit leg is sampled before break points are applied
# to it (#102). The engine picks a break's pivot by INDEX into the leg's point
# array, so the sketch needs enough points that a small position difference is
# visible; 41 puts them 2.5% apart, finer than the operator can type.
_BREAK_LEG_SAMPLES = 41


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
    source, pinned, legacy_override, warnings:[str], prov{}}. ``staged`` (dict
    {i: {"pass_angle":v, "reach":v}}) previews unapplied table edits.
    ``angle`` is None in RAW mode. Purely advisory — never mutates the op.

    ``prov`` is the per-FIELD provenance record (2026-07-28): for each of
    anchor / extend / clr / angle / reach it names which stage of the priority
    chain produced the live number and which candidates it beat —
    ``{field: {"source": key, "value": v, "losers": [(key, v), …]}}``, losers
    ordered nearest-priority first. The row-level ``source`` tag only says
    "something on this pass is manual"; it cannot say WHICH field, which is
    what makes a stray pin hard to find. Consumed by the pass-table
    explanation bar, ui/dialogs/recipe_audit.py and explain.py.
    """
    count = int(op.get("count", 1))
    # "point" joins these: a positioning move has no passes to tabulate.
    if op.get("type") in ("cutting", "bending", "point"):
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

        # ── provenance recorder (additive; no effect on any computed value) ──
        prov = {}

        def _org(key, _st=st, _pe=pe):
            """Which dict a per-pass edit came from — staged beats applied pin."""
            if _st.get(key) is not None:
                return "staged"
            return "pin"

        def _rec(field, cands, _p=prov):
            """cands = [(source_key, value), …] in PRIORITY order, last wins.
            None values are absent stages and are dropped.

            Never raises: provenance is a display aid, and the pass table (and
            everything reading it) must open even if this bookkeeping fails.
            Consumers already treat a missing record as "no explanation"."""
            try:
                live = [(s, v) for s, v in cands if v is not None]
                if not live:
                    return
                src, val = live[-1]
                _p[field] = {"source": src, "value": val,
                             "losers": [(s, v) for s, v in live[:-1]][::-1]}
            except Exception as e:
                logger.debug(f"provenance record skipped for {field}: {e}")

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
        base_tz = target_z                      # pre-pin value, for provenance
        if edit_tz is not None:
            target_z = edit_tz
        eff_ext = edit_ext if edit_ext is not None else p2_ext
        contact_z = target_z + eff_ext          # engine: contact_z = target_z + p2_z_extend
        total_off = r_tool + blank_thick + eff_clr

        # Absolute P2 (non-conformal placement) — mirrors path_generator.py:861.
        # Computed HERE rather than after the exit maths because a #100 hand-drawn
        # tail is measured from it, and the tail decides where the pass actually
        # ends. Everything below that used to describe the exit parametrically is
        # skipped when a tail exists: it would describe a pass that is not running.
        try:
            r_contact = mgr.get_radius_fast(contact_z) + shell_off
        except Exception:
            r_contact = 0.0
        p2_x_abs = center_x + r_contact + total_off

        _tail = exit_waypoints.get_points(op, i)     # honours the D10 exclusions
        _tail_abs = exit_waypoints.resolve(p2_x_abs, contact_z, _tail) if _tail else []

        _rec("anchor", [("op", base_tz), (_org("target_z"), edit_tz)])
        _rec("extend", [("op", p2_ext), (_org("p2_z_extend"), edit_ext)])
        _rec("clr", [("op", op_clearance), (_org("clearance"), edit_clr)])

        # Exit DIRECTION is resolved BEFORE the reach, because follow-blank needs it to
        # turn the flat flange overhang into the slant length actually travelled.
        # Mirrors the engine, where the θ_B block likewise sits above follow-blank.
        eff_angle = fan_angle = theta_B = None
        exit_dir = (def_p3_x, def_p3_z)         # raw mode: the p3 ratio is the direction
        if pa_deg is not None:
            eff_angle = pa_deg
            if prog_a:
                eff_angle += i * (prog_a_end - eff_angle) / (count - 1)
                fan_angle = eff_angle
            if edit_angle is not None:
                eff_angle = edit_angle
            theta_B = theta_A + math.radians(eff_angle)
            exit_dir = (math.cos(theta_B), math.sin(theta_B))

        follow_reach = None
        if follow and est_flange is not None:
            try:
                fr = est_flange(target_z)
            except Exception:
                fr = 0.0
            if fr > 0:
                # FLAT → SLANT — MUST mirror path_generator.py (2026-09-03). The flange
                # model answers "how far does the sheet stick out sideways"; the stroke
                # travels along the exit, where the same material is longer. Miss this
                # and the table shows a stroke shorter than the machine runs — the exact
                # class of drift the fb_min note below was written about.
                if not op.get("reach_blank_flat_legacy", False):
                    try:
                        from process_planner import flange_slant_length
                        fr = flange_slant_length(
                            mgr.get_radius_fast(target_z) + shell_off, fr, *exit_dir)[0]
                    except Exception:
                        pass
                follow_reach = max(fr * fb_fac + fb_off, 0.0)
                # Degenerate-flange guard — MUST mirror path_generator.py ~638
                # (added to the engine 2026-07-22, missed here until 2026-07-28).
                # Near the base the flange estimate collapses to a few mm, and
                # below min_z it is unphysical and GROWS again; the engine drops
                # follow mode in both cases and falls back to the fan/op reach.
                # Without this the table showed ~9.8mm where the machine ran
                # ~39mm — the displayed number was simply not what runs.
                fb_min = _f(op.get("reach_follow_min"), 10.0) or 0.0
                if follow_reach < fb_min or target_z <= float(mgr.props.get("min_z", 0.0)):
                    follow_reach = None

        p3_x, p3_z = def_p3_x, def_p3_z
        if pa_deg is not None:
            _rec("angle", [("op", pa_deg), ("fan", fan_angle),
                           (_org("pass_angle"), edit_angle)])
            L3 = reach_v if reach_v is not None else math.hypot(p3_x, p3_z)
            base_L3, base_src = L3, ("op" if reach_v is not None else "raw")
            fan_L3 = None
            if prog_r:
                r_end = _f(op.get("progressive_reach_end"), L3)
                r_end = L3 if r_end is None else r_end
                L3 = max(L3 + i * (r_end - L3) / (count - 1), 0.0)
                fan_L3 = L3
            if follow_reach is not None:
                L3 = follow_reach
            if edit_reach is not None:
                L3 = edit_reach
            _rec("reach", [(base_src, base_L3), ("fan", fan_L3),
                           ("follow", follow_reach),
                           (_org("reach"), edit_reach)])
            if L3 > 0.001:
                p3_x = L3 * math.cos(theta_B)
                p3_z = L3 * math.sin(theta_B)
            elif not _tail:
                warnings.append(t("pt_warn_reach_zero"))
            eff_reach = L3
        else:
            raw_len = reach_v
            if follow_reach is not None:
                raw_len = follow_reach
            if edit_reach is not None:
                raw_len = edit_reach
            cur = math.hypot(p3_x, p3_z)
            _rec("reach", [("raw", cur), ("op", reach_v), ("follow", follow_reach),
                           (_org("reach"), edit_reach)])
            if raw_len is not None and cur > 1e-6:
                s = raw_len / cur
                p3_x *= s
                p3_z *= s
            eff_reach = math.hypot(p3_x, p3_z)

        # Clearance anchoring + fold-back guard (engine lines mirror)
        anchored = (reach_v is not None or follow_reach is not None
                    or edit_reach is not None)
        if anchored and not _tail:
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
        # #100: with a hand-drawn tail the pass ends at the LAST WAYPOINT, and
        # reach/angle are no longer inputs — the operator placed the end himself.
        # The reach FIGURE is still derived (P2 → last point) because the
        # beyond-blank advisory is about the stroke, not about the setting; the
        # columns show a dash so it cannot be mistaken for something editable.
        if _tail:
            end_x, end_z = _tail_abs[-1]
            eff_reach = math.hypot(end_x - p2_x_abs, end_z - contact_z)
            eff_angle = None
        else:
            end_x = p2_x_abs + p3_x
            end_z = contact_z + p3_z

        # #102: break points bend the exit leg AFTER the parametric P3 is placed,
        # so without this the table and its sketch describe a pass the machine is
        # not running — the same blind spot #100 had to fix for waypoints.
        #
        # APPROXIMATE BY CONSTRUCTION, and that is a deliberate trade. The engine
        # measures `t` along the REAL exit leg's point array, which starts at T2
        # (after the P2 fillet) and may already be curved by a bow or arc. Here
        # the leg is the schematic straight P2→end. With a small p2_radius the
        # two agree closely; with a large one a break lands a little further
        # along than drawn. Showing the bend approximately beats showing a
        # straight line that is certainly wrong.
        _brk = [] if _tail else exit_breaks.get_breaks(op, i)
        if _brk and not exit_breaks.excluded_reason(op):
            _leg = np.linspace([p2_x_abs, 0.0, contact_z],
                               [end_x, 0.0, end_z], _BREAK_LEG_SAMPLES)
            _leg = exit_breaks.apply(_leg, _brk)
            end_x, end_z = float(_leg[-1][0]), float(_leg[-1][2])
            _brk_leg = [(round(float(p[0]), 3), round(float(p[2]), 3)) for p in _leg]
        else:
            _brk_leg = []

        if est_flange is not None and not is_finish:
            try:
                _fl = est_flange(target_z)
            except Exception:
                _fl = 0.0
            if _fl > 0.5 and eff_reach > _fl + 3.0:
                warnings.append(t("pt_warn_beyond_blank").format(
                    mm=round(eff_reach - _fl, 1)))

        # "Nearly the same pass": consecutive exit endpoints closer than the
        # roller-contact scale (~2.5 mm) do no distinguishable extra work.
        if prev_end is not None:
            if math.hypot(end_x - prev_end[0], end_z - prev_end[1]) < 2.5:
                warnings.append(t("pt_warn_duplicate"))
        prev_end = (end_x, end_z)

        # Source tag (priority order, matches the engine)
        if _tail:
            source = t("pt_src_tail").format(n=len(_tail))
        elif bool(st):
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
                     # #100 D20: a tail pass shows a dash — reach and angle no
                     # longer drive it, and a number here would read as editable.
                     "reach": None if _tail else round(eff_reach, 2),
                     # Resolved waypoints, for the 2D preview (absolute, canonical).
                     "tail": [(round(x, 3), round(z, 3)) for x, z in _tail_abs],
                     # #102: the break-bent exit leg, for the 2D preview. Empty
                     # when this pass has no breaks — the straight P2→end line
                     # the preview already draws is then correct.
                     "break_leg": _brk_leg,
                     "n_breaks": len(_brk) if _brk_leg else 0,
                     "p3x": round(p3_x, 2), "p3z": round(p3_z, 2),
                     "end_x": round(end_x, 2), "end_z": round(end_z, 2),
                     # Absolute control points for the 2D preview (schematic; P1 drawn
                     # at the P1_Z anchor so it matches the columns).
                     "p1x": round(p2_x_abs + p1_x, 2), "p1z": round(target_z, 2),
                     "p2x": round(p2_x_abs, 2),
                     # UNROUNDED P2, for callers that do geometry rather than
                     # display (#100's exit-tail editor). P2 sits at EXACTLY the
                     # op clearance by construction, so the 2-decimal rounding
                     # above — up to 5 µm inward — is enough on its own to make a
                     # clearance check report "1.70 mm, needs 1.70 mm" and refuse
                     # every edit. Never hand the rounded value to a check.
                     "p2x_exact": p2_x_abs, "z_exact": contact_z,
                     "source": source, "pinned": pinned,
                     "legacy_override": legacy, "warnings": warnings,
                     "prov": prov})
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
        dialog_sizing.fit(self, 900, 640)
        self.transient(parent)

        # Apply / Cancel / Waypoints / Break points packed FIRST, to the bottom
        # (#103): Tk squeezes whatever was packed LAST when there is not enough
        # room, which in a top-down dialog is always the button row. This is the
        # row operators were losing on a high-DPI screen. Filled in further down.
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", padx=6, pady=6)

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
        # A hand-set value that breaks the operation's own pattern — the thing
        # people open this table to find. Red + bold + a ◆ on the cell itself,
        # because a whole-row tint cannot say WHICH number is the odd one.
        self.tree.tag_configure("odd", foreground="#c01000", background="#ffecea")
        self.tree.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)
        # Self-explaining numbers (2026-07-28): the Source column is row-level,
        # so it cannot say WHICH field is manual. Clicking a cell spells out the
        # chain that produced that one number. Read-only — click never edits.
        self.tree.bind("<ButtonRelease-1>", self._on_cell_click, add="+")

        # #89 — live 2D side view (X-Z): each pass drawn P1→P2→P3 (schematic), the
        # mandrel faint, the selected pass highlighted. Redraws from the CURRENT rows
        # (staged edits included) so you watch the sweep form before Apply.
        # #102: resolved ONCE, here — the sketch must not re-orient while the
        # operator is working in it (user 2026-08-28). Reopen the window to pick
        # up a new camera angle.
        self._orient = preview_orient.resolve(self.app)
        self.preview = tk.Canvas(self, height=150, bg="#0e141b", highlightthickness=0)
        self.preview.pack(fill="x", padx=6, pady=(4, 0))
        self.preview.bind("<Configure>", lambda e: self._draw_preview())

        self.lbl_foot = tk.Label(self, anchor="w", justify="left", fg="#446688")
        self.lbl_foot.pack(fill="x", padx=8, pady=(2, 0))

        # Explanation bar — fed by _on_cell_click / row select.
        self.lbl_explain = tk.Label(self, anchor="w", justify="left", fg="#204060",
                                    bg="#eef3f8", relief="groove", bd=1,
                                    wraplength=860, text=t("rx_explain_hint"))
        self.lbl_explain.pack(fill="x", padx=6, pady=(4, 0))

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

        self.btn_apply = ttk.Button(bar, text=t("pt_btn_apply"), command=self._apply)
        self.btn_apply.pack(side="right", padx=2)
        ttk.Button(bar, text=t("pt_btn_cancel"), command=self._cancel).pack(side="right", padx=2)
        ttk.Button(bar, text=t("pt_btn_unpin"), command=self._unpin_selected).pack(side="left", padx=2)
        ttk.Button(bar, text=t("pt_btn_refresh"), command=self.refresh).pack(side="left", padx=2)
        # #100: per-pass hand-drawn exit tail. Disabled (with the reason) on the
        # ops D10 puts out of scope, so the refusal is visible rather than a
        # button that silently does nothing.
        self.btn_tail = ttk.Button(bar, text=t("pt_btn_tail"), command=self._edit_exit_tail)
        self.btn_tail.pack(side="left", padx=8)
        try:
            import exit_waypoints as _ew
            if _ew.excluded_reason(op):
                self.btn_tail.state(["disabled"])
        except Exception:
            pass
        # #102: per-pass break points. Disabled with its own reason on the ops
        # whose exit leg never reaches the rotation — a different set from the
        # waypoint exclusions, so it gets its own check rather than sharing one.
        self.btn_breaks = ttk.Button(bar, text=t("pt_btn_breaks"),
                                     command=self._edit_break_points)
        self.btn_breaks.pack(side="left", padx=2)
        try:
            import exit_breaks as _eb
            if _eb.excluded_reason(op):
                self.btn_breaks.state(["disabled"])
        except Exception:
            pass

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
                _t = o.get("type")
                if _t == "point":
                    continue          # contributes no pass — must not shift the base
                base += 1 if _t in ("cutting", "bending") else int(o.get("count", 1))
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
        # Which values do not fit this operation's own pattern (shared helper,
        # so the table and the recipe-check window can never disagree).
        try:
            from recipe_explain import outlier_fields
            odd_map = outlier_fields(rows)
        except Exception as e:
            logger.debug(f"outlier highlight skipped: {e}")
            odd_map = {}
        self._odd_map = odd_map
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            odd = odd_map.get(r["i"], set())
            # Exactly ONE styling tag per row: ttk tag precedence with several
            # competing tags is fragile, and 'odd' must always win.
            if odd:
                tags = ["odd"]
            elif str(r["i"]) in {str(k) for k in self.staged}:
                tags = ["staged"]
            elif r["pinned"]:
                tags = ["pin"]
            else:
                tags = []
            if r["warnings"] and not odd:
                tags.append("warn")
            # Prefix directly ON the cell — user feedback 2026-07-08: the row
            # tint alone was not noticed. ✎ = staged edit, ◆ = the value that
            # does not fit this operation's pattern (row tint cannot say which).
            st = self.staged.get(r["i"]) or self.staged.get(str(r["i"])) or {}
            def _mark(key, val, field=None, _st=st, _odd=odd):
                pre = ("✎ " if key in _st else "") + ("◆ " if field in _odd else "")
                return f"{pre}{val}" if pre else val
            a_txt = _mark("pass_angle", "—" if r["angle"] is None else r["angle"], "angle")
            r_txt = _mark("reach", "—" if r["reach"] is None else r["reach"], "reach")
            an_txt = _mark("target_z", r["anchor"], "anchor")
            ex_txt = _mark("p2_z_extend", r["extend"], "extend")
            c_txt = _mark("clearance", r["clr"], "clr")
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

        # Everything below stays in CANONICAL +X — the machine-side mirror that
        # used to live here as `mx()` is now inside `preview_orient.to_plane`,
        # so the pass table and the waypoint editor cannot disagree about it
        # (#89's requirement, #102's implementation).
        cx = float(self.app.params.get("mandrel_pos_x_offset", 0.0) or 0.0)

        # Points: each pass P1→P2→P3 (schematic) + the mandrel profile (roller side).
        pts = []
        for r in rows:
            pts += [(r["p1x"], r["p1z"]), (r["p2x"], r["z"]), (r["end_x"], r["end_z"])]
            pts += list(r.get("tail") or ())         # #100: keep the tail in view
            pts += list(r.get("break_leg") or ())    # #102: and the break-bent leg
        mgr = self.app.mandrel_mgr
        prof = []
        if mgr is not None and getattr(mgr, "profile_z", None) is not None \
                and len(mgr.profile_z) > 1:
            prof = [(cx + float(rr), float(z))
                    for z, rr in zip(mgr.profile_z, mgr.profile_r)]
        allpts = pts + prof
        if not allpts:
            return
        # #102: which axis goes across the sketch now comes from the 3D camera,
        # through the same helper the waypoint editor uses — the two windows used
        # to disagree with each other AND with the 3D view. `to_plane` also
        # applies the machine-side mirror, so `mx()` above must NOT be applied
        # again; the raw canonical values are what go in.
        _or = self._orient
        hv = [preview_orient.to_plane(_or, x, z) for x, z in allpts]
        hs = [p[0] for p in hv]
        vs = [p[1] for p in hv]
        hmin, hmax, vmin, vmax = min(hs), max(hs), min(vs), max(vs)
        hr = max(hmax - hmin, 1.0)
        vr = max(vmax - vmin, 1.0)
        hmin -= hr * 0.06; hmax += hr * 0.06
        vmin -= vr * 0.06; vmax += vr * 0.06
        hr, vr = hmax - hmin, vmax - vmin
        dW, dH = W - mL - mR, H - mT - mB

        def to_c(x, z):
            h, v = preview_orient.to_plane(_or, x, z)
            return (mL + (h - hmin) / hr * dW,
                    mT + (vmax - v) / vr * dH)        # canvas Y grows downward

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
            p1 = to_c(r["p1x"], r["p1z"])
            p2 = to_c(r["p2x"], r["z"])
            tail = r.get("tail") or ()
            brk_leg = r.get("break_leg") or ()
            if tail:
                # #100: draw the REAL exit — P1→P2 then straight through every
                # waypoint. The schematic P2→P3 leg does not exist on this pass,
                # and drawing it would show a pass that is not the one running.
                flat = [p1[0], p1[1], p2[0], p2[1]]
                for x, z in tail:
                    flat.extend(to_c(x, z))
                c.create_line(*flat, fill=col, width=wdt)
                for k, (x, z) in enumerate(tail):
                    wx, wz = to_c(x, z)
                    rr = 3 if k == len(tail) - 1 else 2      # the last one ends the pass
                    c.create_oval(wx - rr, wz - rr, wx + rr, wz + rr,
                                  fill=col, outline="#0e141b")
            elif brk_leg:
                # #102: the exit leg as the breaks bend it, not the straight
                # P2→P3 schematic — which is the line that never moved no matter
                # what the operator typed into the break editor.
                flat = [p1[0], p1[1]]
                for x, z in brk_leg:
                    flat.extend(to_c(x, z))
                c.create_line(*flat, fill=col, width=wdt)
                ex, ez = to_c(*brk_leg[-1])
                c.create_oval(ex - 3, ez - 3, ex + 3, ez + 3, fill=col, outline="#0e141b")
            else:
                p3 = to_c(r["end_x"], r["end_z"])
                c.create_line(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1], fill=col, width=wdt)
            c.create_oval(p2[0] - 2, p2[1] - 2, p2[0] + 2, p2[1] + 2, fill=col, outline="")
        # #102: the axis legend is no longer a constant — it says which way the
        # sketch is actually laid out, which is the only way to tell a flipped
        # view from a differently-shaped pass.
        _hl, _vl = preview_orient.axis_labels(_or)
        c.create_text(mL, H - 5, text=f"{_hl}   ({_vl})", fill="#6a7686",
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

    # Table column → provenance field. Columns without a resolved number
    # (№, contact Z, P3_Z, Source, Warnings) fall back to the row summary.
    _PROV_COL = {"#2": "anchor", "#3": "extend", "#5": "clr",
                 "#6": "angle", "#7": "reach"}

    def _on_cell_click(self, event):
        """Explain the clicked number in plain language (read-only)."""
        try:
            row = self.tree.identify_row(event.y)
            if not row:
                return
            r = next((x for x in (self._last_rows or []) if str(x["i"]) == row), None)
            if r is None:
                return
            from recipe_explain import explain_field, find_overrides
            odd = getattr(self, "_odd_map", {}).get(r["i"], set())
            field = self._PROV_COL.get(self.tree.identify_column(event.x))
            if field:
                txt = explain_field(r, field)
                hot = field in odd
            else:
                # No number in this column — summarise what IS manual on the row,
                # which is the question the Source column raises but can't answer.
                # Lead with the outliers: if the row is flagged red, those are
                # what the flag is about, and listing the deliberate ramps first
                # would point the user at the wrong number.
                hits = [f for f, _ in find_overrides(r)]
                if odd:
                    hits = [f for f in hits if f in odd]
                txt = ("  |  ".join(explain_field(r, f) for f in hits) if hits
                       else t("rx_explain_hint"))
                hot = bool(odd)
            if hot:
                txt = t("rx_odd_prefix") + " " + txt
            self.lbl_explain.config(
                text=txt or t("rx_explain_hint"),
                fg="#c01000" if hot else "#204060",
                bg="#ffecea" if hot else "#eef3f8")
        except Exception as e:
            logger.debug(f"pass-table explain skipped: {e}")

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

    def _edit_exit_tail(self):
        """#100: open the waypoint editor for the SELECTED pass.

        Writes straight into op["pass_edits"][i]["exit_points"] on OK rather than
        into self.staged: the tail is its own modal with its own accept/refuse
        rules, and staging it behind a second Apply would mean an operator could
        stage a tail and then Cancel out of a window that already told him the
        points were accepted.
        """
        op = self._op()
        if op is None:
            return
        try:
            import exit_waypoints as ew
        except Exception as e:
            logger.debug(f"#100 unavailable: {e}")
            return
        reason = ew.excluded_reason(op)
        if reason:
            self.lbl_explain.config(text=t("pt_tail_excluded"))
            return

        sel = self.tree.selection()
        if not sel:
            self.lbl_explain.config(text=t("pt_tail_pick"))
            return
        idx = self.tree.index(sel[0])
        rows = self._last_rows or []
        if idx >= len(rows):
            return
        row = rows[idx]

        def _apply(points, shape=None):
            # BEFORE the mutation: `_push_undo` snapshots the CURRENT ops list
            # ("Snapshot the ops list BEFORE a mutating action", program_tab.py:
            # 1438). This used to run after the writes below, so the snapshot
            # captured the new tail and one undo could not get the old one back.
            try:
                self.ptab._push_undo("exit_tail")
            except Exception:
                pass
            edits = op.setdefault("pass_edits", {})
            key = str(row["i"])
            slot = edits.setdefault(key, {})
            if points:
                slot["exit_points"] = points
                # Only store a non-default shape, so a straight tail (the norm)
                # leaves no key behind and older files stay readable as-is.
                if shape and shape != ew.DEFAULT_SHAPE:
                    slot["exit_shape"] = shape
                else:
                    slot.pop("exit_shape", None)
            else:
                slot.pop("exit_points", None)
                slot.pop("exit_shape", None)
                if not slot:
                    edits.pop(key, None)
            self.refresh()
            try:
                self.ptab._schedule_auto_calc()
            except Exception:
                pass

        from ui.dialogs.exit_tail_dialog import ExitTailDialog
        # EXACT P2 — the rounded display values would put the tail's own start
        # a few µm inside its clearance and refuse every edit (see the row dict).
        dlg = ExitTailDialog(self, self.app, self.op_index, row["i"],
                             (row.get("p2x_exact", row["p2x"]),
                              row.get("z_exact", row["z"])), _apply)
        dlg.grab_set()
        self.wait_window(dlg)

    def _edit_break_points(self):
        """#102: open the break-point editor for the SELECTED pass.

        Writes straight into op["pass_edits"][i]["exit_breaks"] on OK, for the
        same reason the tail editor does: it is its own modal with its own OK,
        and staging it behind the pass table's [Apply] would let an operator
        cancel away changes a window has already accepted.
        """
        op = self._op()
        if op is None:
            return
        try:
            import exit_breaks as eb
        except Exception as e:
            logger.debug(f"#102 unavailable: {e}")
            return
        reason = eb.excluded_reason(op)
        if reason:
            self.lbl_explain.config(text=t(f"pt_breaks_excl_{reason}"))
            return

        sel = self.tree.selection()
        if not sel:
            self.lbl_explain.config(text=t("pt_breaks_pick"))
            return
        idx = self.tree.index(sel[0])
        rows = self._last_rows or []
        if idx >= len(rows):
            return
        pass_index = rows[idx]["i"]

        def _apply(per_pass):
            """per_pass: {pass index -> list of breaks}.

            An empty list means the operator deleted every row, and that has to
            STICK. Where the op still carries a legacy `exit_mid_rotation` the
            empty list is written out, because only a present-but-empty key
            suppresses the fallback (exit_breaks.has_own_list). Where there is no
            legacy break to suppress the key is removed instead, so clearing an
            op that never had breaks leaves no debris in the .ssp.
            """
            # BEFORE the mutation — `_push_undo` snapshots the current ops list,
            # so pushing afterwards would record the already-changed state.
            try:
                self.ptab._push_undo(t("pt_btn_breaks"))
            except Exception:
                pass
            # Read BEFORE the exit_mid_rotation pop below, which is what an
            # emptied pass would otherwise fall back to.
            _suppressible = bool(eb.legacy_break(op))
            edits = op.setdefault("pass_edits", {})
            for i, brk in per_pass.items():
                key = str(i)
                slot = edits.setdefault(key, {})
                if brk:
                    slot["exit_breaks"] = brk
                elif _suppressible:
                    slot["exit_breaks"] = []      # "none, and I mean it"
                else:
                    slot.pop("exit_breaks", None)
                if not slot:
                    edits.pop(key, None)
            # The legacy op-level break is now expressed per pass. Leaving it in
            # place would make it reappear on any pass later cleared — the two
            # would silently disagree about what this operation does.
            #
            # ONLY the rotation. `exit_mid_t` is shared with the #92 curl, which
            # reads it for its own M point; dropping it here would quietly move a
            # curl the operator sets later to the 0.5 default. With the rotation
            # gone `legacy_break` returns nothing anyway, so leaving t costs
            # nothing and removing it costs a shape.
            if any(per_pass.values()):
                op.pop("exit_mid_rotation", None)
            self.refresh()
            if len(per_pass) > 1:
                self.lbl_explain.config(
                    text=t("bp_applied_all").format(n=len(per_pass)))
            try:
                self.ptab._schedule_auto_calc()
            except Exception:
                pass

        from ui.dialogs.break_points_dialog import BreakPointsDialog
        dlg = BreakPointsDialog(self, self.app, self.op_index, pass_index, _apply)
        dlg.grab_set()
        self.wait_window(dlg)

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
