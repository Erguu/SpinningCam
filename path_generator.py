import datetime
import numpy as np
import math
import time
import re
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Trsf
from OCC.Core.TColgp import TColgp_Array1OfPnt
from OCC.Core.GeomAPI import GeomAPI_PointsToBSpline
from logger_config import logger
from kinematics import get_kinematics


def effective_clamp_length(params):
    """Clamp / counter-press zone length in effect (mm, measured UP from the mandrel
    base). TODO #62. The per-part override ``clamp_zone_length`` wins when > 0; otherwise
    the machine-level ``clamp_zone_baseline`` applies. 0 = no clamp zone.

    Note: 0 for the per-part value means "inherit the machine baseline", so a per-part
    value cannot force-disable a non-zero baseline in phase 1 (documented tradeoff)."""
    def _f(v):
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0
    v = _f(params.get("clamp_zone_length", 0.0))
    if v <= 0.0:
        v = _f(params.get("clamp_zone_baseline", 0.0))
    return max(0.0, v)


class PathGenerator:
    def __init__(self):
        self.last_calculated_paths = []
        self.last_mandrel_mgr = None
        self.last_tilt_angles = None       # per-path tilt arrays (tilt_arm machines) or None
        self.last_kinematic_warnings = []  # reachability issues from last G-code generation
        self._path_op_map = []             # toolpath index → op dict (parallel to last_calculated_paths)
        self.last_op_end_z = {}            # op-index → CAM Z the op's last forming pass reaches (incl. p2_z_extend)

    def _ensure_ops_dict(self, params):
        if "operations" in params and isinstance(params["operations"], list) and len(params["operations"]) > 0:
            return params["operations"]
        
        # Legacy Migration
        ops = []
        
        # 1. Roughing
        num_rough = int(params.get("num_sweeping_passes", 3))
        if num_rough > 0:
            ops.append({
                "type": "roughing",
                "enabled": True,
                "count": num_rough,
                "tool_id": params.get("rough_tool_number", "T0101"),
                "r_tool": params.get("roller_visual_radius", 25.0),
                "start_z": params.get("first_pass_p2_contact_z_abs", 10.0),
                "p1_x": params.get("p1_p3_x_offset_from_p2", 40.0),
                "p1_z": params.get("p1_z_offset_from_p2", 50.0),
                "p3_z": params.get("p3_z_offset_from_p2", -20.0),
                "rot": params.get("y_rotation_degrees", 10.0),
                "step": params.get("roughing_step_radial", 1.0),
                "proj_extend_bottom": 0.0,
                "proj_extend_top": 0.0,
            })

        # 2. Finishing
        num_finish = int(params.get("num_finishing_passes", 0))
        if num_finish > 0:
             ops.append({
                "type": "finishing",
                "enabled": True,
                "count": num_finish,
                "tool_id": params.get("finish_tool_number", "T0202"),
                "r_tool": params.get("finish_tool_radius", 25.0),
                "start_z": params.get("first_pass_p2_contact_z_abs", 10.0), 
                "p1_x": params.get("finish_p1_p3_x_offset_from_p2", 10.0),
                "p1_z": params.get("finish_p1_z_offset_from_p2", 10.0),
                "p3_z": params.get("finish_p3_z_offset_from_p2", -10.0),
                "rot": params.get("finish_y_rotation_degrees", 0.0),
                "step": params.get("finish_step_radial", 0.0)
            })
        
        return ops

    def calculate_paths(self, params, overrides, mandrel_mgr, visual_roller_pos=None):
        toolpaths = []
        projections = []
        control_points = []
        deviations = []
        rapids = []
        sequence = [] # Ordered execution list for simulation
        debug_lines = [] # Analysis Lines for Visualization
        self.last_back_pass_meta = {}  # {path_list_index: {"feed": ...}}
        self.last_render_split_idx = {}  # {path_list_index: (line_end_idx, arc_end_idx)}
        self._path_op_map = []  # toolpath index → op dict, synced as paths are appended
        self.last_op_end_z = {}  # op-index → CAM Z the op's last forming pass actually reaches
        self.last_op_reach = {}       # op-index → exit reach magnitude of last forming pass (#61)
        self.last_op_end_angle = {}   # op-index → exit angle (deg from +X) of last forming pass (#61)
        self.last_clamp_warnings = []  # ops whose start_z sits inside the clamp zone (#62)

        props = mandrel_mgr.props
        top_z = props["top_z"]

        # Clamp / counter-press zone (#62): the base region held by the counter-press is
        # not machined. Phase 1 = warning only (no clipping); flag ops that start inside it.
        clamp_len = effective_clamp_length(params)
        clamp_top_z = (props.get("min_z", 0.0) + clamp_len) if clamp_len > 0 else None
        center_x = params.get("mandrel_pos_x_offset", 0.0)
        blank_thick = params.get("final_part_thickness_on_mandrel", 2.0)
        shell_offset = params.get("shell_thickness", 0.0)

        # Rapids Simulation Params (Match generate_gcode defaults)
        home_x = params.get("home_x", 300.0)
        home_z = params.get("home_z", 150.0)
        # [NEW] Pass Retract Offset (Relative)
        retract_x_offset = float(params.get("retract_x", 50.0))
        retract_z_offset = float(params.get("retract_z", 50.0))

        # Roller approach side: +1 = positive X (default), -1 = negative X (roller below/behind mandrel)
        # Generation always happens in canonical (positive X) frame; mirrored at the end if side==-1.
        side = 1.0 if params.get("roller_positive_x_side", True) else -1.0
        home_x_can = center_x + abs(home_x - center_x)   # canonical safe home X (positive)
        retract_x_can = abs(retract_x_offset)              # canonical retract offset (positive)

        # Convert visual_roller_pos to canonical coords if on negative side
        if visual_roller_pos is not None and side == -1:
            visual_roller_pos = (2.0 * center_x - visual_roller_pos[0], visual_roller_pos[1], visual_roller_pos[2])

        operations = self._ensure_ops_dict(params)
        global_pass_idx = 0

        # Initial Position (Home) — canonical coordinates
        current_pt = np.array([home_x_can, 0, home_z])
        current_tool = None

        # [NEW] Initial Homing Visualization if visual pos differs from Home
        if visual_roller_pos is not None:
             start_vis = np.array(visual_roller_pos)
             
             # G-Code Header: G0 Z150 (Move Z to Home Z), then G0 X300 (Move X to Home X)
             # Simulate this sequence from visual start.
             
             # 1. Move Z to Home Z (keeping Visual X)
             step1 = np.array([start_vis[0], 0, home_z]) 
             
             # 2. Move X to Home X (at Home Z) -> [Home.X, 0, Home.Z]
             step2 = np.array([home_x_can, 0, home_z])
             
             add_homing = False
             
             # Check if we are far enough to matter
             if np.linalg.norm(start_vis - step1) > 1.0:
                 rapids.append(np.array([start_vis, step1]))
                 sequence.append(("rapid", np.array([start_vis, step1])))
                 add_homing = True
                 
             if np.linalg.norm(step1 - step2) > 1.0:
                 rapids.append(np.array([step1, step2]))
                 sequence.append(("rapid", np.array([step1, step2])))
                 add_homing = True
             
             if add_homing:
                 current_pt = step2

        for op_index, op in enumerate(operations):
            if not op.get("enabled", True): continue

            count = int(op.get("count", 1))
            is_finish = (op.get("type") == "finishing")
            r_tool = float(op.get("r_tool", 25.0))
            # Unified clearance = gap between the roller contact and the blank surface.
            # Single source of truth for EVERY pass type (roughing & finishing alike), so
            # the same value always yields the same contact standoff. Legacy recipes (no
            # `clearance` key) fall back to the old split knobs so their toolpaths are
            # unchanged: finishing = finish_allowance + safety; roughing = target_clearance
            # (the value its old correction loop forced the contact to).
            op_clearance = op.get("clearance")
            if op_clearance is None:
                if is_finish:
                    op_clearance = float(op.get("finish_allowance", 0.0)) + float(params.get("safety_clearance_roller_to_part", 0.0))
                else:
                    op_clearance = float(params.get("target_clearance", 0.0))
            op_clearance = float(op_clearance)
            op_tool_id = op.get("tool_id", "T0101")
            
            # [UPDATED] Tool Change Logic
            # Always simulate movement if ID changes, regardless of M6 flag
            need_tool_change = (op_tool_id != current_tool) or (current_tool is None)
            
            if need_tool_change and current_tool is not None:
                # Retract to Home SAFE (Split move: Z home first, then X out)
                # 1. Move to Home Z (keeping current X)
                safe_mid = np.array([current_pt[0], 0, home_z])

                # Only add if distance > 1mm
                if np.linalg.norm(current_pt - safe_mid) > 1.0:
                    r_seg1 = np.array([current_pt, safe_mid])
                    rapids.append(r_seg1)
                    sequence.append(("rapid", r_seg1))

                # 2. Move to Home X (at Home Z)
                home_pt = np.array([home_x_can, 0, home_z])
                if np.linalg.norm(safe_mid - home_pt) > 1.0:
                    r_seg2 = np.array([safe_mid, home_pt])
                    rapids.append(r_seg2)
                    sequence.append(("rapid", r_seg2))

                current_pt = home_pt
                
            current_tool = op_tool_id

            # --- Cutting / Bending: simple radial plunge, single pass ---
            op_type_str = op.get("type", "roughing")
            if op_type_str in ("cutting", "bending"):
                z_pos          = float(op.get("z_pos", 0.0))
                plunge_x_global  = float(op.get("plunge_x", center_x + 50.0))
                approach_x_global = plunge_x_global + retract_x_can

                prev_paths_len = len(toolpaths)
                path = np.array([[approach_x_global, 0.0, z_pos],
                                 [plunge_x_global,   0.0, z_pos]])
                toolpaths.append(path)
                projections.append(np.array([[plunge_x_global, 0.0, z_pos]]))
                control_points.append(np.array([[plunge_x_global, 0.0, z_pos]]))
                deviations.append(np.array([0.0, 0.0]))

                if len(toolpaths) > prev_paths_len:
                    start_pt = path[0]
                    end_pt   = path[-1]
                    for seg in self._safe_rapid_segments(current_pt, start_pt, current_pt[0]):
                        rapids.append(seg)
                        sequence.append(("rapid", seg))
                    sequence.append(("cut", path, r_tool, op_tool_id))
                    retract_pt = np.array([end_pt[0] + retract_x_can, 0, end_pt[2] + retract_z_offset])
                    r_seg2 = np.array([end_pt, retract_pt])
                    rapids.append(r_seg2)
                    sequence.append(("rapid", r_seg2))
                    current_pt = retract_pt

                while len(self._path_op_map) < len(toolpaths):
                    self._path_op_map.append(op)
                # Cutting/bending "reach" is the plunge Z.
                self.last_op_end_z[op_index] = z_pos
                global_pass_idx += 1
                continue

            # Op Params
            def_p1_x = float(op.get("p1_x", 40.0)); def_p1_z = float(op.get("p1_z", 50.0))
            def_p3_x = float(op.get("p3_x", def_p1_x))
            def_p3_z = float(op.get("p3_z", -20.0)); def_rot = float(op.get("rot", 0.0))
            start_h = float(op.get("start_z", 10.0))

            # Clamp-zone advisory (#62): warn (do not clip) if this op begins inside the
            # counter-press region. Uses a small epsilon so a start exactly at the top edge
            # is fine.
            if clamp_top_z is not None and start_h < clamp_top_z - 1e-6:
                self.last_clamp_warnings.append({
                    "op_index": op_index,
                    "op_type": op.get("type", "roughing"),
                    "start_z": start_h,
                    "clamp_top_z": clamp_top_z,
                })

            # end_z operasyona özeldir; tanımlıysa kullan, yoksa mandrel tepesine git
            op_end_z = op.get("end_z", None)
            end_h = float(op_end_z) if op_end_z is not None else top_z

            # Record the CAM Z where this op's LAST forming pass actually reaches,
            # for the Program-tab "Real End Z" column. This mirrors the per-pass
            # target_z/contact_z math below (lines ~294-300) for the last pass:
            #   roughing: contact = target_z + p2_z_extend, where target_z is
            #             start_h for a single pass, else end_h (the last pass).
            #   finishing: sweeps the whole zone start_h→end_h, so its end is end_h
            #             (no p2_z_extend — it is forced to 0 for finishing).
            if is_finish:
                self.last_op_end_z[op_index] = end_h
            else:
                _last_target_z = start_h if count <= 1 else end_h
                self.last_op_end_z[op_index] = _last_target_z + float(op.get("p2_z_extend", 0.0))


            # Auto-Align Feature: Read from params
            auto_align = params.get("auto_calc_angle", True)
            
            for i in range(count):
                ovr = overrides.get(global_pass_idx, {})
                if is_finish:
                     p1_x    = ovr.get("finish_p1_p3_x_offset_from_p2", def_p1_x)
                     p1_z    = ovr.get("finish_p1_z_offset_from_p2", def_p1_z)
                     p3_x    = p1_x
                     p3_z    = ovr.get("finish_p3_z_offset_from_p2", def_p3_z)
                     base_rot = ovr.get("finish_y_rotation_degrees", def_rot)
                else:
                     p1_x    = ovr.get("p1_p3_x_offset_from_p2", def_p1_x)
                     p1_z    = ovr.get("p1_z_offset_from_p2",    def_p1_z)
                     p3_x    = def_p3_x
                     p3_z    = ovr.get("p3_z_offset_from_p2",    def_p3_z)
                     base_rot = ovr.get("y_rotation_degrees",    def_rot)
                
                
                # Normalize p3_z to positive convention: op stores it negative (e.g. -20) as a user
                # convenience but _create_and_store_pass now uses it signed (+ = forward in Z).
                p3_z = abs(p3_z)

                # Reach (#61): single authoritative exit-stroke magnitude |P2→P3|. Unset or
                # <=0 keeps the legacy behavior EXACTLY (magnitude implied by p3_x/p3_z).
                # When set, direction comes from pass_angle (below) or, in raw mode, from the
                # p3_x/p3_z ratio (which is scaled to this length, ratio preserved).
                _reach_v = op.get("reach", None)
                try:
                    _reach_v = float(_reach_v) if _reach_v not in (None, "") else None
                except (TypeError, ValueError):
                    _reach_v = None
                if _reach_v is not None and _reach_v <= 0:
                    _reach_v = None

                # Pass Angle override — Option B: L3 = |P2→P3| preserved, only direction rotates.
                # θ_A = angle of P2→P1 from +X in XZ. θ_B = θ_A + pass_angle. p3 = L3 * (cos θ_B, sin θ_B).
                # linear_approach/linear_full: θ_A is always -90° (pure -Z entry).
                _pa_deg = op.get("pass_angle", None)
                if _pa_deg is not None:
                    _eff_angle = float(_pa_deg)
                    if op.get("progressive_angle_enabled", False) and count > 1:
                        # Fan target: last pass reaches progressive_angle_end
                        # (default 180° = laid along the surface). Any end value
                        # is allowed — smaller than 180 stops the fan early,
                        # smaller than pass_angle fans downward.
                        try:
                            _prog_end = float(op.get("progressive_angle_end", 180.0))
                        except (TypeError, ValueError):
                            _prog_end = 180.0
                        _eff_angle += i * (_prog_end - _eff_angle) / (count - 1)
                    _L3 = _reach_v if _reach_v is not None else math.sqrt(p3_x ** 2 + abs(p3_z) ** 2)
                    # Progressive reach: sweep the P2→P3 stroke length across passes,
                    # independent of the direction sweep (progressive_angle). First pass
                    # keeps the current reach, last pass reaches progressive_reach_end.
                    # Orthogonal to the angle fan: θ_B sets direction, _L3 sets length.
                    if op.get("progressive_reach_enabled", False) and count > 1:
                        try:
                            _reach_end = float(op.get("progressive_reach_end", _L3))
                        except (TypeError, ValueError):
                            _reach_end = _L3
                        _L3 = max(_L3 + i * (_reach_end - _L3) / (count - 1), 0.0)
                    if _L3 > 0.001:
                        _shape = op.get("pass_shape", "spline")
                        if _shape in ("linear_approach", "linear_full"):
                            _theta_A = -math.pi / 2
                        else:
                            _px, _pz = abs(p1_x), abs(p1_z)
                            _theta_A = math.atan2(-_pz, _px) if _px > 0.001 else -math.pi / 2
                        _theta_B = _theta_A + math.radians(_eff_angle)
                        p3_x = _L3 * math.cos(_theta_B)
                        p3_z = _L3 * math.sin(_theta_B)
                        _dbg_warn = " ← p3_x<0: clearance correction will dominate, further angle increase has diminishing effect" if p3_x < 0 else ""
                        logger.info(
                            f"[PARAM_DEBUG] '{op.get('type','?')} {i+1}' (global pass {global_pass_idx+1}): "
                            f"pass_angle={_pa_deg:.1f}° | "
                            f"θ_A={math.degrees(_theta_A):.1f}° + {_pa_deg:.1f}° = θ_B={math.degrees(_theta_B):.1f}° | "
                            f"P3 offset → X={p3_x:+.2f}mm Z={p3_z:+.2f}mm{_dbg_warn}"
                        )
                else:
                    # Raw exit mode (no pass angle): reach scales the (p3_x, p3_z) vector
                    # length, preserving its X/Z ratio (direction). Unset reach → unchanged.
                    if _reach_v is not None:
                        _cur = math.sqrt(p3_x ** 2 + p3_z ** 2)
                        if _cur > 1e-6:
                            _s = _reach_v / _cur
                            p3_x *= _s
                            p3_z *= _s

                # Record this pass's exit reach + angle for the LAST forming pass so the
                # Program tab can show end-reach / end-angle beside Real End Z (#61).
                if not is_finish and i == count - 1:
                    _fr = math.sqrt(p3_x ** 2 + p3_z ** 2)
                    self.last_op_reach[op_index] = _fr
                    self.last_op_end_angle[op_index] = (
                        math.degrees(math.atan2(p3_z, p3_x)) if _fr > 1e-6 else 0.0)

                if count <= 1:
                    target_z = start_h
                else:
                    target_z = start_h + (i / (count - 1) * (end_h - start_h))

                p2_z_extend = float(op.get("p2_z_extend", 0.0)) if not is_finish else 0.0
                contact_z   = target_z + p2_z_extend

                r_contact = mandrel_mgr.get_radius_fast(contact_z) + shell_offset
                nx, nz = mandrel_mgr.get_normal_at_z(contact_z)
                total_off = r_tool + blank_thick + op_clearance
                # Per-op conformal flag: normal-projected P2 placement. Falls back to global conformal_clearance_all_operations.
                conformal = op.get("conformal_clearance_operation_specific", params.get("conformal_clearance_all_operations", False))
                if conformal:
                    p2_x = center_x + r_contact + nx * total_off
                    p2_z = contact_z + nz * total_off
                else:
                    p2_x = center_x + r_contact + total_off
                    p2_z = contact_z

                # Reach is clearance-independent (#61, user 2026-07-05): when reach is set,
                # anchor the exit END to the ZERO-clearance contact reference so two passes
                # with the same reach land at the SAME absolute P3 regardless of clearance.
                # P2 carries the clearance standoff (radial in non-conformal, along the normal
                # in conformal); shifting the P3 offset inward by that clearance component
                # cancels it out of the endpoint. NOTE: exact for base_rot=0 (linear approach
                # / rotation off); auto-rotated splines rotate P3 about P2, so it is
                # approximate there (documented; verify per case).
                if _reach_v is not None:
                    if conformal:
                        p3_x -= op_clearance * nx
                        p3_z -= op_clearance * nz
                    else:
                        p3_x -= op_clearance

                pass_label = f"{op.get('type').capitalize()} {i+1}"
                
                prev_paths_len = len(toolpaths)
                
                m_min_z = mandrel_mgr.props.get("min_z", 0.0)
                m_top_z = mandrel_mgr.props.get("top_z", 100.0)

                if is_finish:
                    adaptive_mode = params.get("finish_trace_mandrel_profile", False)
                    if adaptive_mode:
                        conf_start = max(m_min_z, start_h)
                        conf_end   = min(m_top_z, end_h)
                        self._create_adaptive_pass(conf_start, conf_end, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_label, toolpaths, projections, control_points, deviations, params, additional_radial_offset=op_clearance)
                    elif op.get("straight_line_mode", False):
                        total_off = r_tool + blank_thick + op_clearance
                        r_s = mandrel_mgr.get_radius_fast(start_h) + shell_offset
                        nx_s, nz_s = mandrel_mgr.get_normal_at_z(start_h)
                        p_s = np.array([center_x + r_s + nx_s * total_off, 0.0, start_h + nz_s * total_off])
                        r_e = mandrel_mgr.get_radius_fast(end_h) + shell_offset
                        nx_e, nz_e = mandrel_mgr.get_normal_at_z(end_h)
                        p_e = np.array([center_x + r_e + nx_e * total_off, 0.0, end_h + nz_e * total_off])
                        toolpaths.append(np.array([p_s, p_e]))
                        projections.append(np.array([[center_x + r_s, 0.0, start_h], [center_x + r_e, 0.0, end_h]]))
                        control_points.append(np.array([]))
                        deviations.append(np.array([0.0, 0.0]))
                    else:
                        self._create_sweeping_pass(start_h, end_h, mandrel_mgr, center_x, r_tool, blank_thick, op_clearance, shell_offset, pass_label, toolpaths, projections, control_points, deviations, safety_clearance=0.0)
                else:
                    # effective_p1_z extends the approach arm so its START stays at target_z - p1_z
                    # while its END reaches contact_z = target_z + p2_z_extend.
                    effective_p1_z = p1_z + p2_z_extend
                    self._create_and_store_pass(p1_x, effective_p1_z, p3_z, p3_x, gp_Pnt(p2_x, 0, p2_z), base_rot, auto_align, toolpaths, projections, control_points, deviations, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_label, params, debug_lines, op=op)
                
                # Check newly added path for Rapids
                if len(toolpaths) > prev_paths_len:
                    new_path = toolpaths[-1]
                    if len(new_path) > 0:

                        # ── Reverse direction: traverse this pass in the inverse
                        # direction (e.g. top→root). Geometry is identical — only the
                        # point order flips, so G-code/SCL emission, the rapid
                        # approach/retract ends, and simulation all run inverted. This
                        # is cut-direction-only: the pass-to-pass progression order
                        # (set by the outer `for i in range(count)` loop) is untouched.
                        # The straight-arm/exit-curve split index no longer maps after
                        # reversal, so drop it and let rendering/PLC fall back to corner
                        # detection (geometrically identical for a reversed point set).
                        if op.get("direction", "forward") == "reverse":
                            _rev_idx = len(toolpaths) - 1
                            new_path = np.array(new_path, dtype=float)[::-1]
                            toolpaths[-1] = new_path
                            if len(projections[-1]) > 0:
                                projections[-1] = np.array(projections[-1])[::-1]
                            if len(deviations[-1]) > 0:
                                deviations[-1] = np.array(deviations[-1])[::-1]
                            self.last_render_split_idx.pop(_rev_idx, None)

                        # ── Compute back pass path first (needed before sequence so swap can be applied) ──
                        _bp_path = None
                        _bp_feed = None
                        _bp_proj = None
                        _bp_devs = None
                        if op.get("back_pass_enabled", False):
                            _bp_feed = float(op.get("back_pass_feed", float(op.get("feed", 100.0))))
                            bp_arc_x    = float(op.get("back_pass_arc_x", 0.0))
                            bp_arc_z    = float(op.get("back_pass_arc_z", 0.0))
                            _fwd_idx    = len(toolpaths) - 1
                            _fwd_splits = self.last_render_split_idx.get(_fwd_idx)

                            if _fwd_splits is not None:
                                # True mirror: reuse the forward FORMING portion verbatim,
                                # reversed. new_path[_line_end:] is T1 → (P2 fillet) → exit
                                # → P3, so the back pass follows p2_radius and the exit
                                # curve exactly — bp_arc=0 gives a bit-exact reverse of the
                                # forward forming stroke. The straight approach arm
                                # (new_path[:_line_end], parallel to the mandrel axis) is
                                # intentionally excluded: it is pure positioning, an ironing
                                # back-stroke should not retrace it, and on tapered mandrels
                                # its lower end forced the whole pass outward.
                                _line_end, _ = _fwd_splits
                                forming_part = np.array(new_path[_line_end:], dtype=float)
                                _bp_path = forming_part[::-1].copy()

                                # bp_arc_x/z: smooth parabolic bow of the curve, zero at the
                                # P3 and T1 endpoints (so continuity with the approach/retract
                                # and the fillet tangency are preserved), peaking at mid-span.
                                if (abs(bp_arc_x) > 1e-9 or abs(bp_arc_z) > 1e-9) and len(_bp_path) >= 3:
                                    _tt = np.linspace(0.0, 1.0, len(_bp_path))
                                    _w  = 4.0 * _tt * (1.0 - _tt)
                                    _bp_path = _bp_path + np.outer(_w, np.array([bp_arc_x, 0.0, bp_arc_z]))

                                # Clearance correction via the same uniform-radial-shift
                                # principle the forward spline pass uses (segment-aware, no
                                # Z-range blind spot), so the back pass obeys the exact same
                                # clearance guarantee even after a bp_arc bow.
                                _bp_target_clearance = op_clearance
                                _bp_path = self._correct_clearance_uniform(
                                    _bp_path, mandrel_mgr, center_x, r_tool, blank_thick,
                                    shell_offset, _bp_target_clearance)
                            else:
                                # Shapes with no tracked straight-line boundary (e.g.
                                # "spline"): mirror the forward path as a whole.
                                _bp_path = np.array(new_path)[::-1]

                                if (abs(bp_arc_x) > 1e-9 or abs(bp_arc_z) > 1e-9) and len(_bp_path) >= 3:
                                    _tt = np.linspace(0.0, 1.0, len(_bp_path))
                                    _w  = 4.0 * _tt * (1.0 - _tt)
                                    _bp_path = _bp_path + np.outer(_w, np.array([bp_arc_x, 0.0, bp_arc_z]))

                                _bp_target_clearance = op_clearance
                                _bp_path = self._correct_clearance_uniform(
                                    _bp_path, mandrel_mgr, center_x, r_tool, blank_thick,
                                    shell_offset, _bp_target_clearance)

                            _bp_proj, _bp_devs = self._compute_proj_and_devs(
                                _bp_path, mandrel_mgr, center_x,
                                shell_offset, blank_thick, r_tool, op)

                        # ── Swap: old back pass becomes new forward, old forward becomes new back ──
                        # When swapped, the back pass arc (P3→P2) is reversed to run P2→P3 as the
                        # first stroke; the original forward path is reversed (P3→P1) as the second.
                        _swapped = op.get("back_pass_swapped", False) and _bp_path is not None
                        if _swapped:
                            fwd_path = _bp_path[::-1]
                            bck_path = np.array(new_path)[::-1]
                            bck_feed = _bp_feed
                            fwd_proj = np.array(projections[-1]) if len(projections[-1]) > 0 else np.array([])
                            fwd_devs = np.array(deviations[-1]) if len(deviations[-1]) > 0 else np.array([])
                            bck_proj = _bp_proj if len(_bp_proj) > 0 else np.array([])
                            bck_devs = _bp_devs if len(_bp_devs) > 0 else np.array([])
                            toolpaths[-1]   = fwd_path
                            projections[-1] = fwd_proj
                            deviations[-1]  = fwd_devs
                        else:
                            fwd_path = new_path
                            bck_path = _bp_path
                            bck_feed = _bp_feed
                            bck_proj = _bp_proj
                            bck_devs = _bp_devs

                        start_pt = fwd_path[0]
                        end_pt   = fwd_path[-1]

                        # 1. Rapid to Start — X is already retracted; use retract X as clearance, not full home X
                        for seg in self._safe_rapid_segments(current_pt, start_pt, current_pt[0]):
                            rapids.append(seg)
                            sequence.append(("rapid", seg))

                        # Cut Path
                        sequence.append(("cut", fwd_path, r_tool, op_tool_id))
                        current_pt = end_pt

                        # Back pass (or swapped back pass)
                        if bck_path is not None:
                            # No retract between forward and back pass — the forward ends
                            # at P3 and the (mirror) back pass starts at the same P3, so the
                            # roller flows straight into the return stroke. Only bridge with
                            # a safe move if a bp_arc bow / clearance shift moved the back
                            # pass start away from the forward end.
                            self.last_back_pass_meta[len(toolpaths)] = {"feed": bck_feed}
                            toolpaths.append(bck_path)
                            projections.append(bck_proj)
                            control_points.append(np.array([]))
                            deviations.append(bck_devs)
                            bp_s = bck_path[0]
                            bp_e = bck_path[-1]
                            if np.linalg.norm(current_pt - bp_s) > 1e-3:
                                for seg in self._safe_rapid_segments(current_pt, bp_s, current_pt[0]):
                                    rapids.append(seg)
                                    sequence.append(("rapid", seg))
                            sequence.append(("cut", bck_path, r_tool, op_tool_id))
                            bp_ret = np.array([bp_e[0] + retract_x_can, 0, bp_e[2] + retract_z_offset])
                            rapids.append(np.array([bp_e, bp_ret]))
                            sequence.append(("rapid", np.array([bp_e, bp_ret])))
                            current_pt = bp_ret
                        else:
                            # No back pass: retract after the forward pass as usual.
                            retract_pt = np.array([end_pt[0] + retract_x_can, 0, end_pt[2] + retract_z_offset])
                            r_seg2 = np.array([end_pt, retract_pt])
                            rapids.append(r_seg2)
                            sequence.append(("rapid", r_seg2))
                            current_pt = retract_pt

                # Keep the path→op map in sync with everything appended during
                # this pass (forward + optional back pass), whatever the branch.
                while len(self._path_op_map) < len(toolpaths):
                    self._path_op_map.append(op)
                global_pass_idx += 1

        # [NEW] Final Return to Home
        # User requested roller to return to Safety Home Position at end.
        home_pt = np.array([home_x_can, 0, home_z])

        if np.linalg.norm(current_pt - home_pt) > 1.0:
            for seg in self._safe_rapid_segments(current_pt, home_pt, home_x_can):
                rapids.append(seg)
                sequence.append(("rapid", seg))
        
        # Mirror all X coordinates if roller is on negative X side
        if side == -1.0:
            def _mirror_pts(arr):
                """Mirror numpy array (N,3) in X around center_x."""
                a = np.array(arr, dtype=float)
                a[:, 0] = 2.0 * center_x - a[:, 0]
                return a

            toolpaths = [_mirror_pts(p) for p in toolpaths]
            projections = [_mirror_pts(p) for p in projections]

            mirrored_cp = []
            for cp in control_points:
                mc = np.array(cp, dtype=float)
                if mc.ndim == 2:
                    mc[:, 0] = 2.0 * center_x - mc[:, 0]
                mirrored_cp.append(mc)
            control_points = mirrored_cp

            mirrored_rapids = []
            for seg in rapids:
                s = np.array(seg, dtype=float)
                s[:, 0] = 2.0 * center_x - s[:, 0]
                mirrored_rapids.append(s)
            rapids = mirrored_rapids

            mirrored_debug = []
            for seg in debug_lines:
                # format: [p_pass, p_mandrel, status, clearance_value]
                p0 = np.array(seg[0], dtype=float); p0[0] = 2.0 * center_x - p0[0]
                p1 = np.array(seg[1], dtype=float); p1[0] = 2.0 * center_x - p1[0]
                mirrored_debug.append([p0, p1] + list(seg[2:]))
            debug_lines = mirrored_debug

            mirrored_seq = []
            for item in sequence:
                kind = item[0]
                if kind == "rapid":
                    s = np.array(item[1], dtype=float)
                    s[:, 0] = 2.0 * center_x - s[:, 0]
                    mirrored_seq.append(("rapid", s))
                elif kind == "cut":
                    mirrored_seq.append(("cut", _mirror_pts(item[1]), item[2]) + item[3:])
                else:
                    mirrored_seq.append(item)
            sequence = mirrored_seq

        # ── Per-point tilt angles (tilt-arm machines only, e.g. ID112) ──────
        # Built AFTER mirroring: tilt derives from each point's Z in both modes
        # (mirror-invariant, direction-invariant — back passes need no special
        # handling, the same Z always yields the same angle).
        kin = get_kinematics(params)
        if kin is not None:
            self.last_tilt_angles = [
                self._compute_tilt_for_path(
                    np.array(pth, dtype=float),
                    self._path_op_map[idx] if idx < len(self._path_op_map) else None,
                    mandrel_mgr, kin,
                )
                for idx, pth in enumerate(toolpaths)
            ]
        else:
            self.last_tilt_angles = None

        if self.last_clamp_warnings:
            _w = self.last_clamp_warnings[0]
            logger.warning(
                f"[CLAMP] {len(self.last_clamp_warnings)} op(s) start inside the clamp zone "
                f"(top Z={_w['clamp_top_z']:.1f}); first: op #{_w['op_index'] + 1} "
                f"'{_w['op_type']}' start_z={_w['start_z']:.1f}")

        self.last_calculated_paths = toolpaths
        self.last_calculated_sequence = sequence
        self.last_mandrel_mgr = mandrel_mgr
        return toolpaths, projections, control_points, deviations, rapids, debug_lines

    def _compute_tilt_for_path(self, pts, op, mandrel_mgr, kin):
        """CANONICAL tilt source — per-point tilt (deg) for any point array.

        Works on the full stored path AND on a PLC-decimated subset, so the 3D
        view, the simulation and the emitted G-code always agree:
          - "normal" mode derives tilt from the surface normal at each point's
            Z (clamped into the mandrel range, same principle as
            _correct_clearance_uniform) plus the op's lead/lag tilt_offset;
          - "interp" mode ties the angle to SURFACE POSITION: tilt_start at
            the op's start_z, tilt_end at its end_z, linear in the point's Z
            in between (clamped to the zone). The angle is a property of where
            on the surface the roller is, not of pass progress — so every pass
            of a multi-pass op, and back passes running in reverse, all agree.
        All values are clamped to the machine's B travel via kin.clamp_tilt.
        """
        pts = np.asarray(pts, dtype=float)
        n = len(pts)
        if n == 0:
            return np.zeros(0)
        op = op or {}
        mode = op.get("tilt_mode", "normal")

        if mode == "interp":
            t0 = float(op.get("tilt_start", 0.0))
            t1 = float(op.get("tilt_end", 0.0))
            z0 = float(op.get("start_z", mandrel_mgr.props.get("min_z", 0.0)))
            z1 = float(op.get("end_z",   mandrel_mgr.props.get("top_z", 0.0)))
            span = z1 - z0
            if abs(span) < 1e-9:
                raw = np.full(n, t0)
            else:
                frac = np.clip((pts[:, 2] - z0) / span, 0.0, 1.0)
                raw = t0 + frac * (t1 - t0)
        else:  # "normal"
            off = float(op.get("tilt_offset", 0.0))
            m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
            m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
            raw = np.empty(n)
            for i in range(n):
                zc = min(max(pts[i][2], m_min_z), m_top_z)
                nx, nz = mandrel_mgr.get_normal_at_z(zc)
                # Canonical outward normal (positive-X frame): a cylinder wall
                # (nx=1, nz=0) gives tilt 0 = radial, exactly like machine #1.
                raw[i] = math.degrees(math.atan2(nz, nx)) + off

        return np.array([kin.clamp_tilt(v) for v in raw])

    def _create_adaptive_pass(self, start_z, end_z, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_name, t_list, p_list, c_list, d_list, params, additional_radial_offset=0.0):
        """
        Generates a dense G-Code path by offsetting the Mandrel Profile at fine intervals.
        Designed for complex geometries with sharp radius changes.
        """
        resolution = float(params.get("finish_trace_resolution", 0.5))
        if resolution < 0.1: resolution = 0.1
        
        # Determine Z range and steps
        z_min = min(start_z, end_z)
        z_max = max(start_z, end_z)
        steps = int((z_max - z_min) / resolution) + 2
        
        # Decide direction
        forward = (start_z < end_z)
        z_vals = np.linspace(start_z, end_z, steps) if forward else np.linspace(start_z, end_z, steps)
        
        path_points = []
        cached_radii = []

        # Safety Offset Calculation
        total_offset = r_tool + blank_thick + additional_radial_offset

        bow_height = float(params.get("adaptive_bow_height", 0.0))

        z_min = np.min(z_vals)
        z_max = np.max(z_vals)
        z_len = z_max - z_min
        if z_len < 0.001: z_len = 1.0

        for z in z_vals:
            m_rad = mandrel_mgr.get_radius_fast(z)
            cached_radii.append(m_rad)
            nx, nz = mandrel_mgr.get_normal_at_z(z)

            t = (z - z_min) / z_len
            parabolic_offset = bow_height * 4 * t * (1.0 - t)

            r_contact = m_rad + shell_offset + parabolic_offset

            p_roller_x = (center_x + r_contact) + (nx * total_offset)
            p_roller_z = z + (nz * total_offset)

            path_points.append([p_roller_x, 0, p_roller_z])

        # Store Result
        pts_arr = np.array(path_points)
        t_list.append(pts_arr)
        
        # Consistent Visualization Data
        # Projections: Trace contacting surface (r_contact)
        proj_pts = []
        for z, m_rad in zip(z_vals, cached_radii):
            px = center_x + m_rad + shell_offset + blank_thick
            proj_pts.append([px, 0, z])
            
        p_list.append(np.array(proj_pts))        
        c_list.append(np.array([])) # Control Pts (None)
        
        # Deviations must match point count for scalars
        if len(pts_arr) > 0:
            # Use surface_z (not roller Z) for mandrel radius lookup.
            # On curved surfaces (sphere, etc.) the roller is pushed in Z by the normal component,
            # so pt[2] (roller Z) differs from the surface contact Z — using it gives wrong clearance.
            devs = []
            for pt, m_r in zip(pts_arr, cached_radii):
                dist = math.sqrt((pt[0]-center_x)**2 + pt[1]**2)
                limit = m_r + blank_thick + shell_offset + r_tool
                devs.append(dist - limit)
            d_list.append(np.array(devs))
        else:
            d_list.append(np.array([]))
            logger.warning(f"Adaptive Pass '{pass_name}' generated 0 points! Range: {start_z:.2f} to {end_z:.2f}")

        logger.info(f"Generated Adaptive Pass '{pass_name}': {len(pts_arr)} points.") 

    def _arc_fillet_at_p2(self, p2_arr, d1, d2, radius, leg1, leg2, check_res):
        """True tangent-circle fillet at vertex p2_arr between two rays d1, d2
        (unit vectors pointing away from the vertex along each leg).

        Returns (T1, T2, arc_pts): T1/T2 are the tangent points on leg1/leg2
        where the arc begins/ends, arc_pts is the polyline from T1 to T2
        (inclusive) approximating the arc. If radius <= 0 or the legs are
        (nearly) collinear (no real corner), T1 == T2 == p2_arr and arc_pts
        is empty — callers should treat that as "no fillet".
        """
        d1 = d1 / max(np.linalg.norm(d1), 1e-9)
        d2 = d2 / max(np.linalg.norm(d2), 1e-9)
        cos_a = float(np.clip(np.dot(d1, d2), -1.0, 1.0))
        angle = math.acos(cos_a)
        if radius <= 0.01 or angle < 1e-3 or angle > math.pi - 1e-3:
            return p2_arr.copy(), p2_arr.copy(), np.empty((0, 3))

        tangent_len = radius / math.tan(angle / 2.0)
        max_len = max(0.0, min(leg1, leg2) * 0.9)
        tangent_len = min(tangent_len, max_len)
        eff_radius = tangent_len * math.tan(angle / 2.0)
        if tangent_len < 1e-6 or eff_radius < 0.01:
            return p2_arr.copy(), p2_arr.copy(), np.empty((0, 3))

        T1 = p2_arr + tangent_len * d1
        T2 = p2_arr + tangent_len * d2
        b = d1 + d2
        b_norm = np.linalg.norm(b)
        if b_norm < 1e-9:
            return p2_arr.copy(), p2_arr.copy(), np.empty((0, 3))
        b = b / b_norm
        center_dist = eff_radius / math.sin(angle / 2.0)
        O = p2_arr + center_dist * b

        u1 = (T1 - O) / eff_radius
        u2 = (T2 - O) / eff_radius
        th1 = math.atan2(u1[2], u1[0])
        th2 = math.atan2(u2[2], u2[0])
        sweep = th2 - th1
        if sweep > math.pi:
            sweep -= 2 * math.pi
        elif sweep < -math.pi:
            sweep += 2 * math.pi

        n_arc = max(4, int(eff_radius * abs(sweep) / check_res))
        t_vals = np.linspace(0.0, 1.0, n_arc)
        thetas = th1 + t_vals * sweep
        arc_pts = np.stack([
            O[0] + eff_radius * np.cos(thetas),
            np.zeros_like(thetas),
            O[2] + eff_radius * np.sin(thetas)
        ], axis=1)
        return T1, T2, arc_pts

    def _enforce_min_clearance(self, points, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, target_clearance):
        """Per-point safety net: pushes any point that violates the minimum
        roller/mandrel clearance outward along the local surface normal, just
        enough to satisfy target_clearance. Points already clear, and points
        outside the mandrel's Z range, are returned unchanged.
        """
        m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
        m_top_z = mandrel_mgr.props.get("top_z", float('inf'))
        corrected = []
        for pt in points:
            sim_x, sim_y, sim_z = pt
            if sim_z < m_min_z or sim_z > m_top_z:
                corrected.append([sim_x, sim_y, sim_z])
                continue
            m_rad = max(0.0, mandrel_mgr.get_radius_fast(sim_z))
            dist = math.sqrt((sim_x - center_x) ** 2 + sim_y ** 2)
            required = m_rad + blank_thick + shell_offset + r_tool + target_clearance
            if dist < required:
                deficit = required - dist
                pnx, pnz = mandrel_mgr.get_normal_at_z(sim_z)
                corrected.append([sim_x + deficit * pnx, sim_y, sim_z + deficit * pnz])
            else:
                corrected.append([sim_x, sim_y, sim_z])
        return np.array(corrected)

    def _correct_clearance_uniform(self, points, mandrel_mgr, center_x, r_tool,
                                   blank_thick, shell_offset, target_clearance,
                                   max_iter=8):
        """Enforces target_clearance over an entire pre-built polyline (e.g. a
        back pass) using the SAME uniform-radial-shift principle that the
        forward spline pass uses in _create_and_store_pass: find the worst
        clearance over the whole stroke, then translate every point rigidly
        outward by that deficit. The bow/shape produced by back_pass_arc_x/z
        is preserved exactly — only its radial position is corrected — just as
        the forward correction preserves the spline shape and only shifts it.

        Two things this fixes versus the old per-point _clamp_radial_clearance:

        1. No Z-range blind spot. The old clamp (and the forward min-clearance
           scan) SKIP every point whose Z is outside [min_z, top_z]. A back
           pass arc routinely extends past the mandrel top (P3 = contact_z +
           p3_z_offset, and on high passes contact_z is already near top_z), so
           those points were never checked — with an inward back_pass_arc_x or
           a flaring/convex profile they dived straight into the mandrel near
           the top edge while the safety net did nothing. Here the radius
           lookup Z is CLAMPED into the mandrel range instead of skipped, so
           the region just past an edge is treated as the edge radius and can
           never be dived into.

        2. Segment-aware. Clearance is sampled along each segment, not just at
           the stored vertices, so a straight G1 chord between two safe points
           can't cut through a convex surface unnoticed.

        Only outward corrections are applied (deficit > 0); an already-clear
        path is never pulled inward, so a deliberate outward bow is kept.
        """
        pts = np.array(points, dtype=float)
        if len(pts) < 2:
            return pts

        m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
        m_top_z = mandrel_mgr.props.get("top_z", float('inf'))

        # Outward direction along X. Canonical generation keeps every path point
        # on one side of the spindle axis, so a single sign is correct.
        side = 1.0 if (float(np.mean(pts[:, 0])) - center_x) >= 0 else -1.0

        check_res = 0.5
        for _ in range(max_iter):
            min_clear = float('inf')
            for a, b in zip(pts[:-1], pts[1:]):
                seg_len = float(np.linalg.norm(b - a))
                n = max(2, int(seg_len / check_res) + 1)
                for t in np.linspace(0.0, 1.0, n):
                    sx, sy, sz = a + t * (b - a)
                    zc = min(max(sz, m_min_z), m_top_z)          # clamp, don't skip
                    m_rad = max(0.0, mandrel_mgr.get_radius_fast(zc))
                    dist = math.sqrt((sx - center_x) ** 2 + sy ** 2)
                    clear = dist - (m_rad + blank_thick + shell_offset + r_tool)
                    if clear < min_clear:
                        min_clear = clear

            if min_clear == float('inf'):
                break                                            # nothing to check
            diff = target_clearance - min_clear
            if diff <= 0.01:
                break                                            # safe (never pull in)
            pts[:, 0] += side * diff
        return pts

    def _create_and_store_pass(self, p1_x_offset, p1_z_offset, p3_z_offset, p3_x_offset, initial_p2, base_rot, auto_align, t_list, p_list, c_list, d_list, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_name, params, debug_lines=None, op=None):
            # --- Smart Spline Optimization V6 (Morphing) ---
            # Instead of rigid shifting, independently adjust control points based on where collision occurs.
            
            # 1. Initialize Absolute Control Points
            p2 = initial_p2
            # P1/P3 start based on P2, preserving offset relationship initially
            calc_p1_z = p2.Z() - abs(p1_z_offset)
            p1 = gp_Pnt(p2.X() + abs(p1_x_offset), 0, calc_p1_z)
            
            calc_p3_z = p2.Z() + p3_z_offset
            p3 = gp_Pnt(p2.X() + p3_x_offset, 0, calc_p3_z)
            _dbg_init_p2x = p2.X()
            logger.info(
                f"[PARAM_DEBUG] '{pass_name}' control pts: "
                f"P1=({p1.X():.2f}, Z={p1.Z():.2f})  "
                f"P2=({p2.X():.2f}, Z={p2.Z():.2f})  "
                f"P3=({p3.X():.2f}, Z={p3.Z():.2f})"
            )

            final_points = []
            _ap_split    = None  # index where exit portion starts in pts_raw (linear_approach/linear_full only)
            _fillet_len  = 0     # number of P2 arc-fillet points in pts_raw (0 = sharp corner)

            # Gouge Check Parameters
            max_iterations = 20

            # Resolution for Checking
            check_res = max(0.05, float(params.get("collision_resolution", 0.5)))
            
            for attempt in range(max_iterations):
                # 2. Generate Spline (High Rez based on Check Res)
                # Estimate length for step count
                approx_len = p1.Distance(p2) + p2.Distance(p3)
                num_points = int(max(10, approx_len / check_res))
                
                pass_shape = (op or {}).get("pass_shape", "spline")

                if pass_shape in ("linear_approach", "linear_full"):
                    # Approach: straight line of length p1_z from P2 back toward the start.
                    # P1X is ignored entirely — only P1Z controls approach length.
                    p1_z_off  = max(abs(p1_z_offset), 0.1)
                    p2_arr    = np.array([p2.X(), 0.0, p2.Z()])

                    # Approach direction (from P2 toward the approach start).
                    #   • default: pure -Z (vertical, parallel to the spindle axis).
                    #   • approach_follow_surface: along the mandrel surface tangent at P2,
                    #     so the arm runs parallel to an angled surface — constant clearance
                    #     along the whole arm instead of only at P2 (no over-clearing of P2
                    #     on tapered walls). Reduces exactly to -Z on a vertical surface.
                    if (op or {}).get("approach_follow_surface", False):
                        _anx, _anz = mandrel_mgr.get_normal_at_z(p2.Z())
                        _appr = np.array([_anz, 0.0, -_anx])      # tangent ⟂ surface normal
                        _aln  = np.linalg.norm(_appr)
                        _appr = _appr / _aln if _aln > 1e-9 else np.array([0.0, 0.0, -1.0])
                        if _appr[2] > 0.0:                        # head toward lower Z (base side)
                            _appr = -_appr
                    else:
                        _appr = np.array([0.0, 0.0, -1.0])

                    ap_start  = p2_arr + p1_z_off * _appr
                    p3_arr    = np.array([p3.X(), 0.0, p3.Z()])
                    p2p3_len  = max(np.linalg.norm(p3_arr - p2_arr), 0.1)

                    # True tangent-circle fillet at P2 (radius in mm). d1 points back
                    # along the approach (so the fillet stays tangent to the arm even when
                    # it is tilted to the surface), d2 points toward P3.
                    d1 = _appr
                    d2 = (p3_arr - p2_arr) / p2p3_len
                    p2_radius = float((op or {}).get("p2_radius", 0.0))
                    T1, T2, arc_pts = self._arc_fillet_at_p2(p2_arr, d1, d2, p2_radius, p1_z_off, p2p3_len, check_res)
                    _fillet_len = len(arc_pts)

                    if pass_shape == "linear_full":
                        n_ex         = max(2, int(np.linalg.norm(p3_arr - T2) / check_res))
                        exit_portion = np.linspace(T2, p3_arr, n_ex)
                    else:
                        # Exit curve: circular arc T2 → P3.
                        # exit_arc_angle (°): tangent-chord angle at T2.
                        # Positive = bow outward (away from spin axis, larger X).
                        # Negative = bow inward. 0 = straight line (default).
                        # R = chord / (2*sin(angle)), center offset = R*cos(angle)
                        # on the side opposite the bow direction.
                        exit_len     = max(np.linalg.norm(p3_arr - T2), 0.1)
                        _arc_ang_deg = float(params.get("exit_arc_angle", 0.0))
                        _arc_ang_rad = math.radians(abs(_arc_ang_deg))
                        chord_dir    = (p3_arr - T2) / exit_len
                        perp_xz      = np.array([-chord_dir[2], 0.0, chord_dir[0]])
                        if perp_xz[0] < 0:
                            perp_xz = -perp_xz
                        if _arc_ang_rad < 1e-4:
                            exit_portion = np.linspace(T2, p3_arr,
                                                       max(10, int(exit_len / check_res)))
                        else:
                            _sign    = 1.0 if _arc_ang_deg > 0 else -1.0
                            _R       = exit_len / (2.0 * math.sin(_arc_ang_rad))
                            _arc_len = _R * 2.0 * _arc_ang_rad
                            _center  = (0.5 * (T2 + p3_arr)
                                        - _sign * _R * math.cos(_arc_ang_rad) * perp_xz)
                            _u1      = (T2 - _center) / _R
                            _th1     = math.atan2(_u1[2], _u1[0])
                            _sweep   = _sign * 2.0 * _arc_ang_rad
                            _n       = max(10, int(_arc_len / check_res))
                            _t_vals  = np.linspace(0.0, 1.0, _n)
                            _thetas  = _th1 + _t_vals * _sweep
                            exit_portion = np.stack([
                                _center[0] + _R * np.cos(_thetas),
                                np.zeros(_n),
                                _center[2] + _R * np.sin(_thetas)
                            ], axis=1)

                        # Mid-point rotation: pick M at exit_mid_t along the exit and rotate
                        # everything after it about M by exit_mid_rotation degrees (Y-axis,
                        # XZ plane). Whatever the exit shape currently is, this just swings
                        # the M→P3 tail to a new orientation around M — T2→M is untouched.
                        # P3 moves with the tail. Clearance correction (below) still applies.
                        _emid_rot = float((op or {}).get("exit_mid_rotation", 0.0))
                        if abs(_emid_rot) > 0.01 and len(exit_portion) >= 3:
                            _emid_t = min(max(float((op or {}).get("exit_mid_t", 0.5)), 0.05), 0.95)
                            _k = int(round(_emid_t * (len(exit_portion) - 1)))
                            _k = min(max(_k, 1), len(exit_portion) - 2)
                            _Mp = gp_Pnt(float(exit_portion[_k][0]), 0.0, float(exit_portion[_k][2]))
                            _tail = self._apply_rotation(exit_portion[_k + 1:], _emid_rot, _Mp)
                            exit_portion = np.vstack([exit_portion[:_k + 1], _tail])

                    n_ap      = max(2, int(np.linalg.norm(T1 - ap_start) / check_res))
                    approach  = np.linspace(ap_start, T1, n_ap)
                    _ap_split = n_ap - 1   # ap_start → T1 reduces to 2 pts; fillet+exit stays dense
                    if _fillet_len > 0:
                        pts_raw = np.vstack([approach[:-1], arc_pts, exit_portion[1:]])
                    else:
                        pts_raw = np.vstack([approach[:-1], exit_portion])

                    if len(pts_raw) == 0: break

                else:  # "spline" — original behaviour
                    pts_raw = self._generate_spline(p1, p2, p3, num_points)
                    if len(pts_raw) == 0: break

                # 3. Apply Rotation (Aligned to P2 surface normal)
                nx, nz = mandrel_mgr.get_normal_at_z(p2.Z())
                if pass_shape in ("linear_approach", "linear_full"):
                    # Rotation about P2 would tilt the pure-Z approach arm and shift P3
                    # off its computed position — both guarantees this shape exists for.
                    # Direction is already controlled explicitly via pass_angle/progressive.
                    final_rot = 0.0
                else:
                    final_rot = base_rot
                if auto_align and pass_shape not in ("linear_approach", "linear_full"):
                    surface_angle = math.degrees(math.atan2(nz, nx))
                    raw_rot = -surface_angle + base_rot
                    # Clamp 2: geometric constraint — P3 must stay above P2 in Z after rotation.
                    # After Y-axis rotation θ: P3.z_rel = -p1_x*sin(θ) + p3_z*cos(θ).
                    # P3 stays above P2 only when θ < atan2(p3_z, p1_x).
                    # Without this, large positive rotation flips P3 below P2 → arc inverts → straight-line appearance.
                    _px = abs(p1_x_offset); _p3z = abs(p3_z_offset); _p1z = abs(p1_z_offset)
                    _geo_max =  float('inf')
                    _geo_min = float('-inf')
                    if _px > 0.001 and _p3z > 0.001:
                        geo_max_rot = math.degrees(math.atan2(_p3z, _px)) * 0.9
                        raw_rot = min(raw_rot, geo_max_rot)
                        _geo_max = geo_max_rot
                    if _px > 0.001 and _p1z > 0.001:
                        geo_max_neg_rot = math.degrees(math.atan2(_p1z, _px)) * 0.9
                        raw_rot = max(raw_rot, -geo_max_neg_rot)
                        _geo_min = -geo_max_neg_rot
                    final_rot = raw_rot
                    if attempt == 0:
                        _clamp_note = ""
                        if abs(final_rot - (-surface_angle + base_rot)) > 0.1:
                            _clamp_note = f" ← CLAMPED (geo window [{_geo_min:.1f}°, {_geo_max:.1f}°])"
                        logger.info(
                            f"[PARAM_DEBUG] '{pass_name}' rotation: auto_align ON | "
                            f"surface_angle={surface_angle:.1f}° base_rot={base_rot:.1f}° | "
                            f"raw={-surface_angle + base_rot:.1f}° → final={final_rot:.1f}°{_clamp_note}"
                        )
                elif attempt == 0:
                    if pass_shape in ("linear_approach", "linear_full"):
                        logger.info(f"[PARAM_DEBUG] '{pass_name}' rotation: locked to 0° (linear shape — use pass_angle to control direction)")
                    else:
                        logger.info(f"[PARAM_DEBUG] '{pass_name}' rotation: auto_align OFF, using base_rot={final_rot:.1f}° | TIP: enable Auto-Calc Angle to align pass to mandrel surface")

                check_pts = pts_raw
                if abs(final_rot) > 0.01:
                    check_pts = self._apply_rotation(pts_raw, final_rot, p2)
                
                # 4. Clearance check & correction
                # Safety FLOOR (renamed from the old two-way `target_clearance` setter):
                # the minimum allowed roller-to-blank gap. Applied ONE-WAY below — it can
                # only push a pass OUT, never pull it in (pulling in is what overrode the
                # op's clearance and made roughing sit closer than finishing).
                target_clearance = float(params.get("min_safety_gap", params.get("target_clearance", 0.0)))

                # Mandrel Z sınırları — sınır dışındaki noktalarda clearance hesabı yapma
                _m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
                _m_top_z = mandrel_mgr.props.get("top_z", float('inf'))

                if params.get("clearance_correction_per_point", False):
                    # PER-POINT NORMAL CORRECTION
                    # Each point is independently pushed out along its local surface normal
                    # if it violates the minimum clearance. Spline shape is preserved everywhere else.
                    check_pts = self._enforce_min_clearance(
                        check_pts, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, target_clearance)
                    # No further iterations needed — fall through to debug_lines + break

                else:
                    # UNIFORM SHIFT: find minimum clearance, shift all control points in X, iterate
                    min_clearance = float('inf')
                    for pt in check_pts:
                        sim_x, sim_y, sim_z = pt
                        if sim_z < _m_min_z or sim_z > _m_top_z:  # mandrel dışı: atla
                            continue
                        m_rad = max(0.0, mandrel_mgr.get_radius_fast(sim_z))
                        dist_to_axis = math.sqrt((sim_x - center_x)**2 + sim_y**2)
                        clearance = dist_to_axis - (m_rad + blank_thick + shell_offset + r_tool)
                        if clearance < min_clearance:
                            min_clearance = clearance

                    if min_clearance == float('inf'):
                        break  # tüm noktalar mandrel dışında, çarpışma yok

                    # ONE-WAY floor: only act when the closest point is nearer than the
                    # floor; push it back out. Never pull a too-far pass in (that would
                    # override the op's `clearance`).
                    if min_clearance < target_clearance - 0.01:
                        diff = target_clearance - min_clearance   # > 0 → outward only
                        _p2x_before = p2.X()
                        p1 = gp_Pnt(p1.X() + diff, 0, p1.Z())
                        p2 = gp_Pnt(p2.X() + diff, 0, p2.Z())
                        p3 = gp_Pnt(p3.X() + diff, 0, p3.Z())
                        logger.info(
                            f"[PARAM_DEBUG] '{pass_name}' safety-floor iter {attempt+1}: "
                            f"min_clearance={min_clearance:.3f}mm (floor={target_clearance:.3f}mm) → "
                            f"pushing out +{diff:.3f}mm in X | P2: {_p2x_before:.2f} → {p2.X():.2f}"
                        )
                        continue
                
                # If we reach here, check passed or max iterations reached.
                # Generate Final Analysis Line - ONLY the MINIMUM clearance point
                if debug_lines is not None and len(check_pts) > 0:
                    min_cl = float('inf')
                    min_line = None
                    min_status = 0
                    
                    for pt in check_pts:
                         sim_x, sim_y, sim_z = pt

                         m_rad = max(0.0, mandrel_mgr.get_radius_fast(sim_z))
                         required_dist = m_rad + blank_thick + shell_offset + r_tool
                         dist = math.sqrt((sim_x - center_x)**2 + sim_y**2)
                         clearance = dist - required_dist
                         
                         if clearance < min_cl:
                             min_cl = clearance
                             p_pass = [sim_x, sim_y, sim_z]
                             p_mandrel = [center_x + m_rad, 0, sim_z]
                             min_line = [p_pass, p_mandrel]
                             
                             # Color based on clearance
                             if clearance < 0:
                                 min_status = 2 # Collision (Red)
                             elif clearance < target_clearance:
                                 min_status = 1 # Warning (Yellow)
                             else:
                                 min_status = 0 # Safe (Green)
                    
                    if min_line:
                        # Store: [p_pass, p_mandrel, status, clearance_value]
                        debug_lines.append([min_line[0], min_line[1], min_status, min_cl])
                
                # Use the ROTATED points for final output
                final_points = check_pts
                _total_shift = p2.X() - _dbg_init_p2x
                logger.info(
                    f"[PARAM_DEBUG] '{pass_name}' RESULT: {len(final_points)} pts | "
                    f"P2 X: {_dbg_init_p2x:.2f} → {p2.X():.2f} (clearance shift {_total_shift:+.2f}mm) | "
                    f"path start=({final_points[0][0]:.2f}, Z={final_points[0][2]:.2f}) "
                    f"end=({final_points[-1][0]:.2f}, Z={final_points[-1][2]:.2f}) | "
                    f"rotation applied={final_rot:.2f}°"
                )
                break

             
            if len(final_points) == 0:
                final_points = check_pts # Fallback

            # For linear_approach: straight approach arm needs only 2 points (start + P2).
            # Render-split bookkeeping: index of T1 (end of the straight approach
            # line) and T2 (end of the P2 fillet arc) within final_points, tracked
            # through the transforms below so the renderer never has to re-guess
            # the straight/arc/curve boundaries via heuristics.
            _line_end = _ap_split
            _arc_end  = (_ap_split + _fillet_len - 1) if (_ap_split is not None and _fillet_len > 0) else _ap_split

            # Reduce before gcode_resolution so the downsampler doesn't add redundant collinear pts.
            if _ap_split is not None and _ap_split > 1 and len(final_points) > _ap_split + 1:
                final_points = np.vstack([
                    final_points[[0, _ap_split]],
                    final_points[_ap_split + 1:]
                ])
                _arc_end  = max(1, _arc_end - _ap_split + 1)
                _line_end = 1

            # Downsample for G-code output (separate from collision_resolution).
            # T1/T2 are force-kept so the (line_end, arc_end) indices stay valid
            # in the final, possibly-downsampled array.
            gcode_res = float(params.get("gcode_resolution", 2.0))
            _force_idx = {i for i in (_line_end, _arc_end) if i is not None}
            _render_pos = {}
            if gcode_res > 0.01 and len(final_points) > 2:
                downsampled = [final_points[0]]
                for rel_idx, pt in enumerate(final_points[1:-1], start=1):
                    forced = rel_idx in _force_idx
                    if forced or np.linalg.norm(np.array(pt) - np.array(downsampled[-1])) >= gcode_res:
                        downsampled.append(pt)
                    if forced:
                        _render_pos[rel_idx] = len(downsampled) - 1
                downsampled.append(final_points[-1])
                final_points = downsampled
            else:
                for i in _force_idx:
                    if i < len(final_points):
                        _render_pos[i] = i

            _path_idx = len(t_list)
            t_list.append(np.array(final_points))

            if _line_end is not None and _line_end in _render_pos:
                self.last_render_split_idx[_path_idx] = (
                    _render_pos[_line_end],
                    _render_pos.get(_arc_end, _render_pos[_line_end]),
                )
            
            # Control Pts
            c_pts = np.array([ [p1.X(), 0, p1.Z()], [p2.X(), 0, p2.Z()], [p3.X(), 0, p3.Z()] ])
            c_list.append(c_pts)
            
            # Deviation / Heatmap Data
            devs = []
            for pt in final_points:
                m_r = mandrel_mgr.get_radius_fast(pt[2])
                dist = math.sqrt((pt[0]-center_x)**2 + pt[1]**2)
                limit = m_r + blank_thick + shell_offset + r_tool
                if m_r is not None: devs.append(dist - limit)
                else: devs.append(0.0)
            d_list.append(np.array(devs))
            
            # Projections (Visual Helper)
            proj_line = []
            step_size = 5 if len(final_points) > 50 else 1
            for pt in final_points[::step_size]:
                z_cur = pt[2]
                r_surf = mandrel_mgr.get_radius_fast(z_cur)
                if r_surf is None: continue 
                px = center_x + r_surf + shell_offset + blank_thick
                proj_line.append([px, 0, z_cur])
            
            # Projeksiyon çizgisi Z aralığı:
            # op içindeki proj_extend_bottom / proj_extend_top ile kullanıcı
            # mandrel sınırları dışına ne kadar uzatılacağını belirler (mm, default 0).
            _op = op or {}
            _min_z = mandrel_mgr.props.get("min_z", 0.0) - float(_op.get("proj_extend_bottom", 0.0))
            _max_z = mandrel_mgr.props.get("top_z", 100.0) + float(_op.get("proj_extend_top", 0.0))
            proj_line = [p for p in proj_line if _min_z <= p[2] <= _max_z]
            if proj_line: p_list.append(np.array(proj_line))

    def _compute_proj_and_devs(self, path, mandrel_mgr, center_x, shell_offset, blank_thick, r_tool, op=None):
        """Compute projection line and deviation array from the actual path points.
        Used for back passes so their visual data reflects their own geometry rather
        than a reversed copy of the forward pass arrays."""
        devs = []
        for pt in path:
            m_r = mandrel_mgr.get_radius_fast(pt[2])
            dist = math.sqrt((pt[0] - center_x) ** 2 + pt[1] ** 2)
            limit = m_r + blank_thick + shell_offset + r_tool
            devs.append(dist - limit if m_r is not None else 0.0)

        proj_line = []
        step_size = 5 if len(path) > 50 else 1
        for pt in path[::step_size]:
            r_surf = mandrel_mgr.get_radius_fast(pt[2])
            if r_surf is None:
                continue
            proj_line.append([center_x + r_surf + shell_offset + blank_thick, 0, pt[2]])

        _op = op or {}
        _min_z = mandrel_mgr.props.get("min_z", 0.0) - float(_op.get("proj_extend_bottom", 0.0))
        _max_z = mandrel_mgr.props.get("top_z", 100.0) + float(_op.get("proj_extend_top", 0.0))
        proj_line = [p for p in proj_line if _min_z <= p[2] <= _max_z]

        proj_arr = np.array(proj_line) if proj_line else np.array([])
        devs_arr = np.array(devs)
        return proj_arr, devs_arr

    def _contact_zone_mask(self, path_arr, center_x, contact_zone_mm,
                           r_tool, blank_thick, shell_offset):
        """
        Per-point boolean mask marking where the roller is near the mandrel.

        Uses the SAME true roller-to-blank-surface clearance the path generator
        relies on for collision safety (see _correct_clearance_uniform):
            dist  = sqrt((x - center_x)^2 + y^2)          # radial dist from axis
            clear = dist - (surface_radius(z) + blank_thick + shell_offset + r_tool)
        `clear` is 0 when the roller touches the blank and grows as it pulls away.
        Because `dist` is a magnitude it is orientation-independent — it works no
        matter which radial side of the axis the roller sits on — and it follows a
        curved profile via get_radius_fast(z). A point is "in the contact zone" when
        it is within `contact_zone_mm` of the surface:
            clear <= contact_zone_mm
        Applied identically to forward and back passes.

        Returns a numpy bool array (len == len(path_arr)) or None when disabled /
        unavailable (contact_zone_mm <= 0, no mandrel, or fewer than 2 points).
        """
        mgr = self.last_mandrel_mgr
        if contact_zone_mm <= 0 or mgr is None or path_arr is None or len(path_arr) < 2:
            return None
        m_min_z = mgr.props.get("min_z", float('-inf'))
        m_top_z = mgr.props.get("top_z", float('inf'))
        clears = np.empty(len(path_arr))
        for i, (x, y, z) in enumerate(path_arr[:, :3]):
            zc = min(max(z, m_min_z), m_top_z)                 # clamp, don't skip
            m_rad = max(0.0, mgr.get_radius_fast(zc))
            dist = math.sqrt((x - center_x) ** 2 + y ** 2)
            clears[i] = dist - (m_rad + blank_thick + shell_offset + r_tool)
        return clears <= contact_zone_mm

    def generate_gcode(self, feed: int = 1000, speed: int = 200, max_rpm: int = 2000, params: dict = None) -> str:
        """
        Generates CNC G-Code for the calculated toolpaths.

        When params["plc_mode"] is True, each toolpath is decimated using
        the Ramer-Douglas-Peucker algorithm before G-code emission.  The
        closest-to-mandrel point on every pass is always preserved so that
        the critical contact geometry is never lost.  The tolerance is
        controlled by params["plc_tolerance"] (mm, default 0.5).
        The CNC path (gcode_resolution) is NOT affected.
        """
        if not self.last_calculated_paths: return ""
        if params is None: return ""

        # --- PLC Mode: decimated path list ---
        plc_mode = bool(params.get("plc_mode", False))
        plc_tolerance = float(params.get("plc_tolerance", 0.5))
        center_x = float(params.get("mandrel_pos_x_offset", 0.0))

        if plc_mode:
            _exit_tol = float(params.get("plc_exit_tolerance", plc_tolerance))
            paths_to_use = []
            for _pi, _p in enumerate(self.last_calculated_paths):
                _split    = self.last_render_split_idx.get(_pi)
                _app_end  = _split[0] if _split is not None else None
                _arc_end  = _split[1] if _split is not None else None
                paths_to_use.append(
                    self._decimate_path_for_plc(_p, plc_tolerance, center_x,
                                                approach_end_idx=_app_end,
                                                arc_end_idx=_arc_end,
                                                exit_tolerance=_exit_tol)
                )
            logger.info(
                f"[PLC Mode] Decimated {len(self.last_calculated_paths)} paths. "
                f"Points: {sum(len(p) for p in self.last_calculated_paths)} → "
                f"{sum(len(p) for p in paths_to_use)} (tol={plc_tolerance} mm)"
            )
        else:
            paths_to_use = self.last_calculated_paths

        # ── Tilt-arm machines (ID112): per-point B words + reachability check.
        # Tilt is recomputed from the emitted point list itself (decimated or
        # not) via _compute_tilt_for_path, so words always match the points.
        _tilt_kin = get_kinematics(params)
        _tilt_mgr = getattr(self, "last_mandrel_mgr", None)
        self.last_kinematic_warnings = []

        invert_x = params.get("machine_invert_x", False)
        invert_z = params.get("machine_invert_z", False)  # [NEW] Z axis inversion
        dia_mode = params.get("machine_output_diameter_mode", False)
        
        # [NEW] Machine Origin in Global Coords (Post-Processor)
        origin_x = params.get("machine_origin_x", 0.0)
        origin_z = params.get("machine_origin_z", 0.0)
        # Override: origin = safe home position
        if params.get("origin_use_home", False):
            origin_x = params.get("home_x", 0.0)
            origin_z = params.get("home_z", 0.0)
        
        # Additional Work Offsets (G54 style, applied AFTER origin transformation)
        off_x = params.get("machine_gcode_offset_x", 0.0)
        off_z = params.get("machine_gcode_offset_z", 0.0)
        
        # Axis direction multipliers
        dir_x = -1.0 if invert_x else 1.0
        dir_z = -1.0 if invert_z else 1.0
        
        # Get Template Strings
        header_tmpl = params.get("gcode_header", "G21 G90 G18\nG54")
        
        # Tool & Operation Setup
        operations = self._ensure_ops_dict(params)

        # Custom Commands
        raw_cmds = params.get("custom_commands", [])
        pass_cmds = [(int(float(c["value"])), c["cmd"]) for c in raw_cmds if c.get("trigger") == "pass"]
        z_cmds    = [(float(c["value"]), c["cmd"])      for c in raw_cmds if c.get("trigger") == "z"]

        mcode_descriptions = params.get("mcode_descriptions", {})

        def _annotate_mcode(cmd_str):
            """Append M-code description as a G-code comment if one is defined."""
            if '(' in cmd_str:
                return cmd_str
            m = re.search(r'M(\d+)', cmd_str, re.IGNORECASE)
            if m:
                desc = mcode_descriptions.get(m.group(1), "")
                if desc:
                    return f"{cmd_str} ({desc})"
            return cmd_str
        
        # Split line by line
        plc_label = " [PLC MODE]" if plc_mode else ""
        gcode = ["%", f"O1001 (METAL SIVAMA - {len(paths_to_use)} PASO{plc_label})"]
        gcode.extend(header_tmpl.splitlines())
        
        # Configurable Machine Home / Safe Pts
        home_x = params.get("home_x", 300.0)
        home_z = params.get("home_z", 150.0)
        
        # [NEW] Transform Home Position through post-processor
        home_x_machine = ((home_x - origin_x) * dir_x) + off_x
        home_z_machine = ((home_z - origin_z) * dir_z) + off_z
        if dia_mode: home_x_machine *= 2.0
        
        # Machine Settings Comment Block
        gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gcode.append(f"(Generated: {gen_time})")

        # --- CONTACT POINT (calibration touch) — highlighted, critical info ---
        calib = params.get("calibration_last_session", {}) or {}
        c_x = str(calib.get("entry_x", "")).strip()
        c_z = str(calib.get("entry_z", "")).strip()
        if c_x or c_z:
            c_surf = str(calib.get("surface", "")).strip()
            c_tool = str(calib.get("tool_var", "")).strip()
            c_rt   = str(calib.get("entry_rt", "")).strip()
            c_bt   = str(calib.get("entry_blank_t", "")).strip()
            gcode.extend([
                "(========================================)",
                "(===       CONTACT / TEMAS NOKTASI    ===)",
                f"(===   X = {c_x or '?':<6}   Z = {c_z or '?':<6}       ===)",
                "(========================================)",
            ])
            detail = []
            if c_surf: detail.append(f"Surface={c_surf}")
            if c_tool: detail.append(f"Tool={c_tool}")
            if c_rt:   detail.append(f"Rr={c_rt}mm")
            if c_bt:   detail.append(f"Blank={c_bt}mm")
            if detail:
                gcode.append(f"(Contact ref: {', '.join(detail)})")

        gcode.extend([
            "(--- MAKINE AYARLARI / POST-PROCESSOR ---)",
            f"(Machine Origin: X={origin_x}, Z={origin_z})",
            f"(Axis Direction: X={'INVERTED' if invert_x else 'NORMAL'}, Z={'INVERTED' if invert_z else 'NORMAL'})",
            f"(Output Mode: {'DIAMETER' if dia_mode else 'RADIUS'})",
            f"(G54 Offset: X={off_x}, Z={off_z})",
            f"(Program Start: X={params.get('home_x', 300.0)}, Z={params.get('home_z', 150.0)}) (PLC handles actual homing)",
            f"(Retract: X={params.get('retract_x', 50.0)}, Z={params.get('retract_z', 50.0)})",
            "(--- PARCA / BLANK ---)",
            f"(Blank Radius: {params.get('blank_radius', 0.0)} mm)",
            f"(Blank Z Shift: {params.get('blank_z_shift', 0.0)} mm)",
            f"(Final Thickness: {params.get('final_part_thickness_on_mandrel', 2.0)} mm)",
            f"(Safety Clearance: {params.get('safety_clearance_roller_to_part', 0.5)} mm)",
            "(--- MANDREL POZISYON ---)",
            f"(Mandrel Offset: X={params.get('mandrel_pos_x_offset', 0.0)}, Z={params.get('mandrel_pos_z_offset', 0.0)})",
            f"(Mandrel Rotation: Rx={params.get('mandrel_rot_x', 0.0)}, Ry={params.get('mandrel_rot_y', 0.0)}, Rz={params.get('mandrel_rot_z', 0.0)})",
            "(--- OPERASYONLAR ---)",
        ])
        for i, op in enumerate(operations):
            op_type = op.get("type", "Process").upper()
            op_count = op.get("count", 1)
            op_tool = op.get("tool_id", "T0101")
            op_speed = op.get("speed", 0)
            op_s_mode = op.get("speed_mode", "CSS")
            op_feed = op.get("feed", 0)
            op_f_mode = op.get("feed_mode", "mm_min")
            op_r = op.get("r_tool", 0)
            gcode.append(
                f"(Op{i+1}: {op_type}, {op_count} paso, {op_tool}, "
                f"R={op_r}mm, {op_s_mode}={op_speed}, {op_f_mode}={op_feed})"
            )
        gcode.extend([
            "",
            f"G50 S{max_rpm} (Devir Siniri)",
            f"G0 Z{home_z_machine:.3f} (Program Start Z)",
            f"G0 X{home_x_machine:.3f} (Program Start X)",
            ""
        ])

        # Cylinder GOTO — one-time, before spindle start
        cyl_pos_mm = float(params.get("cylinder_position_mm", 0.0))
        if params.get("cylinder_enabled", True) and cyl_pos_mm > 0:
            gcode.append(f"(--- SILINDIR / CYLINDER ---)")
            _cyl_desc = mcode_descriptions.get("40", "CYLINDER GOTO")
            gcode.append(f"M40 P{cyl_pos_mm:.1f} ({_cyl_desc} {cyl_pos_mm:.1f} mm)")
            gcode.append("")

        safe_x_machine = home_x_machine  # Use transformed safe X
        current_tool = None
        global_path_idx = 0
        total_paths = len(paths_to_use)
        
        # --- OPERATION BASED LOOP ---
        for op_idx, op in enumerate(operations):
            if not op.get("enabled", True): continue
            
            count = int(op.get("count", 1))
            op_tool = op.get("tool_id", "T0101")
            op_type = op.get("type", "Process").upper()
            
            # Velocity Params
            s_mode = op.get("speed_mode", "CSS") # CSS or RPM
            f_mode = op.get("feed_mode", "mm_min") # mm_min or mm_rev
            
            def_speed = params.get("surface_speed_m_min", 200)
            def_feed = params.get("feed_rate_mm_min", 300)
            
            val_speed = float(op.get("speed", def_speed))
            val_feed = float(op.get("feed", def_feed))
            
            code_speed = "G96" if s_mode == "CSS" else "G97"
            code_feed = "G98" if f_mode == "mm_min" else "G99"
            
            # Tool Change / Init Logic
            tool_differs = (op_tool != current_tool)
            
            if tool_differs and current_tool is not None:
                 gcode.extend(["", "(--- TOOL CHANGE SAFETY ---)"])
                 gcode.append(f"G0 Z{home_z_machine:.3f} (Home Z)")
                 gcode.append(f"G0 X{safe_x_machine:.3f} (Retract X)")
                 gcode.extend(["M5", "M1"])

            if tool_differs or current_tool is None:
                 gcode.append(f"M6 {op_tool} ({op_type})")
                 gcode.append(f"{code_speed} S{int(val_speed)} M3")
                 gcode.append(f"{code_feed} (Feed: {f_mode})")
                 gcode.append("")
                 current_tool = op_tool
            elif current_tool == op_tool:
                 gcode.append(f"(Update Params: {val_speed} {s_mode}, {val_feed} {f_mode})")
                 gcode.append(f"{code_speed} S{int(val_speed)} M3")
                 gcode.append(f"{code_feed}")

            for i in range(count):
                if global_path_idx >= total_paths: break

                path = paths_to_use[global_path_idx]
                gcode.append(f"(--- OP {op_idx+1}: {op_type} - PASO {i+1} ---)")

                # Per-pass feed
                t_pass = (i / (count - 1)) if count > 1 else 0.0
                pass_feed         = val_feed
                feed_contact_sv   = float(op.get("feed_contact",     pass_feed))
                feed_contact_ev   = float(op.get("feed_contact_end", feed_contact_sv))
                pass_feed_contact = feed_contact_sv + t_pass * (feed_contact_ev - feed_contact_sv)
                contact_zone_mm   = float(op.get("contact_zone_mm",  0.0))
                # Per-point mask: True where the roller is within contact_zone_mm of
                # the blank surface (same clearance measure the path generator uses).
                cz_r_tool      = float(op.get("r_tool", 25.0))
                cz_blank_thick = float(params.get("final_part_thickness_on_mandrel", 2.0))
                cz_shell_off   = float(params.get("shell_thickness", 0.0))
                contact_mask = self._contact_zone_mask(np.array(path), center_x, contact_zone_mm,
                                                       cz_r_tool, cz_blank_thick, cz_shell_off)

                # Per-point tilt for this (possibly decimated) point list.
                pass_tilts = None
                if _tilt_kin is not None and _tilt_mgr is not None:
                    pass_tilts = self._compute_tilt_for_path(np.array(path), op, _tilt_mgr, _tilt_kin)
                    _issues = _tilt_kin.check_reachable(np.array(path), pass_tilts)
                    if _issues:
                        self.last_kinematic_warnings.extend(
                            f"Op{op_idx+1} P{i+1}: {s}" for s in _issues[:5])

                # Pass-triggered custom commands (1-indexed)
                pass_num = global_path_idx + 1
                for (pn, pcmd) in pass_cmds:
                    if pn == pass_num:
                        gcode.append(_annotate_mcode(pcmd))

                def transform_pt(p_arr):
                    """
                    Post-Processor Coordinate Transformation:
                    X_machine = ((X_global - origin_x) * direction_x) + offset_x
                    Z_machine = ((Z_global - origin_z) * direction_z) + offset_z
                    """
                    x, y, z = p_arr[0], p_arr[1], p_arr[2]
                    # Apply post-processor transformation
                    x_out = ((x - origin_x) * dir_x) + off_x
                    z_out = ((z - origin_z) * dir_z) + off_z
                    # Apply diameter mode if enabled
                    if dia_mode: x_out *= 2.0
                    return x_out, z_out

                def _b_word(tilts, idx):
                    """' B<deg>' G-code word, or '' on plain-XZ machines (111 output unchanged)."""
                    if tilts is None:
                        return ""
                    return f" B{_tilt_kin.tilt_to_b(float(tilts[idx])):.3f}"

                s_x, s_z = transform_pt(path[0])
                gcode.append(f"G0 X{s_x:.3f} Z{s_z:.3f}{_b_word(pass_tilts, 0)} (Op{op_idx+1} P{i+1})")
                
                zones = op.get("zones", [])
                current_s_val = val_speed
                current_f_val = -1.0
                fired_z_indices = set()
                prev_raw_z = path[0][2] if len(path) > 0 else None

                for _pi, p in enumerate(path[1:], start=1):
                    tx, tz = transform_pt(p)
                    raw_z = p[2]

                    # Z-triggered custom commands (fire once per threshold per pass)
                    if prev_raw_z is not None:
                        for zi, (z_thresh, z_cmd) in enumerate(z_cmds):
                            if zi not in fired_z_indices:
                                if (prev_raw_z <= z_thresh < raw_z) or (prev_raw_z >= z_thresh > raw_z):
                                    gcode.append(_annotate_mcode(z_cmd))
                                    fired_z_indices.add(zi)
                    prev_raw_z = raw_z

                    # Check Zones
                    target_s = val_speed
                    target_f = pass_feed

                    for zdata in zones:
                         try:
                             zstart = float(zdata.get("start_z", 0))
                             zend = float(zdata.get("end_z", 0))
                             if min(zstart, zend) <= raw_z <= max(zstart, zend):
                                  target_s = float(zdata.get("speed", val_speed))
                                  target_f = float(zdata.get("feed", pass_feed))
                                  break
                         except (TypeError, ValueError, KeyError): pass

                    # Contact zone overrides everything — slow feed near the mandrel
                    if contact_mask is not None and contact_mask[_pi]:
                        target_f = pass_feed_contact
                    
                    s_suffix = ""
                    if target_s != current_s_val:
                         s_suffix = f" {code_speed} S{int(target_s)}"
                         current_s_val = target_s
                    
                    f_suffix = ""
                    if abs(target_f - current_f_val) > 0.001:
                        f_suffix = f" F{target_f:.3f}"
                        current_f_val = target_f

                    gcode.append(f"G1 X{tx:.3f} Z{tz:.3f}{_b_word(pass_tilts, _pi)}{f_suffix}{s_suffix} (Op{op_idx+1} P{i+1})")
                
                # Skip the forward retract when a back pass follows — the back pass
                # starts where the forward ended (P3), so the roller flows straight in.
                _bp_meta = getattr(self, 'last_back_pass_meta', {})
                _back_follows = (global_path_idx + 1) in _bp_meta
                if len(path) > 0 and not _back_follows:
                    last_pt = path[-1]
                    ret_x_off = float(params.get("retract_x", 50.0))
                    ret_z_off = float(params.get("retract_z", 50.0))

                    raw_ret_x = last_pt[0] + ret_x_off
                    raw_ret_z = last_pt[2] + ret_z_off

                    rx, rz = transform_pt([raw_ret_x, 0, raw_ret_z])
                    gcode.append(f"G0 X{rx:.3f} Z{rz:.3f} (Retract Op{op_idx+1} P{i+1})")

                gcode.append("")
                _fwd_last_pt = path[-1] if len(path) > 0 else None
                global_path_idx += 1

                # Back pass G-code (consumed here, not by the outer for i loop)
                if global_path_idx < total_paths and global_path_idx in _bp_meta:
                    bp_info     = _bp_meta[global_path_idx]
                    bp_path     = paths_to_use[global_path_idx]
                    bp_feed_val = float(bp_info.get("feed", val_feed))
                    gcode.append(f"(--- OP {op_idx+1}: {op_type} - BACK PASS {i+1} ---)")
                    # Same per-point contact zone as the forward pass (shared op settings):
                    # slow to the contact feed where the back pass nears the mandrel — the
                    # back pass runs outer→inner, so this catches its inner end.
                    bp_mask = self._contact_zone_mask(np.array(bp_path), center_x, contact_zone_mm,
                                                      cz_r_tool, cz_blank_thick, cz_shell_off)
                    # Tilt derives from each point's Z, so a back pass needs no
                    # special handling — the same Z always yields the same angle.
                    bp_tilts = None
                    if _tilt_kin is not None and _tilt_mgr is not None:
                        bp_tilts = self._compute_tilt_for_path(np.array(bp_path), op, _tilt_mgr,
                                                               _tilt_kin)
                        _issues = _tilt_kin.check_reachable(np.array(bp_path), bp_tilts)
                        if _issues:
                            self.last_kinematic_warnings.extend(
                                f"Op{op_idx+1} BP{i+1}: {s}" for s in _issues[:5])
                    # Only approach if the back pass start isn't already the forward end
                    # (bp_arc bow / clearance shift can move it); otherwise flow straight in.
                    if _fwd_last_pt is None or np.linalg.norm(np.array(_fwd_last_pt) - np.array(bp_path[0])) > 1e-3:
                        bs_x, bs_z = transform_pt(bp_path[0])
                        gcode.append(f"G0 X{bs_x:.3f} Z{bs_z:.3f}{_b_word(bp_tilts, 0)} (Op{op_idx+1} BP{i+1})")
                    # Base feed line (unchanged when no contact zone -> identical output).
                    gcode.append(f"G1 F{bp_feed_val:.3f}")
                    current_bp_f = bp_feed_val
                    for _bpi, bp_pt in enumerate(bp_path[1:], start=1):
                        tx, tz = transform_pt(bp_pt)
                        target_bp_f = pass_feed_contact if (bp_mask is not None and bp_mask[_bpi]) else bp_feed_val
                        f_suffix = ""
                        if abs(target_bp_f - current_bp_f) > 0.001:
                            f_suffix = f" F{target_bp_f:.3f}"
                            current_bp_f = target_bp_f
                        gcode.append(f"G1 X{tx:.3f} Z{tz:.3f}{_b_word(bp_tilts, _bpi)}{f_suffix} (Op{op_idx+1} BP{i+1})")
                    if len(bp_path) > 0:
                        bl = bp_path[-1]
                        rx, rz = transform_pt([bl[0] + float(params.get("retract_x", 50.0)), 0,
                                               bl[2] + float(params.get("retract_z", 50.0))])
                        gcode.append(f"G0 X{rx:.3f} Z{rz:.3f} (Retract Op{op_idx+1} BP{i+1})")
                    gcode.append("")
                    global_path_idx += 1

        if self.last_kinematic_warnings:
            logger.warning(f"[TILT] {len(self.last_kinematic_warnings)} kinematic reachability "
                           f"issue(s) in generated G-code; first: {self.last_kinematic_warnings[0]}")

        # Final Safety Return (Use transformed coordinates)
        gcode.append("(--- PROGRAM SONU GUVENLI DONUS ---)")
        gcode.append(f"G0 Z{home_z_machine:.3f}")
        gcode.append(f"G0 X{home_x_machine:.3f}")
        
        footer_tmpl = params.get("gcode_footer", "M5\nM30")
        gcode.extend(footer_tmpl.splitlines())
        gcode.append("%")
        return "\n".join(gcode)

    def _safe_rapid_segments(self, p_from, p_to, safe_x):
        """
        Mandrelın içinden geçmemek için rapid'i 3 adıma böler:
        1. X'i safe_x'e çek  (her iki noktanın da max X'i + margin)
        2. Z'de hareket et   (güvenli X'te)
        3. Hedef X'e yaklaş
        Eğer Z değişimi yoksa (sadece X hareketi) direkt gider.
        """
        segs = []
        threshold = 1.0  # mm

        # Safe X: her iki noktanın dışında olmalı. home_x değil, dinamik hesap.
        clearance_x = max(p_from[0], p_to[0], safe_x)

        mid1 = np.array([clearance_x, 0.0, p_from[2]])
        mid2 = np.array([clearance_x, 0.0, p_to[2]])

        # Z farkı küçükse (aynı seviyede) direkt git, 3-adıma gerek yok
        if abs(p_from[2] - p_to[2]) < threshold:
            if np.linalg.norm(p_from - p_to) > threshold:
                segs.append(np.array([p_from, p_to]))
            return segs

        if np.linalg.norm(p_from - mid1) > threshold:
            segs.append(np.array([p_from, mid1]))
        if np.linalg.norm(mid1 - mid2) > threshold:
            segs.append(np.array([mid1, mid2]))
        if np.linalg.norm(mid2 - p_to) > threshold:
            segs.append(np.array([mid2, p_to]))

        if not segs and np.linalg.norm(p_from - p_to) > threshold:
            segs.append(np.array([p_from, p_to]))

        return segs

    def _generate_spline(self, p1, p2, p3, num_points=100):
        try:
            arr = TColgp_Array1OfPnt(1,3)
            arr.SetValue(1, p1); arr.SetValue(2, p2); arr.SetValue(3, p3)
            bs = GeomAPI_PointsToBSpline(arr)
            if not bs.IsDone(): return np.array([])
            
            curve = bs.Curve()
            pts = []
            
            # Use dynamic resolution
            if num_points < 10: num_points = 10
            
            for t in np.linspace(curve.FirstParameter(), curve.LastParameter(), num_points):
                p = curve.Value(t)
                pts.append([p.X(), p.Y(), p.Z()])
            return np.array(pts)
        except Exception as e:
            logger.error(f"Spline generation failed: {e}")
            return np.array([])

    def _apply_rotation(self, points, deg, pivot_point):
        rad = math.radians(deg)
        trsf = gp_Trsf()
        axis = gp_Ax1(pivot_point, gp_Dir(0, 1, 0))
        trsf.SetRotation(axis, rad)
        new_pts = []
        for p in points:
            gp = gp_Pnt(p[0], p[1], p[2]).Transformed(trsf)
            new_pts.append([gp.X(), gp.Y(), gp.Z()])
        return np.array(new_pts)

    # -----------------------------------------------------------------------
    # PLC MODE HELPERS
    # -----------------------------------------------------------------------

    def _rdp_decimate(self, points, tolerance):
        """
        Ramer-Douglas-Peucker (RDP) path decimation.
        Returns the indices of the points to keep from `points` (numpy Nx3 array).
        `tolerance` is the maximum allowed perpendicular deviation in mm.
        """
        if len(points) <= 2:
            return list(range(len(points)))

        kept = {0, len(points) - 1}
        stack = [(0, len(points) - 1)]
        while stack:
            start, end = stack.pop()
            if end - start <= 1:
                continue
            seg_vec = points[end] - points[start]
            seg_len = np.linalg.norm(seg_vec)
            max_dist = 0.0
            max_idx = start + 1
            for i in range(start + 1, end):
                if seg_len < 1e-9:
                    d = np.linalg.norm(points[i] - points[start])
                else:
                    t = np.dot(points[i] - points[start], seg_vec) / (seg_len * seg_len)
                    proj = points[start] + t * seg_vec
                    d = np.linalg.norm(points[i] - proj)
                if d > max_dist:
                    max_dist = d
                    max_idx = i
            if max_dist > tolerance:
                kept.add(max_idx)
                stack.append((start, max_idx))
                stack.append((max_idx, end))
        return sorted(kept)

    def _decimate_path_for_plc(self, path, tolerance, center_x,
                               approach_end_idx=None,
                               arc_end_idx=None,
                               exit_tolerance=None):
        """
        Decimates a toolpath for PLC point-to-point output.

        The point closest to the mandrel (minimum X distance from center_x)
        is always kept as a critical contact point — this is where the roller
        presses hardest and the geometry is most sensitive.

        Structural split parameters (all optional, for linear_approach passes):

          approach_end_idx : index of T1 (end of straight approach arm).
            The approach arm [0..T1] is kept verbatim as 2 pts — it is a
            straight line and needs no RDP. Without this, the long ap_start→P2
            chord dilutes fillet deviations and over-decimates the forward pass.

          arc_end_idx : index of T2 (end of P2 fillet arc, start of exit curve).
            When provided together with approach_end_idx, the path is split into
            three independent RDP regions:
              1. approach  [ap_start..T1]  → kept verbatim (2 pts)
              2. fillet    [T1..T2]        → RDP with `tolerance`
              3. exit      [T2..P3]        → RDP with `exit_tolerance`
            This gives the exit curve its own short T2→P3 chord so its
            curvature is evaluated correctly — without this, the exit sits in
            the same RDP half as the fillet and the long chord from the contact
            point to P3 can make a real Bézier exit curve look nearly straight.

          exit_tolerance : RDP tolerance used only for the exit section [T2..P3].
            Falls back to `tolerance` when None. Setting it higher than
            `tolerance` produces fewer exit points while keeping the fillet
            at full accuracy; setting it lower forces more exit detail.

        Returns a numpy array of the retained points.
        """
        pts = np.array(path)
        if len(pts) <= 2:
            return pts

        _exit_tol = exit_tolerance if exit_tolerance is not None else tolerance

        _has_app = approach_end_idx is not None and 0 < approach_end_idx < len(pts) - 1
        _has_arc = (arc_end_idx is not None and _has_app
                    and arc_end_idx > approach_end_idx
                    and arc_end_idx < len(pts) - 1)

        if _has_app and _has_arc:
            # Three-section split: approach verbatim, fillet and exit each get
            # their own RDP call with the correct short chord.
            approach_part = pts[:approach_end_idx + 1]              # [ap_start, T1]
            fillet_part   = pts[approach_end_idx : arc_end_idx + 1] # [T1..T2]
            exit_part     = pts[arc_end_idx:]                        # [T2..P3]
            dec_fillet = self._decimate_path_for_plc(fillet_part, tolerance, center_x)
            dec_exit   = self._decimate_path_for_plc(exit_part, _exit_tol, center_x)
            # Stitch: approach_part ends with T1, dec_fillet starts with T1 → drop one.
            # dec_fillet ends with T2, dec_exit starts with T2 → drop one.
            result = np.vstack([approach_part[:-1], dec_fillet])
            if len(dec_exit) > 1:
                result = np.vstack([result, dec_exit[1:]])
            return result

        if _has_app:
            # Two-section split: approach verbatim, rest with RDP.
            approach_part = pts[:approach_end_idx + 1]
            curve_part    = pts[approach_end_idx:]
            dec_curve = self._decimate_path_for_plc(curve_part, tolerance, center_x)
            return np.vstack([approach_part[:-1], dec_curve])

        # --- 1. Find critical (closest-to-mandrel) point ---
        x_distances = np.abs(pts[:, 0] - center_x)
        critical_idx = int(np.argmin(x_distances))

        # --- 2. Split path at critical point and decimate each half ---
        half1 = pts[:critical_idx + 1]
        half2 = pts[critical_idx:]

        keep1 = self._rdp_decimate(half1, tolerance)
        keep2 = self._rdp_decimate(half2, tolerance)

        # Map local half-indices back to global indices, avoiding duplicate at split
        result_pts = list(half1[keep1])
        for local_idx in keep2:
            if local_idx == 0:
                continue  # already included as last of half1
            result_pts.append(half2[local_idx])

        return np.array(result_pts)

    def calculate_estimated_time(self, params):
        ops = self._ensure_ops_dict(params)
        total_time = 0.0
        global_path_idx = 0
        paths = self.last_calculated_paths
        
        for op in ops:
            if not op.get("enabled", True): continue
            count = int(op.get("count", 1))
            
            s_mode = op.get("speed_mode", "CSS")
            f_mode = op.get("feed_mode", "mm_min")
            def_speed = params.get("surface_speed_m_min", 200)
            def_feed = params.get("feed_rate_mm_min", 300)
            val_speed = float(op.get("speed", def_speed))
            val_feed = float(op.get("feed", def_feed))
            
            zones = op.get("zones", [])
            
            for _ in range(count):
                if global_path_idx >= len(paths): break
                path = paths[global_path_idx]
                
                if len(path) > 1:
                    for j in range(len(path) - 1):
                        p1 = path[j]
                        p2 = path[j+1]
                        
                        dx = p2[0]-p1[0]; dy = p2[1]-p1[1]; dz = p2[2]-p1[2]
                        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                        if dist <= 0.0001: continue
                        
                        cur_s = val_speed
                        cur_f = val_feed
                        raw_z = p1[2]
                        
                        for zdata in zones:
                             try:
                                 zs = float(zdata.get("start_z", 0)); ze = float(zdata.get("end_z", 0))
                                 if min(zs, ze) <= raw_z <= max(zs, ze):
                                      cur_s = float(zdata.get("speed", val_speed))
                                      cur_f = float(zdata.get("feed", val_feed))
                                      break
                             except (TypeError, ValueError, KeyError): pass
                        
                        seg_time_min = 0.0
                        
                        if f_mode == "mm_min":
                            if cur_f > 0: seg_time_min = dist / cur_f
                        else:
                            rpm = cur_s
                            if s_mode == "CSS":
                                avg_x = abs((p1[0]+p2[0])/2.0)
                                if avg_x < 1.0: avg_x = 1.0
                                dia = 2.0 * avg_x
                                rpm = (cur_s * 1000.0) / (math.pi * dia)
                                max_rpm = float(params.get("spindle_speed_limit_rpm", 3000))
                                rpm = min(rpm, max_rpm)
                            
                            if rpm > 0 and cur_f > 0:
                                f_min = cur_f * rpm
                                seg_time_min = dist / f_min
                        
                        total_time += (seg_time_min * 60.0) 

                global_path_idx += 1
                
        return total_time

    def _create_sweeping_pass(self, start_z, end_z, mandrel_mgr, center_x, r_tool, blank_thick, finish_allowance, shell_offset, pass_name, t_list, p_list, c_list, d_list, safety_clearance=0.0):
        # Sweeping / Ironing Pass: Traces the Mandrel Surface directly
        path_pts = []
        projs = []
        devs = []

        dist = abs(end_z - start_z)
        if dist < 1.0: return

        step_size = 1.0 # 1mm resolution
        num_steps = int(dist / step_size)
        step_dir = -1.0 if start_z > end_z else 1.0

        current_z = start_z

        for _ in range(num_steps + 1):
            if (step_dir > 0 and current_z > end_z) or (step_dir < 0 and current_z < end_z):
                current_z = end_z

            m_rad = mandrel_mgr.get_radius_fast(current_z) + shell_offset
            nx, nz = mandrel_mgr.get_normal_at_z(current_z)

            total_off = r_tool + blank_thick + safety_clearance + finish_allowance

            rx = center_x + m_rad + (nx * total_off)
            rz = current_z + (nz * total_off)
            
            path_pts.append([rx, 0.0, rz])
            projs.append([center_x + m_rad, 0.0, current_z])
            devs.append(0.0) 
            
            current_z += (step_size * step_dir)
            if abs(current_z - end_z) < 0.1: break
            
        t_list.append(np.array(path_pts, dtype=float))
        p_list.append(np.array(projs,    dtype=float))
        c_list.append(np.array([],       dtype=float))
        d_list.append(np.array(devs,     dtype=float))