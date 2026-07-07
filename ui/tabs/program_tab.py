import copy
import tkinter as tk
from tkinter import ttk, messagebox
from ui.dialogs.zone_manager import ZoneManager
from ui.dialogs.tool_manager import ToolManager
from ui.helpers_ui import _fmt_num
from i18n import t

# Accurate default each op-parameter field falls back to when left empty.
# Sourced from the op.get(key, DEFAULT) fallbacks in path_generator.py so the
# faded hint is guaranteed to match real behaviour. A number is shown as
# "default <n>"; a string is shown verbatim (used for relative defaults that
# fall back to another field, e.g. "= Feed").
# clearance is handled per-op-type via the default_hint argument at its two call
# sites (roughing = target_clearance, finishing = allowance+safety).
# exit_curve_tension is intentionally absent: it was removed from path
# generation, so the field no longer has any effect (no honest default to show).
OP_PARAM_DEFAULTS = {
    # ── Fixed-constant defaults ──────────────────────────────────────────
    "count": 1,
    "z_pos": 0,
    "start_z": 10,
    "p1_x": 40,
    "p1_z": 50,
    "p3_z": -20,
    "rot": 0,
    "pass_angle": "off",            # empty = angle feature disabled
    "progressive_angle_end": 180,
    "progressive_reach_end": 30,
    "reach_blank_factor": 1.0,
    "p2_z_extend": 0,
    "p2_radius": 0,
    "exit_mid_t": 0.5,
    "exit_mid_rotation": 0,
    "proj_extend_bottom": 0,
    "proj_extend_top": 0,
    "contact_zone_mm": 0,
    "tilt_start": 0,
    "tilt_end": 0,
    "tilt_offset": 0,
    "back_pass_arc_x": 0,
    "back_pass_arc_z": 0,
    "speed": 200,                   # falls back to global surface_speed_m_min
    "feed": 300,                    # falls back to global feed_rate_mm_min
    # ── Variable defaults — fall back to another value ───────────────────
    "p3_x": "= P1 X",
    "feed_contact": "= Feed",
    "feed_contact_end": "= Feed Contact",
    "back_pass_feed": "= Feed",
    "end_z": "= mandrel top",
    "plunge_x": "= center + 50",
}


# ══════════════════════════════════════════════════════════════════════════
# Customize View — configurable columns + Basic/Advanced field visibility.
#
# These tables drive the "Customize View" dialog and the Program-tab op editor.
# OP_PARAM_UNIVERSE is the master list of every parameter each op *type* can
# render — it is hand-kept in sync with on_op_select() (same maintenance
# contract as OP_PARAM_DEFAULTS above). If you add/remove a field in
# on_op_select, mirror it here or it won't be taggable/columnable.
#
# OP_PARAM_LABELS maps each key to an i18n label key (reused for both the
# customize rows and the tree column headers). _DEFAULT_BASIC / _DEFAULT_COLUMNS
# seed a program that has no saved op_view_config yet (per-program config lives
# in params["op_view_config"]; see _view_cfg / _default_cfg).
# ══════════════════════════════════════════════════════════════════════════

_UNIVERSE_COMMON = ["speed_mode", "speed", "feed_mode", "feed"]

OP_PARAM_UNIVERSE = {
    "roughing": _UNIVERSE_COMMON + [
        "tool_id", "count", "direction",
        "tilt_mode", "tilt_start", "tilt_end", "tilt_offset",
        "start_z", "end_z", "p2_z_extend", "proj_extend_bottom", "proj_extend_top",
        "pass_shape", "p2_radius", "exit_curve_tension", "exit_mid_rotation",
        "exit_mid_t", "conformal_clearance_operation_specific",
        "approach_follow_surface", "p1_x", "p1_z", "p3_x", "p3_z", "reach",
        "reach_follow_blank", "reach_blank_factor",
        "pass_angle", "progressive_angle_enabled", "progressive_angle_end",
        "progressive_reach_enabled", "progressive_reach_end",
        "clearance", "rot",
        "contact_zone_mm", "feed_contact", "feed_contact_end",
        "back_pass_enabled", "back_pass_swapped", "back_pass_feed",
        "back_pass_arc_x", "back_pass_arc_z",
    ],
    "finishing": _UNIVERSE_COMMON + [
        "tool_id", "count", "direction",
        "tilt_mode", "tilt_start", "tilt_end", "tilt_offset",
        "start_z", "end_z", "proj_extend_bottom", "proj_extend_top",
        "clearance", "pass_shape", "straight_line_mode",
    ],
    "cutting":  _UNIVERSE_COMMON + ["tool_id", "z_pos", "plunge_x"],
    "bending":  _UNIVERSE_COMMON + ["tool_id", "z_pos", "plunge_x"],
}

# Tilt fields only exist on tilt-arm machines; filtered out otherwise.
_TILT_KEYS = ("tilt_mode", "tilt_start", "tilt_end", "tilt_offset")

# key -> i18n label key (customize rows + column headers).
OP_PARAM_LABELS = {
    "speed_mode": "lbl_speed_mode", "speed": "vp_speed",
    "feed_mode": "lbl_feed_mode",   "feed": "vp_feed",
    "tool_id": "lbl_tool_id", "count": "lbl_pass_count", "direction": "lbl_direction",
    "tilt_mode": "lbl_tilt_mode", "tilt_start": "lbl_tilt_start",
    "tilt_end": "lbl_tilt_end", "tilt_offset": "lbl_tilt_offset",
    "start_z": "lbl_zone_start", "end_z": "lbl_zone_end",
    "p2_z_extend": "lbl_p2z_extend",
    "proj_extend_bottom": "lbl_proj_bottom", "proj_extend_top": "lbl_proj_top",
    "z_pos": "lbl_z_pos", "plunge_x": "lbl_plunge_x",
    "clearance": "lbl_clearance", "pass_shape": "lbl_shape_mode",
    "straight_line_mode": "lbl_straight_line",
    "p2_radius": "lbl_p2_radius", "exit_curve_tension": "lbl_exit_tension",
    "exit_mid_rotation": "lbl_exit_mid_rot", "exit_mid_t": "lbl_exit_mid_t",
    "conformal_clearance_operation_specific": "lbl_conformal_clr",
    "approach_follow_surface": "lbl_approach_surf",
    "p1_x": "lbl_p1x", "p1_z": "lbl_p1z", "p3_x": "lbl_p3x", "p3_z": "lbl_p3z",
    "reach": "lbl_reach",
    "reach_follow_blank": "lbl_reach_follow",
    "reach_blank_factor": "lbl_reach_factor",
    "pass_angle": "lbl_pass_angle",
    "progressive_angle_enabled": "lbl_progressive",
    "progressive_angle_end": "lbl_progressive_end",
    "progressive_reach_enabled": "lbl_progressive_reach",
    "progressive_reach_end": "lbl_reach_end",
    "rot": "lbl_rotation",
    "contact_zone_mm": "lbl_zone_size", "feed_contact": "lbl_feed_contact",
    "feed_contact_end": "lbl_feed_contact_end",
    "back_pass_enabled": "vp_back_pass", "back_pass_swapped": "lbl_swap_order",
    "back_pass_feed": "lbl_back_feed",
    "back_pass_arc_x": "lbl_back_arc_x", "back_pass_arc_z": "lbl_back_arc_z",
}

# Group toggles → dependent keys. When a toggle is hidden (advanced) its
# dependents are hidden too, so no orphaned sub-fields are left behind.
GROUP_DEPS = {
    "back_pass_enabled": ["back_pass_swapped", "back_pass_feed",
                          "back_pass_arc_x", "back_pass_arc_z"],
    "progressive_angle_enabled": ["progressive_angle_end"],
    "progressive_reach_enabled": ["progressive_reach_end"],
}

# Section header id -> keys under it. A header is hidden when none of its keys
# are currently visible (avoids stray empty section titles in Basic view).
SECTION_KEYS = {
    "speed_feed": ["speed_mode", "speed", "feed_mode", "feed"],
    "path_shape": ["pass_shape", "p2_radius", "exit_curve_tension",
                   "exit_mid_rotation", "exit_mid_t",
                   "conformal_clearance_operation_specific",
                   "approach_follow_surface", "p1_x", "p1_z", "p3_x", "p3_z", "reach",
                   "reach_follow_blank", "reach_blank_factor"],
    "pass_angle": ["pass_angle", "progressive_angle_enabled",
                   "progressive_angle_end", "progressive_reach_enabled",
                   "progressive_reach_end", "clearance", "rot"],
    "contact_zone": ["contact_zone_mm", "feed_contact", "feed_contact_end"],
    "back_pass": ["back_pass_enabled", "back_pass_swapped", "back_pass_feed",
                  "back_pass_arc_x", "back_pass_arc_z"],
}

# Per-type "basic" seed (everything else in the universe is advanced by default).
_DEFAULT_BASIC = {
    "roughing":  {"speed_mode", "speed", "feed_mode", "feed", "tool_id", "count",
                  "direction", "start_z", "end_z", "clearance", "pass_shape"},
    "finishing": {"speed_mode", "speed", "feed_mode", "feed", "tool_id", "count",
                  "direction", "start_z", "end_z", "clearance", "pass_shape",
                  "straight_line_mode"},
    "cutting":   {"speed_mode", "speed", "feed_mode", "feed", "tool_id",
                  "z_pos", "plunge_x"},
    "bending":   {"speed_mode", "speed", "feed_mode", "feed", "tool_id",
                  "z_pos", "plunge_x"},
}

# Per-type default column picks (subset of the universe).
_DEFAULT_COLUMNS = {
    "roughing":  ["count", "start_z", "end_z"],
    "finishing": ["count", "start_z", "end_z"],
    "cutting":   ["z_pos", "plunge_x"],
    "bending":   ["z_pos", "plunge_x"],
}

# ── Batch edit (#67) ─────────────────────────────────────────────────────
# Parameters that CAN be batch-edited at all: numeric scalars only (the batch
# modes are += / = / ×=). Strings, booleans and mode combos are excluded — the
# Customize dialog only offers the Batch checkbox for keys in this set.
_BATCH_ELIGIBLE = {
    "speed", "feed", "count", "start_z", "end_z", "p2_z_extend",
    "proj_extend_bottom", "proj_extend_top", "p2_radius",
    "exit_curve_tension", "exit_mid_rotation", "exit_mid_t",
    "p1_x", "p1_z", "p3_x", "p3_z", "reach", "reach_blank_factor",
    "pass_angle", "progressive_angle_end", "progressive_reach_end",
    "clearance", "rot", "contact_zone_mm", "feed_contact",
    "feed_contact_end", "back_pass_feed", "back_pass_arc_x",
    "back_pass_arc_z", "tilt_start", "tilt_end", "tilt_offset",
    "z_pos", "plunge_x",
}

# Integer-valued params: batch results are rounded and floored to 1.
_BATCH_INT_KEYS = {"count"}

# Default Batch ticks for a program with no saved config — the curated everyday
# subset; the user tunes it per program in Customize View (third checkbox).
_DEFAULT_BATCH_KEYS = {
    "speed", "feed", "count", "start_z", "end_z", "clearance",
    "reach", "reach_blank_factor", "pass_angle", "rot", "z_pos", "plunge_x",
}


def _default_cfg(op_type):
    """Resolved fallback config for an op type with no saved op_view_config."""
    uni = OP_PARAM_UNIVERSE.get(op_type, [])
    basic = _DEFAULT_BASIC.get(op_type, set(uni))
    return {
        "columns":  [k for k in _DEFAULT_COLUMNS.get(op_type, []) if k in uni],
        "advanced": [k for k in uni if k not in basic],
        "batch":    [k for k in uni if k in _DEFAULT_BATCH_KEYS],
    }


class OpUndoStack:
    """Snapshot-based undo/redo history for the operations list (#66).

    Pure logic, no Tk — ProgramTab wraps it with the UI refresh, so it stays
    headless-testable (_test_undo.py). Each entry is (label, deep-copy of the
    ops list, selected index at snapshot time). Ops are plain JSON dicts, so a
    deep copy is cheap even for large programs. Per-session only: the owner
    clears it on project load. Semantics are the standard editor model: push
    records the state BEFORE a mutating action and clears redo; undo moves the
    current state to the redo stack and hands back the snapshot; redo is the
    mirror. Depth-limited — when full, the OLDEST snapshot drops off silently.
    """
    DEPTH = 50

    def __init__(self):
        self._undo = []
        self._redo = []

    def push(self, label, ops, sel_idx=None):
        self._undo.append((label, copy.deepcopy(ops), sel_idx))
        if len(self._undo) > self.DEPTH:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self, current_ops, current_sel=None):
        """Returns (label, ops_to_restore, sel_idx) or None if nothing to undo."""
        if not self._undo:
            return None
        label, ops, sel = self._undo.pop()
        self._redo.append((label, copy.deepcopy(current_ops), current_sel))
        return label, ops, sel

    def redo(self, current_ops, current_sel=None):
        """Returns (label, ops_to_restore, sel_idx) or None if nothing to redo."""
        if not self._redo:
            return None
        label, ops, sel = self._redo.pop()
        self._undo.append((label, copy.deepcopy(current_ops), current_sel))
        return label, ops, sel

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)


class ProgramTab:
    def __init__(self, parent_frame, app, ui_root, ui_helper):
        self.app = app
        self.ui_root = ui_root
        self.helper = ui_helper
        self.frame = parent_frame
        self._auto_calc_debounce_id = None
        # #66: snapshot undo/redo for op-list mutations (button/structural
        # actions only — per-field typing is deliberately not tracked).
        self._op_undo = OpUndoStack()
        # #67: op indices ticked in the ☑ column for batch editing. Cleared on
        # any structural mutation (indices would go stale) and on project load.
        self._batch_checked = set()

        self._create_widgets()

    # ------------------------------------------------------------------
    # Pass Info helpers
    # ------------------------------------------------------------------

    def _op_logical_count(self, op):
        """Number of *forward* passes this op contributes (cutting/bending always 1)."""
        if op.get("type", "roughing") in ("cutting", "bending"):
            return 1
        return int(op.get("count", 1))

    def _op_toolpath_stride(self, op):
        """Toolpath-list entries per forward pass: 2 when back_pass_enabled
        doubles the path count (forward + its back pass), else 1."""
        if op.get("type", "roughing") in ("cutting", "bending"):
            return 1
        return 2 if op.get("back_pass_enabled", False) else 1

    def _get_pass_type_list(self):
        """Returns one (op_type, tool_id, is_back, r_tool, op_idx) tuple per actual entry in
        the calculated toolpaths list — accounting for back_pass_enabled,
        which inserts an extra back-pass entry after each forward pass."""
        result = []
        for op_i, op in enumerate(self.app.params.get("operations", [])):
            if not op.get("enabled", True):
                continue
            op_type = op.get("type", "roughing")
            tool_id = op.get("tool_id", "?")
            r_tool  = float(op.get("r_tool", 0.0))
            has_back = self._op_toolpath_stride(op) == 2
            for _ in range(self._op_logical_count(op)):
                result.append((op_type, tool_id, False, r_tool, op_i))
                if has_back:
                    result.append((op_type, tool_id, True, r_tool, op_i))
        return result

    def refresh_sim_controls(self):
        """Update Step button enabled state based on simulation status."""
        if not hasattr(self, "btn_step"):
            return
        sc = self.app.sim_controller
        if sc.is_running and sc.is_paused:
            self.btn_step.config(state="normal", bg="#4caf50")
        else:
            self.btn_step.config(state="disabled", bg="#b0bec5")

    def _compute_op_end_z(self):
        """Map op-index -> the CAM Z the op's last forming pass actually reaches,
        including p2_z_extend (which pushes the last pass past the planned Zone
        End Z). The value is computed authoritatively by the path generator
        while it builds the paths (path_generator.last_op_end_z), in the SAME
        CAM Z reference as the Zone Start/End Z the user sets — so the two
        columns line up. Empty until the toolpaths are calculated."""
        return dict(getattr(self.app.path_gen, "last_op_end_z", {}) or {})

    def refresh_pass_info(self):
        """Rebuild the pass-info text box from last_calculated_paths."""
        try:
            txt = self.txt_pass_info
        except AttributeError:
            return  # widget not yet built

        paths = getattr(self.app.path_gen, "last_calculated_paths", [])
        center_x = float(self.app.params.get("mandrel_pos_x_offset", 0.0))

        # Coordinate transform parameters (mirror what generate_gcode does)
        invert_x = self.app.params.get("machine_invert_x", False)
        invert_z = self.app.params.get("machine_invert_z", False)
        dir_x = -1.0 if invert_x else 1.0
        dir_z = -1.0 if invert_z else 1.0
        if self.app.params.get("origin_use_home", False):
            origin_x = float(self.app.params.get("home_x", 0.0))
            origin_z = float(self.app.params.get("home_z", 0.0))
        else:
            origin_x = float(self.app.params.get("machine_origin_x", 0.0))
            origin_z = float(self.app.params.get("machine_origin_z", 0.0))
        off_x = float(self.app.params.get("machine_gcode_offset_x", 0.0))
        off_z = float(self.app.params.get("machine_gcode_offset_z", 0.0))
        dia_mode = self.app.params.get("machine_output_diameter_mode", False)

        def to_machine(pt):
            x_out = ((pt[0] - origin_x) * dir_x) + off_x
            z_out = ((pt[2] - origin_z) * dir_z) + off_z
            if dia_mode:
                x_out *= 2.0
            return x_out, z_out

        pass_types = self._get_pass_type_list()

        # Tilt-arm (ID112): per-pass B start/end reference for the operator.
        tilt_arrays = getattr(self.app.path_gen, "last_tilt_angles", None)
        _tilt_kin = None
        if tilt_arrays is not None:
            try:
                from kinematics import get_kinematics
                _tilt_kin = get_kinematics(self.app.params)
            except Exception:
                pass

        txt.config(state="normal")
        txt.delete("1.0", "end")

        import numpy as np

        if not paths:
            txt.insert("end", t("pass_info_empty"), "dim")
            txt.config(state="disabled")
            return

        last_op_idx = -1
        all_ops = self.app.params.get("operations", [])

        for i, path in enumerate(paths):
            if len(path) == 0:
                continue

            entry   = pass_types[i] if i < len(pass_types) else ("roughing", "?", False, 0.0, -1)
            op_type = entry[0]
            tool_id = entry[1]
            is_back = entry[2]
            r_tool  = entry[3]
            op_idx  = entry[4] if len(entry) > 4 else -1

            # ── Per-operation zone reference block ──────────────────────
            if op_idx != last_op_idx:
                last_op_idx = op_idx
                if op_idx >= 0 and op_type not in ("cutting", "bending"):
                    try:
                        mzp = self.app.mandrel_mgr.profile_z
                        if mzp is not None and len(mzp) >= 2:
                            op_def   = all_ops[op_idx] if op_idx < len(all_ops) else {}
                            zone_sz  = float(op_def.get("start_z", float(mzp[0])))
                            zone_ez  = float(op_def.get("end_z",   float(mzp[-1])))

                            pos_x = bool(self.app.params.get("roller_positive_x_side", True))
                            sign  = 1.0 if pos_x else -1.0

                            home_x_cam = float(self.app.params.get("home_x", 0.0))
                            home_z_cam = float(self.app.params.get("home_z", 0.0))
                            hx, hz = to_machine((home_x_cam - sign * r_tool, 0, home_z_cam))

                            r_s = self.app.mandrel_mgr.get_radius_fast(zone_sz)
                            r_e = self.app.mandrel_mgr.get_radius_fast(zone_ez)
                            sx, szm = to_machine((center_x + sign * r_s, 0, zone_sz))
                            ex, ezm = to_machine((center_x + sign * r_e, 0, zone_ez))

                            txt.insert("end",
                                f" ROLLER TIP → MANDREL EDGE  (r={r_tool:.1f} mm) \n", "ref_hdr")
                            txt.insert("end",
                                f"  Zone Start (Z={zone_sz:.1f}):  "
                                f"ΔX={abs(hx-sx):>8.3f}   ΔZ={abs(hz-szm):>8.3f} mm\n"
                                f"  Zone End   (Z={zone_ez:.1f}):  "
                                f"ΔX={abs(hx-ex):>8.3f}   ΔZ={abs(hz-ezm):>8.3f} mm\n\n",
                                "ref")
                    except Exception:
                        pass

            tag_map = {"finishing": "finish_hdr", "cutting": "cut_hdr", "bending": "bend_hdr"}
            tag = tag_map.get(op_type, "rough_hdr")
            lbl_map = {"finishing": "FINISHING", "cutting": "CUTTING", "bending": "BENDING"}
            lbl = lbl_map.get(op_type, "ROUGHING")
            if is_back:
                lbl += " (BACK)"

            pts = np.array(path)

            txt.insert("end", f" Pass {i+1}  [{lbl}]  {tool_id} \n", tag)

            if op_type in ("cutting", "bending"):
                # Path is [approach, plunge] — just show the plunge target
                plunge_xm, plunge_zm = to_machine(pts[-1])
                approach_xm, approach_zm = to_machine(pts[0])
                txt.insert("end", f"  Approach →  X: {approach_xm:>8.3f}   Z: {approach_zm:>8.3f}\n", "data")
                txt.insert("end", f"  Plunge   →  X: {plunge_xm:>8.3f}   Z: {plunge_zm:>8.3f}\n", "contact")
            else:
                # Start / End
                s_xm, s_zm = to_machine(pts[0])
                e_xm, e_zm = to_machine(pts[-1])

                # Closest to mandrel = minimum X distance from center_x
                x_dists = np.abs(pts[:, 0] - center_x)
                crit_idx = int(np.argmin(x_dists))
                c_xm, c_zm = to_machine(pts[crit_idx])
                crit_x_dist = float(x_dists[crit_idx])  # in CAM space

                # Tip X: shift roller center inward by r_tool in CAM space (display only)
                tip_xm, _ = to_machine((float(pts[crit_idx][0]) - r_tool, 0, float(pts[crit_idx][2])))

                txt.insert("end", f"  Start   →  X: {s_xm:>8.3f}   Z: {s_zm:>8.3f}\n", "data")
                txt.insert("end", f"  End     →  X: {e_xm:>8.3f}   Z: {e_zm:>8.3f}\n", "data")
                txt.insert("end", f"  Contact →  ctr X: {c_xm:>8.3f}   tip X: {tip_xm:>8.3f}"
                                   f"   Z: {c_zm:>8.3f}   (Δ: {crit_x_dist:.3f} mm)\n", "contact")

                # Reach = realized exit stroke |P2→P3| (contact → end), the physical
                # meaning of the 'reach' parameter, in mm.
                _reach_mm = float(np.hypot(pts[-1][0] - pts[crit_idx][0],
                                           pts[-1][2] - pts[crit_idx][2]))
                txt.insert("end", f"  Reach   →  |P2→P3|: {_reach_mm:>7.2f} mm\n", "data")

                # B-axis start→end (tilt-arm machines) — operator pre-run reference
                if tilt_arrays is not None and i < len(tilt_arrays):
                    _ta = tilt_arrays[i]
                    if _ta is not None and len(_ta) > 0:
                        _b0 = _tilt_kin.tilt_to_b(float(_ta[0]))  if _tilt_kin else float(_ta[0])
                        _b1 = _tilt_kin.tilt_to_b(float(_ta[-1])) if _tilt_kin else float(_ta[-1])
                        txt.insert("end", f"  Tilt    →  B: {_b0:>7.2f}°  →  {_b1:>7.2f}°\n", "data")
            txt.insert("end", "\n")

        txt.config(state="disabled")

    def _flush_entries(self):
        """Force-save all active entry widgets to params (call before destroying widgets or closing)."""
        for fn in self._active_entry_savers:
            try:
                fn()
            except:
                pass

    # ------------------------------------------------------------------
    # Customize View — config resolver, field visibility, dynamic columns
    # ------------------------------------------------------------------

    def _universe_for(self, op_type):
        """Master parameter list for an op type, with tilt fields dropped on
        non-tilt-arm machines (they aren't rendered there)."""
        uni = OP_PARAM_UNIVERSE.get(op_type, [])
        adapter = getattr(self.app, "active_adapter", None)
        is_tilt = adapter is not None and adapter.get_kinematics() == "tilt_arm"
        if is_tilt:
            return list(uni)
        return [k for k in uni if k not in _TILT_KEYS]

    def _view_cfg(self, op_type):
        """Per-program view config for an op type, falling back to defaults.
        Never mutates params — the config is only materialised when the user
        edits it in the Customize dialog."""
        stored = self.app.params.get("op_view_config", {}).get(op_type)
        if not stored:
            return _default_cfg(op_type)
        return {"columns":  list(stored.get("columns", [])),
                "advanced": list(stored.get("advanced", [])),
                # Older saved configs predate the Batch column (#67): fall back
                # to the curated default. An explicit [] (user unticked all)
                # is respected — only a MISSING key falls back.
                "batch":    list(stored["batch"]) if "batch" in stored
                            else _default_cfg(op_type)["batch"]}

    def _hidden_keys(self, op_type):
        """Set of param keys to hide from the editor for this op type given the
        global Advanced toggle. Expands group toggles to their dependents."""
        if self.app.params.get("op_view_show_advanced", False):
            return set()
        hidden = set(self._view_cfg(op_type)["advanced"])
        for parent, deps in GROUP_DEPS.items():
            if parent in hidden:
                hidden.update(deps)
        return hidden

    def _apply_field_visibility(self, op_type):
        """Hide advanced field rows (and now-empty section headers) from the
        property editor. Non-destructive: values are untouched, only hidden."""
        hidden = self._hidden_keys(op_type)
        children = self.f_prop_editor.winfo_children()
        if hidden:
            for w in children:
                pk = getattr(w, "_pkey", None)
                if pk is not None and pk in hidden:
                    w.pack_forget()
        # Section headers: hide when none of their member keys stay visible.
        rendered = {getattr(w, "_pkey", None) for w in children}
        rendered.discard(None)
        visible = rendered - hidden
        for w in children:
            sec = getattr(w, "_section", None)
            if sec is not None:
                keys = SECTION_KEYS.get(sec, [])
                if not any(k in visible for k in keys):
                    w.pack_forget()

    def _add_section_header(self, section_id, text, separator=True):
        """A section header frame tagged for visibility control. Returns the
        inner frame so callers can add extra widgets (e.g. a help button)."""
        fr = ttk.Frame(self.f_prop_editor)
        fr._section = section_id
        fr.pack(fill="x")
        if separator:
            ttk.Separator(fr, orient="horizontal").pack(fill="x", pady=(6, 2))
        inner = ttk.Frame(fr)
        inner.pack(fill="x")
        ttk.Label(inner, text=text, font=("Arial", 8, "bold"),
                  foreground="#004488").pack(side="left", anchor="w",
                                             padx=10, pady=(0, 2))
        return inner

    def _param_label(self, key):
        return t(OP_PARAM_LABELS.get(key, key))

    def _column_union(self):
        """Ordered, de-duped union of every type's selected columns."""
        seen = []
        for ot in ("roughing", "finishing", "cutting", "bending"):
            uni = self._universe_for(ot)
            for k in self._view_cfg(ot)["columns"]:
                if k in uni and k not in seen:
                    seen.append(k)
        return seen

    def _cell_value(self, op, key, op_type):
        """Text for one configurable column cell. '—' when the parameter does
        not apply to this op type."""
        if key not in self._universe_for(op_type):
            return "—"
        if key not in op:
            dv = OP_PARAM_DEFAULTS.get(key)
            return _fmt_num(dv) if isinstance(dv, (int, float)) and not isinstance(dv, bool) else ""
        val = op[key]
        if isinstance(val, bool):
            return "✓" if val else ""
        if isinstance(val, float):
            return _fmt_num(val)
        return str(val)

    def rebuild_tree_columns(self):
        """(Re)configure the ops-table columns: fixed base + configured extras."""
        extra = self._column_union()
        base = ("Sel", "Idx", "On", "Type", "Count", "Tool", "RealEndZ", "EndReach", "EndAngle")
        cols = base + tuple(f"x_{k}" for k in extra)
        self.tree_ops.configure(columns=cols)
        self.tree_ops.heading("Sel", text="☑"); self.tree_ops.column("Sel", width=28, anchor="center")
        self.tree_ops.heading("Idx", text="#"); self.tree_ops.column("Idx", width=30, anchor="w")
        self.tree_ops.heading("On", text=t("col_on")); self.tree_ops.column("On", width=35, anchor="center")
        self.tree_ops.heading("Type", text=t("col_type")); self.tree_ops.column("Type", width=70)
        self.tree_ops.heading("Count", text=t("col_count")); self.tree_ops.column("Count", width=40)
        self.tree_ops.heading("Tool", text=t("col_tool")); self.tree_ops.column("Tool", width=50)
        self.tree_ops.heading("RealEndZ", text=t("col_real_end_z")); self.tree_ops.column("RealEndZ", width=75, anchor="center")
        self.tree_ops.heading("EndReach", text=t("col_end_reach")); self.tree_ops.column("EndReach", width=70, anchor="center")
        self.tree_ops.heading("EndAngle", text=t("col_end_angle")); self.tree_ops.column("EndAngle", width=65, anchor="center")
        for k in extra:
            self.tree_ops.heading(f"x_{k}", text=self._param_label(k))
            self.tree_ops.column(f"x_{k}", width=75, anchor="center")
        self._extra_cols = list(extra)

    def after_view_config_changed(self):
        """Called by the Customize dialog after it materialises op_view_config."""
        self.rebuild_tree_columns()
        self.refresh_ops_tree()
        if self.tree_ops.selection():
            self.on_op_select(None, _flush=False)
        self.app.save_settings_json()

    def open_view_customizer(self):
        from ui.dialogs.view_customizer import ViewCustomizerDialog
        ViewCustomizerDialog(self.frame.winfo_toplevel(), self.app, self)

    def _create_widgets(self):
        self._active_entry_savers = []
        # Frame for Treeview
        f_tree = ttk.Frame(self.frame)
        f_tree.pack(fill="both", expand=True, padx=5, pady=5)

        cols = ("Sel", "Idx", "On", "Type", "Count", "Tool", "RealEndZ", "EndReach", "EndAngle")
        self.tree_ops = ttk.Treeview(f_tree, columns=cols, show="headings", height=6)
        self.tree_ops.heading("Sel", text="☑"); self.tree_ops.column("Sel", width=28, anchor="center")
        self.tree_ops.heading("Idx", text="#"); self.tree_ops.column("Idx", width=30)
        self.tree_ops.heading("On", text=t("col_on")); self.tree_ops.column("On", width=35, anchor="center")
        self.tree_ops.heading("Type", text=t("col_type")); self.tree_ops.column("Type", width=70)
        self.tree_ops.heading("Count", text=t("col_count")); self.tree_ops.column("Count", width=40)
        self.tree_ops.heading("Tool", text=t("col_tool")); self.tree_ops.column("Tool", width=50)
        self.tree_ops.heading("RealEndZ", text=t("col_real_end_z")); self.tree_ops.column("RealEndZ", width=75, anchor="center")
        self.tree_ops.heading("EndReach", text=t("col_end_reach")); self.tree_ops.column("EndReach", width=70, anchor="center")
        self.tree_ops.heading("EndAngle", text=t("col_end_angle")); self.tree_ops.column("EndAngle", width=65, anchor="center")
        self.tree_ops.tag_configure("op_disabled", foreground="#9e9e9e")

        # Vertical + horizontal scrollbars. The table can carry many configured
        # columns (Zone Start/End Z, clearance, feeds…) — without the horizontal
        # bar the rightmost columns are clipped off the narrow sidebar with no
        # way to reach them. Pack the bars first so the tree fills what's left.
        sb = ttk.Scrollbar(f_tree, orient="vertical", command=self.tree_ops.yview)
        sb.pack(side="right", fill="y")
        sb_x = ttk.Scrollbar(f_tree, orient="horizontal", command=self.tree_ops.xview)
        sb_x.pack(side="bottom", fill="x")
        self.tree_ops.configure(yscrollcommand=sb.set, xscrollcommand=sb_x.set)
        self.tree_ops.pack(side="left", fill="both", expand=True)
        self.tree_ops.bind("<<TreeviewSelect>>", self.on_op_select)
        self.tree_ops.bind("<Double-1>", self._on_tree_double_click)
        # #67: clicking the ☑ cell toggles the row's batch tick (and eats the
        # click so it doesn't disturb the normal row selection).
        self.tree_ops.bind("<Button-1>", self._on_tree_click)

        # Toolbar
        f_tools = ttk.Frame(self.frame)
        f_tools.pack(fill="x", padx=5, pady=2)

        # Actions — op types come from the active machine adapter so a machine
        # type can offer a different operation set (TODO.md #48/#51). One
        # dropdown instead of a button per type: the toolbar stays usable as
        # the op set grows and leaves room for Suggest/On-Off.
        _op_menu_labels = {
            "roughing":  t("btn_add_rough"),
            "finishing": t("btn_add_finish"),
            "cutting":   t("btn_add_cut"),
            "bending":   t("btn_add_bend"),
        }
        adapter = getattr(self.app, "active_adapter", None)
        op_types = adapter.get_available_op_types() if adapter else list(_op_menu_labels.keys())

        mb_add = ttk.Menubutton(f_tools, text=t("btn_add_op"), width=8)
        _add_menu = tk.Menu(mb_add, tearoff=0)
        for op_type in op_types:
            if op_type not in _op_menu_labels:
                continue  # op types without UI support yet (future hot ops)
            _add_menu.add_command(label=_op_menu_labels[op_type].lstrip("+ "),
                                  command=lambda ot=op_type: self.add_op(ot))
        mb_add["menu"] = _add_menu
        mb_add.pack(side="left", padx=1)
        self.helper.bind_tooltip(mb_add, "Listeye yeni operasyon ekle: kaba, bitirme, kesme, kıvırma. "
                                         "Tip seçmek için tıkla.")

        # Advisory operation suggester — only for machines that support the
        # roughing/finishing op pair (both current adapters do).
        if "roughing" in op_types and "finishing" in op_types:
            btn_suggest = tk.Button(f_tools, text=t("btn_suggest_ops"),
                                    bg="#fff3cd", activebackground="#ffe69c",
                                    relief="raised", bd=1, padx=6,
                                    command=self.open_op_suggester)
            btn_suggest.pack(side="left", padx=4)
            self.helper.bind_tooltip(btn_suggest,
                "Mandrel profiline ve malzemeye göre kaba + bitirme operasyonu ÖNERİR. "
                "Öneri yalnızca başlangıç noktasıdır — uygulamadan önce gözden geçirilir, "
                "hiçbir şey otomatik eklenmez.")

        btn_continue = ttk.Button(f_tools, text=t("btn_continue_prev"), width=10,
                                  command=self.continue_from_previous)
        btn_continue.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_continue,
            "Seçili operasyonu, ÜSTÜNDEKİ operasyonun SON pasının bitiş durumundan DOLDUR: "
            "Başlangıç Z = önceki opun bitiş Z'si, açı = son pasın açısı (yelpaze bitişi dâhil), "
            "reach = son pasın reach'i, ayrıca clearance. Tek seferlik: doldurur, sonra "
            "operasyon bağımsızdır. Örn. önceki opun son pasıyla AYNI konum/açıda ters pas "
            "eklemek için kullan — sonra Yön'ü 'Ters' yap. (Takım kopyalanmaz.)")

        btn_split = ttk.Button(f_tools, text=t("btn_split"), width=6,
                               command=self.open_split_op)
        btn_split.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_split,
            "Seçili çok-paslı operasyonu, aralarına bölücü koyarak BİTİŞİK parçalara böl "
            "(örn. 20 pası 1·1·5·5·4·2·2). Her parça, orijinali BİREBİR üreten bağımsız bir "
            "operasyon olur — sonra aralarına ters pas operasyonları yerleştirmek için "
            "sırala. Kesme/kıvırma bölünemez.")

        btn_reach = ttk.Button(f_tools, text=t("btn_compute_reach"), width=7,
                               command=self.compute_reach_from_blank)
        btn_reach.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_reach,
            "Seçili operasyonun REACH'ini kalan sac flanşından TAHMİN ET ve alanı DOLDUR "
            "(opt-in, sessizce uygulanmaz). Alan-eşdeğerliği modeli: kıskaç tabanından "
            "itibaren şekillenen malzeme çıkarılır, kalan flanşın radyal boyu reach olur. "
            "Çok-paslı + Pass Angle'lı op'ta reach tabanda büyük→tepede küçük yelpazelenir. "
            "TAHMİNDİR — çalıştırmadan önce değeri kontrol et. Sac Yarıçapı gerekir.")

        btn_angle = ttk.Button(f_tools, text=t("btn_compute_angle"), width=7,
                               command=self.compute_angle_from_surface)
        btn_angle.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_angle,
            "Seçili op'un PROGRESSIVE ANGLE BİTİŞİNİ mandrel yüzeyinden TAHMİN ET ve DOLDUR "
            "(opt-in). Bitiş Z'deki duvar teğeti = çıkışın yüzey boyunca yattığı açı; "
            "yaklaşım yönüne göre pass-açı çerçevesine çevrilir. Silindirde 180° verir, "
            "konide duvar eğimini. TAHMİNDİR — şekillendirme yönünü (yukarı/aşağı) "
            "çalıştırmadan önce doğrula. Pass Angle gerekir.")

        btn_toggle = ttk.Button(f_tools, text=t("btn_toggle_op"), width=8,
                                command=self.toggle_op_enabled)
        btn_toggle.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_toggle,
            "Seçili operasyonu pasifleştir / aktifleştir (silmeden). Pasif operasyonlar "
            "hesaplamaya ve G-code'a girmez — alternatifleri yan yana tutup karşılaştırmak "
            "için kullan. Listede çift tıklama da aynı işi yapar.")

        btn_del = ttk.Button(f_tools, text=t("btn_del_op"), width=4, command=self.del_op)
        btn_del.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_del, "Seçili operasyonu listeden sil.")

        # Batch edit (#67): one adjustment applied to many ops at once. Enabled
        # when ≥2 ops are targeted (☑ ticks if any, else the tree selection).
        self.btn_batch = ttk.Button(f_tools, text=t("btn_batch"), width=9,
                                    state="disabled", command=self.open_batch_edit)
        self.btn_batch.pack(side="left", padx=1)
        self.helper.bind_tooltip(self.btn_batch,
            "TOPLU DÜZENLE: seçili operasyonların BİR parametresini tek seferde değiştir "
            "(+= sabit ekle / = değer ata / ×= çarpanla ölçekle). Hedef: ☑ sütununda "
            "işaretli op'lar; hiç işaret yoksa listedeki çoklu seçim (Shift/Ctrl+tık). "
            "En az 2 operasyon gerekir. Uygulamadan önce eski→yeni önizleme gösterilir; "
            "tamamı TEK Geri Al (Ctrl+Z) adımıdır. Sunulan parametreler Özelleştir… "
            "penceresindeki 'Toplu' kutusuyla seçilir.")

        btn_tools = ttk.Button(f_tools, text=t("btn_tools"), width=5, command=self.open_tool_manager)
        btn_tools.pack(side="left", padx=5)
        self.helper.bind_tooltip(btn_tools, "Takım kütüphanesini aç. "
                                            "Rulo geometrilerini (ID, yarıçap) buradan tanımlayabilirsin.")

        # Customize View: choose table columns + tag parameters basic/advanced.
        btn_customize = ttk.Button(f_tools, text=t("btn_customize_view"),
                                   command=self.open_view_customizer)
        btn_customize.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_customize,
            "Görünümü özelleştir: operasyon tablosunda hangi parametrelerin sütun olarak "
            "gösterileceğini seç ve her operasyon tipi için parametreleri temel/gelişmiş "
            "olarak işaretle. Ayarlar programa (.ssp) kaydedilir; değerlere dokunmaz.")


        # Global Basic/Advanced view switch — hides advanced-tagged fields from
        # the property editor. View-only: hiding a field never changes its value
        # or the toolpath. State is app-wide (not per program).
        self.var_show_adv = tk.BooleanVar(value=bool(self.app.params.get("op_view_show_advanced", False)))
        def _on_toggle_adv():
            self.app.params["op_view_show_advanced"] = self.var_show_adv.get()
            self.app.save_settings_json()
            if self.tree_ops.selection():
                self.on_op_select(None, _flush=False)
        chk_adv = ttk.Checkbutton(f_tools, text=t("chk_show_advanced"),
                                  variable=self.var_show_adv, command=_on_toggle_adv)
        chk_adv.pack(side="left", padx=4)
        self.helper.bind_tooltip(chk_adv,
            "Açık: tüm parametreler görünür (bugünkü davranış).\n"
            "Kapalı: yalnızca 'temel' işaretli parametreler görünür — nadiren "
            "değiştirdiğin alanlar gizlenir.\n"
            "Sadece görünümü etkiler: gizli bir alanın değeri ve takım yolu DEĞİŞMEZ. "
            "Uygulama genelinde geçerlidir, programa özel değildir.")

        # Navigation & Info (Right side)
        btn_up = ttk.Button(f_tools, text="▲", width=3, command=lambda: self.move_op(-1))
        btn_up.pack(side="right", padx=1)
        self.helper.bind_tooltip(btn_up, "Seçili operasyonu listede yukarı taşı. "
                                         "Operasyonlar listede göründükleri sırayla G-code'a yazılır.")

        btn_dn = ttk.Button(f_tools, text="▼", width=3, command=lambda: self.move_op(1))
        btn_dn.pack(side="right", padx=1)
        self.helper.bind_tooltip(btn_dn, "Seçili operasyonu listede aşağı taşı. "
                                         "Operasyonlar listede göründükleri sırayla G-code'a yazılır.")

        # Time Label (Right of buttons, Left of Arrows)
        self.lbl_time = ttk.Label(f_tools, text="--:--", font=("Arial", 10, "bold"), foreground="#004488")
        self.lbl_time.pack(side="right", padx=10)
        self.helper.bind_tooltip(self.lbl_time, "Tahmini toplam program süresi (dakika:saniye). "
                                                 "Tüm pasların toplam yol uzunluğuna ve besleme hızına göre hesaplanır.")

        # Undo/Redo (#66) — snapshot history of op-list actions. Packed after
        # lbl_time with side="right" so they land left of the time readout.
        self.btn_redo = ttk.Button(f_tools, text="↷", width=3,
                                   command=self.redo_op_action, state="disabled")
        self.btn_redo.pack(side="right", padx=1)
        self.helper.bind_tooltip(self.btn_redo,
            "Yinele (Ctrl+Y): geri aldığın operasyon-listesi işlemini tekrar uygular. "
            "Yeni bir işlem yapınca yinele geçmişi temizlenir.")
        self.btn_undo = ttk.Button(f_tools, text="↶", width=3,
                                   command=self.undo_op_action, state="disabled")
        self.btn_undo.pack(side="right", padx=1)
        self.helper.bind_tooltip(self.btn_undo,
            "Geri al (Ctrl+Z): son operasyon-listesi işlemini geri alır — Böl, Sil, Taşı, "
            "Ekle, Devam ⤵, Reach⟲, Açı⟲, Aç/Kapat, Öneri ekleme. Alan içine yazılan "
            "değerler geri alınmaz. En fazla 50 adım; proje yüklenince geçmiş sıfırlanır.")

        # Keyboard shortcuts. Bound on the toplevel; the handlers ignore the
        # event when the Program tab is not the visible tab or when focus is in
        # a text-entry widget (so Ctrl+Z while typing never reverts the op list).
        _top = self.frame.winfo_toplevel()
        _top.bind("<Control-z>", self._on_undo_key)
        _top.bind("<Control-y>", self._on_redo_key)
        _top.bind("<Control-Shift-Z>", self._on_redo_key)
        self._update_undo_buttons()

        # Property Editor (scrollable)
        _prop_outer = ttk.LabelFrame(self.frame, text=t("frm_op_settings"))
        _prop_outer.pack(fill="x", padx=5, pady=5)

        _prop_canvas = tk.Canvas(_prop_outer, height=300, highlightthickness=0)
        _prop_sb = ttk.Scrollbar(_prop_outer, orient="vertical", command=_prop_canvas.yview)
        _prop_canvas.configure(yscrollcommand=_prop_sb.set)
        _prop_sb.pack(side="right", fill="y")
        _prop_canvas.pack(side="left", fill="both", expand=True)

        self.f_prop_editor = ttk.Frame(_prop_canvas)
        _prop_win = _prop_canvas.create_window((0, 0), window=self.f_prop_editor, anchor="nw")

        self.f_prop_editor.bind("<Configure>",
            lambda e: _prop_canvas.configure(scrollregion=_prop_canvas.bbox("all")))
        _prop_canvas.bind("<Configure>",
            lambda e: _prop_canvas.itemconfig(_prop_win, width=e.width))

        def _mwheel(e): _prop_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        _prop_canvas.bind("<Enter>", lambda e: _prop_canvas.bind_all("<MouseWheel>", _mwheel))
        _prop_canvas.bind("<Leave>", lambda e: _prop_canvas.unbind_all("<MouseWheel>"))

        if "operations" not in self.app.params:
             self.app.params["operations"] = self.app.path_gen._ensure_ops_dict(self.app.params)
        self.rebuild_tree_columns()
        self.refresh_ops_tree()

        # --- Quick Actions (anchored to bottom) ---
        f_actions = ttk.Frame(self.frame)
        f_actions.pack(fill="x", side="bottom", padx=5, pady=(2, 5))

        def _quick_calc():
            self._start_async_calc()

        btn_qsim = tk.Button(f_actions, text=t("btn_q_run_sim"), bg="#00bcd4",
                             font=("Arial", 9, "bold"), command=self.ui_root.run_sim)
        btn_qsim.pack(side="right", padx=(2, 0))
        self.helper.bind_tooltip(btn_qsim, "Hesaplanan takım yollarını 3D görünümde simüle et.")

        # Step mode controls (packed right-to-left, so Step btn appears left of Run Sim)
        self.var_step_mode = tk.BooleanVar(value=False)
        def _on_step_mode_toggle():
            self.app.sim_controller.set_step_mode(self.var_step_mode.get())
            self.refresh_sim_controls()
        chk_step = ttk.Checkbutton(f_actions, text=t("chk_step_mode"),
                                   variable=self.var_step_mode, command=_on_step_mode_toggle)
        chk_step.pack(side="right", padx=(0, 6))
        self.helper.bind_tooltip(chk_step, "Her sequence adımından sonra simülasyonu duraklat.")

        self.btn_step = tk.Button(f_actions, text=t("btn_step_one"), bg="#b0bec5",
                                  font=("Arial", 9, "bold"), state="disabled",
                                  command=self.app.sim_controller.step_one)
        self.btn_step.pack(side="right", padx=(0, 2))
        self.helper.bind_tooltip(self.btn_step, "Bir sonraki sequence adımına ilerle (Step Mode aktifken).")

        self.btn_qcalc = tk.Button(f_actions, text=t("btn_q_calculate"), bg="orange",
                                   font=("Arial", 9, "bold"), command=_quick_calc)
        self.btn_qcalc.pack(side="right", padx=2)
        self.helper.bind_tooltip(self.btn_qcalc, "Tüm takım yollarını yeniden hesapla ve görünümü güncelle.")

        # --- Reference Points ---
        self._build_ref_points_panel()

        # --- Pass Info Panel ---
        f_info = ttk.LabelFrame(self.frame, text=t("frm_pass_info"))
        f_info.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        self.txt_pass_info = tk.Text(
            f_info,
            height=10,
            font=("Consolas", 9),
            bg="#1e1e2e",
            fg="#cdd6f4",
            state="disabled",
            wrap="none",
            relief="flat",
            bd=0,
            padx=4,
            pady=4,
        )
        sb_info_y = ttk.Scrollbar(f_info, orient="vertical",   command=self.txt_pass_info.yview)
        sb_info_x = ttk.Scrollbar(f_info, orient="horizontal", command=self.txt_pass_info.xview)
        self.txt_pass_info.configure(yscrollcommand=sb_info_y.set,
                                     xscrollcommand=sb_info_x.set)
        sb_info_y.pack(side="right",  fill="y")
        sb_info_x.pack(side="bottom", fill="x")
        self.txt_pass_info.pack(fill="both", expand=True)

        # Colour tags
        self.txt_pass_info.tag_configure("rough_hdr",   background="#1d4d99", foreground="#a8d8ff",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("finish_hdr",  background="#7a4500", foreground="#ffd580",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("cut_hdr",     background="#1a4a1a", foreground="#b5e8b5",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("bend_hdr",    background="#4a1a4a", foreground="#e8b5e8",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("data",        foreground="#cdd6f4",
                                         font=("Consolas", 9))
        self.txt_pass_info.tag_configure("contact",     foreground="#a6e3a1",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("ref_hdr",     background="#2a2a3e", foreground="#89dceb",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("ref",         foreground="#f9e2af",
                                         font=("Consolas", 9))
        self.txt_pass_info.tag_configure("dim",         foreground="#6c7086",
                                         font=("Consolas", 9, "italic"))

        # Initial fill (may be empty until paths are calculated)
        self.refresh_pass_info()

    def open_tool_manager(self):
        ToolManager(self.frame.winfo_toplevel(), self.ui_root)

    def refresh_ops_tree(self):
        ops = self.app.params.get("operations", [])
        existing_items = self.tree_ops.get_children()

        # Real Z each op's last forward pass actually reaches (P2, incl.
        # p2_z_extend) — blank until the toolpaths are calculated.
        end_z_map = self._compute_op_end_z()
        # End reach + end angle of each op's last forming pass (#61) — same source
        # timing as RealEndZ (path generator records them during calculate_paths).
        reach_map = dict(getattr(self.app.path_gen, "last_op_reach", {}) or {})
        angle_map = dict(getattr(self.app.path_gen, "last_op_end_angle", {}) or {})

        extra_cols = getattr(self, "_extra_cols", [])
        for i, op in enumerate(ops):
            _on = op.get("enabled", True)
            _ot = op.get("type", "roughing")
            _rz = end_z_map.get(i)
            _rr = reach_map.get(i)
            _ra = angle_map.get(i)
            vals = ["☑" if i in self._batch_checked else "☐",
                    i+1, "✓" if _on else "—", op.get("type", "?").upper(),
                    op.get("count", 1), op.get("tool_id", "?"),
                    _fmt_num(_rz) if _rz is not None else "—",
                    _fmt_num(_rr) if _rr is not None else "—",
                    (f"{_ra:.1f}°" if _ra is not None else "—")]
            for k in extra_cols:
                vals.append(self._cell_value(op, k, _ot))
            vals = tuple(vals)
            tags = () if _on else ("op_disabled",)
            if i < len(existing_items):
                self.tree_ops.item(existing_items[i], values=vals, tags=tags)
            else:
                self.tree_ops.insert("", "end", iid=str(i), values=vals, tags=tags)

        if len(existing_items) > len(ops):
            for i in range(len(ops), len(existing_items)):
                self.tree_ops.delete(existing_items[i])

        self.update_time_estimate()
        self._update_batch_button()

    def toggle_op_enabled(self):
        """Passivate/reactivate the selected op without deleting it. Disabled
        ops are skipped by calculate_paths and generate_gcode (op.get("enabled"))
        so alternatives can be kept side by side and compared."""
        sel = self.tree_ops.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
            op = self.app.params["operations"][idx]
        except (ValueError, IndexError):
            return
        self._push_undo(t("btn_toggle_op"))
        op["enabled"] = not op.get("enabled", True)
        self.refresh_ops_tree()
        # refresh_ops_tree updates rows in place (op count unchanged), so the
        # selection is preserved — only re-select if it was somehow lost, to
        # avoid re-firing on_op_select (a full property-editor rebuild) for nothing.
        if self.tree_ops.selection() != (str(idx),):
            self.tree_ops.selection_set(str(idx))
        self._schedule_auto_calc()

    def _on_tree_double_click(self, event):
        # Double-click anywhere on a row toggles its enabled state — except on
        # the ☑ cell, which belongs to the batch tick (#67).
        if self.tree_ops.identify_column(event.x) == "#1":
            return "break"
        row = self.tree_ops.identify_row(event.y)
        if row:
            # A single-click already selected the row; only set selection if the
            # double-click landed on a different row, so we don't rebuild the
            # property editor twice per toggle.
            if self.tree_ops.selection() != (row,):
                self.tree_ops.selection_set(row)
            self.toggle_op_enabled()

    def _schedule_auto_calc(self, delay_ms=300):
        """Debounced auto-calc: resets the timer on every call; fires once after delay_ms of silence."""
        if self._auto_calc_debounce_id is not None:
            self.frame.after_cancel(self._auto_calc_debounce_id)
        self._auto_calc_debounce_id = self.frame.after(delay_ms, self._fire_auto_calc)

    def _fire_auto_calc(self):
        self._auto_calc_debounce_id = None
        # Respect the auto-calc setting: with it off, toggling / editing ops
        # only refreshes the list (done by the caller) and never recomputes.
        if not self.app.params.get("auto_calculate_paths", False):
            return
        if self.app._calc_running:
            # Calc already in progress — retry after it finishes
            self._schedule_auto_calc(delay_ms=150)
            return
        # Run in the background thread so toggling an op or editing a field
        # never freezes the UI. Previously this called update_scene("paths"),
        # which ran calculate_paths synchronously on the main thread.
        self._start_async_calc()

    def _start_async_calc(self):
        """Kick off a background path calculation, then re-render when it lands.
        Shared by the Quick-Calc button and the debounced auto-calc so both stay
        off the main thread. No-op if a calculation is already running."""
        if self.app._calc_running:
            return
        # Opt-in #61(B): before recomputing, refresh reach for any op locked to the blank
        # edge so a start_z/end_z change immediately re-kisses the flange (never stale).
        self._refresh_auto_reach()
        # Compute roller_pos from current params (same logic as update_scene header)
        _side = 1.0 if self.app.params.get("roller_positive_x_side", True) else -1.0
        _r = 25.0
        try:
            ops = self.app.params.get("operations", [])
            if ops:
                _r = float(ops[0].get("r_tool", 25.0))
        except Exception:
            pass
        _rx = self.app.params.get("home_x", 300.0) + _side * _r
        _rz = self.app.params.get("home_z", 150.0)
        import numpy as _np
        roller_pos = _np.array([_rx, 0, _rz])

        # Busy state
        self.btn_qcalc.config(state="disabled", text=t("status_calculating"))
        self.ui_root.config(cursor="watch")
        self.ui_root.lbl_info.config(text=t("status_calculating"))
        self.ui_root.update_idletasks()

        self.app.calculate_async(roller_pos=roller_pos)
        self._poll_calc_queue()

    def _poll_calc_queue(self):
        """Poll the background calculation queue every 50 ms; render when done."""
        try:
            status, result = self.app._calc_queue.get_nowait()
        except Exception:
            # Not done yet — check again in 50 ms
            self.frame.after(50, self._poll_calc_queue)
            return

        self.app._calc_running = False

        if status == "ok":
            self.app._pending_paths = result
            try:
                self.app.update_scene("paths", use_cached_paths=True)
            except Exception as e:
                from logger_config import logger
                logger.error(f"Render after async calc failed: {e}")
            self.update_time_estimate()
        else:
            from logger_config import logger
            logger.error(f"Background path calculation error: {result}")

        self.btn_qcalc.config(state="normal", text=t("btn_q_calculate"))
        self.ui_root.config(cursor="")

        # Clamp-zone advisory (#62): surface it in the status bar so the operator
        # actually sees it (path_gen only logs it). Persists until the next calc.
        if status == "ok":
            self.ui_root.refresh_clamp_status()
        else:
            self.ui_root.lbl_info.config(text=t("status_ready"), fg="#ddd")

    def update_time_estimate(self):
        try:
            sec = self.app.path_gen.calculate_estimated_time(self.app.params)
            m, s = divmod(int(sec), 60)
            if self.lbl_time: self.lbl_time.config(text=f"{t('lbl_est_time')} {m:02d}:{s:02d}")
        except: pass

    # ------------------------------------------------------------------
    # Undo / Redo for op-list actions (#66)
    # ------------------------------------------------------------------

    def _sel_op_idx(self):
        """Selected op index in the tree, or None."""
        sel = self.tree_ops.selection()
        try:
            return int(sel[0]) if sel else None
        except (ValueError, IndexError):
            return None

    def _push_undo(self, label):
        """Snapshot the ops list BEFORE a mutating toolbar/structural action.
        Called by every op-list mutator (add/del/move/toggle/split/continue/
        Reach⟲/Angle⟲/suggester insert). Per-field typing edits deliberately
        do NOT push — they are cheap to redo by hand and would flood the stack."""
        self._op_undo.push(label, self.app.params.get("operations", []),
                           self._sel_op_idx())
        self._update_undo_buttons()

    def _update_undo_buttons(self):
        if not hasattr(self, "btn_undo"):
            return
        self.btn_undo.config(state="normal" if self._op_undo.can_undo else "disabled")
        self.btn_redo.config(state="normal" if self._op_undo.can_redo else "disabled")

    def clear_undo_history(self):
        """Undo history is per-session and per-project: cleared on project load."""
        self._op_undo.clear()
        self._update_undo_buttons()
        self._clear_batch_checks()

    def undo_op_action(self, event=None):
        self._apply_history(self._op_undo.undo, "msg_undo_done")

    def redo_op_action(self, event=None):
        self._apply_history(self._op_undo.redo, "msg_redo_done")

    def _apply_history(self, pop_fn, msg_key):
        """Shared undo/redo: swap the live ops list with the popped snapshot.
        The current state moves to the counterpart stack (handled by pop_fn)."""
        # Commit pending field edits FIRST so the snapshot of the current state
        # (pushed to the counterpart stack) reflects what the user sees.
        self._flush_entries()
        res = pop_fn(self.app.params.get("operations", []), self._sel_op_idx())
        if res is None:
            return
        label, ops, sel = res
        self._clear_batch_checks()  # #67: indices are stale against the restored list
        # Discard stale property-editor state BEFORE swapping the list — the
        # entry savers are bound to positional indices of the OLD list and
        # would clobber the restored ops on the next flush (see del_op / #56).
        self._active_entry_savers = []
        self._active_op_idx = None
        for w in self.f_prop_editor.winfo_children():
            w.destroy()

        self.app.params["operations"] = ops
        self.refresh_ops_tree()
        if ops:
            new_sel = min(sel if sel is not None else 0, len(ops) - 1)
            self.tree_ops.selection_set(str(new_sel))
            self.on_op_select(None, _flush=False)
        else:
            self.tree_ops.selection_set(())
        self._update_undo_buttons()
        self._schedule_auto_calc()
        try:
            self.ui_root.lbl_info.config(text=t(msg_key).format(a=label), fg="#ddd")
        except Exception:
            pass

    def _key_event_allowed(self, event):
        """True when a Ctrl+Z/Y keypress should act on the op list: the Program
        tab is the visible tab and focus is not inside a text-entry widget."""
        if not self.frame.winfo_ismapped():
            return False
        try:
            cls = event.widget.winfo_class()
        except Exception:
            return True
        return cls not in ("Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox")

    def _on_undo_key(self, event):
        if self._key_event_allowed(event):
            self.undo_op_action()

    def _on_redo_key(self, event):
        if self._key_event_allowed(event):
            self.redo_op_action()

    # ------------------------------------------------------------------
    # Batch edit (#67): multi-select + one adjustment on many ops
    # ------------------------------------------------------------------

    def _on_tree_click(self, event):
        """Toggle the ☑ batch tick when the click lands on the Sel cell.
        Returns 'break' there so the click doesn't change the row selection."""
        if self.tree_ops.identify_region(event.x, event.y) != "cell":
            return None
        if self.tree_ops.identify_column(event.x) != "#1":  # Sel is first
            return None
        row = self.tree_ops.identify_row(event.y)
        if not row:
            return None
        try:
            idx = int(row)
        except ValueError:
            return None
        if idx in self._batch_checked:
            self._batch_checked.discard(idx)
        else:
            self._batch_checked.add(idx)
        self.tree_ops.set(row, "Sel", "☑" if idx in self._batch_checked else "☐")
        self._update_batch_button()
        return "break"

    def _clear_batch_checks(self):
        """Drop all ☑ ticks — indices go stale on structural list changes."""
        if self._batch_checked:
            self._batch_checked.clear()
        self._update_batch_button()

    def _batch_targets(self):
        """Op indices the batch edit applies to: the ☑ ticks when any are set,
        otherwise the tree's (extended) selection. Sorted, deduped, in-range."""
        n = len(self.app.params.get("operations", []))
        if self._batch_checked:
            raw = self._batch_checked
        else:
            raw = set()
            for item in self.tree_ops.selection():
                try:
                    raw.add(int(item))
                except ValueError:
                    pass
        return sorted(i for i in raw if 0 <= i < n)

    def _update_batch_button(self):
        if not hasattr(self, "btn_batch"):
            return
        n = len(self._batch_targets())
        if n >= 2:
            self.btn_batch.config(state="normal", text=f"{t('btn_batch')} ({n})")
        else:
            self.btn_batch.config(state="disabled", text=t("btn_batch"))

    def _batch_param_options(self, targets):
        """Ordered [(key, label)] offered in the batch dialog: union of the
        Batch-ticked params across the target ops' types, numeric-only."""
        ops = self.app.params.get("operations", [])
        types = []
        for i in targets:
            ot = ops[i].get("type", "roughing")
            if ot not in types:
                types.append(ot)
        seen = []
        for ot in types:
            uni = set(self._universe_for(ot))
            for k in self._view_cfg(ot)["batch"]:
                if k in uni and k in _BATCH_ELIGIBLE and k not in seen:
                    seen.append(k)
        return [(k, self._param_label(k)) for k in seen]

    @staticmethod
    def _batch_compute(ops, indices, key, mode, value, universe):
        """Pure #67 core (headless-tested): what a batch apply would do.

        mode: 'add' (+= value) | 'set' (= value) | 'scale' (×= value).
        universe: {op_type: iterable of param keys} — ops of a type that
        doesn't carry `key` are skipped, mirroring the property editor.
        Returns (changes, skipped): changes[idx] = (old, new) with old=None
        when the op had no value and no numeric default (set-mode only);
        skipped[idx] = reason key ('na' = param not in type, 'nobase' =
        add/scale with nothing to start from).
        """
        changes, skipped = {}, {}
        for i in indices:
            op = ops[i]
            ot = op.get("type", "roughing")
            if key not in universe.get(ot, ()):
                skipped[i] = "na"
                continue
            old = op.get(key)
            if not isinstance(old, (int, float)) or isinstance(old, bool):
                dv = OP_PARAM_DEFAULTS.get(key)
                old = dv if isinstance(dv, (int, float)) and not isinstance(dv, bool) else None
            if mode == "set":
                new = value
            elif old is None:
                skipped[i] = "nobase"
                continue
            elif mode == "add":
                new = old + value
            else:  # scale
                new = old * value
            if key in _BATCH_INT_KEYS:
                new = max(1, int(round(new)))
            else:
                new = round(float(new), 6)
            changes[i] = (old, new)
        return changes, skipped

    def open_batch_edit(self):
        targets = self._batch_targets()
        if len(targets) < 2:
            return
        options = self._batch_param_options(targets)
        if not options:
            messagebox.showinfo(t("dlg_batch_title"), t("msg_batch_noparams"))
            return
        from ui.dialogs.batch_edit_dialog import BatchEditDialog
        BatchEditDialog(self.frame.winfo_toplevel(), self, targets, options)

    def _apply_batch(self, key, changes):
        """Apply callback from BatchEditDialog: one undo snapshot (#66) for the
        whole batch, write the new values, refresh, recalc (debounced)."""
        if not changes:
            return
        self._push_undo(t("btn_batch"))
        ops = self.app.params.get("operations", [])
        for idx, (_old, new) in changes.items():
            if 0 <= idx < len(ops):
                ops[idx][key] = new
        self.refresh_ops_tree()
        # Rebuild the editor so its entry widgets (and savers) pick up the new
        # values — otherwise the anchor op's next flush would write the stale
        # pre-batch value back over the batch result.
        if self.tree_ops.selection():
            self.on_op_select(None, _flush=False)
        self._schedule_auto_calc()
        try:
            self.ui_root.lbl_info.config(
                text=t("msg_batch_done").format(n=len(changes),
                                                p=self._param_label(key)), fg="#ddd")
        except Exception:
            pass

    def on_op_select(self, event, _flush=True):
        sel = self.tree_ops.selection()
        self._update_batch_button()
        if not sel:
            for w in self.f_prop_editor.winfo_children(): w.destroy()
            return

        try:
            idx = int(sel[0])
            if idx >= len(self.app.params["operations"]): return
            op = self.app.params["operations"][idx]
        except: return

        # Seçili operasyonun global pas indeksini hesapla (toolpaths list
        # index space — back_pass_enabled doubles an op's entry count, so
        # each prior op contributes logical_count * stride entries, not
        # just its logical pass count).
        cumulative = 0
        for i, o in enumerate(self.app.params.get("operations", [])):
            if i == idx: break
            if o.get("enabled", True):
                cumulative += self._op_logical_count(o) * self._op_toolpath_stride(o)

        # Operasyon değiştiyse within-op sayacını sıfırla
        if not hasattr(self, '_active_op_idx') or self._active_op_idx != idx:
            self._within_op_idx = 0
            self._active_op_idx = idx
        self._op_start_pass_idx = cumulative
        # _within_op_idx is a direct toolpath-entry offset within this op (0-based),
        # so it can land on back-pass entries too (forward/back are interleaved when
        # back_pass_enabled — stride 2).
        self.app.active_editing_pass_idx = cumulative + self._within_op_idx
        self.app.recolor_paths()

        # #63: refresh the faded-blue deformed-blank overlay for the now-current active pass.
        # Cheap — rebuilds only the small overlay surface + renders; does NOT recompute paths.
        try:
            self.app.update_deformed_blank(render=True)
        except Exception:
            pass

        if _flush:
            self._flush_entries()
        self._active_entry_savers = []
        for w in self.f_prop_editor.winfo_children(): w.destroy()

        op_type = op.get("type", "roughing")

        # Save as Default button
        def _save_preset(_op=op, _type=op_type):
            preset = {k: v for k, v in _op.items() if k != "type"}
            if "op_presets" not in self.app.params:
                self.app.params["op_presets"] = {}
            self.app.params["op_presets"][_type] = preset
            self.app.save_settings_json()
            btn_preset.config(text=t("btn_saved"), foreground="green")
            self.frame.after(1500, lambda: btn_preset.config(text=t("btn_save_default"), foreground=""))

        btn_preset = ttk.Button(self.f_prop_editor, text=t("btn_save_default"), command=_save_preset)
        btn_preset.pack(fill="x", padx=10, pady=(5, 2))
        self.helper.bind_tooltip(btn_preset,
            f"Bu {op_type} operasyonunun parametrelerini varsayılan olarak kaydet.\n"
            "Sonraki '+' butonuyla eklenen aynı tip operasyon bu parametrelerle başlar.")

        # Paso navigatörü — birden fazla toolpath girdisi olan operasyonlar için.
        # back_pass_enabled olduğunda her ileri pasın ardından bir geri pas gelir
        # (stride 2), bu yüzden navigatör ileri+geri tüm girdiler arasında gezinir:
        # ör. 5 pas + geri pas = 10 girdi.
        count  = self._op_logical_count(op)
        stride = self._op_toolpath_stride(op)
        n_entries = count * stride

        def _pass_nav_text(within, c=count, s=stride):
            if s == 2:
                fwd_no  = within // 2 + 1
                is_back = (within % 2 == 1)
                return f"{t('pass_nav_label')}  {fwd_no} / {c}   {t('pass_nav_back') if is_back else t('pass_nav_fwd')}"
            return f"{t('pass_nav_label')}  {within + 1} / {c}"

        if n_entries > 1:
            # Clamp a stale within-op index (e.g. when toggling back pass on/off).
            if self._within_op_idx >= n_entries:
                self._within_op_idx = 0
                self.app.active_editing_pass_idx = self._op_start_pass_idx

            f_nav = ttk.Frame(self.f_prop_editor)
            f_nav.pack(fill="x", padx=5, pady=(5, 2))

            self._lbl_pass_nav = ttk.Label(
                f_nav, text=_pass_nav_text(self._within_op_idx),
                font=("Arial", 10, "bold"), foreground="purple")

            def go_prev(n=n_entries):
                if self._within_op_idx > 0:
                    self._within_op_idx -= 1
                    self.app.active_editing_pass_idx = self._op_start_pass_idx + self._within_op_idx
                    self._lbl_pass_nav.config(text=_pass_nav_text(self._within_op_idx))
                    self.app.recolor_paths()
                    self.app.update_deformed_blank(render=True)   # #63: bend blank to this pass

            def go_next(n=n_entries):
                if self._within_op_idx < n - 1:
                    self._within_op_idx += 1
                    self.app.active_editing_pass_idx = self._op_start_pass_idx + self._within_op_idx
                    self._lbl_pass_nav.config(text=_pass_nav_text(self._within_op_idx))
                    self.app.recolor_paths()
                    self.app.update_deformed_blank(render=True)   # #63: bend blank to this pass

            ttk.Button(f_nav, text="◀", width=3, command=go_prev).pack(side="left")
            self._lbl_pass_nav.pack(side="left", padx=8)
            ttk.Button(f_nav, text="▶", width=3, command=go_next).pack(side="left")
            ttk.Separator(self.f_prop_editor, orient="horizontal").pack(fill="x", pady=(4, 2))

        # --- Speed & Feed ---
        self._add_section_header("speed_feed", t("lbl_speed_feed"), separator=False)
        # Speed
        self._add_prop_combo(idx, "speed_mode", t("lbl_speed_mode"), ["CSS", "RPM"], op,
                             "CSS (G96): Sabit yüzey hızı — mil devri çapa göre otomatik ayarlanır, yüzey kalitesi daha düzgün. "
                             "RPM (G97): Sabit devir — mil hızı sabit kalır.")
        s_lbl = t("lbl_speed_mmin") if op.get("speed_mode", "CSS") == "CSS" else t("lbl_speed_rpm")
        s_tooltip = ("Yüzey hızı değeri (m/dak). CSS modunda kullanılır. "
                     "Metal sıvama için tipik değer: 100–400 m/dak."
                     if op.get("speed_mode", "CSS") == "CSS" else
                     "Mil devri (RPM). Sabit RPM modunda kullanılır. "
                     "Tipik değer: 300–2000 RPM, malzeme ve çapa göre değişir.")
        self._add_prop_entry(idx, "speed", s_lbl, op, is_float=True, tooltip=s_tooltip)

        # Feed
        self._add_prop_combo(idx, "feed_mode", t("lbl_feed_mode"), ["mm_min", "mm_rev"], op,
                             "mm/min (G98): Besleme hızı dakikada mm olarak. "
                             "mm/rev (G99): Tur başına mm olarak — devir değişse de talaş kalınlığı sabit kalır.")
        f_lbl = t("lbl_feed_mmin") if op.get("feed_mode", "mm_min") == "mm_min" else t("lbl_feed_mrev")
        f_tooltip = ("Besleme hızı (mm/dak). "
                     "Metal sıvama için tipik değer: 100–600 mm/dak. "
                     "Düşük değer = daha iyi yüzey, yüksek değer = hızlı üretim."
                     if op.get("feed_mode", "mm_min") == "mm_min" else
                     "Tur başına besleme (mm/dev). "
                     "Tipik değer: 0.1–1.0 mm/dev. Devir değişse de talaş kalınlığı sabit kalır.")
        self._add_prop_entry(idx, "feed", f_lbl, op, is_float=True, tooltip=f_tooltip)

        # --- Cutting / Bending: simplified property set ---
        if op_type in ("cutting", "bending"):
            ttk.Separator(self.f_prop_editor, orient="horizontal").pack(fill="x", pady=5)

            # Tool ID
            f_tool = ttk.Frame(self.f_prop_editor)
            f_tool._pkey = "tool_id"
            f_tool.pack(fill="x", padx=10, pady=2)
            tk.Label(f_tool, text=t("lbl_tool_id")).pack(side="left")
            tool_ids = [tl["id"] for tl in self.ui_root.tool_library]
            if not tool_ids: tool_ids = ["T0101", "T0202"]
            cb_tool = ttk.Combobox(f_tool, values=tool_ids, width=15)
            cb_tool.pack(side="right")
            cb_tool.set(op.get("tool_id", "T0101"))
            _cb_r_var = tk.StringVar()
            def _init_cb_r_var():
                tl = next((tl for tl in self.ui_root.tool_library if tl["id"] == op.get("tool_id", "")), None)
                if tl:
                    r_cal = tl.get("r_tool")
                    r = r_cal if r_cal is not None else tl.get("radius", op.get("r_tool", 0.0))
                else:
                    r = op.get("r_tool", 0.0)
                _cb_r_var.set(f"{r:.1f} mm")
            _init_cb_r_var()

            def on_tool_change_cb(event=None, _idx=idx):
                tid = cb_tool.get().strip()
                if tid:
                    self.app.on_param_change(f"operations[{_idx}].tool_id", tid, "paths")
                    found = next((tl for tl in self.ui_root.tool_library if tl["id"] == tid), None)
                    if found:
                        r_cal = found.get("r_tool")
                        r = r_cal if r_cal is not None else found.get("radius", 0.0)
                        self.app.on_param_change(f"operations[{_idx}].r_tool", r, "paths")
                        _cb_r_var.set(f"{r:.1f} mm")
            cb_tool.bind("<<ComboboxSelected>>", on_tool_change_cb)
            cb_tool.bind("<Return>", on_tool_change_cb)
            cb_tool.bind("<FocusOut>", on_tool_change_cb)

            f_r_cb = ttk.Frame(self.f_prop_editor)
            f_r_cb.pack(fill="x", padx=10, pady=2)
            ttk.Label(f_r_cb, text=t("lbl_tool_radius"), width=15).pack(side="left")
            ttk.Label(f_r_cb, textvariable=_cb_r_var, foreground="#6c7086").pack(side="right")
            self._add_prop_entry(idx, "z_pos", t("lbl_z_pos"), op, is_float=True,
                                 tooltip="Kesim / kıvırma Z pozisyonu (mm, global koordinat). "
                                         "Takım bu Z koordinatında radyal hareket yapar.")
            self._add_prop_entry(idx, "plunge_x", t("lbl_plunge_x"), op, is_float=True,
                                 tooltip="Takımın plunge yapacağı hedef X koordinatı (mm, global koordinat). "
                                         "Mandrel merkezinden itibaren radyal mesafe. "
                                         "Takım bu X'e kadar besleme hızında ilerler.")
            self._apply_field_visibility(op_type)
            return

        # Zones Button
        f_z = ttk.Frame(self.f_prop_editor)
        f_z.pack(fill="x", padx=2, pady=5)
        def open_zones():
            ZoneManager(self.frame.winfo_toplevel(), self.app, idx)

        btn_z = tk.Button(f_z, text=t("btn_variable_zones"), bg="lightblue", command=open_zones)
        btn_z.pack(fill="x")
        self.helper.bind_tooltip(btn_z, "Belirli Z derinliklerinde hız ve besleme değişimi tanımla. "
                                        "Örn: mandrel boynunda daha yavaş besleme, düz bölgede hızlı.")

        ttk.Separator(self.f_prop_editor, orient="horizontal").pack(fill="x", pady=5)

        # Common Props
        # Tool ID Selector
        f_tool = ttk.Frame(self.f_prop_editor)
        f_tool._pkey = "tool_id"
        f_tool.pack(fill="x", padx=10, pady=2)
        tk.Label(f_tool, text=t("lbl_tool_id")).pack(side="left")

        tool_ids = [tl["id"] for tl in self.ui_root.tool_library]
        if not tool_ids: tool_ids = ["T0101", "T0202"]

        cb_tool = ttk.Combobox(f_tool, values=tool_ids, width=15)
        cb_tool.pack(side="right")
        cb_tool.set(op.get("tool_id", "T0101"))

        _r_var = tk.StringVar()
        def _init_r_var():
            tl = next((tl for tl in self.ui_root.tool_library if tl["id"] == op.get("tool_id", "")), None)
            if tl:
                r_cal = tl.get("r_tool")
                r = r_cal if r_cal is not None else tl.get("radius", op.get("r_tool", 0.0))
            else:
                r = op.get("r_tool", 0.0)
            _r_var.set(f"{r:.1f} mm")
        _init_r_var()

        def on_tool_change(event=None):
            tid = cb_tool.get().strip()
            if not tid:
                return
            self.app.on_param_change(f"operations[{idx}].tool_id", tid, "paths")
            found = next((tl for tl in self.ui_root.tool_library if tl["id"] == tid), None)
            if found:
                r_cal = found.get("r_tool")
                r = r_cal if r_cal is not None else found.get("radius", 0.0)
                self.app.on_param_change(f"operations[{idx}].r_tool", r, "paths")
                _r_var.set(f"{r:.1f} mm")

        cb_tool.bind("<<ComboboxSelected>>", on_tool_change)
        cb_tool.bind("<Return>", on_tool_change)
        cb_tool.bind("<FocusOut>", on_tool_change)
        self.helper.bind_tooltip(cb_tool, "Bu operasyon için kullanılacak takımı seç. "
                                          "Takım kütüphanesinde tanımlı rulolar listelenir.")

        f_r = ttk.Frame(self.f_prop_editor)
        f_r.pack(fill="x", padx=10, pady=2)
        ttk.Label(f_r, text=t("lbl_tool_radius"), width=15).pack(side="left")
        ttk.Label(f_r, textvariable=_r_var, foreground="#6c7086").pack(side="right")
        self._add_prop_entry(idx, "count", t("lbl_pass_count"), op, is_int=True, rebuild=True,
                             tooltip="Bu operasyonda oluşturulacak pas sayısı. "
                                     "Kaba işlemde: malzemeyi mandrel'e adım adım yaklaştıran pas sayısı. "
                                     "Bitirmede: genellikle 1–3 pas yeterlidir.")

        # Pass direction (Forward / Reverse) — roughing & finishing only.
        # Reverse flips only the cut traversal of each pass (geometry unchanged);
        # the pass-to-pass progression order stays the same.
        f_dir = ttk.Frame(self.f_prop_editor)
        f_dir._pkey = "direction"
        f_dir.pack(fill="x", padx=10, pady=2)
        ttk.Label(f_dir, text=t("lbl_direction"), width=15).pack(side="left")
        _dir_map = {t("opt_forward"): "forward", t("opt_reverse"): "reverse"}
        _dir_rev = {v: k for k, v in _dir_map.items()}
        _dir_var = tk.StringVar(value=_dir_rev.get(op.get("direction", "forward"), t("opt_forward")))
        cb_dir = ttk.Combobox(f_dir, values=list(_dir_map.keys()), textvariable=_dir_var,
                              state="readonly", width=16)
        cb_dir.pack(side="right", fill="x", expand=True)
        def _on_dir(event=None, _i=idx, _v=_dir_var, _m=_dir_map):
            self.app.params["operations"][_i]["direction"] = _m.get(_v.get(), "forward")
            if self.app.params.get("calc_active", False):
                self.app.update_scene("paths")
        cb_dir.bind("<<ComboboxSelected>>", _on_dir)
        self.helper.bind_tooltip(cb_dir,
            "Pasın kesim (ilerleme) yönü.\n"
            "İleri (Forward): varsayılan yön.\n"
            "Ters (Reverse): kesim yönü tersine çevrilir (uç→kök).\n"
            "Çok paslı işlemde sadece her pasın kesim yönü değişir; "
            "pasların oluşturulma sırası aynı kalır.")

        # Tilt (B axis) — tilt-arm machines only (ID112). Per-op tilt source:
        # normal = follow surface normal (+offset), interp = linear in Z
        # between the op's Start Z and End Z (surface-position based).
        _adapter = getattr(self.app, "active_adapter", None)
        if _adapter is not None and _adapter.get_kinematics() == "tilt_arm":
            f_tm = ttk.Frame(self.f_prop_editor)
            f_tm._pkey = "tilt_mode"
            f_tm.pack(fill="x", padx=10, pady=2)
            ttk.Label(f_tm, text=t("lbl_tilt_mode"), width=15).pack(side="left")
            _tm_map = {t("opt_tilt_normal"): "normal", t("opt_tilt_interp"): "interp"}
            _tm_rev = {v: k for k, v in _tm_map.items()}
            _tm_var = tk.StringVar(value=_tm_rev.get(op.get("tilt_mode", "normal"),
                                                     t("opt_tilt_normal")))
            cb_tm = ttk.Combobox(f_tm, values=list(_tm_map.keys()), textvariable=_tm_var,
                                 state="readonly", width=16)
            cb_tm.pack(side="right", fill="x", expand=True)
            def _on_tm(event=None, _i=idx, _v=_tm_var, _m=_tm_map):
                self.app.params["operations"][_i]["tilt_mode"] = _m.get(_v.get(), "normal")
                if self.app.params.get("calc_active", False):
                    self.app.update_scene("paths")
                # Re-render so mode-specific fields (offset vs start/end) swap.
                self.on_op_select(None, _flush=False)
            cb_tm.bind("<<ComboboxSelected>>", _on_tm)
            self.helper.bind_tooltip(cb_tm,
                "Rulo eğim (B ekseni) kaynağı.\n"
                "Yüzey Normali: eğim her noktada mandrel yüzey normalini izler; "
                "Eğim Ofseti ile öne/arkaya yatırılabilir.\n"
                "Başlangıç→Bitiş: açı, noktanın Z konumuna bağlıdır — operasyonun "
                "Başlangıç Z'sinde başlangıç açısı, Bitiş Z'sinde bitiş açısı, "
                "arada Z'ye göre doğrusal geçiş.")
            if op.get("tilt_mode", "normal") == "interp":
                self._add_prop_entry(idx, "tilt_start", t("lbl_tilt_start"), op, is_float=True,
                                     tooltip="Operasyonun Başlangıç Z konumundaki eğim açısı (°). "
                                             "Açı yüzey konumuna (Z) bağlıdır, pasa değil — her pas "
                                             "aynı Z'de aynı açıyı kullanır. "
                                             "0° = radyal kızak (makine #1 ile aynı duruş), "
                                             "pozitif değer takımı +Z yönüne eğer.")
                self._add_prop_entry(idx, "tilt_end", t("lbl_tilt_end"), op, is_float=True,
                                     tooltip="Operasyonun Bitiş Z konumundaki eğim açısı (°). "
                                             "Aradaki noktalar Z'ye göre doğrusal geçer; bölge "
                                             "dışındaki Z değerleri uç açılara kırpılır.")
            else:
                self._add_prop_entry(idx, "tilt_offset", t("lbl_tilt_offset"), op, is_float=True,
                                     tooltip="Yüzey normaline eklenen sabit açı (°). "
                                             "Pozitif = takım ilerleme yönünde öne yatar (lead), "
                                             "negatif = geriye yatar (lag). B limitlerine kırpılır.")

        # Zone range: Start Z to End Z  (with flat-section hint)
        try:
            flat_z = self.app.mandrel_mgr.get_flat_start_z()
            if flat_z is not None:
                f_hint = ttk.Frame(self.f_prop_editor)
                f_hint.pack(fill="x", padx=10, pady=(2, 0))
                hint_txt = t("lbl_flat_hint").format(f"{flat_z:.1f}")
                ttk.Label(f_hint, text=hint_txt,
                          foreground="#888800", font=("Arial", 8, "italic")).pack(side="left")
        except Exception:
            pass

        self._add_prop_entry(idx, "start_z", t("lbl_zone_start"), op, is_float=True,
                             tooltip="Bu operasyonun başladığı Z pozisyonu (mm, global koordinat). "
                                     "Pasların ilk temas noktasının Z değeri. "
                                     "Mandrel yüzünden itibaren ölçülür.")
        self._add_prop_entry(idx, "end_z", t("lbl_zone_end"), op, is_float=True,
                             tooltip="Bu operasyonun bittiği Z pozisyonu (mm, global koordinat). "
                                     "Pas bitiş noktasının Z değeri. "
                                     "Start Z'den büyük olmalı.")
        if op_type == "roughing":
            self._add_prop_entry(idx, "p2_z_extend", t("lbl_p2z_extend"), op, is_float=True,
                                 tooltip="Her pasın P2 temas noktasını Z ekseninde ileri kaydırır (mm). "
                                         "linear_approach modunda yaklaşım kolu bu kadar daha uzağa uzanır — "
                                         "paslar arasındaki boşluğu doldurmak için kullanılır. "
                                         "Önerilen değer: (Zone uzunluğu / pas sayısı) − P1 Z")

        self._add_prop_entry(idx, "proj_extend_bottom", t("lbl_proj_bottom"), op, is_float=True,
                             tooltip="Turkuaz projeksiyon çizgisini mandrel alt sınırının kaç mm altına uzat. "
                                     "Lineer şekillerde pozitif değer gir, küresel şekillerde 0 bırak.")
        self._add_prop_entry(idx, "proj_extend_top", t("lbl_proj_top"), op, is_float=True,
                             tooltip="Turkuaz projeksiyon çizgisini mandrel üst sınırının kaç mm üstüne uzat. "
                                     "Lineer şekillerde pozitif değer gir, küresel şekillerde 0 bırak.")

        if op_type == "roughing":
            _hdr = self._add_section_header("path_shape", t("lbl_path_shape_hdr"))
            ttk.Button(_hdr, text=" ? ", width=3,
                       command=lambda _op=op: self._show_pass_diagram(_op)).pack(side="right", padx=(4, 0))

            # Pass shape mode
            f_shape = ttk.Frame(self.f_prop_editor)
            f_shape._pkey = "pass_shape"
            f_shape.pack(fill="x", padx=2, pady=1)
            ttk.Label(f_shape, text=t("lbl_shape_mode"), width=15).pack(side="left")
            _shape_opts = ["spline", "linear_approach", "linear_full"]
            _shape_var = tk.StringVar(value=op.get("pass_shape", "spline"))
            cb_shape = ttk.Combobox(f_shape, values=_shape_opts, textvariable=_shape_var,
                                    state="readonly", width=16)
            cb_shape.pack(side="right", fill="x", expand=True)
            def _on_shape(event=None, _i=idx, _v=_shape_var):
                self.app.params["operations"][_i]["pass_shape"] = _v.get()
                if self.app.params.get("calc_active", False):
                    self.app.update_scene("paths")
                # Re-render so fields that only apply to certain shape modes
                # (P1 X, P2 Radius, Exit Tension, Exit Mid Rot/t, Approach ∥ Surf)
                # show/hide immediately.
                self.on_op_select(None)
            cb_shape.bind("<<ComboboxSelected>>", _on_shape)
            self.helper.bind_tooltip(cb_shape,
                "spline: P1→P2→P3 tam spline eğrisi (varsayılan).\n"
                "linear_approach: Z ekseninde yatay yaklaşım (P1X yoksayılır), P2→P3 spline eğrisi.\n"
                "linear_full: Z ekseninde yatay yaklaşım + P2→P3 düz çizgi — tamamen lineer, eğri yok.")

            pass_shape_val = op.get("pass_shape", "spline")
            is_linear = pass_shape_val in ("linear_approach", "linear_full")

            if is_linear:
                self._add_prop_entry(idx, "p2_radius", t("lbl_p2_radius"), op, is_float=True,
                                     tooltip="P2 köşesinde gerçek sabit-yarıçaplı bir daire yayı (fileto) oluşturur. "
                                             "linear_approach ve linear_full modlarında etkilidir.\n"
                                             "0 veya boş = keskin köşe (varsayılan).\n"
                                             "Yay, düz yaklaşım koluna ve çıkışa (P2→P3) tam tanjant olacak şekilde "
                                             "geometrik olarak hesaplanır — yaklaşıklama değil, gerçek yarıçap.\n"
                                             "Çok büyük değerler mevcut kol uzunluklarına göre otomatik sınırlanır.\n"
                                             "Tipik: 5–15 mm.")

            if pass_shape_val == "linear_approach":
                self._add_prop_entry(idx, "exit_curve_tension", t("lbl_exit_tension"), op, is_float=True,
                                     tooltip="P2→P3 çıkış eğrisinin kıvrım miktarı (P2→P3 mesafesinin oranı).\n"
                                             "Varsayılan: 0.4  (P2→P3 uzunluğunun %40'ı kadar kontrol noktası yüksekliği).\n"
                                             "Büyük değer → daha kıvrımlı çıkış, küçük değer → P3'e neredeyse düz çizgi.\n"
                                             "Önerilen aralık: 0.1–1.5.\n"
                                             "Geri pas da aynı değeri kullanır: bp_arc_x/z=0 iken geri pas, "
                                             "ileri çıkış eğrisinin tam tersidir.")

                # Exit Mid Rotation — M noktasından sonrasını M etrafında döndürür
                self._add_prop_entry(idx, "exit_mid_rotation", t("lbl_exit_mid_rot"), op, is_float=True,
                                     tooltip="P2→P3 çıkış eğrisi üzerinde bir M noktası seçip, M'den SONRASINI "
                                             "(M→P3 kuyruğu) M etrafında bu açıda döndürür (derece, XZ düzlemi).\n"
                                             "T2→M kısmı değişmez; P3 kuyrukla birlikte döner.\n"
                                             "0 veya boş = etkisiz (düz çıkış eğrisi). Pozitif/negatif yönü değiştirir.\n"
                                             "Sadece linear_approach modunda geçerli. Clearance düzeltmesi yine uygulanır.")
                self._add_prop_entry(idx, "exit_mid_t", t("lbl_exit_mid_t"), op, is_float=True,
                                     tooltip="M noktasının çıkış eğrisi üzerindeki konumu (oran, 0–1, varsayılan 0.5).\n"
                                             "Küçük = M P2'ye yakın (daha uzun kuyruk döner), büyük = P3'e yakın.\n"
                                             "0.05–0.95 arasına sınırlanır. Sadece Exit Mid Rot ≠ 0 iken etkilidir.")

            f_conf = ttk.Frame(self.f_prop_editor)
            f_conf._pkey = "conformal_clearance_operation_specific"
            f_conf.pack(fill="x", padx=2, pady=1)
            ttk.Label(f_conf, text=t("lbl_conformal_clr"), width=15).pack(side="left")
            conf_var = tk.BooleanVar(value=bool(op.get("conformal_clearance_operation_specific", False)))
            def toggle_conformal(i=idx):
                self.app.params["operations"][i]["conformal_clearance_operation_specific"] = conf_var.get()
                if self.app.params.get("calc_active", False):
                    self.app.update_scene("paths")
            ttk.Checkbutton(f_conf, variable=conf_var, command=toggle_conformal).pack(side="right")
            self.helper.bind_tooltip(f_conf,
                "Temas noktası P2'yi mandrel yüzey normaline göre yerleştir (finishing gibi). "
                "Eğimli yüzeylerde clearance'ı doğru tutar. "
                "Kapalıysa saf radyal offset kullanılır.")

            if is_linear:
                f_afs = ttk.Frame(self.f_prop_editor)
                f_afs._pkey = "approach_follow_surface"
                f_afs.pack(fill="x", padx=2, pady=1)
                ttk.Label(f_afs, text=t("lbl_approach_surf"), width=15).pack(side="left")
                afs_var = tk.BooleanVar(value=bool(op.get("approach_follow_surface", False)))
                def toggle_afs(i=idx):
                    self.app.params["operations"][i]["approach_follow_surface"] = afs_var.get()
                    if self.app.params.get("calc_active", False):
                        self.app.update_scene("paths")
                ttk.Checkbutton(f_afs, variable=afs_var, command=toggle_afs).pack(side="right")
                self.helper.bind_tooltip(f_afs,
                    "Yalnızca linear_approach / linear_full modunda.\n"
                    "Açık: P1→P2 yaklaşım kolu, mandrel yüzey teğetine PARALEL gider — eğimli "
                    "yüzeyde kol boyunca clearance SABİT kalır ve P2 fazladan dışarı itilmez.\n"
                    "Kapalı (varsayılan): kol dik (Z eksenine paralel) — sadece P2 yüzeye göre "
                    "yerleşir, kol açılı yüzeye paralel olmayabilir.\n"
                    "Dik (silindirik) yüzeyde iki mod da aynıdır.")

            if not is_linear:
                self._add_prop_entry(idx, "p1_x", t("lbl_p1x"), op, is_float=True,
                                     tooltip="Spline giriş noktasının (P1) temas noktasından X eksenindeki uzaklığı (mm). "
                                             "Büyük değer = rulo daha dışarıdan yanaşır, yumuşak giriş eğrisi. "
                                             "Tipik: 30–60 mm.\n"
                                             "Yalnızca spline modunda kullanılır.")
            self._add_prop_entry(idx, "p1_z", t("lbl_p1z"), op, is_float=True,
                                 tooltip="Spline giriş noktasının (P1) temas noktasından Z eksenindeki uzaklığı (mm). "
                                         "Büyük değer = rulo temas öncesi daha uzaktan yaklaşır. "
                                         "Tipik: 30–70 mm.")
            self._add_prop_entry(idx, "p3_x", t("lbl_p3x"), op, is_float=True,
                                 tooltip="Çıkış noktasının (P3) temas noktasından X eksenindeki uzaklığı (mm). "
                                         "P1 X'ten bağımsız olarak ayarlanabilir. "
                                         "Default: boş = P1 X değeri kullanılır.")
            self._add_prop_entry(idx, "p3_z", t("lbl_p3z"), op, is_float=True,
                                 tooltip="Spline çıkış noktasının (P3) temas noktasından Z eksenindeki uzaklığı (mm). "
                                         "Negatif değer = rulo temas sonrası mandrel'in içine doğru ilerler (pas uzunluğu). "
                                         "Tipik: -10 ile -40 mm arası.")
            self._add_prop_entry(idx, "reach", t("lbl_reach"), op, is_float=True,
                                 tooltip="Çıkış kolu uzunluğu |P2→P3| (mm) — tek 'erişim' parametresi (#61). "
                                         "Boş/0 = eski davranış: uzunluk p3_x/p3_z'den gelir. "
                                         "Değer girilince yön KORUNUR (Pass Angle varsa ondan, yoksa p3_x/p3_z "
                                         "oranından) ve yalnızca uzunluk bu değere ölçeklenir. "
                                         "Böylece açıyı bozmadan pası uzatıp kısaltabilirsin.")

            # Reach follows blank (opt-in #61 B): lock reach to the flange edge so it
            # auto-recomputes whenever start_z/end_z change — the exit always kisses the
            # blank rim. Overrides the manual reach above. Needs Sheet Radius.
            f_rfb = ttk.Frame(self.f_prop_editor)
            f_rfb._pkey = "reach_follow_blank"
            f_rfb.pack(fill="x", padx=2, pady=1)
            ttk.Label(f_rfb, text=t("lbl_reach_follow"), width=15).pack(side="left")
            rfb_var = tk.BooleanVar(value=bool(op.get("reach_follow_blank", False)))
            def toggle_rfb(i=idx, v=rfb_var):
                self.app.params["operations"][i]["reach_follow_blank"] = v.get()
                if v.get():
                    self._refresh_auto_reach()   # fill reach now so the field reflects it
                self.on_op_select(None, _flush=False)  # rebuild editor to show new reach
                self._start_async_calc()
            ttk.Checkbutton(f_rfb, variable=rfb_var, command=toggle_rfb).pack(side="right")
            self.helper.bind_tooltip(f_rfb,
                "Reach'i sac flanşına KİLİTLE (opt-in, #61 B): start_z/end_z değiştikçe reach "
                "otomatik olarak kalan flanşa göre yeniden hesaplanır — çıkış hep sacın ucunu "
                "'öper'. Yukarıdaki manuel reach'i geçersiz kılar. Sac Yarıçapı gerekir. TAHMİN.")

            self._add_prop_entry(idx, "reach_blank_factor", t("lbl_reach_factor"), op, is_float=True,
                                 tooltip="Sactan hesaplanan reach'i ÇARPAN ile ölçekler. Reach⟲ ve "
                                         "'Reach sacı takip etsin' değerine uygulanır.\n"
                                         "1.00 = tam sac ucunu öp (varsayılan), 0.90 = %90 (ucundan "
                                         "önce dur), 1.10 = %110 (ucunu geç).\n"
                                         "Boş = 1.00.")

            self._add_section_header("pass_angle", t("lbl_pass_angle_hdr"))

            self._add_prop_entry(idx, "pass_angle", t("lbl_pass_angle"), op, is_float=True, rebuild=True,
                                 tooltip="P2 temas noktasındaki iç açı (derece). "
                                         "P2→P1 ve P2→P3 vektörleri arasındaki açı.\n"
                                         "180° = düz geçiş (P1-P2-P3 doğrusal). Küçük açı = P2'de sivri dönüş.\n"
                                         "P2→P3 kol uzunluğu (L3) korunur, sadece P3 yönü değişir.\n"
                                         "Boş bırakılırsa P3 X/Z değerleri doğrudan kullanılır (devre dışı).\n"
                                         "linear_approach'ta tipik aralık: 90°–180°.")

            if op.get("pass_angle", None) is not None and count > 1:
                f_prog = ttk.Frame(self.f_prop_editor)
                f_prog._pkey = "progressive_angle_enabled"
                f_prog.pack(fill="x", padx=2, pady=1)
                ttk.Label(f_prog, text=t("lbl_progressive"), width=15).pack(side="left")
                prog_var = tk.BooleanVar(value=bool(op.get("progressive_angle_enabled", False)))
                def toggle_progressive(i=idx):
                    self.app.params["operations"][i]["progressive_angle_enabled"] = prog_var.get()
                    # Re-render the editor so the fan end-angle field appears/hides
                    self.on_op_select(None)
                    if self.app.params.get("calc_active", False):
                        self.app.update_scene("paths")
                ttk.Checkbutton(f_prog, variable=prog_var, command=toggle_progressive).pack(side="right")
                self.helper.bind_tooltip(f_prog,
                    "Açıyı paslar boyunca Pass Angle'dan yelpaze bitiş açısına doğru lineer artır.\n"
                    "İlk pas: Pass Angle değerini kullanır.\n"
                    "Son pas: Yelpaze Bitiş Açısı (varsayılan 180° = düz geçiş).\n"
                    "Ara paslar: lineer interpolasyon.\n"
                    "Pass Angle boşsa bu ayar etkisizdir.")
                if op.get("progressive_angle_enabled", False):
                    self._add_prop_entry(idx, "progressive_angle_end", t("lbl_progressive_end"), op,
                                         is_float=True,
                                         tooltip="Yelpazenin SON pasta ulaşacağı açı (derece). "
                                                 "Boş = 180° (malzeme yüzey boyunca yatırılır). "
                                                 "Daha küçük bir değer yelpazeyi erken durdurur — "
                                                 "her pası 180°'ye kadar bükmek istemediğinde kullan. "
                                                 "Pass Angle'dan küçük değer yelpazeyi ters yöne açar.")

                # Progressive Reach: shorten (or lengthen) the P2→P3 stroke per pass.
                # Independent of the angle fan above — angle sets direction, this sets
                # length (L3). Both can run together.
                f_reach = ttk.Frame(self.f_prop_editor)
                f_reach._pkey = "progressive_reach_enabled"
                f_reach.pack(fill="x", padx=2, pady=1)
                ttk.Label(f_reach, text=t("lbl_progressive_reach"), width=15).pack(side="left")
                reach_var = tk.BooleanVar(value=bool(op.get("progressive_reach_enabled", False)))
                def toggle_reach(i=idx):
                    self.app.params["operations"][i]["progressive_reach_enabled"] = reach_var.get()
                    self.on_op_select(None)
                    if self.app.params.get("calc_active", False):
                        self.app.update_scene("paths")
                ttk.Checkbutton(f_reach, variable=reach_var, command=toggle_reach).pack(side="right")
                self.helper.bind_tooltip(f_reach,
                    "P2→P3 kol uzunluğunu (stroke) paslar boyunca lineer değiştir.\n"
                    "İlk pas: mevcut P3 uzunluğunu kullanır.\n"
                    "Son pas: Uzunluk Bitiş değerine ulaşır (kısaltmak için daha küçük gir).\n"
                    "Ara paslar: lineer interpolasyon.\n"
                    "Açı yelpazesinden bağımsızdır — yön açıyla, uzunluk bununla ayarlanır; "
                    "ikisi birlikte çalışır.\n"
                    "Pass Angle boşsa bu ayar etkisizdir.")
                if op.get("progressive_reach_enabled", False):
                    self._add_prop_entry(idx, "progressive_reach_end", t("lbl_reach_end"), op,
                                         is_float=True,
                                         tooltip="P2→P3 kolunun SON pasta ulaşacağı uzunluk (mm). "
                                                 "İlk pas mevcut P3 uzunluğunu (√(P3x²+P3z²)) kullanır, "
                                                 "son pas bu değere iner/çıkar. "
                                                 "Mandrel yukarı çıktıkça kalan flanş küçülür — "
                                                 "her pasta çıkış strokunu kısaltmak için kullan.")
            self._add_prop_entry(idx, "clearance", t("lbl_clearance"), op, is_float=True,
                                 default_hint="= target clr",
                                 tooltip="Rulo temas noktasının blank yüzeyinden boşluğu (mm). "
                                         "Tüm pas tiplerinde aynı anlam: 0 = yüzeye temas (r_tool + part kalınlığı), "
                                         "pozitif = yüzeyden o kadar uzak. min_safety_gap güvenlik tabanıdır.")
            self._add_prop_entry(idx, "rot", t("lbl_rotation"), op, is_float=True,
                                 tooltip="Rulonun spline yolunun mandrel yüzeyine göre açısı (derece). "
                                         "Auto-Calc Angle açıksa bu değer otomatik hesaplanır. "
                                         "Manuel modda: 0° = Z eksenine paralel, pozitif değer = mandrel'e dönük.")

            self._add_section_header("contact_zone", t("lbl_contact_zone_hdr"))
            self._add_prop_entry(idx, "contact_zone_mm", t("lbl_zone_size"), op, is_float=True,
                                 tooltip="P2 etrafındaki yavaş besleme bölgesinin yarıçapı (mm). "
                                         "Bu mesafe içinde normal Feed yerine Feed Contact kullanılır. "
                                         "Default: 0 = devre dışı.")
            self._add_prop_entry(idx, "feed_contact", t("lbl_feed_contact"), op, is_float=True,
                                 tooltip="Temas bölgesinde kullanılacak yavaş besleme hızı (ilk pas için). "
                                         "Default: boş = normal pas Feed'i kullanılır.")
            if count > 1:
                self._add_prop_entry(idx, "feed_contact_end", t("lbl_feed_contact_end"), op, is_float=True,
                                     tooltip="Son pastaki temas bölgesi besleme hızı. Feed Contact'tan bu değere interpolasyon. "
                                             "Default: boş = Feed Contact sabit kalır.")

            self._add_section_header("back_pass", t("lbl_back_pass_hdr"))
            f_bp = ttk.Frame(self.f_prop_editor)
            f_bp._pkey = "back_pass_enabled"
            f_bp.pack(fill="x", padx=2, pady=1)
            ttk.Label(f_bp, text=t("lbl_enable"), width=15).pack(side="left")
            bp_var = tk.BooleanVar(value=bool(op.get("back_pass_enabled", False)))
            def toggle_bp(i=idx):
                self.app.params["operations"][i]["back_pass_enabled"] = bp_var.get()
                if self.app.params.get("calc_active", False):
                    self.app.update_scene("paths")
                # Swap Order / Back Feed / Back Arc X/Z only matter when back-pass
                # is enabled — rebuild so they show/hide immediately.
                self.on_op_select(None)
            ttk.Checkbutton(f_bp, variable=bp_var, command=toggle_bp).pack(side="right")
            self.helper.bind_tooltip(f_bp,
                "Her ileri pasın ardından aynı yolu ters yönde tekrar geçer. "
                "Malzeme dağılımını dengeler, springback azaltır, yüzey kalitesini artırır.")

            if op.get("back_pass_enabled", False):
                f_bps = ttk.Frame(self.f_prop_editor)
                f_bps._pkey = "back_pass_swapped"
                f_bps.pack(fill="x", padx=2, pady=1)
                ttk.Label(f_bps, text=t("lbl_swap_order"), width=15).pack(side="left")
                bps_var = tk.BooleanVar(value=bool(op.get("back_pass_swapped", False)))
                def toggle_bps(i=idx):
                    self.app.params["operations"][i]["back_pass_swapped"] = bps_var.get()
                    if self.app.params.get("calc_active", False):
                        self.app.update_scene("paths")
                ttk.Checkbutton(f_bps, variable=bps_var, command=toggle_bps).pack(side="right")
                self.helper.bind_tooltip(f_bps,
                    "İleri ve geri pas sırasını ters çevirir. "
                    "Aktifken: geri pas şekli (P2→P3 ark) ilk olarak çalışır, "
                    "ardından ileri pas ters yönde (P3→P1) geri döner. "
                    "Sadece Back Pass Enable ile birlikte etkilidir.")
                self._add_prop_entry(idx, "back_pass_feed", t("lbl_back_feed"), op, is_float=True,
                                     tooltip="Geri pas besleme hızı (mm/dak). "
                                             "Boş = operasyonun normal besleme hızı kullanılır. "
                                             "Genellikle ileri pastan yavaş (ütüleme etkisi için).")
                self._add_prop_entry(idx, "back_pass_arc_x", t("lbl_back_arc_x"), op, is_float=True,
                                     tooltip="Geri pas, ileri pasın forming eğrisinin (P2 fileto + P3 çıkışı dahil) "
                                             "tam tersidir — yani P2 Radius'u ve çıkış eğrisini birebir izler.\n"
                                             "Back Arc X, bu eğriye X ekseninde parabolik bir bombe ekler: uçlarda "
                                             "(P3 ve T1) sıfır, orta noktada maksimum. 0 = ileri pasın tam aynası.\n"
                                             "Mandrel'e çok yaklaşırsa otomatik olarak minimum clearance'a geri çekilir "
                                             "(çarpışma riski yok).\n"
                                             "Pozitif = mandrel'den uzaklaşır, negatif = mandrel'e doğru.")
                self._add_prop_entry(idx, "back_pass_arc_z", t("lbl_back_arc_z"), op, is_float=True,
                                     tooltip="Geri pas forming eğrisine Z ekseninde parabolik bombe ekler (uçlarda sıfır, "
                                             "ortada maksimum). 0 = ileri pasın tam aynası.\n"
                                             "Mandrel'e çok yaklaşırsa otomatik olarak minimum clearance'a geri çekilir "
                                             "(çarpışma riski yok).")
        else:
            self._add_prop_entry(idx, "clearance", t("lbl_clearance"), op, is_float=True,
                                 default_hint="= allow.+safety",
                                 tooltip="Finishing pasının mandrel yüzeyinden ekstra uzaklığı (mm). "
                                         "0 = tam yüzey teması (r_tool + part_thickness). "
                                         "Pozitif değer = paso yüzeyden bu kadar daha uzakta kalır.")

            # Pass shape mode
            f_shape = ttk.Frame(self.f_prop_editor)
            f_shape._pkey = "pass_shape"
            f_shape.pack(fill="x", padx=2, pady=1)
            ttk.Label(f_shape, text=t("lbl_shape_mode"), width=15).pack(side="left")
            _shape_opts = ["spline", "linear_approach", "linear_full"]
            _shape_var = tk.StringVar(value=op.get("pass_shape", "spline"))
            cb_shape = ttk.Combobox(f_shape, values=_shape_opts, textvariable=_shape_var,
                                    state="readonly", width=16)
            cb_shape.pack(side="right", fill="x", expand=True)
            def _on_shape(event=None, _i=idx, _v=_shape_var):
                self.app.params["operations"][_i]["pass_shape"] = _v.get()
                if self.app.params.get("calc_active", False):
                    self.app.update_scene("paths")
            cb_shape.bind("<<ComboboxSelected>>", _on_shape)
            self.helper.bind_tooltip(cb_shape,
                "spline: P1→P2→P3 tam spline eğrisi (varsayılan).\n"
                "linear_approach: Z ekseninde yatay yaklaşım (P1X yoksayılır), P2→P3 spline eğrisi.\n"
                "linear_full: Z ekseninde yatay yaklaşım + P2→P3 düz çizgi — tamamen lineer, eğri yok.")

            # Straight Line Mode
            f_sl = ttk.Frame(self.f_prop_editor)
            f_sl._pkey = "straight_line_mode"
            f_sl.pack(fill="x", padx=2, pady=1)
            ttk.Label(f_sl, text=t("lbl_straight_line"), width=15).pack(side="left")
            sl_var = tk.BooleanVar(value=bool(op.get("straight_line_mode", False)))

            def toggle_straight_line(i=idx):
                self.app.params["operations"][i]["straight_line_mode"] = sl_var.get()
                if self.app.params.get("calc_active", False):
                    self.app.update_scene("paths")

            ttk.Checkbutton(f_sl, variable=sl_var, command=toggle_straight_line).pack(side="right")
            self.helper.bind_tooltip(f_sl, "Bitirme pasını mandrel konturunu takip eden çok noktalı yol yerine "
                                           "iki nokta arası tek düz G1 hamlesi olarak oluştur. "
                                           "Basit konik veya düz yüzeyler için idealdir.")

        # Basic/Advanced gating: hide advanced-tagged fields (and now-empty
        # section headers) unless the global Advanced toggle is on. Runs for
        # both the roughing and finishing branches.
        self._apply_field_visibility(op_type)

    def _add_prop_combo(self, op_idx, key, label, values, op_dict, tooltip=""):
        f = ttk.Frame(self.f_prop_editor)
        f._pkey = key
        f.pack(fill="x", padx=2, pady=1)
        ttk.Label(f, text=label, width=15).pack(side="left")

        curr = op_dict.get(key, values[0])
        cb = ttk.Combobox(f, values=values, state="readonly")
        cb.set(curr)
        cb.pack(side="right", fill="x", expand=True)

        def save(e):
            self._flush_entries()
            self.app.params["operations"][op_idx][key] = cb.get()
            self.on_op_select(None)
            self.update_time_estimate()

        cb.bind("<<ComboboxSelected>>", save)
        self.helper.bind_tooltip(cb, tooltip)
        self.helper.bind_tooltip(f, tooltip)

    def _add_prop_entry(self, op_idx, key, label, op_dict, is_int=False, is_float=False, tooltip="", rebuild=False,
                        default_hint=None):
        f = ttk.Frame(self.f_prop_editor)
        f._pkey = key
        f.pack(fill="x", padx=2, pady=1)
        ttk.Label(f, text=label, width=15).pack(side="left")

        # Faded default hint at the far right (packed before the entry so the
        # entry still expands to fill the space between label and hint).
        # default_hint overrides the table for fields whose default depends on
        # op type (e.g. clearance).
        _dflt = default_hint if default_hint is not None else OP_PARAM_DEFAULTS.get(key)
        if _dflt is not None:
            _dtxt = _dflt if isinstance(_dflt, str) else _fmt_num(_dflt)
            tk.Label(f, text=f"{t('hint_default')} {_dtxt}",
                     fg=self.helper.HINT_COLOR, font=self.helper.HINT_FONT,
                     anchor="e").pack(side="right", padx=(4, 2))

        val = op_dict.get(key, "")
        var = tk.StringVar(value=str(val))

        def save(e=None):
            try:
                v = var.get().strip()
                if v == "":
                    self.app.params["operations"][op_idx].pop(key, None)
                else:
                    if is_int: v = int(v)
                    elif is_float: v = float(v)
                    self.app.params["operations"][op_idx][key] = v
                self.refresh_ops_tree()
                if self.app.params.get("auto_calculate_paths", False):
                    self._schedule_auto_calc()
                if rebuild:
                    # Re-render the property panel so visibility of fields that
                    # depend on this value (e.g. Pass Count -> Feed Contact End,
                    # Pass Angle -> Progressive) updates immediately. _flush=False
                    # avoids re-entering this same save() via _flush_entries.
                    self.on_op_select(None, _flush=False)
            except: pass

        self._active_entry_savers.append(save)
        entry = ttk.Entry(f, textvariable=var)
        entry.pack(side="right", fill="x", expand=True)
        entry.bind("<FocusOut>", save)
        entry.bind("<Return>", save)
        entry.bind("<Button-1>", lambda e: e.widget.focus_force())
        self.helper.bind_tooltip(entry, tooltip)
        self.helper.bind_tooltip(f, tooltip)

    # ── Pass Diagram Popup ────────────────────────────────────────────────
    def _show_pass_diagram(self, op):
        """Open a canvas-based visual guide: which parameter affects which part of the pass."""
        dlg = tk.Toplevel(self.frame.winfo_toplevel())
        dlg.title(t("dlg_pass_diagram"))
        dlg.geometry("980x560")
        dlg.resizable(True, True)

        frm_top = ttk.Frame(dlg)
        frm_top.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(frm_top, text=t("lbl_shape"), font=("Arial", 9, "bold")).pack(side="left", padx=(0, 6))
        shape_var = tk.StringVar(value=op.get("pass_shape", "spline"))
        for s in ("spline", "linear_approach", "linear_full"):
            ttk.Radiobutton(frm_top, text=s, variable=shape_var, value=s).pack(side="left", padx=6)

        # Two-column layout: diagram canvas (left, resizable) + formula panel (right, fixed)
        frm_main = ttk.Frame(dlg)
        frm_main.pack(fill="both", expand=True, padx=10, pady=4)

        canvas = tk.Canvas(frm_main, bg="#1a1a2e", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        frm_form = tk.Frame(frm_main, bg="#0d1520", width=232)
        frm_form.pack(side="right", fill="y")
        frm_form.pack_propagate(False)

        tk.Label(frm_form, text=t("lbl_param_formulas"),
                 bg="#0d1520", fg="#7799cc",
                 font=("Consolas", 9, "bold")).pack(pady=(6, 2))
        tk.Frame(frm_form, bg="#223355", height=1).pack(fill="x", padx=4, pady=(0, 3))

        form_text = tk.Text(frm_form, bg="#0d1520", fg="#cce0ff",
                            font=("Consolas", 8), width=29, wrap=tk.WORD,
                            state="disabled", relief="flat",
                            cursor="arrow", padx=8, pady=2,
                            highlightthickness=0, insertwidth=0)
        form_text.pack(fill="both", expand=True)
        form_text.tag_config("hdr",  foreground="#6699cc", font=("Consolas", 8, "bold"))
        form_text.tag_config("fml",  foreground="#88ccaa")
        form_text.tag_config("val",  foreground="#ffbb55")
        form_text.tag_config("note", foreground="#778899")

        ttk.Button(dlg, text=t("btn_close"), command=dlg.destroy).pack(pady=(0, 8))

        def _update_formulas(shape):
            form_text.config(state="normal")
            form_text.delete("1.0", tk.END)

            def h(s): form_text.insert(tk.END, s + "\n", "hdr")
            def f(s): form_text.insert(tk.END, s + "\n", "fml")
            def v(s): form_text.insert(tk.END, s + "\n", "val")
            def n(s): form_text.insert(tk.END, s + "\n", "note")
            def sp():  form_text.insert(tk.END, "\n")

            p1x_  = float(op.get("p1_x",  40.0))
            p1z_  = float(op.get("p1_z",  50.0))
            p3z_  = abs(float(op.get("p3_z", -20.0)))
            p3x_r = op.get("p3_x", None)
            p3x_  = float(p3x_r) if p3x_r is not None else p1x_
            step_ = max(float(op.get("step",  5.0)), 1.0)
            rot_  = float(op.get("rot",   0.0))
            p2r_  = float(op.get("p2_radius", 0.0))
            cf_   = bool(op.get("conformal_clearance_operation_specific", False))
            pa_r  = op.get("pass_angle", None)
            pa_   = float(pa_r) if pa_r is not None else None
            ten_  = float(op.get("exit_curve_tension", 0.4))

            h("── P1  (entry point) ───")
            f("P1.Z = P2.Z − p1_z")
            v(f"     = P2.Z − {p1z_:.0f} mm")
            if shape == "spline":
                f("P1.X = P2.X + p1_x")
                v(f"     = P2.X + {p1x_:.0f} mm")
                n("  radial lift before contact")
            else:
                f("P1.X = P2.X")
                n("  horizontal approach (no X lift)")
            sp()
            h("── P3  (exit point) ────")
            f("P3.Z = P2.Z + |p3_z|")
            n("  p3_z stored as negative,")
            n("  abs() applied at runtime")
            v(f"     = P2.Z + {p3z_:.0f} mm")
            f("P3.X = P2.X + p3_x")
            v(f"     = P2.X + {p3x_:.0f} mm")
            sp()
            if pa_ is not None:
                h("── pass_angle ───────────")
                f("angle at P2 between")
                f("  P1→P2 (incoming) and")
                f("  P2→P3 (outgoing)")
                v(f"= {pa_:.0f}°")
                n("  larger → steeper exit")
                sp()
            if shape == "spline" and abs(rot_) > 0.1:
                h("── rot  (rotation) ─────")
                f("tilts the P1-P2-P3 spline")
                f("around P2 in the X-Z plane")
                v(f"= {rot_:.0f}°")
                n("  +° rotates toward tip")
                sp()
            if shape == "linear_approach":
                h("── exit_curve_tension ──")
                f("bezier ctrl point Z pos:")
                f("  ctrl.Z = P2.Z")
                f("    + (P3.Z−P2.Z) × t")
                v(f"  = P2.Z + {p3z_*ten_:.1f} mm")
                v(f"  t = {ten_:.2f}")
                n("  0 → ctrl stays at P2.Z")
                n("  1 → ctrl at P3.Z level")
                sp()
            h("── step ─────────────────")
            f("radial spacing per pass")
            f("next P2.X = P2.X − step")
            v(f"= {step_:.1f} mm")
            sp()
            if p2r_ > 0.5:
                h("── p2_radius ────────────")
                f("corner fillet at P2")
                v(f"= {p2r_:.1f} mm")
                sp()
            if cf_:
                h("── conformal_clearance_operation_specific ──")
                f("shifts P2 along mandrel")
                f("surface normal for uniform")
                f("roller-to-blank gap")
                n("  uses profile normals")

            form_text.config(state="disabled")

        zoom = [1.0]
        pan  = [0.0, 0.0]
        drag = [None, None]

        def _redraw(event=None):
            canvas.delete("all")
            w = canvas.winfo_width()  or 700
            h = canvas.winfo_height() or 460
            self._draw_pass_diagram(canvas, w, h, shape_var.get(), op,
                                    zoom[0], (pan[0], pan[1]))

        def _on_scroll(event):
            factor = 1.15
            delta = getattr(event, "delta", 0)
            if delta > 0 or getattr(event, "num", 0) == 4:
                zoom[0] = min(zoom[0] * factor, 8.0)
            else:
                zoom[0] = max(zoom[0] / factor, 0.25)
            _redraw()

        def _on_drag_start(event):
            drag[0] = event.x;  drag[1] = event.y

        def _on_drag(event):
            if drag[0] is not None:
                pan[0] += event.x - drag[0]
                pan[1] += event.y - drag[1]
                drag[0] = event.x;  drag[1] = event.y
                _redraw()

        def _on_drag_end(event):
            drag[0] = None

        canvas.bind("<MouseWheel>",      _on_scroll)
        canvas.bind("<Button-4>",        _on_scroll)
        canvas.bind("<Button-5>",        _on_scroll)
        canvas.bind("<ButtonPress-1>",   _on_drag_start)
        canvas.bind("<B1-Motion>",       _on_drag)
        canvas.bind("<ButtonRelease-1>", _on_drag_end)
        canvas.bind("<Double-Button-1>",
                    lambda e: (zoom.__setitem__(0, 1.0),
                               pan.__setitem__(0, 0.0),
                               pan.__setitem__(1, 0.0),
                               _redraw()))

        def _on_shape_change(*_):
            _redraw()
            _update_formulas(shape_var.get())

        shape_var.trace_add("write", _on_shape_change)
        canvas.bind("<Configure>", _redraw)
        dlg.after(80, lambda: (_redraw(), _update_formulas(shape_var.get())))

    def _draw_pass_diagram(self, canvas, W, H, shape, op, zoom=1.0, pan=(0.0, 0.0)):
        """Static representative pass diagram — positions are fixed for visual clarity;
        actual param values appear only in annotation labels.
        zoom: scroll-wheel factor; pan: (dx,dy) drag offset in canvas pixels."""
        import math as _m
        import numpy as _np

        # ── Palette ──────────────────────────────────────────────────────
        C_MAND   = "#3a7abf";  C_MFILL = "#1e3a5a"
        C_PATH   = "#ff9944"
        C_GHOST  = "#7755bb"
        C_PT_C   = "#ff5555"   # P2 contact
        C_PT_A   = "#55dd88"   # P1/P3
        C_DZ     = "#6699ff"   # Z-dimension
        C_DX     = "#ffaa44"   # X-dimension
        C_ANG    = "#ffee44"   # angle arc
        C_STEP   = "#bb88ff"   # step ghost
        C_RADIUS = "#44eecc"   # P2 fillet
        C_CONF   = "#44aaff"   # conformal normal
        C_LBL    = "#ddeeff"
        C_OFF    = "#4a5060"   # inactive
        C_AX     = "#2a3a4a"

        # ── Read actual values (labels only — positions are fixed) ───────
        p1x  = float(op.get("p1_x",  40.0))
        p1z  = float(op.get("p1_z",  50.0))
        p3z  = abs(float(op.get("p3_z", -20.0)))
        p3x_raw = op.get("p3_x", None)
        p3x  = float(p3x_raw) if p3x_raw is not None else p1x
        step = max(float(op.get("step",  5.0)), 1.0)
        rot  = float(op.get("rot",   0.0))
        p2r  = float(op.get("p2_radius", 0.0))
        conformal   = bool(op.get("conformal_clearance_operation_specific", False))
        pa_raw      = op.get("pass_angle", None)
        pa          = float(pa_raw) if pa_raw is not None else None
        exit_tension = float(op.get("exit_curve_tension", 0.4))
        pos_x = self.app.params.get("roller_positive_x_side", True)
        xs = 1.0 if pos_x else -1.0   # +1 = mandrel below, -1 = mandrel above

        is_linear = shape in ("linear_approach", "linear_full")
        is_full   = (shape == "linear_full")

        # ── Fixed representative canvas positions ──────────────────────────
        # These are chosen to always look clear regardless of actual param values.
        # xs=+1: mandrel is below (large canvas Y); xs=-1: mandrel is above (small Y).
        cx_p2 = W * 0.42
        cy_p2 = H * (0.52 if xs > 0 else 0.48)

        P2  = (cx_p2, cy_p2)
        # Mandrel block: below (xs=1) or above (xs=-1)
        mand_near = cy_p2 + xs * H * 0.14
        mand_far  = cy_p2 + xs * H * 0.26

        # P1: entry
        if is_linear:
            P1 = (W * 0.10, cy_p2)                        # horizontal approach
        else:
            P1 = (W * 0.10, cy_p2 - xs * H * 0.30)       # above/below (spline arch)

        # P3: exit (always angled away from mandrel)
        P3 = (W * 0.80, cy_p2 - xs * H * 0.25)

        # Ghost pass (one step farther from mandrel)
        STEP_PX = 32                                       # fixed visual step height
        P2g = (cx_p2, cy_p2 - xs * STEP_PX)
        if is_linear:
            P1g = (W * 0.10, cy_p2 - xs * STEP_PX)
        else:
            P1g = (W * 0.10, cy_p2 - xs * (H * 0.30 + STEP_PX))
        P3g = (W * 0.80, cy_p2 - xs * (H * 0.25 + STEP_PX))

        # ── Draw helpers ──────────────────────────────────────────────────
        def circle(cx_, cy_, r, fill, outline=""):
            canvas.create_oval(cx_-r, cy_-r, cx_+r, cy_+r,
                               fill=fill, outline=outline or fill, width=2)

        def text(cx_, cy_, s, color, anchor="center", bold=False, sz=9):
            fnt = ("Consolas", sz, "bold") if bold else ("Consolas", sz)
            canvas.create_text(cx_, cy_, text=s, fill=color, font=fnt, anchor=anchor)

        def qbez(a, ctrl, b, n=36):
            """Quadratic bezier a→b via ctrl → flat point list."""
            a, ctrl, b = (_np.array(a, dtype=float), _np.array(ctrl, dtype=float),
                          _np.array(b, dtype=float))
            pts = []
            for i in range(n + 1):
                t = i / n
                p = (1-t)**2*a + 2*(1-t)*t*ctrl + t**2*b
                pts += [float(p[0]), float(p[1])]
            return pts

        def arch(a, mid, b, n=40):
            """Quadratic bezier that passes through 'mid' at t=0.5, guaranteed visible."""
            a, mid, b = (_np.array(a, dtype=float), _np.array(mid, dtype=float),
                         _np.array(b, dtype=float))
            midAB = (a + b) * 0.5
            ctrl  = 2.0*mid - midAB          # passes through mid at t=0.5
            # Guarantee ≥40px perpendicular bow
            chord = b - a
            cl = float(_np.linalg.norm(chord)) + 1e-9
            cu = chord / cl
            perp = _np.array([-cu[1], cu[0]])
            if float(_np.dot(perp, mid - midAB)) < 0:
                perp = -perp
            if float(_np.dot(ctrl - midAB, perp)) < 80.0:
                ctrl = midAB + perp * 80.0
            return qbez(a, ctrl, b, n)

        # ── Zoom helpers (all positions are "base space"; zp() → canvas space) ──
        zcx, zcy = W / 2, H / 2

        def zp(x, y):
            return (zcx + (x - zcx) * zoom + pan[0],
                    zcy + (y - zcy) * zoom + pan[1])

        def zpts(lst):
            out = []
            for i in range(0, len(lst), 2):
                out += list(zp(lst[i], lst[i+1]))
            return out

        def zsz(base): return max(7, int(base * zoom))
        def zlw(base): return max(1, int(base * zoom))

        # ── Draw helpers (take BASE coords, apply zp internally) ──────────
        def circle(cx_, cy_, r, fill, outline=""):
            zx, zy = zp(cx_, cy_)
            zr = max(2, r * zoom)
            canvas.create_oval(zx-zr, zy-zr, zx+zr, zy+zr,
                               fill=fill, outline=outline or fill, width=zlw(2))

        def text(cx_, cy_, s, color, anchor="center", bold=False, sz=9):
            zx, zy = zp(cx_, cy_)
            fnt = ("Consolas", zsz(sz), "bold") if bold else ("Consolas", zsz(sz))
            canvas.create_text(zx, zy, text=s, fill=color, font=fnt, anchor=anchor)

        def bracket_h(x1, x2, y, color, label):
            zx1, zy  = zp(x1, y);  zx2, _ = zp(x2, y)
            zt = max(3, int(5 * zoom))
            for zxv in (zx1, zx2):
                canvas.create_line(zxv, zy-zt, zxv, zy+zt, fill=color, width=1)
            canvas.create_line(zx1, zy, zx2, zy, fill=color, width=1, dash=(3,3))
            ly = zy - zsz(12) if xs > 0 else zy + zsz(12)
            canvas.create_text((zx1+zx2)/2, ly, text=label,
                               fill=color, font=("Consolas", zsz(8)), anchor="center")

        def bracket_v(x, y1, y2, color, label, right=True):
            zx, zy1 = zp(x, y1);  _, zy2 = zp(x, y2)
            zt = max(3, int(5 * zoom))
            for zyv in (zy1, zy2):
                canvas.create_line(zx-zt, zyv, zx+zt, zyv, fill=color, width=1)
            canvas.create_line(zx, zy1, zx, zy2, fill=color, width=1, dash=(3,3))
            anch = "w" if right else "e"
            off  = max(6, int(6 * zoom))
            canvas.create_text(zx + (off if right else -off), (zy1+zy2)/2,
                               text=label, fill=color,
                               font=("Consolas", zsz(8)), anchor=anch)

        def dashline(a, b, color):
            canvas.create_line(*zp(*a), *zp(*b), fill=color, dash=(2,5), width=1)

        def leader_text(anchor_base, label_base, s, color, sz=8, anchor="w"):
            """Label with a dashed leader line; both coords in base space."""
            zax, zay = zp(*anchor_base)
            zlx, zly = zp(*label_base)
            dr = max(2.5, 3.0 * zoom)
            canvas.create_oval(zax-dr, zay-dr, zax+dr, zay+dr, fill=color, outline="")
            canvas.create_line(zax, zay, zlx, zly, fill=color, dash=(2, 4), width=1)
            canvas.create_text(zlx, zly, text=s, fill=color,
                               font=("Consolas", zsz(sz)), anchor=anchor)

        # ── Axes ──────────────────────────────────────────────────────────
        az_y = cy_p2 + xs * H * 0.04
        canvas.create_line(*zp(W*0.06, az_y), *zp(W*0.93, az_y),
                           fill=C_AX, width=1, arrow=tk.LAST)
        text(W*0.94, az_y, "Z", C_LBL, anchor="w", bold=True, sz=10)

        ax_x0 = W * 0.055
        ax_bot = cy_p2 + xs * H * 0.30
        ax_top = cy_p2 - xs * H * 0.38
        canvas.create_line(*zp(ax_x0, max(ax_bot, ax_top)),
                           *zp(ax_x0, min(ax_bot, ax_top)),
                           fill=C_AX, width=1, arrow=tk.LAST)
        text(ax_x0, min(ax_bot, ax_top) - 8,
             "X ↑ away" if xs > 0 else "X ↓ away", C_LBL, bold=True, sz=8)

        # ── Mandrel block ─────────────────────────────────────────────────
        my1, my2 = min(mand_near, mand_far), max(mand_near, mand_far)
        mr1x, mr1y = zp(W*0.04, my1);  mr2x, mr2y = zp(W*0.96, my2)
        canvas.create_rectangle(mr1x, mr1y, mr2x, mr2y,
                                fill=C_MFILL, outline=C_MAND, width=zlw(2))
        rw_b = int(W * 0.92);  rh_b = int(my2 - my1)
        HS = max(8, rw_b // 12)
        for k in range(-rh_b, rw_b, HS):
            xa = W*0.04 + max(0, k);       ya = my1 + max(0, -k)
            xb = W*0.04 + min(rw_b, k+rh_b); yb = ya + (xb - (W*0.04 + max(0, k)))
            yb = min(yb, my2)
            if xa < xb and ya < my2:
                canvas.create_line(*zp(xa, ya), *zp(xb, yb), fill=C_MAND, width=1)
        text(W*0.50, (my1+my2)/2, "MANDREL", C_MAND, bold=True, sz=9)
        canvas.create_line(*zp(P2[0], P2[1]),
                           *zp(P2[0], my1 if xs > 0 else my2),
                           fill=C_MAND, dash=(3,4), width=1)

        # ── Ghost pass ────────────────────────────────────────────────────
        if is_linear:
            canvas.create_line(*zp(*P1g), *zp(*P2g), fill=C_GHOST, width=1, dash=(4,3))
            if is_full:
                canvas.create_line(*zp(*P2g), *zp(*P3g), fill=C_GHOST, width=1, dash=(4,3))
            else:
                gctrl = (P2g[0] + (P3g[0]-P2g[0]) * exit_tension, P2g[1])
                canvas.create_line(*zpts(qbez(P2g, gctrl, P3g, n=24)),
                                   fill=C_GHOST, width=1, dash=(4,3))
        else:
            canvas.create_line(*zpts(arch(P1g, P2g, P3g, n=28)),
                               fill=C_GHOST, width=1, dash=(4,3))
        dashline(P2, P2g, C_STEP)
        _step_mid = ((P2[0]+P2g[0])/2, (P2[1]+P2g[1])/2)
        leader_text(_step_mid, (P2[0]-68, _step_mid[1]),
                    f"step = {step:.1f}mm", C_STEP, sz=8, anchor="e")
        circle(*P2g, 4, C_GHOST)

        # ── Main toolpath ─────────────────────────────────────────────────
        pw = zlw(3)
        if shape == "spline":
            canvas.create_line(*zpts(arch(P1, P2, P3)), fill=C_PATH, width=pw)

        elif shape == "linear_approach":
            canvas.create_line(*zp(*P1), *zp(*P2), fill=C_PATH, width=pw)
            ctrl_e = (P2[0] + (P3[0]-P2[0]) * exit_tension, P2[1])
            canvas.create_line(*zpts(qbez(P2, ctrl_e, P3)), fill=C_PATH, width=pw)
            if p2r > 0.5:
                zx2, zy2 = zp(*P2);  zrr = max(5, int(18*zoom))
                canvas.create_arc(zx2-zrr, zy2-zrr, zx2+zrr, zy2+zrr,
                                  start=0, extent=90*xs,
                                  outline=C_RADIUS, style=tk.ARC, width=zlw(2))
                leader_text((P2[0]+18, P2[1]-xs*9),
                            (P2[0]+58, P2[1]-xs*30),
                            f"p2_radius\n{p2r:.1f}mm", C_RADIUS, sz=8)

        else:  # linear_full
            canvas.create_line(*zp(*P1), *zp(*P2), fill=C_PATH, width=pw)
            canvas.create_line(*zp(*P2), *zp(*P3), fill=C_PATH, width=pw)
            if p2r > 0.5:
                zx2, zy2 = zp(*P2);  zrr = max(5, int(18*zoom))
                canvas.create_arc(zx2-zrr, zy2-zrr, zx2+zrr, zy2+zrr,
                                  start=0, extent=90*xs,
                                  outline=C_RADIUS, style=tk.ARC, width=zlw(2))
                leader_text((P2[0]+18, P2[1]-xs*9),
                            (P2[0]+58, P2[1]-xs*30),
                            f"p2_radius\n{p2r:.1f}mm", C_RADIUS, sz=8)

        # ── Dimension annotations — format: "param_name = value  (what it sets)" ──
        ann_y_z1 = P1[1] - xs * 22
        dashline(P1, (P1[0], ann_y_z1), C_DZ)
        dashline(P2, (P2[0], ann_y_z1), C_DZ)
        bracket_h(P1[0], P2[0], ann_y_z1, C_DZ, f"p1_z  {p1z:.0f}mm")

        ann_y_z3 = P3[1] - xs * 22
        dashline(P3, (P3[0], ann_y_z3), C_DZ)
        dashline(P2, (P2[0], ann_y_z3), C_DZ)
        bracket_h(P2[0], P3[0], ann_y_z3, C_DZ, f"p3_z  {p3z:.0f}mm")

        if not is_linear:
            bracket_v(P1[0]-24, P1[1], P2[1], C_DX,
                      f"p1_x\n{p1x:.0f}mm", right=False)
        bracket_v(P3[0]+10, P3[1], P2[1], C_DX, f"p3_x\n{p3x:.0f}mm")

        # Pass Angle arc
        if pa is not None and not is_full:
            ar = 24
            v1 = (P1[0]-P2[0], P1[1]-P2[1]);  v2 = (P3[0]-P2[0], P3[1]-P2[1])
            a1 = _m.degrees(_m.atan2(-v1[1], v1[0]))
            a2 = _m.degrees(_m.atan2(-v2[1], v2[0]))
            lo, ext = min(a1, a2), abs(a2-a1)
            if ext > 180: lo, ext = max(a1, a2), 360-ext
            zx2, zy2 = zp(*P2);  zar = max(12, int(ar*zoom))
            canvas.create_arc(zx2-zar, zy2-zar, zx2+zar, zy2+zar,
                              start=lo, extent=ext, outline=C_ANG, style=tk.ARC, width=zlw(2))
            am = _m.radians(lo + ext/2)
            _ang_off = ar + 40
            _ang_ax = P2[0] + _ang_off * _m.cos(am)
            _ang_ay = P2[1] - _ang_off * _m.sin(am)
            leader_text((P2[0] + ar*_m.cos(am), P2[1] - ar*_m.sin(am)),
                        (_ang_ax, _ang_ay),
                        f"pass_angle\n{pa:.0f}°", C_ANG, sz=8,
                        anchor="w" if _m.cos(am) >= 0 else "e")

        # Exit tension label (uses leader line to avoid crowding P2)
        if shape == "linear_approach":
            ctrl_e_pt = (P2[0] + (P3[0]-P2[0]) * exit_tension, P2[1])
            _et_lbl = (ctrl_e_pt[0] + 8, ctrl_e_pt[1] + xs * 34)
            leader_text(ctrl_e_pt, _et_lbl,
                        f"exit_tension\n{exit_tension:.2f}", C_ANG, sz=8)

        # Rotation arc (spline only) — leader line keeps label away from pass_angle text
        if not is_linear and abs(rot) > 0.5:
            rr = 16
            vis_ext = max(20, min(int(abs(rot)*2), 110)) * (1 if rot > 0 else -1)
            zx2, zy2 = zp(*P2);  zrr = max(8, int(rr*zoom))
            canvas.create_arc(zx2-zrr, zy2-zrr, zx2+zrr, zy2+zrr,
                              start=90, extent=vis_ext,
                              outline="#dd66ff", style=tk.ARC, width=zlw(2), dash=(3,2))
            _rot_anchor = (P2[0] + rr*_m.cos(_m.radians(90 + vis_ext/2)),
                           P2[1] - rr*_m.sin(_m.radians(90 + vis_ext/2)))
            leader_text(_rot_anchor, (P2[0] + 52, P2[1] - xs*36),
                        f"rot  {rot:.0f}°", "#dd66ff", sz=8)

        # Conformal normal arrow
        if conformal:
            cn_end = (P2[0]+6, P2[1] - xs * 44)
            ash = (max(4,int(8*zoom)), max(5,int(10*zoom)), max(2,int(4*zoom)))
            canvas.create_line(*zp(*P2), *zp(*cn_end), fill=C_CONF, width=zlw(2),
                               arrow=tk.LAST, arrowshape=ash)
            leader_text(cn_end, (cn_end[0]+12, cn_end[1]-8),
                        "conformal\nclearance ON", C_CONF, sz=8, anchor="w")

        # ── Point markers ──────────────────────────────────────────────────
        lbl_off = -18 if xs > 0 else +28
        circle(*P1, 6, C_PT_A, "#001100")
        text(P1[0], P1[1]+lbl_off, "P1\n(Entry)",   C_PT_A, bold=True, sz=9)
        circle(*P2, 7, C_PT_C, "#110000")
        text(P2[0], P2[1]-lbl_off, "P2\n(Contact)", C_PT_C, bold=True, sz=9)
        circle(*P3, 6, C_PT_A, "#001100")
        text(P3[0], P3[1]+lbl_off, "P3\n(Exit)",    C_PT_A, bold=True, sz=9)

        # ── Legend (fixed at bottom — text capped at 8pt, no inactive items) ──
        leg_y = H - 18
        if shape == "spline":
            items = [
                (C_PT_A,    "P1/P3 — approach & exit"),
                (C_PT_C,    "P2 — contact point"),
                (C_DZ,      "Z offsets"),
                (C_DX,      "X offsets"),
                (C_ANG,     "Pass Angle"),
                ("#dd66ff", "Rotation"),
                (C_STEP,    "Step per pass"),
            ]
        elif shape == "linear_approach":
            items = [
                (C_PT_A,   "P1 approach / P3 exit"),
                (C_PT_C,   "P2 contact"),
                (C_DZ,     "Approach Z / P3 Z"),
                (C_DX,     "P3 X — exit height"),
                (C_RADIUS, "P2 Radius — fillet"),
                (C_ANG,    "Pass Angle / Exit Tension"),
                (C_STEP,   "Step"),
            ]
        else:
            items = [
                (C_PT_A,   "P1 approach / P3 exit"),
                (C_PT_C,   "P2 contact"),
                (C_DZ,     "Approach Z / P3 Z"),
                (C_DX,     "P3 X — exit height"),
                (C_RADIUS, "P2 Radius — fillet"),
                (C_STEP,   "Step"),
            ]
        lsz = 8   # legend text never scales — keeps rows from overlapping
        col_w = max(1, (W - 20) / len(items))
        for k, (color, lbl) in enumerate(items):
            lx = 10 + k * col_w
            canvas.create_rectangle(lx, leg_y-2, lx+10, leg_y+8, fill=color, outline="")
            canvas.create_text(lx+14, leg_y+3, text=lbl,
                               fill=color, font=("Consolas", lsz), anchor="w")

    # ── Reference Points ──────────────────────────────────────────────────

    _REF_COLORS = ["yellow", "deeppink", "cyan", "lime", "orange", "magenta", "white"]

    def _build_ref_points_panel(self):
        frm = ttk.LabelFrame(self.frame, text=t("frm_ref_points"))
        frm.pack(fill="x", padx=5, pady=(0, 3))

        f_tv = ttk.Frame(frm)
        f_tv.pack(fill="x", padx=2, pady=(2, 0))

        cols = ("Z", "X", "Label")
        self.tree_refs = ttk.Treeview(f_tv, columns=cols, show="headings", height=3)
        self.tree_refs.heading("Z",     text="Z (mm)"); self.tree_refs.column("Z",     width=75,  anchor="center")
        self.tree_refs.heading("X",     text="X (mm)"); self.tree_refs.column("X",     width=75,  anchor="center")
        self.tree_refs.heading("Label", text="Label");  self.tree_refs.column("Label", width=130)
        sb_r = ttk.Scrollbar(f_tv, orient="vertical", command=self.tree_refs.yview)
        self.tree_refs.configure(yscrollcommand=sb_r.set)
        sb_r.pack(side="right", fill="y")
        self.tree_refs.pack(fill="x")
        self.tree_refs.bind("<Double-1>", lambda e: self._edit_ref_point())

        f_btns = ttk.Frame(frm)
        f_btns.pack(fill="x", padx=2, pady=(2, 3))
        ttk.Button(f_btns, text=t("btn_ref_add"),    width=7, command=self._add_ref_point).pack(side="left", padx=(0, 2))
        ttk.Button(f_btns, text=t("btn_ref_remove"), width=9, command=self._remove_ref_point).pack(side="left", padx=2)
        ttk.Button(f_btns, text=t("btn_edit"),       width=5, command=self._edit_ref_point).pack(side="left", padx=2)

        self.refresh_ref_points_tree()

    def refresh_ref_points_tree(self):
        try: tv = self.tree_refs
        except AttributeError: return
        tv.delete(*tv.get_children())
        for i, pt in enumerate(self.app.params.get("reference_points", [])):
            z   = float(pt.get("z", 0.0))
            x   = float(pt.get("x", 0.0))
            lbl = str(pt.get("label", ""))
            tv.insert("", "end", iid=str(i), values=(f"{z:.1f}", f"{x:.1f}", lbl))

    def _ref_point_dialog(self, title, z=0.0, x=0.0, label=""):
        """Show a small dialog; returns (z, x, label) or None.
        z/x are offsets from the current roller tip — (0,0) = at tip."""
        dlg = tk.Toplevel(self.frame.winfo_toplevel())
        dlg.title(title)
        dlg.geometry("290x165")
        dlg.resizable(False, False)
        dlg.grab_set()
        result = [None]

        for row, (text, var_val) in enumerate([(t("lbl_z_offset_tip"), str(z)),
                                               (t("lbl_x_offset_tip"), str(x)),
                                               (t("lbl_label_colon"),  label)]):
            ttk.Label(dlg, text=text).grid(row=row, column=0, padx=10, pady=5, sticky="w")
            v = tk.StringVar(value=var_val)
            ttk.Entry(dlg, textvariable=v, width=14).grid(row=row, column=1, padx=8, pady=5)
            if row == 0: var_z = v
            elif row == 1: var_x = v
            else: var_lbl = v

        def _ok():
            try: result[0] = (float(var_z.get()), float(var_x.get()), var_lbl.get().strip())
            except ValueError: return
            dlg.destroy()

        f_b = ttk.Frame(dlg)
        f_b.grid(row=3, column=0, columnspan=2, pady=6)
        ttk.Button(f_b, text=t("btn_ok"),     command=_ok,           width=8).pack(side="left",  padx=4)
        ttk.Button(f_b, text=t("btn_cancel"), command=dlg.destroy,   width=8).pack(side="right", padx=4)
        dlg.bind("<Return>", lambda e: _ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.wait_window()
        return result[0]

    def _add_ref_point(self):
        tip_x = float(self.app.params.get("home_x", 0.0))
        tip_z = float(self.app.params.get("home_z", 0.0))
        res = self._ref_point_dialog(t("dlg_add_ref_point"), z=0.0, x=0.0)
        if res is None: return
        dz, dx, label = res
        z, x = tip_z + dz, tip_x + dx
        pts = self.app.params.setdefault("reference_points", [])
        color = self._REF_COLORS[len(pts) % len(self._REF_COLORS)]
        pts.append({"z": z, "x": x, "label": label, "color": color})
        self.refresh_ref_points_tree()
        self.app.update_scene("ref_points")

    def _remove_ref_point(self):
        sel = self.tree_refs.selection()
        if not sel: return
        idx = int(sel[0])
        pts = self.app.params.get("reference_points", [])
        if 0 <= idx < len(pts):
            pts.pop(idx)
        self.refresh_ref_points_tree()
        self.app.update_scene("ref_points")

    def _edit_ref_point(self):
        sel = self.tree_refs.selection()
        if not sel: return
        idx = int(sel[0])
        pts = self.app.params.get("reference_points", [])
        if not (0 <= idx < len(pts)): return
        pt = pts[idx]
        tip_x = float(self.app.params.get("home_x", 0.0))
        tip_z = float(self.app.params.get("home_z", 0.0))
        res = self._ref_point_dialog(t("dlg_edit_ref_point"),
                                     z=float(pt.get("z", 0.0)) - tip_z,
                                     x=float(pt.get("x", 0.0)) - tip_x,
                                     label=str(pt.get("label", "")))
        if res is None: return
        dz, dx, lbl = res
        pt["z"], pt["x"], pt["label"] = tip_z + dz, tip_x + dx, lbl
        self.refresh_ref_points_tree()
        self.app.update_scene("ref_points")

    # ── Operations ────────────────────────────────────────────────────────

    def open_op_suggester(self):
        from ui.dialogs.op_suggester import OpSuggesterDialog
        OpSuggesterDialog(self.ui_root, self.app, self.ui_root.tool_library,
                          self._apply_suggested_ops)

    def _apply_suggested_ops(self, ops, blank_thickness):
        """Callback from OpSuggesterDialog Apply: insert the reviewed ops and,
        if the user changed the blank thickness in the dialog, route it through
        on_param_change so it persists like any other Process-tab edit."""
        cur = float(self.app.params.get("final_part_thickness_on_mandrel", 2.0))
        if blank_thickness and abs(float(blank_thickness) - cur) > 1e-9:
            self.app.on_param_change("final_part_thickness_on_mandrel", float(blank_thickness))
        if "operations" not in self.app.params:
            self.app.params["operations"] = []
        self._push_undo(t("btn_suggest_ops"))
        self.app.params["operations"].extend(ops)
        self.refresh_ops_tree()

    @staticmethod
    def _split_op(op, sizes, end_z_fallback):
        """Split a multi-pass op into contiguous chunk-ops that reproduce it EXACTLY (#64).

        `sizes` = list of chunk pass-counts (each >=1, must sum to op count).
        `end_z_fallback` = the Z the engine uses when end_z is None (mandrel top_z), so an
        open-ended op can still be sliced into concrete chunks. Returns a list of op dicts.

        Exact because Z, pass_angle (→progressive_angle_end), reach (→progressive_reach_end)
        and interp-tilt all progress LINEARLY across passes, so a chunk covering passes
        [a..b] with its endpoints set to the a/b sub-range values reproduces that slice.
        Single-pass chunks collapse the fan to a fixed value. Everything else is copied.
        """
        C = int(op.get("count", 1))
        sizes = [int(s) for s in sizes]
        if any(s < 1 for s in sizes) or sum(sizes) != C:
            raise ValueError(f"chunk sizes {sizes} must be >=1 and sum to count {C}")

        def lerp(v0, v1, i):
            return v0 if C <= 1 else v0 + (i / (C - 1)) * (v1 - v0)

        Zs = float(op.get("start_z", 10.0))
        Ze = float(op["end_z"]) if op.get("end_z") is not None else float(end_z_fallback)

        has_pa = op.get("pass_angle") is not None
        As = float(op.get("pass_angle")) if has_pa else None
        prog_a = has_pa and bool(op.get("progressive_angle_enabled", False)) and C > 1
        Ae = float(op.get("progressive_angle_end", 180.0)) if prog_a else As

        rv = op.get("reach", None)
        try:
            rv = float(rv) if rv not in (None, "") else None
        except (TypeError, ValueError):
            rv = None
        if rv is not None and rv <= 0:
            rv = None
        prog_r = has_pa and bool(op.get("progressive_reach_enabled", False)) and C > 1
        if prog_r:
            import math
            Rbase = rv if rv is not None else math.hypot(
                float(op.get("p3_x", 0.0) or 0.0), abs(float(op.get("p3_z", -20.0) or 0.0)))
            Rend = float(op.get("progressive_reach_end", Rbase))

        interp_tilt = op.get("tilt_mode") == "interp"
        Ts = float(op.get("tilt_start", 0.0)) if interp_tilt else None
        Te = float(op.get("tilt_end", 0.0)) if interp_tilt else None

        chunks, a = [], 0
        for m in sizes:
            b = a + m - 1
            ch = dict(op)
            ch["count"] = m
            ch["start_z"] = round(lerp(Zs, Ze, a), 6)
            ch["end_z"] = round(lerp(Zs, Ze, b), 6)
            if prog_a:
                ch["pass_angle"] = round(lerp(As, Ae, a), 6)
                ch["progressive_angle_enabled"] = m > 1
                if m > 1:
                    ch["progressive_angle_end"] = round(lerp(As, Ae, b), 6)
            elif has_pa:
                ch["pass_angle"] = As
            if prog_r:
                ch["reach"] = round(lerp(Rbase, Rend, a), 6)
                ch["progressive_reach_enabled"] = m > 1
                if m > 1:
                    ch["progressive_reach_end"] = round(lerp(Rbase, Rend, b), 6)
            elif rv is not None:
                ch["reach"] = rv
            if interp_tilt:
                ch["tilt_start"] = round(lerp(Ts, Te, a), 6)
                ch["tilt_end"] = round(lerp(Ts, Te, b), 6)
            chunks.append(ch)
            a = b + 1
        return chunks

    @staticmethod
    def _pass_previews(op, end_z_fallback):
        """Per-pass {z, angle} for the split dialog (same linear formulas as _split_op)."""
        C = int(op.get("count", 1))

        def lerp(v0, v1, i):
            return v0 if C <= 1 else v0 + (i / (C - 1)) * (v1 - v0)

        Zs = float(op.get("start_z", 10.0))
        Ze = float(op["end_z"]) if op.get("end_z") is not None else float(end_z_fallback)
        has_pa = op.get("pass_angle") is not None
        As = float(op.get("pass_angle")) if has_pa else None
        prog_a = has_pa and bool(op.get("progressive_angle_enabled", False)) and C > 1
        Ae = float(op.get("progressive_angle_end", 180.0)) if prog_a else As
        return [{"z": lerp(Zs, Ze, i), "angle": (lerp(As, Ae, i) if prog_a else As)}
                for i in range(C)]

    def _blank_reach_values(self, op):
        """Flange-model reach for an op → (r_start, r_end, fanned), or None if not
        computable (wrong type / no blank / fully consumed). Shared by the manual Reach⟲
        button and the auto 'reach follows blank' refresh (#61 option B)."""
        if op.get("type") in ("cutting", "bending"):
            return None
        R = float(self.app.params.get("blank_radius", 0.0) or 0.0)
        if R <= 0:
            return None
        from process_planner import estimate_flange_reach
        mgr = self.app.mandrel_mgr
        top_z = float(mgr.props.get("top_z", op.get("end_z") or 0.0))
        start_z = float(op.get("start_z", 10.0))
        end_z = float(op["end_z"]) if op.get("end_z") is not None else top_z
        r_start = estimate_flange_reach(mgr, R, start_z)
        r_end = estimate_flange_reach(mgr, R, end_z)
        if r_start <= 0 and r_end <= 0:
            return None
        # Optional operator modifier: scale the blank-derived reach by a factor (default 1.0
        # = kiss the exact flange edge; 0.9 = 90% of it, stop short; 1.1 = 10% past). Applied
        # to both base and top of the fan.
        _fac = op.get("reach_blank_factor", 1.0)
        try:
            factor = float(_fac) if _fac not in (None, "") else 1.0
        except (TypeError, ValueError):
            factor = 1.0
        r_start = max(r_start * factor, 0.0)
        r_end = max(r_end * factor, 0.0)
        fanned = int(op.get("count", 1)) > 1 and op.get("pass_angle") is not None
        return (round(r_start, 2), round(r_end, 2), fanned)

    def _apply_blank_reach(self, op, vals):
        """Write flange-model reach into an op: reach (base flange) + progressive-reach
        fan end (top flange) when the op is a progressive-angle multi-pass op."""
        r_start, r_end, fanned = vals
        op["reach"] = r_start
        if fanned:
            op["progressive_reach_enabled"] = True
            op["progressive_reach_end"] = r_end

    def _refresh_auto_reach(self):
        """Opt-in #61 (option B): for every op flagged ``reach_follow_blank``, recompute
        reach from the blank flange so the exit keeps KISSING the blank edge as start_z/
        end_z change. Silent — called before each program-tab recalc. Returns True if any
        op changed (so the tree can refresh)."""
        changed = False
        for op in self.app.params.get("operations", []):
            if not op.get("reach_follow_blank"):
                continue
            vals = self._blank_reach_values(op)
            if vals:
                self._apply_blank_reach(op, vals)
                changed = True
        if changed:
            try:
                self.refresh_ops_tree()
            except Exception:
                pass
        return changed

    def compute_reach_from_blank(self):
        """Opt-in (#61 step 4): estimate the selected op's reach from the remaining blank
        flange and FILL the reach field(s) — never silent. Uses the area-equivalence flange
        model (radial overhang from the clamped base). For a progressive-angle multi-pass op
        it also fans progressive_reach_end (bigger flange at the base → smaller near the top).
        The value is a starting estimate: the operator reviews it before running."""
        sel = self.tree_ops.selection()
        if not sel:
            messagebox.showinfo(t("msg_reach_title"), t("msg_reach_noselect"))
            return
        try:
            idx = int(sel[0])
        except (ValueError, IndexError):
            return
        ops = self.app.params.get("operations", [])
        if idx >= len(ops):
            return
        op = ops[idx]
        if op.get("type") in ("cutting", "bending"):
            messagebox.showinfo(t("msg_reach_title"), t("msg_reach_badtype"))
            return
        R = float(self.app.params.get("blank_radius", 0.0) or 0.0)
        if R <= 0:
            messagebox.showinfo(t("msg_reach_title"), t("msg_reach_noblank"))
            return
        # Guard against a DIAMETER typed into the (radius) Sheet Radius field — the classic
        # mistake that doubles the blank and roughly triples the estimated reach. Warn if the
        # blank radius exceeds 2.5× the mandrel base radius; still allow (operator judgement).
        base_r = float(self.app.mandrel_mgr.props.get("br", 0.0) or 0.0)
        if base_r > 1.0 and R > base_r * 2.5:
            if not messagebox.askyesno(t("msg_reach_title"),
                                       t("msg_reach_diam").format(r=R, b=base_r)):
                return
        vals = self._blank_reach_values(op)
        if not vals:
            messagebox.showinfo(t("msg_reach_title"), t("msg_reach_zero"))
            return
        self._push_undo(t("btn_compute_reach"))
        self._apply_blank_reach(op, vals)
        r_start, r_end, fanned = vals

        self.refresh_ops_tree()
        self.tree_ops.selection_set(str(idx))
        self.on_op_select(None, _flush=False)
        self._start_async_calc()
        if fanned:
            messagebox.showinfo(t("msg_reach_title"),
                                t("msg_reach_done_fan").format(rs=round(r_start, 2),
                                                               re=round(r_end, 2)))
        else:
            messagebox.showinfo(t("msg_reach_title"),
                                t("msg_reach_done").format(r=round(r_start, 2)))

    def compute_angle_from_surface(self):
        """Opt-in (#61): estimate the selected op's progressive-angle fan END from the
        mandrel surface and FILL it — never silent. The exit that lays material along the
        wall points along the surface tangent at the op's end Z; converting that to the
        pass-angle frame gives the fan-end angle (cylinder → 180°, cone → the wall slope).
        The value is a starting estimate: the operator confirms the forming direction and
        reviews it before running."""
        sel = self.tree_ops.selection()
        if not sel:
            messagebox.showinfo(t("msg_angle_title"), t("msg_reach_noselect"))
            return
        try:
            idx = int(sel[0])
        except (ValueError, IndexError):
            return
        ops = self.app.params.get("operations", [])
        if idx >= len(ops):
            return
        op = ops[idx]
        if op.get("type") in ("cutting", "bending"):
            messagebox.showinfo(t("msg_angle_title"), t("msg_reach_badtype"))
            return
        if op.get("pass_angle") in (None, ""):
            messagebox.showinfo(t("msg_angle_title"), t("msg_angle_nopassangle"))
            return

        from process_planner import estimate_surface_angle
        mgr = self.app.mandrel_mgr
        start_z = float(op.get("start_z", 0.0))
        end_z = float(op["end_z"]) if op.get("end_z") is not None else start_z
        forming_up = end_z >= start_z  # tangent points the way the passes travel in Z
        theta_end = estimate_surface_angle(mgr, end_z, forming_up)  # deg from +X

        # Approach direction θ_A (same convention as the path engine): linear approach is a
        # pure -Z entry (-90°); a spline entry follows the P1 offset direction.
        shape = op.get("pass_shape", "spline")
        if shape in ("linear_approach", "linear_full"):
            theta_a = -90.0
        else:
            px, pz = abs(float(op.get("p1_x", 0.0))), abs(float(op.get("p1_z", 0.0)))
            theta_a = math.degrees(math.atan2(-pz, px)) if px > 0.001 else -90.0

        ang_end = round(theta_end - theta_a, 1)
        self._push_undo(t("btn_compute_angle"))
        op["progressive_angle_end"] = ang_end
        if int(op.get("count", 1)) > 1:
            op["progressive_angle_enabled"] = True  # fan only takes effect with >1 pass

        self.refresh_ops_tree()
        self.tree_ops.selection_set(str(idx))
        self.on_op_select(None, _flush=False)
        self._start_async_calc()
        messagebox.showinfo(t("msg_angle_title"),
                            t("msg_angle_done").format(a=ang_end,
                                                       s=round(theta_end, 1),
                                                       p=round(theta_a, 1)))

    def open_split_op(self):
        """Split the selected multi-pass op into contiguous chunk-ops (#64). Opens the
        visual divider dialog; on confirm replaces the op in-place with the chunks (which
        reproduce it exactly). The chunks are ordinary ops — reorder them (Move Up/Down /
        drag) to interleave reverse passes between."""
        sel = self.tree_ops.selection()
        if not sel:
            messagebox.showinfo(t("msg_split_title"), t("msg_split_noselect"))
            return
        try:
            idx = int(sel[0])
        except (ValueError, IndexError):
            return
        ops = self.app.params.get("operations", [])
        if idx >= len(ops):
            return
        op = ops[idx]
        if op.get("type") in ("cutting", "bending"):
            messagebox.showinfo(t("msg_split_title"), t("msg_split_badtype"))
            return
        if int(op.get("count", 1)) < 2:
            messagebox.showinfo(t("msg_split_title"), t("msg_split_toosmall"))
            return

        top_z = float(self.app.mandrel_mgr.props.get("top_z", op.get("end_z") or 0.0))
        from ui.dialogs.split_op_dialog import SplitOpDialog
        top = self.frame.winfo_toplevel()
        dlg = SplitOpDialog(top, int(op.get("count", 1)), self._pass_previews(op, top_z))
        top.wait_window(dlg)
        sizes = dlg.result
        if not sizes or len(sizes) < 2:
            return  # cancelled or no divider set

        chunks = self._split_op(op, sizes, top_z)
        self._push_undo(t("btn_split"))
        self._clear_batch_checks()  # #67: indices shift after the split
        # Discard stale property-editor state before mutating operations (see del_op / #56).
        self._active_entry_savers = []
        self._active_op_idx = None
        for w in self.f_prop_editor.winfo_children():
            w.destroy()
        ops[idx:idx + 1] = chunks
        self.refresh_ops_tree()
        self.tree_ops.selection_set(str(idx))
        self.on_op_select(None, _flush=False)
        self._start_async_calc()
        try:
            self.ui_root.lbl_info.config(text=t("msg_split_done").format(n=len(chunks)), fg="#ddd")
        except Exception:
            pass

    @staticmethod
    def _continue_fill_values(prev, prev_end_z, prev_reach):
        """Pure computation for continue_from_previous (#61 step 2): the fields to copy
        into the next op from the previous op's LAST-pass end-state. `prev_end_z` /
        `prev_reach` are the path generator's computed values (or None → param fallback).
        Returns a dict; tool is deliberately excluded."""
        out = {}
        end_z = prev_end_z if prev_end_z is not None else prev.get("end_z", prev.get("start_z"))
        if end_z is not None:
            out["start_z"] = round(float(end_z), 3)
        # exit angle / direction of the previous op's last pass
        if prev.get("pass_angle") is not None:
            if prev.get("progressive_angle_enabled") and int(prev.get("count", 1)) > 1:
                out["pass_angle"] = float(prev.get("progressive_angle_end", 180.0))
            else:
                out["pass_angle"] = float(prev.get("pass_angle"))
        else:
            # raw mode: copy the exit direction (p3_x/p3_z ratio) so the angle matches
            if prev.get("p3_x") is not None:
                out["p3_x"] = prev.get("p3_x")
            if prev.get("p3_z") is not None:
                out["p3_z"] = prev.get("p3_z")
        reach = prev_reach if prev_reach is not None else prev.get("reach")
        if reach is not None:
            out["reach"] = round(float(reach), 3)
        if prev.get("clearance") is not None:
            out["clearance"] = prev.get("clearance")
        return out

    def continue_from_previous(self):
        """One-shot: fill the selected op's start-state from the op ABOVE it (#61 step 2).

        Copies the previous op's LAST forming pass end-state into the selected op so the
        new op begins where the previous one finished — Start Z (where it ended), the exit
        angle/direction (pass angle incl. progressive fan end, or the raw p3_x/p3_z ratio),
        the reach, and clearance. Then the op is INDEPENDENT (edit freely, e.g. flip
        Direction to Reverse). Prefers the path generator's computed end-state
        (last_op_end_z / last_op_reach — needs a prior calculation); falls back to the
        previous op's parameters when paths were not calculated yet. Tool is NOT copied.
        """
        sel = self.tree_ops.selection()
        if not sel:
            messagebox.showinfo(t("msg_continue_title"), t("msg_continue_noselect"))
            return
        try:
            idx = int(sel[0])
        except (ValueError, IndexError):
            return
        ops = self.app.params.get("operations", [])
        if idx <= 0 or idx >= len(ops):
            messagebox.showinfo(t("msg_continue_title"), t("msg_continue_nofirst"))
            return
        prev, cur = ops[idx - 1], ops[idx]
        pg = self.app.path_gen
        self._push_undo(t("btn_continue_prev"))
        cur.update(self._continue_fill_values(
            prev,
            getattr(pg, "last_op_end_z", {}).get(idx - 1),
            getattr(pg, "last_op_reach", {}).get(idx - 1)))

        self.refresh_ops_tree()
        self.tree_ops.selection_set(str(idx))
        self.on_op_select(None, _flush=False)
        self._start_async_calc()
        try:
            self.ui_root.lbl_info.config(
                text=t("msg_continue_done").format(idx=idx + 1, prev=idx), fg="#ddd")
        except Exception:
            pass

    def add_op(self, mode):
        if "operations" not in self.app.params:
            self.app.params["operations"] = []
        self._push_undo(t("btn_add_op"))

        # Load from saved preset if available
        preset = self.app.params.get("op_presets", {}).get(mode)
        if preset:
            new_op = dict(preset)
            new_op["type"] = mode
            new_op["enabled"] = True
            self.app.params["operations"].append(new_op)
            self.refresh_ops_tree()
            return

        if mode in ("cutting", "bending"):
            # Cutting/bending: single radial plunge at mandrel end
            def_tool_id = "T0303"
            for tl in self.ui_root.tool_library:
                if tl["id"] == def_tool_id:
                    break
            else:
                # Fall back to first tool in library if T0303 not found
                if self.ui_root.tool_library:
                    def_tool_id = self.ui_root.tool_library[0].get("id", "T0303")

            new_op = {
                "type": mode, "enabled": True, "count": 1,
                "tool_id": def_tool_id,
                "r_tool": 0.0,
                "z_pos": 0.0,
                "plunge_x": 50.0,
                "feed": 50.0, "feed_mode": "mm_min",
                "speed": 300.0, "speed_mode": "RPM",
            }
            self.app.params["operations"].append(new_op)
            self.refresh_ops_tree()
            return

        # Inherit rotation from last op
        def_rot = 10.0
        if self.app.params["operations"]:
             def_rot = self.app.params["operations"][-1].get("rot", 10.0)

        # Choose default tool based on mode
        if mode == "roughing":
            def_tool_id = "T0101"
        else:
            def_tool_id = "T0202"

        # Look up tool radius from library — prefer calibrated r_tool, fall back to geometry radius
        def_r_tool = 25.0  # fallback default
        for tl in self.ui_root.tool_library:
            if tl["id"] == def_tool_id:
                # Explicit-None: a calibrated r_tool of 0.0 is valid and must not
                # fall through to the disc radius (matches sync_operation_r_tools).
                _rt = tl.get("r_tool")
                def_r_tool = _rt if _rt is not None else tl.get("radius", 25.0)
                break

        # If not found by default ID, try to use first available tool of matching type
        if def_r_tool == 25.0 and self.ui_root.tool_library:
            first_tool = self.ui_root.tool_library[0]
            def_tool_id = first_tool.get("id", def_tool_id)
            _rt = first_tool.get("r_tool")
            def_r_tool = _rt if _rt is not None else first_tool.get("radius", 25.0)

        new_op = {
            "type": mode, "enabled": True, "count": 1,
            "tool_id": def_tool_id,
            "r_tool": def_r_tool,
            "p1_x": 40.0, "p1_z": 50.0, "p3_z": -20.0,
            "start_z": 0.0, "end_z": 200.0,
            "step": 1.0,
            "clearance": 0.0,
            "rot": def_rot,
            "feed": 100.0, "speed": 500.0,
            "pass_shape": "spline",
        }
        self.app.params["operations"].append(new_op)
        self.refresh_ops_tree()

    def del_op(self):
        sel = self.tree_ops.selection()
        if not sel:
            return
        idx = int(sel[0])
        self._push_undo(t("btn_del_op"))
        self._clear_batch_checks()  # #67: indices shift after the removal
        # Discard the current property-editor state BEFORE removing the op.
        # The entry-savers are bound to positional indices and still hold the
        # deleted op's widget values; if left in place, the next
        # _flush_entries() would write them into whichever op now occupies
        # that index (deleting the first set would clobber the second with
        # the first's values). Destroying the widgets also kills their own
        # FocusOut/Return bindings, which reference the stale index too.
        self._active_entry_savers = []
        self._active_op_idx = None
        for w in self.f_prop_editor.winfo_children():
            w.destroy()

        self.app.params["operations"].pop(idx)
        self.refresh_ops_tree()

        # Rebuild the editor for whatever op now sits at (or before) idx.
        ops = self.app.params.get("operations", [])
        if ops:
            new_sel = min(idx, len(ops) - 1)
            self.tree_ops.selection_set(str(new_sel))
            self.on_op_select(None, _flush=False)

    def move_op(self, d):
        sel = self.tree_ops.selection()
        if not sel:
            return
        idx = int(sel[0])
        new_idx = idx + d
        if not (0 <= new_idx < len(self.app.params["operations"])):
            return
        # Commit pending edits for the selected op first (savers are still
        # bound to its current index), then discard them so the reselect
        # below can't write the moved op's old widget values into the op
        # that swaps into this index.
        self._flush_entries()
        self._push_undo(t("act_move_op"))
        self._clear_batch_checks()  # #67: the swap invalidates ticked indices
        self._active_entry_savers = []
        self._active_op_idx = None
        ops = self.app.params["operations"]
        ops[idx], ops[new_idx] = ops[new_idx], ops[idx]
        self.refresh_ops_tree()
        self.tree_ops.selection_set(str(new_idx))
        self.on_op_select(None, _flush=False)

    def rebuild(self):
        for widget in self.frame.winfo_children():
            widget.destroy()
        self._create_widgets()
