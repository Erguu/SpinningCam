import pyvista as pv
import json
import os
import sys
import numpy as np
import math
import tkinter as tk
from tkinter import filedialog
import threading
import queue
import copy
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator, effective_clamp_length
from simulation_controller import SimulationController
from tool_step_loader import ToolStepLoader
from logger_config import logger

class SpinningApp:
    def __init__(self, plotter=None, headless=False):
        # 1. Initialize Managers (single instantiation — second block below does the real init)
        self.tool_library = []   # populated by SpinningCamWindow after load_tools()
        self.tool_step_loader = ToolStepLoader(base_dir=self.get_base_path())
        
        # 2. State Variables
        self.params = self.load_settings()
        self.gui_pass_overrides = {}
        self.active_editing_pass_idx = 0
        self.apply_to_specific_pass_only = False
        self.step_file_path_global = ""
        self.headless = headless
        self.active_machine_profile = None
        self.active_adapter = None

        # Background path calculation state
        self._calc_queue = queue.Queue()
        self._calc_running = False
        self._pending_paths = None   # set by worker thread, consumed by update_scene

        # 3. Actors Dictionary
        self.actors = {
            "mandrel": None, "blank": None, "roller": None,
            "paths": [], "projs": [], "cps": [], "labels": [], "approach": None, "shell": None,
            "pass_dist_lines": [], "analysis_lines": [],
            "dist_line": None, "dist_label": None,
            "anim_roller": None,
            "roller_tip": None,
            "workspace": None, "workspace_wire": None,
            "cylinder_stem": None, "cylinder_head": None,
            "ref_points": [], "ref_point_labels": [],
            "tip_dist": [], "ref_point_dist": [],
            "mandrel_dims": [],
            "clamp_zone": None, "deformed_blank": None,
        }
        # #63 phase 1: selected op index driving the faded-blue deformed-blank overlay;
        # its formed Z is read fresh from path_gen.last_op_end_z each draw (survives recalc).
        # None = no overlay.
        self._deformed_op_idx = None

        # 4. Setup Plotter & UI
        self.plotter = pv.Plotter(window_size=(1000, 800), title="SpinningCam3D")
        self.plotter.set_background('white')
        self._setup_scene_basics()

        self.mandrel_mgr = MandrelManager()
        self.path_gen = PathGenerator()
        self.ui = None
        self.sim_controller = SimulationController(self.plotter, None, lambda: self.actors)
        
        # Force visibility on startup despite loaded settings
        self.params["calc_active"] = True
        self.update_scene("all", force_path_calc=True)

    def get_base_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def load_settings(self):
        default_params = {
            "num_sweeping_passes": 3,
            "first_pass_p2_contact_z_abs": 10.0, 
            "y_rotation_degrees": 10.0,
            "calc_active": True,
            "cam_azimuth": 0.0, "cam_elevation": 0.0, "cam_roll": 90.0,
            "mandrel_rot_x": 0.0, "mandrel_rot_y": 0.0, "mandrel_rot_z": 0.0,
            "mandrel_pos_x_offset": 0.0, "mandrel_pos_z_offset": 0.0,
            "p1_p3_x_offset_from_p2": 40.0, 
            "p1_z_offset_from_p2": 50.0, 
            "p3_z_offset_from_p2": -20.0,
            "roughing_step_radial": 1.0,
            "final_part_thickness_on_mandrel": 2.0, "safety_clearance_roller_to_part": 0.5,
            "min_safety_gap": 0.0,  # one-way safety floor (replaces the two-way target_clearance setter)
            "shell_thickness": 2.0, "blank_radius": 120.0, "blank_z_shift": 0.0,
            "roller_visual_radius": 25.0,
            "show_advanced_sliders": False, "show_visual_sliders": False,
            "last_scroll_val": 100.0,
            "machine_invert_x": False,
            "machine_invert_z": False,  # [NEW] Z axis inversion for post-processor
            "machine_origin_x": 0.0,    # [NEW] Machine origin X in global coords
            "machine_origin_z": 0.0,    # [NEW] Machine origin Z in global coords
            "machine_output_diameter_mode": False,
            "machine_gcode_offset_x": 0.0,
            "machine_gcode_offset_z": 0.0,
            "gcode_header": "G21 G90 G18\nG54",
            "gcode_footer": "M5\nM30",
            
            # Finishing Group Defaults (Dual Control) - Matched to Rough for consistent size
            "finish_p1_p3_x_offset_from_p2": 40.0,
            "finish_p1_z_offset_from_p2": 50.0,
            "finish_p3_z_offset_from_p2": -20.0,
            "finish_y_rotation_degrees": 0.0,
            "finish_step_radial": 0.0, # Added for Finish Options
            
            # V5 Adaptive
            "finish_trace_mandrel_profile": False,
            "conformal_clearance_all_operations": False,
            "finish_trace_resolution": 0.5,
            "adaptive_bow_height": 0.0,

            # Path Correction
            "clearance_correction_per_point": False,
            "collision_resolution": 0.5,   # collision scan step (mm) — Process tab
            "exit_arc_angle": 0.0,          # exit arc tangent-chord angle (deg) — Process tab

            # Working Area (Workspace)
            "gcode_resolution": 2.0,

            # PLC Output Mode
            "plc_mode": False,
            "plc_tolerance": 0.5,
            "workspace_show": True,
            "workspace_x_min": 0.0,
            "workspace_x_max": 300.0,
            "workspace_z_min": 0.0,
            "workspace_z_max": 500.0,

            # Placeable 3D rulers (visual only — never affect toolpaths).
            # X ruler = horizontal scale bar at Z = ruler_x_at_z; runs from
            #   ruler_x_start -> ruler_x_end along X (labels = distance from Start).
            # Z ruler = vertical scale bar at X = ruler_z_at_x; runs from
            #   ruler_z_start -> ruler_z_end along Z (labels = distance from Start).
            # End == Start => auto-fit the scene from Start (Start=0 => labels read
            # true machine X / Z). Start -> End sets the direction.
            "show_rulers": False,
            "ruler_x_at_z": 0.0,
            "ruler_z_at_x": 0.0,
            "ruler_x_start": 0.0,
            "ruler_x_end": 0.0,
            "ruler_z_start": 0.0,
            "ruler_z_end": 0.0,

            # Draw the passes at the roller TOUCH POINT (tip) instead of the roller
            # centre — visual only, pulls each drawn line in by r_tool. No effect on
            # path generation or G-code.
            "show_tip_paths": False,

            # Clamp / counter-press zone (TODO #62). The base region of the part is
            # held between the counter-press and the mandrel and is NOT machined.
            #   clamp_zone_length   = per-part override (mm, measured UP from the
            #                         mandrel base). 0 = inherit the machine baseline.
            #   clamp_zone_baseline = machine-level default (machine profile key).
            # Effective length = override if > 0 else baseline (see path_generator
            # .effective_clamp_length). Phase 1 = warning + 3D band only (no clipping).
            "clamp_zone_length": 0.0,
            "clamp_zone_baseline": 0.0,

            # #63: show the faded-blue deformed-blank overlay (follows the selected pass).
            "show_deformed_blank": True,
            # #63: radial nudge (mm) for the overlay — +out / -in — to tune its position.
            "deformed_blank_offset": 0.0,

            # Cylinder
            "cylinder_show": True,
            "cylinder_enabled": True,
            "cylinder_position_mm": 0.0,
            "cylinder_x_pos": 0.0,
            "cylinder_z_base": 200.0,

            # Custom Commands
            "custom_commands": [{"trigger": "pass", "value": 4, "cmd": "M41 P1"}],

            # M-Code Descriptions: maps M-code number (str) → description shown as G-code comment
            "mcode_descriptions": {"40": "Cylinder Goto", "41": "Clamp On", "42": "Clamp Off"},

            # Internal: last loaded STEP path (used to avoid overwriting blank_radius on same-file reload)
            "last_step_path": "",

            # Application version — forced from version.APP_VERSION after settings load
            # (settings.json can never pin a stale version). See changelog.py.
            "app_version": "1.002",
            # Last app version whose changelog the user acknowledged with "Don't show again".
            "changelog_seen_version": "",

            # Operation parameter presets — saved per op type (roughing/finishing/cutting/bending)
            "op_presets": {},

            # UI Language
            "language": "EN",
        }

        # Pristine factory defaults (before merging the user's saved settings.json).
        # Used by the UI to show each field's default value as a faded hint.
        self.factory_defaults = dict(default_params)

        base_path = self.get_base_path()
        json_path = os.path.join(base_path, "settings.json")
        
        logger.info(f"Loading settings from: {json_path}")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding='utf-8') as f:
                    loaded = json.load(f)
                    
                    # Validate settings (non-blocking - just log warnings)
                    try:
                        from config_schema import validate_settings
                        valid, msg = validate_settings(loaded)
                        if valid:
                            logger.info("Settings validated successfully.")
                        else:
                            logger.warning(f"Settings validation warning: {msg}")
                    except ImportError:
                        pass  # Schema module not available, skip validation
                    
                    default_params.update(loaded)
                    logger.info("Settings loaded successfully.")
            except Exception as e:
                logger.error(f"Settings JSON incomplete or corrupt: {e}")
        else:
            logger.warning("Settings file not found! Using defaults.")
        # Version is a property of the BUILD, not the saved settings — force it from code
        # so an old settings.json can never display/compare a stale version (changelog).
        try:
            from version import APP_VERSION
            default_params["app_version"] = APP_VERSION
        except Exception as e:
            logger.warning(f"Could not force app_version from version.py: {e}")
        try:
            from config_schema import migrate_clearance
            migrate_clearance(default_params)
        except Exception as e:
            logger.warning(f"Clearance migration skipped: {e}")
        return default_params

    def save_settings_json(self):
        try:
            from machine_loader import MACHINE_PROFILE_KEYS
            _machine_keys = set(MACHINE_PROFILE_KEYS) | {"machine_id", "machine_name", "_path"}
            data = {k: v for k, v in self.params.items() if k not in _machine_keys}
            base_path = self.get_base_path()
            json_path = os.path.join(base_path, "settings.json")
            with open(json_path, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.info("Settings saved to JSON.")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    def _setup_scene_basics(self):
        self.plotter.add_axes(line_width=5, labels_off=False)
        origin_sphere = pv.Sphere(radius=2.0, center=(0,0,0))
        self.plotter.add_mesh(origin_sphere, color='red', render_points_as_spheres=True)
        self.plotter.add_text("PROGRAM ZERO (G54)", position=(10, 10), font_size=8, color='red')
        # Fix Visual Bug: Explicit bounds to prevent infinite auto-scaling
        self.plotter.show_grid(bounds=(-200, 600, -200, 200, -200, 800), color='black')
        # Fix Clipping Bug: Büyük nesnelerde kamera döndürünce kayboluyor sorunu.
        # VTK her mouse hareketinde clipping range'i yeniden hesaplar ve near plane'i
        # çok uzağa iter. Observer ile her render öncesi sabit geniş bir range zorla.
        def _force_clipping(obj, evt):
            self.plotter.camera.clipping_range = (0.1, 500000)
        self.plotter.renderer.AddObserver('StartEvent', _force_clipping)

    def _update_grid_dynamic(self):
        # Calculate optimal grid bounds based on visible actors
        # Initialize with reasonable defaults
        xmin, xmax, ymin, ymax, zmin, zmax = -100, 300, -100, 100, -100, 400
        
        has_actor = False
        for key in ["mandrel", "roller", "shell", "blank"]:
            actor = self.actors.get(key)
            if actor and actor.GetVisibility():
                b = actor.GetBounds()
                xmin = min(xmin, b[0]); xmax = max(xmax, b[1])
                ymin = min(ymin, b[2]); ymax = max(ymax, b[3])
                zmin = min(zmin, b[4]); zmax = max(zmax, b[5])
                has_actor = True
        
        # Clamp infinite bounds if glitch occurs
        xmin = max(xmin, -500)
        ymin = max(ymin, -500)
        zmin = max(zmin, -500)
        
        # Pad slightly
        pad = 20
        bounds = (xmin-pad, xmax+pad, ymin-pad, ymax+pad, zmin-pad, zmax+pad)

        # show_grid rebuilds the whole cube-axes actor — skip when bounds are
        # unchanged (rounded to kill float jitter from actor.GetBounds()).
        _key = tuple(round(b, 1) for b in bounds)
        if getattr(self, "_last_grid_bounds", None) == _key:
            return
        self._last_grid_bounds = _key

        # Update Grid
        self.plotter.show_grid(bounds=bounds, color='black')

    def _run_calc_worker(self, params_snap, gui_overrides_snap, roller_pos):
        """Background thread: run calculate_paths and push result to _calc_queue."""
        try:
            result = self.path_gen.calculate_paths(
                params_snap, gui_overrides_snap, self.mandrel_mgr,
                visual_roller_pos=roller_pos,
            )
            self._calc_queue.put(("ok", result))
        except Exception as e:
            self._calc_queue.put(("error", e))

    def sync_operation_r_tools(self):
        """Re-pull each operation's r_tool from the tool library so operations never keep
        a stale private copy.

        Root cause of the 2026-06-25 "finishing pass sits closer than roughing" bug:
        roughing and finishing used the same tool_id (T0103) but two different snapshotted
        r_tool values (79.5 vs 74.31), because r_tool is copied into the op when a tool is
        picked and never refreshed.

        tools.json is the single source of truth. Its `r_tool` is the CALIBRATED machine
        reach (disc radius + mounting offset) and must NOT be overwritten with raw STEP disc
        geometry. Falls back to `radius` only when r_tool is genuinely absent (explicit None
        test — 0.0 is a valid calibrated value, so the `or` idiom must not be used here).
        Logs drift instead of masking it.
        """
        lib = {tl.get("id"): tl for tl in (self.tool_library or [])}
        if not lib:
            return
        for i, op in enumerate(self.params.get("operations", [])):
            tl = lib.get(op.get("tool_id"))
            if tl is None:
                continue
            r_cal = tl.get("r_tool")
            lib_r = r_cal if r_cal is not None else tl.get("radius")
            if lib_r is None:
                continue
            lib_r = float(lib_r)
            old = op.get("r_tool")
            if old is None or abs(float(old) - lib_r) > 1e-6:
                logger.info("r_tool sync: operations[%d] (%s) %s -> %.3f (from tool library)",
                            i, op.get("tool_id"), old, lib_r)
                op["r_tool"] = lib_r
            # Safety sanity check: the calibrated reach must never be SMALLER than the raw
            # disc radius — that would drive the roller into the part. A negative gap smells
            # like the calibration was overwritten with disc geometry (the original regression).
            radius = tl.get("radius")
            if r_cal is not None and radius is not None and (lib_r - float(radius)) < -1e-6:
                logger.warning("Tool %s: calibrated r_tool=%.3f < disc radius=%.3f — possible "
                               "mis-calibration, roller may gouge the part.",
                               op.get("tool_id"), lib_r, float(radius))

    def check_angled_clearance(self):
        """ADVISORY ONLY (2026-07-03) — never alters a toolpath.

        The scalar r_tool clearance model is exact on cylindrical surfaces but
        drifts on slopes, because the real roller is a tilted disc, not a sphere:

          radial branch (plain roughing):
              true gap = (blank+clr)*cos(theta) - blank - delta(theta)
          normal branch (finishing / conformal roughing):
              true gap = r_tool*(1-cos(theta)) + clr - delta(theta)

        where theta = surface-normal tilt from radial and delta(theta) = roller-body
        penetration measured from the tool's STEP mesh (get_support_table). This
        method samples each enabled op's Z range and warns (log + one popup per
        recipe signature) when |true gap - commanded clearance| exceeds
        `angled_clearance_warn_threshold` (default 0.5 mm). On a near-cylindrical
        mandrel every deviation is ~0 and it stays silent.
        """
        try:
            if self.mandrel_mgr is None or self.mandrel_mgr.props.get("min_z") is None:
                return
            lib = {tl.get("id"): tl for tl in (self.tool_library or [])}
            if not lib:
                return
            thr = float(self.params.get("angled_clearance_warn_threshold", 0.5))
            blank = float(self.params.get("final_part_thickness_on_mandrel", 0.0))
            side = 1.0 if self.params.get("roller_positive_x_side", True) else -1.0
            m_min_z = float(self.mandrel_mgr.props.get("min_z"))
            m_top_z = float(self.mandrel_mgr.props.get("top_z", m_min_z))
            global_conformal = self.params.get("conformal_clearance_all_operations", False)

            findings = []
            for op in self.params.get("operations", []):
                if not op.get("enabled", True):
                    continue
                op_type = op.get("type", "roughing")
                if op_type not in ("roughing", "finishing"):
                    continue
                tl = lib.get(op.get("tool_id"))
                if tl is None:
                    continue
                table = self.tool_step_loader.get_support_table(tl, side)
                if table is None:
                    continue
                angles, deltas = table
                r_tool = float(op.get("r_tool", tl.get("r_tool") or tl.get("radius") or 25.0))
                clr = float(op.get("clearance", 0.0))
                is_normal_model = (op_type == "finishing") or op.get(
                    "conformal_clearance_operation_specific", global_conformal)

                z0 = min(float(op.get("start_z", m_min_z)), float(op.get("end_z", m_top_z)))
                z1 = max(float(op.get("start_z", m_min_z)), float(op.get("end_z", m_top_z)))
                if op_type == "roughing":
                    z1 += max(0.0, float(op.get("p2_z_extend", 0.0)))
                z0, z1 = max(z0, m_min_z), min(z1, m_top_z)
                if z1 - z0 < 0.5:
                    continue

                worst_dev, worst_z, worst_tilt = 0.0, z0, 0.0
                for z in np.linspace(z0, z1, 120):
                    nx, nz = self.mandrel_mgr.get_normal_at_z(float(z))
                    tilt = math.degrees(math.atan2(nz, nx))
                    delta = float(np.interp(tilt, angles, deltas))
                    if is_normal_model:
                        dev = r_tool * (1.0 - nx) - delta      # true gap - commanded clr
                    else:
                        dev = (blank + clr) * (nx - 1.0) - delta
                    if abs(dev) > abs(worst_dev):
                        worst_dev, worst_z, worst_tilt = dev, float(z), tilt

                if abs(worst_dev) > thr:
                    model_name = "normal" if is_normal_model else "radial"
                    findings.append((op.get("name") or op_type, op.get("tool_id"),
                                     model_name, worst_dev, worst_z, worst_tilt))

            if not findings:
                self._angled_clearance_sig = None
                return

            lines = []
            for name, tid, model_name, dev, z, tilt in findings:
                line = (f"  • {name} ({tid}, {model_name}): "
                        f"{dev:+.2f} mm at Z={z:.1f} (surface tilt {tilt:+.0f}°)")
                lines.append(line)
                logger.warning("Angled-surface clearance deviation: %s", line.strip())

            sig = tuple((tid, round(dev, 2)) for _, tid, _, dev, _, _ in findings)
            if sig == getattr(self, "_angled_clearance_sig", None):
                return                                   # already shown for this recipe
            self._angled_clearance_sig = sig
            if not self.headless:
                try:
                    from tkinter import messagebox
                    from i18n import t
                    messagebox.showwarning(
                        t("angled_clearance_warn_title"),
                        t("angled_clearance_warn_intro") + "\n\n" + "\n".join(lines)
                        + "\n\n" + t("angled_clearance_warn_legend"))
                except Exception:
                    pass                                 # never let the advisory break a calc
        except Exception:
            logger.exception("check_angled_clearance failed (advisory only, ignored)")

    def calculate_async(self, roller_pos=None):
        """
        Start a background path calculation. Non-reentrant — ignores call if already running.
        The caller must poll _calc_queue (via after()) and call
        update_scene("paths", use_cached_paths=True) when the result arrives.
        """
        if self._calc_running:
            return False
        self._calc_running = True
        self.sync_operation_r_tools()   # ops pull r_tool from library before the snapshot
        params_snap = copy.deepcopy(self.params)
        gui_overrides_snap = copy.deepcopy(self.gui_pass_overrides)
        t = threading.Thread(
            target=self._run_calc_worker,
            args=(params_snap, gui_overrides_snap, roller_pos),
            daemon=True,
        )
        t.start()
        return True

    def update_scene(self, update_type="all", force_path_calc=False, use_cached_paths=False):
        """Rebuild scene actors for the given update_type, rendering ONCE at the end.

        Every plotter.add_mesh / remove_actor call defaults to render=True, so
        without suppression a single "all" update triggers a full re-render per
        actor touched (30-80 renders). Batch them and render once.
        """
        _was_suppressed = bool(getattr(self.plotter, "suppress_rendering", False))
        self.plotter.suppress_rendering = True
        try:
            self._update_scene_impl(update_type, force_path_calc, use_cached_paths)
        finally:
            self.plotter.suppress_rendering = _was_suppressed
        if not _was_suppressed:
            try:
                self.plotter.render()
            except Exception:
                pass

    def redraw_paths_cached(self):
        """Redraw the scene from the LAST computed paths, without recalculating —
        for visual-only toggles such as show_tip_paths. If nothing has been
        calculated yet, falls back to a normal (calculating) update."""
        tup = getattr(self, "_last_render_tuple", None)
        if tup is not None:
            self._pending_paths = tup
            self.update_scene("all", use_cached_paths=True)
        else:
            self.update_scene("all", force_path_calc=True)

    def _rtool_for_pass(self, k):
        """Roller radius r_tool of the op that owns global pass index k."""
        ops = self.params.get("operations", [])
        total = 0
        for op in ops:
            if not op.get("enabled", True):
                continue
            span = int(op.get("count", 1)) * (2 if op.get("back_pass_enabled") else 1)
            if k < total + span:
                return float(op.get("r_tool", 25.0) or 25.0)
            total += span
        return float(ops[0].get("r_tool", 25.0) or 25.0) if ops else 25.0

    def _shift_path_to_tip(self, p_arr, r_tool):
        """VISUAL-ONLY: return a copy of a toolpath pulled radially inward by the
        roller radius r_tool, so the drawn line sits at the roller TOUCH POINT
        instead of the roller centre. Path generation is untouched — this only
        moves what gets rendered.

        The stored path point is the roller centre; the contact point is r_tool
        nearer the spin axis (the same relation update_deformed_blank uses). Shift
        is radial about the mandrel centre X, clamped so it never crosses the axis.
        """
        cx = float(self.params.get("mandrel_pos_x_offset", 0.0))
        out = np.array(p_arr, dtype=float)
        dx = out[:, 0] - cx
        sgn = np.where(dx < 0.0, -1.0, 1.0)
        out[:, 0] = cx + sgn * np.maximum(np.abs(dx) - float(r_tool), 0.1)
        return out

    def update_deformed_blank(self, render=False):
        """(#63) Faded-blue overlay of the blank as bent by the SELECTED pass. Built DIRECTLY
        from the pass's own toolpath (contact P2 → exit P3), pulled in by the tool radius so it
        sits on the sheet — so it FOLLOWS THE PASS'S ANGLE AND REACH exactly, and updates as you
        step passes. Purely visual — position/thickness not to scale (tune with
        ``deformed_blank_offset``). ``render=True`` forces a redraw when called standalone."""
        if self.actors.get("deformed_blank"):
            try: self.plotter.remove_actor(self.actors["deformed_blank"])
            except Exception: pass
        self.actors["deformed_blank"] = None
        if not self.params.get("show_deformed_blank", True):
            if render:
                try: self.plotter.render()
                except Exception: pass
            return
        try:
            paths = getattr(self.path_gen, "last_calculated_paths", None)
            if paths:
                import numpy as _np, pyvista as _pv
                k = int(getattr(self, "active_editing_pass_idx", len(paths) - 1))
                k = max(0, min(k, len(paths) - 1))
                p = paths[k]
                if p is not None and len(p) >= 2:
                    pts = _np.asarray(p, dtype=float)
                    cx = float(self.params.get("mandrel_pos_x_offset", 0.0))
                    r_tool = self._rtool_for_pass(k)
                    off = float(self.params.get("deformed_blank_offset", 0.0) or 0.0)
                    ci = int(_np.argmin(_np.abs(pts[:, 0] - cx)))   # contact P2
                    seg = pts[ci:]                                   # forming stroke → exit P3
                    if len(seg) < 2:                                 # nothing to revolve (guard)
                        raise ValueError("empty pass segment")
                    # Sheet radius = roller-path radius pulled IN by the tool radius (+ optional
                    # visual offset). The segment's slope IS the pass angle; its length IS reach.
                    radial = _np.maximum(_np.abs(seg[:, 0] - cx) - r_tool + off, 0.1)
                    prof = _np.column_stack([radial, _np.zeros(len(seg)), seg[:, 2]])
                    surf = _pv.lines_from_points(prof).extrude_rotate(
                        angle=360.0, resolution=60, capping=False, rotation_axis=(0, 0, 1))
                    if abs(cx) > 1e-9:
                        surf = surf.translate((cx, 0.0, 0.0), inplace=False)
                    self.actors["deformed_blank"] = self.plotter.add_mesh(
                        surf, color=(0.20, 0.55, 1.0), opacity=0.40, style="surface",
                        smooth_shading=True)
        except Exception as e:
            logger.warning(f"Deformed-blank overlay failed: {e}")
        if render:
            try: self.plotter.render()
            except Exception: pass

    def _update_scene_impl(self, update_type="all", force_path_calc=False, use_cached_paths=False):
        # --- HESAPLAMALAR ---
        # Derive Roller Radius from Active Operation (or default if single-pass editing logic fails)
        r_rad = 25.0
        try:
             ops = self.params.get("operations", [])
             total_passes = 0
             active_idx = getattr(self, "active_editing_pass_idx", -1)
             
             found_op = False
             for op in ops:
                 if not op.get("enabled", True): continue
                 count = int(op.get("count", 1))
                 if active_idx >= 0 and active_idx < total_passes + count:
                     # This is the active op
                     r_rad = float(op.get("r_tool", 25.0))
                     found_op = True
                     break
                 total_passes += count
             
             # Fallback logic if nothing active
             if not found_op and len(ops) > 0:
                 r_rad = float(ops[0].get("r_tool", 25.0))
        except: pass
        
        # Roller idle position = Program Start (home) position.
        # home_x / home_z are TIP coordinates (the point that contacts the workpiece).
        # The sphere center must be shifted outward by r_rad so the tip lands at home_x.
        _side = 1.0 if self.params.get("roller_positive_x_side", True) else -1.0
        rx_tip = self.params.get("home_x", 300.0)
        rz_tip = self.params.get("home_z", 150.0)

        rx_center = rx_tip + _side * r_rad   # sphere center is r_rad outward from tip
        rz_center = rz_tip

        _m_min_z = self.mandrel_mgr.props.get("min_z", rz_tip)
        _m_top_z = self.mandrel_mgr.props.get("top_z", rz_tip)
        _clamped_z = max(_m_min_z, min(_m_top_z, rz_tip))
        _clamped_r = self.mandrel_mgr.get_radius_fast(_clamped_z)

        roller_pos = np.array([rx_center, 0, rz_center])

        # Visualize Safe Home
        if "home_marker" in self.actors: 
             self.plotter.remove_actor(self.actors["home_marker"])
             
        home_x = self.params.get("home_x", 300.0)
        home_z = self.params.get("home_z", 150.0)
        
        try:
            # Simple Green Sphere at Home
            home_mesh = pv.Sphere(radius=3.0, center=(home_x, 0, home_z))
            self.actors["home_marker"] = self.plotter.add_mesh(home_mesh, color='green', render_points_as_spheres=True)
            
            # [NEW] Safety Label
            if "home_lbl" in self.actors: self.plotter.remove_actor(self.actors["home_lbl"])
            label_pos = [home_x, 0, home_z + 10] # Offset slightly Z
            lbl = [f"SAFE HOME\nX{home_x:.1f} Z{home_z:.1f}"]
            self.actors["home_lbl"] = self.plotter.add_point_labels(np.array([label_pos]), lbl, point_size=0, font_size=14, text_color='green', always_visible=True)
        except: pass

        # Reference Points
        if update_type in ["all", "ref_points"]:
            for a in self.actors.get("ref_points", []) + self.actors.get("ref_point_labels", []):
                try: self.plotter.remove_actor(a)
                except: pass
            self.actors["ref_points"] = []
            self.actors["ref_point_labels"] = []
            for pt in self.params.get("reference_points", []):
                try:
                    z   = float(pt.get("z", 0.0))
                    x   = float(pt.get("x", 0.0))
                    lbl = str(pt.get("label", ""))
                    col = str(pt.get("color", "yellow"))
                    sphere = pv.Sphere(radius=5.0, center=(x, 0, z))
                    self.actors["ref_points"].append(
                        self.plotter.add_mesh(sphere, color=col, opacity=0.95)
                    )
                    txt = f"{lbl}  Z{z:.1f}" if lbl else f"Z{z:.1f}"
                    self.actors["ref_point_labels"].append(
                        self.plotter.add_point_labels(
                            np.array([[x, 0, z + 8]]), [txt],
                            point_size=0, font_size=11,
                            text_color=col, always_visible=True
                        )
                    )
                except Exception as _e:
                    logger.warning(f"Reference point render failed: {_e}")

        # Reference point distance indicators — measured from roller tip (0,0) origin
        if update_type in ["all", "ref_points", "visual"]:
            for a in self.actors.get("ref_point_dist", []):
                try: self.plotter.remove_actor(a)
                except: pass
            self.actors["ref_point_dist"] = []
            if self.params.get("show_tip_distance", False):
                for pt in self.params.get("reference_points", []):
                    try:
                        pz  = float(pt.get("z", 0.0))
                        px  = float(pt.get("x", 0.0))
                        col = str(pt.get("color", "yellow"))
                        # ΔX / ΔZ relative to the roller tip position
                        dx  = px - rx_tip
                        dz  = pz - rz_tip
                        # L-shaped indicator: horizontal from tip → ref X (at tip Z),
                        # then vertical from tip Z → ref Z (at ref X)
                        self.actors["ref_point_dist"].append(
                            self.plotter.add_lines(
                                np.array([[rx_tip, 0., rz_tip], [px, 0., rz_tip]]),
                                color=col, width=2))
                        self.actors["ref_point_dist"].append(
                            self.plotter.add_lines(
                                np.array([[px, 0., rz_tip], [px, 0., pz]]),
                                color=col, width=2))
                        for _pt2, _lbl2, _tc in [
                            ([(rx_tip + px) / 2., 0., rz_tip + 8],        f"ΔX={dx:+.1f}mm", 'orange'),
                            ([px + _side * 12,    0., (rz_tip + pz) / 2.], f"ΔZ={dz:+.1f}mm", 'cyan'),
                        ]:
                            self.actors["ref_point_dist"].append(
                                self.plotter.add_point_labels(
                                    np.array([_pt2]), [_lbl2],
                                    point_size=0, font_size=10,
                                    text_color=_tc, always_visible=True, shape=None))
                    except Exception as _e:
                        logger.warning(f"Ref point distance display failed: {_e}")

        mandrel_radius_at_z = _clamped_r
        mandrel_surface_x = self.params["mandrel_pos_x_offset"] + mandrel_radius_at_z
        gap_x = rx_tip - mandrel_surface_x
        dist_z = rz_tip - self.params["mandrel_pos_z_offset"]
        # Blank mandrel tabanında durmali. Mandrel her zaman mandrel_pos_z_offset'te baslar.
        # first_pass_p2_contact_z_abs de ayni degeri tasiyor (STEP yuklenince auto-set edilir).
        blank_z = self.params["mandrel_pos_z_offset"] + self.params.get("blank_z_shift", 0.0)

        # 1. Mandrel & Blank
        if update_type == "all":
            self.mandrel_mgr.update_geometry(self.params["mandrel_rot_x"], self.params["mandrel_rot_y"], self.params["mandrel_rot_z"], 
                                        self.params["mandrel_pos_x_offset"], self.params["mandrel_pos_z_offset"])
            if self.actors["mandrel"]: self.plotter.remove_actor(self.actors["mandrel"])
            
            if self.mandrel_mgr.mesh_cache:
                m_mesh = self.mandrel_mgr.mesh_cache.copy()
                # Trust MandrelManager's orientation (It already sets Z-min to offset)
                # bounds = m_mesh.bounds
                # z_bottom = bounds[4]
                # m_mesh.translate([0, 0, -z_bottom])
                # m_mesh.translate([0, 0, self.params["mandrel_pos_z_offset"]])
                self.actors["mandrel"] = self.plotter.add_mesh(m_mesh, color='dimgray', opacity=0.6, smooth_shading=True)

            # Mandrel dimension annotation
            for _a in self.actors.get("mandrel_dims", []):
                try: self.plotter.remove_actor(_a)
                except: pass
            self.actors["mandrel_dims"] = []
            if self.mandrel_mgr.mesh_cache:
                try:
                    _p    = self.mandrel_mgr.props
                    _h    = _p["h"]
                    _top  = _p["top_z"]
                    _bot  = _p["min_z"]
                    _pz   = self.mandrel_mgr.profile_z
                    _prf  = self.mandrel_mgr.profile_r
                    _cx   = self.params.get("mandrel_pos_x_offset", 0.0)

                    if len(_prf) > 0:
                        _imin  = int(np.argmin(_prf));  _r_min = float(_prf[_imin]);  _z_rmin = float(_pz[_imin])
                        _imax  = int(np.argmax(_prf));  _r_max = float(_prf[_imax]);  _z_rmax = float(_pz[_imax])
                    else:
                        _r_min, _z_rmin = _p["tr"], _top
                        _r_max, _z_rmax = _p["br"], _bot

                    # Linear fit on (z, r) → surface angle + R² linearity indicator
                    _angle_str = "—"
                    if len(_pz) >= 4 and _h > 1.0:
                        _coeffs = np.polyfit(_pz, _prf, 1)          # slope, intercept
                        _slope  = _coeffs[0]
                        _r_pred = np.polyval(_coeffs, _pz)
                        _ss_res = float(np.sum((_prf - _r_pred) ** 2))
                        _ss_tot = float(np.sum((_prf - np.mean(_prf)) ** 2))
                        _r2     = 1.0 - _ss_res / _ss_tot if _ss_tot > 1e-9 else 1.0
                        _ang    = math.degrees(math.atan(abs(_slope)))
                        if _r2 >= 0.99:
                            _angle_str = f"{_ang:.1f}°  (linear)"
                        elif _r2 >= 0.95:
                            _angle_str = f"{_ang:.1f}°  (approx)"
                        else:
                            _angle_str = f"—  (curved, R²={_r2:.2f})"

                    # Table label — placed to the left (negative-X) side
                    _lx = _cx - _r_max - 25
                    _dim_text = (
                        f" MANDREL PROFILE \n"
                        f"─────────────────\n"
                        f" L       {_h:>7.1f} mm\n"
                        f" R min   {_r_min:>7.1f} mm  @ Z={_z_rmin:.1f}\n"
                        f" R max   {_r_max:>7.1f} mm  @ Z={_z_rmax:.1f}\n"
                        f" Angle   {_angle_str}"
                    )
                    self.actors["mandrel_dims"].append(
                        self.plotter.add_point_labels(
                            np.array([[_lx - 10, 0.0, (_top + _bot) / 2.0]]), [_dim_text],
                            point_size=0, font_size=11, text_color='steelblue',
                            always_visible=True, fill_shape=True,
                            shape_color='aliceblue', shape_opacity=0.88
                        )
                    )
                except Exception as _e:
                    logger.warning(f"Mandrel dimension annotation failed: {_e}")

            if self.actors["blank"]: self.plotter.remove_actor(self.actors["blank"])
            # Blank disk her zaman rotation axis'te (X=0) ortalanır.
            # mandrel_pos_x_offset STEP dosyasındaki offset'i düzeltir ama blank gerçek makine ekseninde kalır.
            cyl = pv.Cylinder(center=(0, 0, blank_z),
                            direction=(0,0,1), radius=self.params["blank_radius"], height=2)
            self.actors["blank"] = self.plotter.add_mesh(cyl, color='deepskyblue', opacity=0.4)

            # Workspace
            for key in ("workspace", "workspace_wire"):
                if self.actors.get(key): self.plotter.remove_actor(self.actors[key])
                self.actors[key] = None
            if self.params.get("workspace_show", True):
                try:
                    wx_min = float(self.params.get("workspace_x_min", 0.0))
                    wx_max = float(self.params.get("workspace_x_max", 300.0))
                    wz_min = float(self.params.get("workspace_z_min", 0.0))
                    wz_max = float(self.params.get("workspace_z_max", 500.0))
                    roller_pos_x = bool(self.params.get("roller_positive_x_side", True))
                    ws_box = pv.Box(bounds=(wx_min, wx_max, -wx_max, wx_max, wz_min, wz_max) if roller_pos_x else (-wx_max, -wx_min, -wx_max, wx_max, wz_min, wz_max))
                    self.actors["workspace"] = self.plotter.add_mesh(
                        ws_box, color='steelblue', opacity=0.04, style='surface')
                    self.actors["workspace_wire"] = self.plotter.add_mesh(
                        ws_box, color='steelblue', opacity=0.3, style='wireframe', line_width=1)
                except Exception as e:
                    logger.warning(f"Workspace render failed: {e}")

            # Clamp / counter-press zone (#62): translucent red band over the base
            # region that must NOT be machined. Length = per-part override or machine
            # baseline (effective_clamp_length). Purely visual; no toolpath impact.
            if self.actors.get("clamp_zone"):
                self.plotter.remove_actor(self.actors["clamp_zone"])
            self.actors["clamp_zone"] = None
            _clamp_len = effective_clamp_length(self.params)
            if _clamp_len > 0:
                try:
                    _cz_min = float(self.mandrel_mgr.props.get("min_z", 0.0))
                    _cz_mid = _cz_min + _clamp_len * 0.5
                    _cz_r = self.mandrel_mgr.get_radius_fast(_cz_mid) + 5.0
                    band = pv.Cylinder(center=(0, 0, _cz_mid), direction=(0, 0, 1),
                                       radius=_cz_r, height=_clamp_len, resolution=48)
                    self.actors["clamp_zone"] = self.plotter.add_mesh(
                        band, color='red', opacity=0.18, style='surface')
                except Exception as e:
                    logger.warning(f"Clamp-zone render failed: {e}")

            # Cylinder (T-shape) — stem extends from z_base downward toward roller/blank
            # Head (flange) is at the low-Z end, always facing toward the roller.
            for key in ("cylinder_stem", "cylinder_head"):
                if self.actors.get(key): self.plotter.remove_actor(self.actors[key])
                self.actors[key] = None
            if self.params.get("cylinder_show", True):
                try:
                    cyl_pos    = float(self.params.get("cylinder_position_mm", 0.0))
                    cx         = float(self.params.get("cylinder_x_pos", 0.0))
                    z_base     = float(self.params.get("cylinder_z_base", 200.0))
                    stem_r     = 12.0
                    head_r     = 35.0
                    head_h     = 10.0
                    stem_len   = max(cyl_pos, stem_r * 2)   # at least visible
                    # Stem: from z_base down to (z_base - stem_len)
                    stem_center = (cx, 0, z_base - stem_len / 2)
                    # Head: flat disc at the low-Z tip of the stem
                    head_z      = z_base - stem_len
                    head_center = (cx, 0, head_z - head_h / 2)
                    stem_mesh = pv.Cylinder(center=stem_center, direction=(0, 0, 1),
                                            radius=stem_r, height=stem_len, resolution=24)
                    head_mesh = pv.Cylinder(center=head_center, direction=(0, 0, 1),
                                            radius=head_r, height=head_h, resolution=24)
                    self.actors["cylinder_stem"] = self.plotter.add_mesh(stem_mesh, color='silver', opacity=0.85, smooth_shading=True)
                    self.actors["cylinder_head"] = self.plotter.add_mesh(head_mesh, color='darkorange', opacity=0.9, smooth_shading=True)
                except Exception as e:
                    import logging; logging.getLogger(__name__).warning(f"Cylinder render failed: {e}")

        # 2. Shell
        if update_type in ["all", "shell", "shell_and_paths"]:
            if self.actors["shell"]: self.plotter.remove_actor(self.actors["shell"])
            shell_grid = self.mandrel_mgr.generate_shell_mesh(self.params["shell_thickness"], self.params["mandrel_pos_x_offset"])
            if shell_grid:
                self.actors["shell"] = self.plotter.add_mesh(shell_grid, color='lime', opacity=0.3, smooth_shading=True)

        # 2.5 Contact-zone band (Velocity Colors overlay)
        # A faded translucent shell wrapping the mandrel at the OUTER edge of the
        # contact zone: radius = surface + blank + shell + r_tool + contact_zone_mm.
        # This is exactly where the roller centre enters the contact zone and slows
        # to the contact feed, so the band hugs the near (slow) portions of the
        # toolpaths. Renderer-only — it does NOT touch the toolpaths or path
        # generation. Toggled by the "velocity_color_mode" checkbox.
        if update_type in ["all", "shell", "shell_and_paths", "visual"]:
            for a in self.actors.get("contact_bands", []):
                self.plotter.remove_actor(a)
            self.actors["contact_bands"] = []
            if self.params.get("velocity_color_mode", False):
                center_x  = float(self.params.get("mandrel_pos_x_offset", 0.0))
                blank_th  = float(self.params.get("final_part_thickness_on_mandrel", 2.0))
                shell_off = float(self.params.get("shell_thickness", 0.0))
                seen = set()
                for op in self.params.get("operations", []):
                    if not op.get("enabled", True):
                        continue
                    cz = float(op.get("contact_zone_mm", 0.0))
                    if cz <= 0:
                        continue
                    r_tool = float(op.get("r_tool", 25.0))
                    thickness = blank_th + shell_off + r_tool + cz
                    key = round(thickness, 2)
                    if key in seen:              # skip identical bands from other ops
                        continue
                    seen.add(key)
                    try:
                        band = self.mandrel_mgr.generate_shell_mesh(thickness, center_x)
                        if band:
                            self.actors["contact_bands"].append(self.plotter.add_mesh(
                                band, color='red', opacity=0.18, smooth_shading=True))
                    except Exception as e:
                        logger.warning(f"Contact-zone band render failed: {e}")

        # 3. Paths
        # #76/#83 (R3 — one calc path): a LIVE param edit (auto-calc on, no force,
        # no cached result) delegates the heavy recalc to the Program tab's
        # background worker instead of running calculate_paths synchronously on
        # the UI thread (this froze the app for seconds on e.g. a blank-radius
        # edit). Current path actors stay visible until the fresh result lands
        # and re-renders via update_scene("paths", use_cached_paths=True).
        # force_path_calc callers (startup, project load, explicit flows) keep
        # the old synchronous behavior — correctness over responsiveness there.
        _delegate_async = (update_type in ["all", "paths", "shell_and_paths", "visual"]
                           and self.params.get("auto_calculate_paths", False)
                           and not force_path_calc and not use_cached_paths
                           and self.params.get("calc_active", False)
                           and getattr(self, "ui_program", None) is not None)
        if _delegate_async:
            self.ui_program._schedule_auto_calc()
        if (not _delegate_async) and update_type in ["all", "paths", "shell_and_paths", "visual"] and (self.params.get("auto_calculate_paths", False) or force_path_calc or use_cached_paths):
            # Ensure rapids key exists
            if "rapids" not in self.actors: self.actors["rapids"] = []
            if "analysis_lines" not in self.actors: self.actors["analysis_lines"] = []

            for a in self.actors["paths"] + self.actors["projs"] + self.actors["cps"] + self.actors["rapids"] + self.actors["pass_dist_lines"] + self.actors["analysis_lines"]: self.plotter.remove_actor(a)
            if self.actors["approach"]: self.plotter.remove_actor(self.actors["approach"])
            self.actors["paths"], self.actors["projs"], self.actors["cps"], self.actors["rapids"], self.actors["pass_dist_lines"], self.actors["analysis_lines"] = [], [], [], [], [], []
            
            if self.params["calc_active"]:
                if use_cached_paths and self._pending_paths is not None:
                    paths, projs, cps, devs, rapids, debug_lines = self._pending_paths
                    self._pending_paths = None
                else:
                    self.sync_operation_r_tools()   # ops pull r_tool from library before calc
                    paths, projs, cps, devs, rapids, debug_lines = self.path_gen.calculate_paths(self.params, self.gui_pass_overrides, self.mandrel_mgr, visual_roller_pos=roller_pos)
                # Keep the last full render tuple so a VISUAL-ONLY toggle (e.g. tip
                # paths) can redraw from it without a recalculation.
                self._last_render_tuple = (paths, projs, cps, devs, rapids, debug_lines)
                self.check_angled_clearance()   # advisory only, never alters paths

                # Build per-path type list. Must mirror calculate_paths' toolpath
                # order exactly: skip disabled ops, cutting/bending = 1 path,
                # back_pass_enabled inserts a back entry after each forward pass.
                ops = self.params.get("operations", [])
                op_types = []   # one entry per toolpath, in render order
                for op in ops:
                    if not op.get("enabled", True):
                        continue
                    op_type = op.get("type", "roughing")
                    count = 1 if op_type in ("cutting", "bending") else int(op.get("count", 1))
                    has_back = op_type not in ("cutting", "bending") and op.get("back_pass_enabled", False)
                    for _ in range(count):
                        op_types.append(op_type)
                        if has_back:
                            op_types.append("back")

                logger.info(f"Rendering {len(paths)} paths.")
                for i, (p, pr, dev) in enumerate(zip(paths, projs, devs)):
                    if len(p) == 0: 
                        logger.warning(f"Path {i} has 0 points.")
                        continue
                    
                    is_active = (i == self.active_editing_pass_idx)
                    _ptype = op_types[i] if i < len(op_types) else "roughing"
                    is_finish_pass = (_ptype == "finishing")
                    is_back_pass   = (_ptype == "back")

                    # Colors: roughing=blue, finishing=orange, back=teal, active=magenta
                    col = 'blue' # default for roughing
                    lw = 5
                    
                    # Velocity Colors mode no longer recolors the passes themselves
                    # (that flat per-pass coloring ignored zones/contact feed and was
                    # misleading). Instead a translucent contact-zone band is drawn as
                    # an overlay (see section 2.5). Passes keep their type colors.
                    if is_active:
                        col = 'magenta'
                        lw = 7
                    elif is_finish_pass:
                        col = 'orange'
                    elif is_back_pass:
                        col = 'teal'
                    
                    if len(p) > 1:
                        try:
                            p_arr = np.array(p, dtype=float)
                            # VISUAL-ONLY: draw at the roller touch point (tip) instead
                            # of the roller centre when the user asks for it. Path data
                            # itself is unchanged — only this rendered copy moves.
                            if self.params.get("show_tip_paths", False):
                                p_arr = self._shift_path_to_tip(p_arr, self._rtool_for_pass(i))
                            n_pts = len(p_arr)

                            def _seg_poly(pts, straight):
                                if straight or len(pts) <= 2:
                                    return pv.lines_from_points(pts)
                                return pv.Spline(pts, n_points=max(50, min(200, len(pts) * 10)))

                            # path_generator threads the exact straight-line/arc-fillet
                            # boundary indices for linear_approach/linear_full passes — use
                            # them directly instead of guessing where the corner is.
                            splits = self.path_gen.last_render_split_idx.get(i)
                            if splits is not None:
                                line_end = min(splits[0], n_pts - 1)
                                arc_end  = min(max(splits[1], line_end), n_pts - 1)
                                poly = _seg_poly(p_arr[:line_end + 1], straight=True)
                                if arc_end > line_end:
                                    # Arc points are already geometrically exact — render as
                                    # a polyline, no spline smoothing needed.
                                    poly = poly.merge(_seg_poly(p_arr[line_end:arc_end + 1], straight=True))
                                if arc_end < n_pts - 1:
                                    poly = poly.merge(_seg_poly(p_arr[arc_end:], straight=False))
                            else:
                                # Fallback (e.g. back passes, spline mode): detect a sharp
                                # corner (>90°) and split there so Spline doesn't overshoot.
                                split_idx = None
                                if n_pts >= 3:
                                    dirs = np.diff(p_arr, axis=0)
                                    lens = np.linalg.norm(dirs, axis=1, keepdims=True)
                                    dirs_n = dirs / np.where(lens < 1e-10, 1e-10, lens)
                                    dots = np.clip(np.einsum('ij,ij->i', dirs_n[:-1], dirs_n[1:]), -1.0, 1.0)
                                    if dots.min() < 0.0:
                                        split_idx = int(np.argmin(dots)) + 1

                                if split_idx is not None:
                                    poly = _seg_poly(p_arr[:split_idx + 1], straight=False).merge(
                                        _seg_poly(p_arr[split_idx:], straight=False)
                                    )
                                else:
                                    poly = _seg_poly(p_arr, straight=False)

                            self.actors["paths"].append(self.plotter.add_mesh(
                                poly,
                                color=col,
                                line_width=lw,
                                render_lines_as_tubes=True
                            ))
                        except Exception as e:
                            logger.error(f"Render failed path {i}: {e}")
                            try: self.actors["paths"].append(self.plotter.add_lines(p_arr, color=col, width=lw))
                            except: pass
                    else:
                        try: self.actors["paths"].append(self.plotter.add_lines(p, color=col, width=5))
                        except: pass
                    if len(pr) > 0:
                        self.actors["projs"].append(self.plotter.add_mesh(pv.lines_from_points(pr), color='cyan', line_width=1))
                    if is_active:
                        for pt in cps[i]:
                            self.actors["cps"].append(self.plotter.add_points(pt, color='blue', point_size=15, render_points_as_spheres=True))
                # DEBUG ANALYSIS LINES - One line per pass showing minimum clearance
                if self.params.get("show_analysis_lines", False) and len(debug_lines) > 0:
                    all_points = []
                    clearance_values = []
                    
                    for line_data in debug_lines:
                        # Format: [p_pass, p_mandrel, status, clearance_value]
                        if len(line_data) >= 4:
                            p1, p2, status, clearance = line_data
                            all_points.append(p1)
                            all_points.append(p2)
                            clearance_values.append(clearance)
                            clearance_values.append(clearance)  # Same for both points
                    
                    if len(all_points) > 0:
                        lines_arr = np.array(all_points)
                        mesh = pv.PolyData(lines_arr)
                        
                        # Build line cells
                        num_lines = len(all_points) // 2
                        idx = 0
                        cells = []
                        for i in range(num_lines):
                            cells.append(2); cells.append(idx); cells.append(idx+1)
                            idx += 2
                        mesh.lines = np.hstack(cells)
                        
                        # Add clearance as scalar data for heatmap
                        mesh.point_data["Clearance"] = np.array(clearance_values)
                        
                        # Heatmap colour scale. min_safety_gap (the floor) can be 0, which
                        # would collapse the range, so keep a sensible minimum span.
                        target = float(self.params.get("min_safety_gap", self.params.get("target_clearance", 0.5)))
                        scale = max(target, 0.5)
                        clim = [-scale, scale*2]  # Range: -scale to 2*scale
                        
                        actor = self.plotter.add_mesh(
                            mesh, 
                            scalars="Clearance",
                            cmap="RdYlGn",  # Red-Yellow-Green colormap
                            clim=clim,
                            line_width=4,
                            scalar_bar_args={"title": "Clearance (mm)", "vertical": True, "position_x": 0.85}
                        )
                        self.actors["analysis_lines"].append(actor)
                # Render Rapids (Dashed Lines for G0)
                if self.params.get("show_rapids", True):
                    for r_seg in rapids:
                        if len(r_seg) < 2: continue
                        try:
                            act = self.plotter.add_lines(r_seg, color='orange', width=2)
                            prop = act.GetProperty()
                            prop.SetLineStipplePattern(0xFF00)
                            prop.SetLineStippleRepeatFactor(2)
                            self.actors["rapids"].append(act)
                        except: pass

                if len(paths) > 0 and len(paths[0]) > 0:
                     self.actors["approach"] = self.plotter.add_lines(np.array([roller_pos, paths[0][0]]), color='black', width=1)

                # Distance lines: mandrel surface → closest contact point per pass
                if self.params.get("show_pass_dist_lines", False):
                    try:
                        center_x = self.params.get("mandrel_pos_x_offset", 0.0)
                        side = 1.0 if self.params.get("roller_positive_x_side", True) else -1.0
                        # Build pass type list to distinguish finishing from roughing
                        pass_types = []
                        for op in self.params.get("operations", []):
                            if not op.get("enabled", True): continue
                            for _ in range(int(op.get("count", 1))):
                                pass_types.append(op.get("type", "roughing"))
                        label_pts, label_txts = [], []
                        for pi, path in enumerate(paths):
                            if len(path) == 0: continue
                            pts = np.array(path)
                            is_finish = (pi < len(pass_types) and pass_types[pi] == "finishing")
                            if is_finish:
                                # Use end point — finishing passes end at the mandrel surface
                                contact = pts[-1]
                            else:
                                # Roughing: find closest point to axis, interpolate if sparse
                                if len(pts) < 10:
                                    t = np.linspace(0, 1, 50)
                                    pts = np.array([pts[0] + ti * (pts[-1] - pts[0]) for ti in t])
                                ci = int(np.argmin(np.abs(pts[:, 0] - center_x)))
                                contact = pts[ci]
                            mandrel_x = center_x + side * self.mandrel_mgr.get_radius_fast(contact[2])
                            surface_pt = np.array([mandrel_x, 0.0, contact[2]])
                            actual_dist = abs(float(contact[0] - mandrel_x))
                            act = self.plotter.add_lines(np.array([surface_pt, contact]), color='black', width=2)
                            self.actors["pass_dist_lines"].append(act)
                            # Label placed at contact point, shifted outward to avoid overlap with line
                            lbl_pos = [contact[0], 0.0, contact[2] + 10]
                            label_pts.append(lbl_pos)
                            label_txts.append(f"{actual_dist:.1f}mm")
                        if label_pts:
                            act = self.plotter.add_point_labels(
                                np.array(label_pts), label_txts,
                                point_size=0, font_size=10, text_color='magenta',
                                always_visible=True, shape=None
                            )
                            self.actors["pass_dist_lines"].append(act)
                    except Exception as e:
                        logger.warning(f"Distance lines render failed: {e}")

        # 4. Roller & Measurement
        if update_type in ["all", "paths", "visual"]:
            # Deformed-blank overlay (#63) — redraws here so it tracks the active pass
            # (pass-stepping calls update_scene("paths")). Faded blue, purely visual.
            self.update_deformed_blank(render=False)
            if self.actors["roller"]: self.plotter.remove_actor(self.actors["roller"])
            if self.actors.get("roller_tip"): self.plotter.remove_actor(self.actors["roller_tip"]); self.actors["roller_tip"] = None

            # Try to load roller shape from tool's STEP file
            roller_mesh = None
            try:
                ops = self.params.get("operations", [])
                active_idx = getattr(self, "active_editing_pass_idx", -1)
                total = 0
                active_op = ops[0] if ops else None
                for op in ops:
                    if not op.get("enabled", True):
                        continue
                    cnt = int(op.get("count", 1))
                    if active_idx >= 0 and active_idx < total + cnt:
                        active_op = op
                        break
                    total += cnt
                if active_op:
                    tid = active_op.get("tool_id", "")
                    tool_entry = next((t for t in self.tool_library if t.get("id") == tid), None)
                    if tool_entry:
                        # Tilt-arm machines (ID112): show the roller at the tilt it
                        # would have at this position, from the active op's tilt mode.
                        _static_tilt = 0.0
                        try:
                            from kinematics import get_kinematics as _get_kin
                            _kin = _get_kin(self.params)
                            if _kin is not None:
                                _static_tilt = float(self.path_gen._compute_tilt_for_path(
                                    np.array([[rx_tip, 0.0, rz_tip]]),
                                    active_op, self.mandrel_mgr, _kin)[0])
                        except Exception as _te:
                            logger.debug(f"Static roller tilt: {_te}")
                        roller_mesh = self.tool_step_loader.get_roller_mesh(
                            tool_entry, _side, rx_tip, rz_tip, tilt_deg=_static_tilt)
            except Exception as _e:
                logger.debug(f"Tool STEP roller: {_e}")

            if roller_mesh is None:
                roller_mesh = pv.Sphere(radius=r_rad, center=roller_pos, theta_resolution=30, phi_resolution=30)

            r_color = 'red' if gap_x < 0 else 'darkgoldenrod'
            self.actors["roller"] = self.plotter.add_mesh(roller_mesh, color=r_color, smooth_shading=True)

            # Tip indicator — small bright sphere at the exact contact point
            tip_mesh = pv.Sphere(radius=2.0, center=(rx_tip, 0.0, rz_tip))
            self.actors["roller_tip"] = self.plotter.add_mesh(tip_mesh, color='lime', smooth_shading=True)

            if self.actors.get("dist_line"): self.plotter.remove_actor(self.actors["dist_line"]); self.actors["dist_line"] = None
            if self.actors.get("dist_label"): self.plotter.remove_actor(self.actors["dist_label"]); self.actors["dist_label"] = None

            # Home gap indicator: mandrel edge → roller edge (hidden when tip distance is shown)
            if not self.params.get("show_tip_distance", False):
                try:
                    side = 1.0 if self.params.get("roller_positive_x_side", True) else -1.0
                    center_x = self.params.get("mandrel_pos_x_offset", 0.0)
                    clamped_z = _clamped_z
                    clamped_r = _clamped_r
                    m_edge_x = center_x + side * clamped_r
                    r_edge_x = rx_center - side * r_rad
                    gap_line_pts = np.array([[m_edge_x, 0.0, rz_tip], [r_edge_x, 0.0, rz_tip]])
                    edge_gap = (r_edge_x - m_edge_x) * side
                    self.actors["dist_line"] = self.plotter.add_lines(gap_line_pts, color='red', width=3)
                    gap_lbl = f"HOME GAP\n{edge_gap:+.1f}mm" if edge_gap >= 0 else f"HOME GAP\n{edge_gap:.1f}mm COLLISION"
                    mid_x = (m_edge_x + r_edge_x) / 2.0
                    self.actors["dist_label"] = self.plotter.add_point_labels(
                        np.array([[mid_x, 0.0, rz_tip + (r_rad + 15) / 2.0]]), [gap_lbl],
                        point_size=0, font_size=11, text_color='red',
                        always_visible=True, shape=None
                    )
                except Exception as e:
                    logger.warning(f"Home gap indicator failed: {e}")
            
            # [NEW] Position Labels
            if self.actors.get("pos_labels"): self.plotter.remove_actor(self.actors["pos_labels"])
            
            lbl_points = []
            lbl_texts = []
            
            # 1. Roller Tip
            lbl_points.append([rx_tip, 0, rz_tip + r_rad + 20])
            lbl_texts.append(f"Roller Tip\nX: {rx_tip:.1f}\nZ: {rz_tip:.1f}")
            
            # 2. Mandrel Origin (if offset)
            mx = self.params["mandrel_pos_x_offset"]
            mz = self.params["mandrel_pos_z_offset"]
            if abs(mx) > 1 or abs(mz) > 1:
                lbl_points.append([mx, 0, mz])
                lbl_texts.append(f"Mandrel Zero\nX:{mx:.1f} Z:{mz:.1f}")
                
            self.actors["pos_labels"] = self.plotter.add_point_labels(
                lbl_points, lbl_texts, point_size=0, font_size=14, text_color='black',
                always_visible=True, fill_shape=True, shape_color='white', shape_opacity=0.6
            )

            # Tip-distance indicator (checkbox-controlled, display only)
            for a in self.actors.get("tip_dist", []):
                try: self.plotter.remove_actor(a)
                except: pass
            self.actors["tip_dist"] = []

            if self.params.get("show_tip_distance", False):
                try:
                    _side   = 1.0 if self.params.get("roller_positive_x_side", True) else -1.0
                    _cx     = float(self.params.get("mandrel_pos_x_offset", 0.0))
                    _m_minz = self.mandrel_mgr.props.get("min_z", 0.0)
                    _m_topz = self.mandrel_mgr.props.get("top_z", rz_tip)
                    _cz     = max(_m_minz, min(_m_topz, rz_tip))
                    _mr     = self.mandrel_mgr.get_radius_fast(_cz)
                    _mx     = _cx + _side * _mr          # mandrel surface X at tip Z

                    dx = (rx_tip - _mx) * _side          # radial gap (+ = clear, - = collision)
                    dz = rz_tip - _m_minz                # Z from mandrel base to tip

                    # Horizontal line: tip → mandrel surface
                    self.actors["tip_dist"].append(
                        self.plotter.add_lines(
                            np.array([[rx_tip, 0.0, rz_tip], [_mx, 0.0, rz_tip]]),
                            color='orange', width=3))

                    # Vertical line: mandrel base → tip
                    self.actors["tip_dist"].append(
                        self.plotter.add_lines(
                            np.array([[rx_tip, 0.0, _m_minz], [rx_tip, 0.0, rz_tip]]),
                            color='cyan', width=3))

                    # Labels
                    _lx_mid = (rx_tip + _mx) / 2.0
                    _lz_mid = (_m_minz + rz_tip) / 2.0
                    _lbl_offset = _side * (r_rad + 10)
                    for _pt, _lbl, _tc in [
                        ([_lx_mid,             0.0, rz_tip + r_rad + 8], f"ΔX = {dx:+.1f} mm", 'orange'),
                        ([rx_tip + _lbl_offset, 0.0, _lz_mid],            f"ΔZ = {dz:.1f} mm",  'cyan'),
                        ([rx_tip,              0.0, rz_tip - r_rad - 8], "TIP  (0, 0)",          'yellow'),
                    ]:
                        self.actors["tip_dist"].append(
                            self.plotter.add_point_labels(
                                np.array([_pt]), [_lbl],
                                point_size=0, font_size=12,
                                text_color=_tc, always_visible=True, shape=None
                            )
                        )
                except Exception as _e:
                    logger.warning(f"Tip distance display failed: {_e}")

        # 5. Camera
        if update_type in ["all", "camera"]:
            az = math.radians(self.params.get("cam_azimuth", 0.0))
            el = math.radians(self.params.get("cam_elevation", 0.0))
            dist = 800; cx = self.params["mandrel_pos_x_offset"]
            new_x = cx + dist * math.cos(el) * math.sin(az)
            new_y = dist * math.cos(el) * math.cos(az)
            new_z = 50 + dist * math.sin(el)
            self.plotter.camera.position = (new_x, new_y, new_z)
            self.plotter.camera.focal_point = (cx, 0, 50)
            self.plotter.camera.up = (0, 0, 1)
            self.plotter.camera.roll = self.params["cam_roll"]
            
        # Fix Visual Bug: Update Grid logic dynamically
        self._update_grid_dynamic()

        # Placeable X/Z scale bars (visual only)
        self._update_rulers()

    def _render_rulers_only(self):
        """Redraw ONLY the placeable scale bars, then render once — no camera
        reset and no path recalc. Used by the ruler controls (mode="rulers") so
        adjusting a ruler is a static, cheap visual update."""
        _was = bool(getattr(self.plotter, "suppress_rendering", False))
        self.plotter.suppress_rendering = True
        try:
            self._update_rulers()
        finally:
            self.plotter.suppress_rendering = _was
        if not _was:
            try:
                self.plotter.render()
            except Exception:
                pass

    def _update_rulers(self):
        """Draw two placeable scale bars — one along X, one along Z — as a visual
        overlay. Purely cosmetic: never touches toolpaths or G-code.

        Placement (where the bar sits, perpendicular to what it measures):
          ruler_x_at_z -> Z level the horizontal X-ruler sits at
          ruler_z_at_x -> X level the vertical Z-ruler sits at
        Extent + direction (along the axis the bar measures):
          ruler_x_start / ruler_x_end -> X ruler runs Start -> End
          ruler_z_start / ruler_z_end -> Z ruler runs Start -> End
        Labels read the distance FROM the Start mark (0 at Start), so the Start is
        the ruler's zero and Start -> End sets the direction. When End == Start the
        extent auto-fits the visible scene (mandrel/roller/shell/blank), anchored at
        Start — so the factory default Start=0 makes the labels read machine X / Z.
        """
        for key in ("ruler_x", "ruler_z"):
            a = self.actors.get(key)
            if a is not None:
                try: self.plotter.remove_actor(a)
                except Exception: pass
                self.actors[key] = None

        if not self.params.get("show_rulers", False):
            return

        # Scene bounds from the visible solid actors (same set the grid uses).
        xmin, xmax, zmin, zmax = 0.0, 100.0, 0.0, 100.0
        got = False
        for k in ("mandrel", "roller", "shell", "blank"):
            act = self.actors.get(k)
            if act and act.GetVisibility():
                b = act.GetBounds()
                if not got:
                    xmin, xmax, zmin, zmax = b[0], b[1], b[4], b[5]
                    got = True
                else:
                    xmin = min(xmin, b[0]); xmax = max(xmax, b[1])
                    zmin = min(zmin, b[4]); zmax = max(zmax, b[5])
        xmin = max(xmin, -500.0); zmin = max(zmin, -500.0)

        def _auto_end(start, lo, hi, step=50.0):
            """End when the user leaves it equal to Start: extend from Start toward
            whichever scene edge is farther, rounded out to a clean multiple of
            `step` so major labels land on round mm."""
            edge = hi if abs(hi - start) >= abs(lo - start) else lo
            if abs(edge - start) < step:
                edge = start + (step if edge >= start else -step)
            return (math.ceil(edge / step) * step) if edge >= 0 else (math.floor(edge / step) * step)

        z_at = float(self.params.get("ruler_x_at_z", 0.0))
        x_at = float(self.params.get("ruler_z_at_x", 0.0))
        x_start = float(self.params.get("ruler_x_start", 0.0))
        x_end   = float(self.params.get("ruler_x_end", 0.0))
        z_start = float(self.params.get("ruler_z_start", 0.0))
        z_end   = float(self.params.get("ruler_z_end", 0.0))
        if x_end == x_start:
            x_end = _auto_end(x_start, xmin, xmax)
        if z_end == z_start:
            z_end = _auto_end(z_start, zmin, zmax)

        def _n_labels(span):
            return max(2, int(abs(span) / 50.0) + 1)   # a major tick every 50 mm

        # plotter.add_ruler() hardcodes reset_camera=True (re-fits the view to all
        # actors), so redrawing the scale bars would zoom the camera away on every
        # ruler tweak — and on every scene update while rulers are on. Snapshot the
        # camera and restore it after, keeping the bars a static overlay (user
        # report 2026-07-08).
        _cam = self.plotter.camera_position
        try:
            self.actors["ruler_x"] = self.plotter.add_ruler(
                pointa=(x_start, 0.0, z_at), pointb=(x_end, 0.0, z_at),
                title="X mm", number_labels=_n_labels(x_end - x_start), label_format="%.0f",
                number_minor_ticks=4, tick_length=6, minor_tick_length=3,
                font_size_factor=0.5, label_color="black", tick_color="black")
        except Exception as e:
            logger.warning(f"X ruler render failed: {e}")
        try:
            self.actors["ruler_z"] = self.plotter.add_ruler(
                pointa=(x_at, 0.0, z_start), pointb=(x_at, 0.0, z_end),
                title="Z mm", number_labels=_n_labels(z_end - z_start), label_format="%.0f",
                number_minor_ticks=4, tick_length=6, minor_tick_length=3,
                font_size_factor=0.5, label_color="black", tick_color="black")
        except Exception as e:
            logger.warning(f"Z ruler render failed: {e}")
        try:
            self.plotter.camera_position = _cam   # undo add_ruler's forced re-fit
        except Exception:
            pass

    def _active_fwd_pass_idx(self):
        """Map active_editing_pass_idx (a toolpath-list index, which includes
        interleaved back-pass entries) to the forward-pass index PathGenerator
        keys per-pass overrides by (its global_pass_idx). A back-pass entry maps
        to its parent forward pass, so an override edited while a back pass is
        selected applies to the forward pass it mirrors. Mirrors the layout in
        calculate_paths: one global_pass_idx per forward pass / cutting / bending,
        and a stride-2 toolpath layout (forward, back) when back_pass_enabled.
        """
        tp_idx = self.active_editing_pass_idx
        fwd = 0
        entry = 0
        for op in self.params.get("operations", []):
            if not op.get("enabled", True):
                continue
            is_cb  = op.get("type", "roughing") in ("cutting", "bending")
            count  = 1 if is_cb else int(op.get("count", 1))
            stride = 1 if is_cb else (2 if op.get("back_pass_enabled", False) else 1)
            for _ in range(count):
                if entry == tp_idx:
                    return fwd
                entry += 1
                if stride == 2:
                    if entry == tp_idx:   # back-pass entry → parent forward pass
                        return fwd
                    entry += 1
                fwd += 1
        return fwd

    # --- WRAPPERS ---
    def on_param_change(self, key, val, mode="paths"):
        # Helper for type conversion (Fix for Phase 17 strings like "T0101")
        def convert(v):
            if isinstance(v, bool): return v
            try: return float(v)
            except: return v
        real_val = convert(val)

        # Machine-profile keys (home_x/z, offsets, workspace, gcode output, …) belong
        # to the active machine profile, not to per-pass overrides or the paths params.
        # They must (a) never be routed into gui_pass_overrides and (b) be auto-persisted
        # to the profile file so edits survive a restart (settings.json excludes them).
        from machine_loader import MACHINE_PROFILE_KEYS
        _is_machine_key = key in MACHINE_PROFILE_KEYS

        # Handle Overrides (Assume only simple keys for now)
        # gui_pass_overrides is keyed in PathGenerator's forward-pass index space
        # (global_pass_idx), NOT the raw toolpath index — back-pass selections map
        # to their parent forward pass so the override actually takes effect.
        if self.apply_to_specific_pass_only and mode == "paths" and "[" not in key and not _is_machine_key:
            _ovr_idx = self._active_fwd_pass_idx()
            if _ovr_idx not in self.gui_pass_overrides: self.gui_pass_overrides[_ovr_idx] = {}
            self.gui_pass_overrides[_ovr_idx][key] = real_val
        else:
            # Handle Nested Keys (e.g. "operations[0].tool_id")
            updated = False
            if key.startswith("operations[") and "]." in key:
                try:
                    idx_end = key.find("]")
                    if idx_end > 11:
                        idx = int(key[11:idx_end])
                        field = key[idx_end+2:]
                        if "operations" in self.params and 0 <= idx < len(self.params["operations"]):
                            self.params["operations"][idx][field] = real_val
                            updated = True
                except: pass
            
            if not updated:
                # Mandrel Z Offset değişince Zone Start Z de aynı miktarda kayar.
                # Mandrel, sheet ve path origin hep birlikte hareket etmeli.
                if key == "mandrel_pos_z_offset":
                    delta = real_val - self.params.get("mandrel_pos_z_offset", 0.0)
                    ops = self.params.get("operations", [])
                    for op in ops:
                        op["start_z"] = op.get("start_z", 0.0) + delta
                    # Legacy param da güncelle
                    self.params["first_pass_p2_contact_z_abs"] = self.params.get("first_pass_p2_contact_z_abs", 0.0) + delta
                self.params[key] = real_val

        # Auto-persist machine-profile edits to the active profile file so the value
        # survives a restart without the user having to click "Save Machine Profile".
        if _is_machine_key:
            self.autosave_machine_profile()

        # [PHASE 8] ULTRA-STRICT Manual Check
        # User requested zero stutter ("visual loading glitches").
        # If mode requires calculation, we SKIP update_scene entirely.
        # Only HESAPLA button (force_calc) calls update_scene directly.
        if mode in ["paths", "shell_and_paths"]:
             if not self.params.get("auto_calculate_paths", False):
                 return

        # Placeable X/Z scale bars are a pure visual overlay: redraw ONLY them.
        # Going through update_scene("all") would reset the camera (line ~1320)
        # and, with auto-calc on, re-run path generation — so every small ruler
        # nudge "zoomed the camera away" and recalculated (user report 2026-07-08).
        if mode == "rulers":
            self._render_rulers_only()
            return

        self.update_scene(mode)

    def autosave_machine_profile(self):
        """Silently write the current machine-profile params to the active profile file.

        settings.json deliberately excludes MACHINE_PROFILE_KEYS (the profile is the
        source of truth, applied over settings on load), so without this the values are
        only persisted when the user clicks "Save Machine Profile". Called on every
        machine-tab edit so those changes survive a restart. No-op if no profile/path.
        """
        profile = getattr(self, "active_machine_profile", None)
        if not profile:
            return
        path = profile.get("_path", "")
        if not path:
            return
        try:
            from machine_loader import MACHINE_PROFILE_KEYS, save_machine_profile
            for k in MACHINE_PROFILE_KEYS:
                if k in self.params:
                    profile[k] = self.params[k]
            save_machine_profile(path, profile)
        except Exception as e:
            logger.error(f"Machine profile autosave failed: {e}")

    def update_slider_and_param(self, key, val, slider_widget, mode):
        rep = slider_widget.GetRepresentation()
        if val < rep.GetMinimumValue(): val = rep.GetMinimumValue()
        if val > rep.GetMaximumValue(): val = rep.GetMaximumValue()
        rep.SetValue(val)
        self.on_param_change(key, val, mode)

    def adjust_val_wrapper(self, key, delta, slider_widget, mode):
        rep = slider_widget.GetRepresentation()
        current = rep.GetValue()
        self.update_slider_and_param(key, current + delta, slider_widget, mode)

    def ask_val_wrapper(self, key, prompt, slider_widget, mode):
        rep = slider_widget.GetRepresentation()
        current = rep.GetValue()
        new_val = self.ui.ask_float("Deger Gir", f"{prompt} icin yeni deger:", current)
        if new_val is not None:
            self.update_slider_and_param(key, new_val, slider_widget, mode)
            
    def cb_idx(self, v):
        self.active_editing_pass_idx = int(round(v))
        self.update_scene("paths")
        # #63: refresh the deformed-blank overlay for the newly selected pass (cheap; no recalc).
        self.update_deformed_blank(render=True)
        
    def cb_scroll(self, v): 
        self.params["last_scroll_val"] = v
        self.ui.update_positions(v, self.params["show_advanced_sliders"], self.params["show_visual_sliders"])
        
    def toggle_tabs(self, tab_name):
        self.params["show_advanced_sliders"] = (tab_name == "advanced")
        self.params["show_visual_sliders"] = (tab_name == "visual")
        self.cb_scroll(self.params.get("last_scroll_val", 100.0))
        
    def toggle_scope(self, v): 
        self.apply_to_specific_pass_only = bool(v)

    def update_roller_visual(self, pos, current_radius, tilt_deg=None):
        """Fast update for simulation loop — called at ~50 fps from check_sim_loop.
        pos: roller CENTER in global coords. current_radius: r_tool for the active cut.
        tilt_deg: B tilt for tilt-arm machines (None on plain XZ machines).

        Strategy: rebuild the actor only when tool/side/radius changes (rare).
        Every other tick just calls actor.SetPosition() — zero allocation, no flicker.
        Both STEP and sphere meshes are built with their tip at local (0,0,0) so the
        same SetPosition(rx_tip, 0, rz_tip) call moves either one correctly; tilt is
        applied per tick with SetOrientation (also allocation-free) about the tip.
        """
        _side = 1.0 if self.params.get("roller_positive_x_side", True) else -1.0
        rx_tip = float(pos[0]) - _side * current_radius
        rz_tip = float(pos[2])

        tid = getattr(self.sim_controller, "current_tool_id", "")

        need_rebuild = (
            not self.actors.get("roller") or
            getattr(self, "_sim_last_tool_id", None) != tid or
            getattr(self, "_sim_last_side", None) != _side or
            getattr(self, "_sim_last_radius", None) != current_radius
        )

        if need_rebuild:
            if self.actors.get("roller"):
                self.plotter.remove_actor(self.actors["roller"])
            if self.actors.get("roller_tip"):
                self.plotter.remove_actor(self.actors["roller_tip"])
                self.actors["roller_tip"] = None

            # Build mesh with tip anchored at local (0,0,0)
            roller_mesh = None
            try:
                if tid:
                    tool_entry = next((t for t in self.tool_library if t.get("id") == tid), None)
                    if tool_entry:
                        roller_mesh = self.tool_step_loader.get_canonical_mesh(tool_entry, _side)
            except Exception as _e:
                logger.debug(f"Sim STEP roller build: {_e}")

            if roller_mesh is None:
                # Sphere with center at (_side * r_rad, 0, 0) so its tip sits at (0,0,0)
                roller_mesh = pv.Sphere(radius=current_radius,
                                        center=(_side * current_radius, 0.0, 0.0),
                                        theta_resolution=24, phi_resolution=24)

            try:
                self.actors["roller"] = self.plotter.add_mesh(roller_mesh, color='orange', smooth_shading=True)
                tip_mesh = pv.Sphere(radius=2.0, center=(0.0, 0.0, 0.0))
                self.actors["roller_tip"] = self.plotter.add_mesh(tip_mesh, color='lime', smooth_shading=True)
            except Exception as e:
                logger.error(f"Roller rebuild error: {e}")
                return

            self._sim_last_tool_id = tid
            self._sim_last_side = _side
            self._sim_last_radius = current_radius

        # Fast path — just translate the existing actors; no remove/add = no flicker
        try:
            if self.actors.get("roller"):
                self.actors["roller"].SetPosition(rx_tip, 0.0, rz_tip)
                if tilt_deg is not None:
                    # Actor origin = mesh local (0,0,0) = tool tip, so this
                    # rotates about the tip. Sign matches _position_mesh.
                    self.actors["roller"].SetOrientation(0.0, -_side * float(tilt_deg), 0.0)
            if self.actors.get("roller_tip"):
                self.actors["roller_tip"].SetPosition(rx_tip, 0.0, rz_tip)
        except Exception as e:
            logger.error(f"Roller move error: {e}")

    def recolor_paths(self):
        """Mevcut pas aktörlerinin rengini yeniden boyar — hesaplama yapmaz, anlık."""
        if not self.actors.get("paths"):
            return

        ops = self.params.get("operations", [])
        op_types = []
        for op in ops:
            if not op.get("enabled", True): continue
            op_type = op.get("type", "roughing")
            is_cb   = op_type in ("cutting", "bending")
            count   = 1 if is_cb else int(op.get("count", 1))
            has_back = not is_cb and op.get("back_pass_enabled", False)
            for _ in range(count):
                op_types.append(op_type)
                if has_back:
                    op_types.append("back")

        for i, actor in enumerate(self.actors["paths"]):
            is_active  = (i == self.active_editing_pass_idx)
            _ptype     = op_types[i] if i < len(op_types) else "roughing"
            is_finish  = (_ptype == "finishing")
            is_back    = (_ptype == "back")

            prop = actor.GetProperty()
            if is_active:
                prop.SetColor(1.0, 0.0, 1.0)   # magenta
                prop.SetLineWidth(7)
            elif is_finish:
                prop.SetColor(1.0, 0.65, 0.0)  # orange
                prop.SetLineWidth(5)
            elif is_back:
                prop.SetColor(0.0, 0.5, 0.5)   # teal
                prop.SetLineWidth(5)
            else:
                prop.SetColor(0.0, 0.0, 1.0)   # blue
                prop.SetLineWidth(5)
        try:
            self.plotter.render()
        except: pass

    def rotate_mandrel(self, axis):
        key = f"mandrel_rot_{axis}"
        self.params[key] = (self.params[key] + 90.0) % 360.0
        self.update_scene("all")

    def load_step_file(self, path):
        if not os.path.exists(path): return False
        self.step_file_path_global = path

        # Reload Mandrel
        success = self.mandrel_mgr.load_step(path)
        if success:
            logger.info(f"Loaded STEP: {path}")
            # Geometriyi önce hesapla ki props dolsun
            self.mandrel_mgr.update_geometry(
                self.params["mandrel_rot_x"], self.params["mandrel_rot_y"], self.params["mandrel_rot_z"],
                self.params["mandrel_pos_x_offset"], self.params["mandrel_pos_z_offset"]
            )
            # Blank radius'u mandrel tabanıyla otomatik eşleştir
            # Only auto-set if this is a different STEP file than last time,
            # so a saved blank_radius is not overwritten on reopen.
            base_r = self.mandrel_mgr.props.get("br", 0.0)
            if base_r > 1.0 and path != self.params.get("last_step_path", ""):
                self.params["blank_radius"] = round(base_r * 1.1, 1)  # %10 fazla: sacın mandrel'den büyük olması lazım
                logger.info(f"Auto-set blank_radius to {self.params['blank_radius']:.1f} (mandrel br={base_r:.1f})")
            self.params["last_step_path"] = path
            # Path başlangıcını mandrel tabanına sync et — blank ve path aynı Z'de başlar
            mandrel_base_z = self.mandrel_mgr.props.get("min_z", self.params["mandrel_pos_z_offset"])
            self.params["first_pass_p2_contact_z_abs"] = mandrel_base_z
            logger.info(f"Auto-set first_pass_p2_contact_z_abs to {mandrel_base_z:.1f} (mandrel base)")
            self.update_scene("all", force_path_calc=True)
            return True
        return False

    def save_gcode(self, v, filepath=None):
        if v:
            try:
                code = self.path_gen.generate_gcode(params=self.params)

                if filepath:
                    out_path = filepath
                else:
                    out_path = os.path.join(self.get_base_path(), "spinning_output.nc")

                with open(out_path, "w") as f: f.write(code)
                logger.info(f"G-Code saved to {out_path}")
            except Exception as e:
                logger.error(f"G-Code save failed: {e}", exc_info=True)

    def save_project(self, filepath):
        if filepath:
            try:
                with open(filepath, "w") as f: 
                    json.dump({"params": self.params, "overrides": self.gui_pass_overrides, "step": self.step_file_path_global}, f)
                logger.info(f"Project saved to {filepath}")
                return True
            except Exception as e:
                logger.error(f"Failed to save project: {e}")
                return False
        return False

    def load_project(self, filepath):
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    d = json.load(f)
                    # The Basic/Advanced view switch is a global app preference,
                    # not a per-program setting — preserve it across a load.
                    _show_adv = self.params.get("op_view_show_advanced", False)
                    loaded_params = d.get("params", {})
                    self.params.update(loaded_params)
                    self.params["op_view_show_advanced"] = _show_adv
                    # Customize-View column/tag config IS per program: if the
                    # loaded file has none, drop any stale in-memory config so
                    # the resolver falls back to sensible defaults.
                    if "op_view_config" not in loaded_params:
                        self.params.pop("op_view_config", None)
                    try:
                        from config_schema import migrate_clearance
                        migrate_clearance(self.params)
                    except Exception:
                        pass
                    # Check overrides format
                    ovr = d.get("overrides", {})
                    self.gui_pass_overrides = {int(k):v for k,v in ovr.items()}
                    
                    self.step_file_path_global = d.get("step", self.step_file_path_global)
                    if self.step_file_path_global and os.path.exists(self.step_file_path_global): 
                        self.mandrel_mgr.load_step(self.step_file_path_global)
                        
                    self.update_scene("all", force_path_calc=True)
                    logger.info(f"Project loaded from {filepath}")
                    return True
            except Exception as e:
                logger.error(f"Failed to load project: {e}")
                return False
        return False

    def _build_ui(self):
        self.ui.build_interface(self)

    def run(self):
        # Startup Step Loading (CLI entry point — not used by the GUI)
        inp = input("STEP Dosyası Yolu > ").strip()
        self.step_file_path_global = inp
        if not self.mandrel_mgr.load_step(inp): 
            self.mandrel_mgr.create_default_cone()
            print("[BILGI] Varsayılan koni oluşturuldu.")
        
        # Initial geometry update
        self.update_scene("all", force_path_calc=True)
        self.plotter.show()

if __name__ == "__main__":
    app = SpinningApp()
    app.run()