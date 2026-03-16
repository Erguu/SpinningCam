import pyvista as pv
import json
import os
import sys
import numpy as np
import math
import tkinter as tk
from tkinter import filedialog
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from gui_manager import GuiManager
from simulation_controller import SimulationController
from logger_config import logger

class SpinningApp:
    def __init__(self, plotter=None, headless=False):
        # 1. Initialize Managers
        self.mandrel_mgr = MandrelManager()
        self.path_gen = PathGenerator()
        
        # 2. State Variables
        self.params = self.load_settings()
        self.gui_pass_overrides = {}
        self.active_editing_pass_idx = 0
        self.apply_to_specific_pass_only = False
        self.step_file_path_global = ""
        self.headless = headless
        
        # 3. Actors Dictionary
        self.actors = {
            "mandrel": None, "blank": None, "roller": None, 
            "paths": [], "projs": [], "cps": [], "labels": [], "approach": None, "shell": None,
            "dist_line": None, "dist_label": None,
            "anim_roller": None
        }

        # 4. Setup Plotter & UI
        # 1. Plotter Setup
        # Create a PyVista Plotter (Standard)
        # We will embed it later.
        self.plotter = pv.Plotter(window_size=(1000, 800), title="SpinningCam3D")
        self.plotter.set_background('white')
        self._setup_scene_basics()
        
        # 2. Managers
        self.mandrel_mgr = MandrelManager()
        self.path_gen = PathGenerator()
        # UI Manager'i sadece headless degilse ve harici plotter (QT) yoksa varsayılan modda baslat
        # Ancak QT modunda "GuiManager" kullanmayacagız, sidebar kullanacagız.
        # Bu yüzden headless=True ise GuiManager'i es geçiyoruz.
        
        if not self.headless:
            self.ui = GuiManager(self.plotter)
            self.sim_controller = SimulationController(self.plotter, self.ui, lambda: self.actors)
            self._build_ui()
            # Initial Update
            self.ui.update_positions(100.0, False, False)
        else:
            self.ui = None
            # Headless modda sim controller UI olmadan calismali
            # SimulationController UI'a bagimli (self.ui.root.update vs).
            # Şimdilik headless modda sim controller devre dışı veya dummy olabilir.
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
            "auto_align_rotation": False,
            "calc_active": True,
            "cam_azimuth": 0.0, "cam_elevation": 0.0, "cam_roll": 90.0,
            "mandrel_rot_x": 0.0, "mandrel_rot_y": 0.0, "mandrel_rot_z": 0.0,
            "mandrel_pos_x_offset": 0.0, "mandrel_pos_z_offset": 0.0,
            "p1_p3_x_offset_from_p2": 40.0, 
            "p1_z_offset_from_p2": 50.0, 
            "p3_z_offset_from_p2": -20.0,
            "roughing_step_radial": 1.0,
            "last_pass_extension_z": 0.0,
            "roller_nose_radius_param": 10.0, "final_part_thickness_on_mandrel": 2.0, "safety_clearance_roller_to_part": 0.5,
            "shell_thickness": 2.0, "blank_radius": 120.0, "blank_z_shift": 0.0,
            "roller_visual_radius": 25.0, 
            "roller_visual_x_offset": 30.0, 
            "roller_visual_z_offset": 0.0,
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
            
            # Tool Change Params
            "tool_change_active": False,
            "rough_tool_number": "T0101",
            "finish_tool_number": "T0202",
            "finish_tool_radius": 25.0,
            
            # Finishing Group Defaults (Dual Control) - Matched to Rough for consistent size
            "finish_p1_p3_x_offset_from_p2": 40.0,
            "finish_p1_z_offset_from_p2": 50.0,
            "finish_p3_z_offset_from_p2": -20.0,
            "finish_y_rotation_degrees": 0.0,
            "finish_p3_z_offset_from_p2": -20.0,
            "finish_y_rotation_degrees": 0.0,
            "finish_step_radial": 0.0, # Added for Finish Options
            
            # V5 Adaptive
            "adaptive_finish_mode": False,
            "adaptive_resolution": 0.5,
        }
        
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
        return default_params

    def save_settings_json(self):
        try:
            base_path = self.get_base_path()
            json_path = os.path.join(base_path, "settings.json")
            with open(json_path, "w", encoding='utf-8') as f:
                json.dump(self.params, f, indent=4)
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
        
        # Update Grid
        self.plotter.show_grid(bounds=bounds, color='black')

    def update_scene(self, update_type="all", force_path_calc=False):
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
        
        # Decoupled from blank_radius (User request)
        rx_center = self.params["mandrel_pos_x_offset"] + r_rad + self.params["roller_visual_x_offset"]
        rz_center = self.params["mandrel_pos_z_offset"] + 2 + r_rad + self.params["roller_visual_z_offset"]
        
        rx_tip = rx_center - r_rad 
        rz_tip = rz_center
        
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
        
        mandrel_radius_at_z = self.mandrel_mgr.get_radius_fast(rz_tip)
        mandrel_surface_x = self.params["mandrel_pos_x_offset"] + mandrel_radius_at_z
        gap_x = rx_tip - mandrel_surface_x
        dist_z = rz_tip - self.params["mandrel_pos_z_offset"]
        blank_z = self.params["mandrel_pos_z_offset"] + self.params["blank_z_shift"]

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

            if self.actors["blank"]: self.plotter.remove_actor(self.actors["blank"])
            cyl = pv.Cylinder(center=(self.params["mandrel_pos_x_offset"], 0, blank_z), 
                            direction=(0,0,1), radius=self.params["blank_radius"], height=2)
            self.actors["blank"] = self.plotter.add_mesh(cyl, color='deepskyblue', opacity=0.4)

        # 2. Shell
        if update_type in ["all", "shell", "shell_and_paths"]:
            if self.actors["shell"]: self.plotter.remove_actor(self.actors["shell"])
            shell_grid = self.mandrel_mgr.generate_shell_mesh(self.params["shell_thickness"], self.params["mandrel_pos_x_offset"])
            if shell_grid:
                self.actors["shell"] = self.plotter.add_mesh(shell_grid, color='lime', opacity=0.3, smooth_shading=True)

        # 3. Paths
        if update_type in ["all", "paths", "shell_and_paths", "visual"] and (self.params.get("auto_calculate_paths", False) or force_path_calc):
            # Ensure rapids key exists
            if "rapids" not in self.actors: self.actors["rapids"] = []
            
            for a in self.actors["paths"] + self.actors["projs"] + self.actors["cps"] + self.actors["rapids"]: self.plotter.remove_actor(a)
            if self.actors["approach"]: self.plotter.remove_actor(self.actors["approach"])
            self.actors["paths"], self.actors["projs"], self.actors["cps"], self.actors["rapids"] = [], [], [], []
            
            if self.params["calc_active"]:
                paths, projs, cps, devs, rapids, debug_lines = self.path_gen.calculate_paths(self.params, self.gui_pass_overrides, self.mandrel_mgr, visual_roller_pos=roller_pos)
                
                num_rough = int(self.params["num_sweeping_passes"]) # Critical for coloring
                
                # Build operation feed rate lookup for velocity coloring
                ops = self.params.get("operations", [])
                op_feeds = []
                for op in ops:
                    feed = float(op.get("feed", 100.0))
                    count = int(op.get("count", 1))
                    for _ in range(count):
                        op_feeds.append(feed)
                
                # Calculate min/max feed for normalization
                if op_feeds:
                    min_feed = min(op_feeds)
                    max_feed = max(op_feeds)
                else:
                    min_feed, max_feed = 100.0, 100.0
                
                # Check if velocity coloring mode is enabled
                velocity_mode = self.params.get("velocity_color_mode", False)
                
                logger.info(f"Rendering {len(paths)} paths.")
                for i, (p, pr, dev) in enumerate(zip(paths, projs, devs)):
                    if len(p) == 0: 
                        logger.warning(f"Path {i} has 0 points.")
                        continue
                    
                    is_active = (i == self.active_editing_pass_idx)
                    is_finish_pass = (i >= num_rough)
                    
                    # Colors
                    col = 'blue' # default for roughing
                    lw = 5
                    
                    if velocity_mode and i < len(op_feeds):
                        # Velocity-based coloring: Green (slow) to Red (fast)
                        feed = op_feeds[i]
                        if max_feed > min_feed:
                            normalized = (feed - min_feed) / (max_feed - min_feed)
                        else:
                            normalized = 0.5
                        # Green (0,255,0) -> Yellow (255,255,0) -> Red (255,0,0)
                        if normalized < 0.5:
                            r = int(normalized * 2 * 255)
                            g = 255
                        else:
                            r = 255
                            g = int((1 - normalized) * 2 * 255)
                        col = (r, g, 0)
                        lw = 6
                    elif is_active:
                        col = 'magenta'
                        lw = 7
                    elif is_finish_pass:
                        col = 'orange' 
                    
                    if len(p) > 1:
                        try:
                            poly = pv.lines_from_points(p)
                            # Create tube-like lines for better visibility
                            self.actors["paths"].append(self.plotter.add_mesh(
                                poly, 
                                color=col, 
                                line_width=lw,
                                render_lines_as_tubes=True
                            ))
                        except Exception as e:
                            logger.error(f"Render failed path {i}: {e}")
                            # Fallback
                            try: self.actors["paths"].append(self.plotter.add_lines(p, color=col, width=lw))
                            except: pass
                    else:
                        try: self.actors["paths"].append(self.plotter.add_lines(p, color=col, width=5))
                        except: pass
                    if len(pr) > 0:
                        self.actors["projs"].append(self.plotter.add_mesh(pv.lines_from_points(pr), color='cyan', line_width=1))
                    if is_active:
                        for pt in cps[i]:
                            self.actors["cps"].append(self.plotter.add_points(pt, color='blue', point_size=15, render_points_as_spheres=True))
                if self.params.get("show_rapids", True):
                     for r in rapids:
                         if len(r) > 1:
                            self.actors["rapids"].append(self.plotter.add_lines(r, color='red', width=1))

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
                        
                        # Get target for clamping
                        target = self.params.get("target_clearance", 0.5)
                        clim = [-target, target*2]  # Range: -target to 2*target
                        
                        actor = self.plotter.add_mesh(
                            mesh, 
                            scalars="Clearance",
                            cmap="RdYlGn",  # Red-Yellow-Green colormap
                            clim=clim,
                            line_width=4,
                            scalar_bar_args={"title": "Clearance (mm)", "vertical": True, "position_x": 0.85}
                        )
                        self.actors["rapids"].append(actor)
                # Render Rapids (Dashed Lines for G0)
                for r_seg in rapids:
                    if len(r_seg) < 2: continue
                    try:
                        act = self.plotter.add_lines(r_seg, color='orange', width=2)
                        # Make dashed
                        prop = act.GetProperty()
                        prop.SetLineStipplePattern(0xFF00)
                        prop.SetLineStippleRepeatFactor(2)
                        self.actors["rapids"].append(act)
                    except: pass

                if len(paths) > 0 and len(paths[0]) > 0:
                     self.actors["approach"] = self.plotter.add_lines(np.array([roller_pos, paths[0][0]]), color='black', width=1)

        # 4. Roller & Measurement
        if update_type in ["all", "paths", "visual"]:
            if self.actors["roller"]: self.plotter.remove_actor(self.actors["roller"])
            
            # Sphere Roller
            roller_mesh = pv.Sphere(radius=r_rad, center=roller_pos, theta_resolution=30, phi_resolution=30)
            r_color = 'red' if gap_x < 0 else 'darkgoldenrod'
            self.actors["roller"] = self.plotter.add_mesh(roller_mesh, color=r_color, smooth_shading=True)
            
            if self.actors.get("dist_line"): self.plotter.remove_actor(self.actors["dist_line"])
            if self.actors.get("dist_label"): self.plotter.remove_actor(self.actors["dist_label"])
            
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

    # --- WRAPPERS ---
    def on_param_change(self, key, val, mode="paths"):
        # Helper for type conversion (Fix for Phase 17 strings like "T0101")
        def convert(v):
            try: return float(v)
            except: return v
        real_val = convert(val)

        # Handle Overrides (Assume only simple keys for now)
        if self.apply_to_specific_pass_only and mode == "paths" and "[" not in key:
            if self.active_editing_pass_idx not in self.gui_pass_overrides: self.gui_pass_overrides[self.active_editing_pass_idx] = {}
            self.gui_pass_overrides[self.active_editing_pass_idx][key] = real_val
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
                self.params[key] = real_val
            
        # [PHASE 8] ULTRA-STRICT Manual Check
        # User requested zero stutter ("visual loading glitches").
        # If mode requires calculation, we SKIP update_scene entirely.
        # Only HESAPLA button (force_calc) calls update_scene directly.
        if mode in ["paths", "shell_and_paths"]:
             if not self.params.get("auto_calculate_paths", False):
                 return

        self.update_scene(mode)

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
        
    def cb_scroll(self, v): 
        self.params["last_scroll_val"] = v
        self.ui.update_positions(v, self.params["show_advanced_sliders"], self.params["show_visual_sliders"])
        
    def toggle_tabs(self, tab_name):
        self.params["show_advanced_sliders"] = (tab_name == "advanced")
        self.params["show_visual_sliders"] = (tab_name == "visual")
        self.cb_scroll(self.params.get("last_scroll_val", 100.0))
        
    def toggle_scope(self, v): 
        self.apply_to_specific_pass_only = bool(v)

    def update_roller_visual(self, pos, current_radius):
        """
        Fast update for simulation loop only.
        pos: [x, 0, z] center of roller contact? No, pos is "roller_pos" (center of sphere).
        current_radius: float
        """
        # Remove old Actor
        if "roller" in self.actors and self.actors["roller"]:
             self.plotter.remove_actor(self.actors["roller"])
        
        # Recreate Roller Mesh
        try:
             mesh = pv.Sphere(radius=current_radius, center=pos)
             self.actors["roller"] = self.plotter.add_mesh(mesh, color='orange', smooth_shading=True)
        except Exception as e:
             logger.error(f"Roller Update Error: {e}")

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
             self.update_scene("all", force_path_calc=True)
             
             # Reset Camera if this is a fresh load?
             # self.plotter.reset_camera() 
             return True
        return False

    def save_gcode(self, v, filepath=None):
        if v:
            code = self.path_gen.generate_gcode(params=self.params)
            
            if filepath:
                out_path = filepath
            else:
                out_path = os.path.join(self.get_base_path(), "spinning_output.nc")
            
            with open(out_path, "w") as f: f.write(code)
            logger.info(f"G-Code saved to {out_path}")

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
                    self.params.update(d.get("params", {}))
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
        """
        Delegates the UI construction to the GuiManager.
        """
        self.ui.build_interface(self)

    def run(self):
        # Startup Step Loading
        default_step = "C:/Users/PC/Documents/CAD_Files/deneme_mandrel.step"
        inp = input(f"STEP Dosyası Yolu (Varsayılan: {default_step}) > ") or default_step
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