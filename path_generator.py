import numpy as np
import math
import time
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Trsf
from OCC.Core.TColgp import TColgp_Array1OfPnt
from OCC.Core.GeomAPI import GeomAPI_PointsToBSpline
from logger_config import logger

class PathGenerator:
    def __init__(self):
        self.last_calculated_paths = [] 

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
                "step": params.get("roughing_step_radial", 1.0)
            })

        # 2. Finishing
        tc_active = params.get("tool_change_active", False)
        num_finish = int(params.get("num_finishing_passes", 1))
        # If TC inactive, we usually don't have explicit finish passes distinct from rough, or maybe we do?
        # In old logic: num_finish used ONLY if tc_active.
        if tc_active and num_finish > 0:
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
        
        props = mandrel_mgr.props
        top_z = props["top_z"]
        center_x = params.get("mandrel_pos_x_offset", 0.0)
        blank_thick = params.get("final_part_thickness_on_mandrel", 2.0)
        shell_offset = params.get("shell_thickness", 0.0)
        last_pass_ext = params.get("last_pass_extension_z", 0.0)
        auto_align = params.get("auto_align_rotation", False)
        
        # Rapids Simulation Params (Match generate_gcode defaults)
        home_x = params.get("home_x", 300.0)
        home_z = params.get("home_z", 150.0)
        safe_x = home_x 
        # [NEW] Pass Retract Offset (Relative)
        retract_x_offset = float(params.get("retract_x", 50.0)) 
        retract_z_offset = float(params.get("retract_z", 50.0)) 
        
        tc_active = params.get("tool_change_active", False)
        
        operations = self._ensure_ops_dict(params)
        global_pass_idx = 0
        end_h = top_z + last_pass_ext
        
        # Initial Position (Home)
        current_pt = np.array([home_x, 0, home_z])
        current_tool = None
        
        # [NEW] Initial Homing Visualization if visual pos differs from Home
        if visual_roller_pos is not None:
             start_vis = np.array(visual_roller_pos)
             
             # G-Code Header: G0 Z150 (Move Z to Home Z), then G0 X300 (Move X to Home X)
             # Simulate this sequence from visual start.
             
             # 1. Move Z to Home Z (keeping Visual X)
             step1 = np.array([start_vis[0], 0, home_z]) 
             
             # 2. Move X to Home X (at Home Z) -> [Home.X, 0, Home.Z]
             step2 = np.array([home_x, 0, home_z])
             
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

        for op in operations:
            if not op.get("enabled", True): continue
            
            count = int(op.get("count", 1))
            is_finish = (op.get("type") == "finishing")
            r_tool = float(op.get("r_tool", 25.0))
            op_tool_id = op.get("tool_id", "T0101")
            
            # [UPDATED] Tool Change Logic
            # Always simulate movement if ID changes, regardless of M6 flag
            need_tool_change = (op_tool_id != current_tool) or (current_tool is None)
            
            if need_tool_change and current_tool is not None:
                # Retract to Home SAFE (Split move: X out, then Z home)
                # 1. Move to Safe X (using Home X for full retract)
                safe_mid = np.array([home_x, 0, current_pt[2]])
                
                # Only add if distance > 1mm
                if np.linalg.norm(current_pt - safe_mid) > 1.0:
                    r_seg1 = np.array([current_pt, safe_mid])
                    rapids.append(r_seg1)
                    sequence.append(("rapid", r_seg1))
                
                # 2. Move to Home Z (at Safe X)
                home_pt = np.array([home_x, 0, home_z])
                if np.linalg.norm(safe_mid - home_pt) > 1.0:
                    r_seg2 = np.array([safe_mid, home_pt])
                    rapids.append(r_seg2)
                    sequence.append(("rapid", r_seg2))
                    
                current_pt = home_pt
                
            current_tool = op_tool_id
            
            # Op Params 
            def_p1_x = float(op.get("p1_x", 40.0)); def_p1_z = float(op.get("p1_z", 50.0))
            def_p3_z = float(op.get("p3_z", -20.0)); def_rot = float(op.get("rot", 0.0))
            def_step = float(op.get("step", 0.0))
            start_h = float(op.get("start_z", 10.0))
            
            
            # Auto-Align Feature: Read from params
            auto_align = params.get("auto_calc_angle", True)
            
            for i in range(count):
                ovr = overrides.get(global_pass_idx, {})
                if is_finish:
                     p1_x = ovr.get("finish_p1_p3_x_offset_from_p2", def_p1_x)
                     p1_z = ovr.get("finish_p1_z_offset_from_p2", def_p1_z)
                     p3_z = ovr.get("finish_p3_z_offset_from_p2", def_p3_z)
                     base_rot = ovr.get("finish_y_rotation_degrees", def_rot)
                     allowance = ovr.get("finish_step_radial", def_step)
                else:
                     p1_x = ovr.get("p1_p3_x_offset_from_p2", def_p1_x)
                     p1_z = ovr.get("p1_z_offset_from_p2", def_p1_z)
                     p3_z = ovr.get("p3_z_offset_from_p2", def_p3_z)
                     base_rot = ovr.get("y_rotation_degrees", def_rot)
                     allowance = ovr.get("roughing_step_radial", def_step)
                
                
                if count <= 1: 
                    target_z = end_h
                else: 
                    target_z = start_h + (i / (count - 1) * (end_h - start_h))
                
                r_contact = mandrel_mgr.get_radius_fast(target_z) + shell_offset
                nx, nz = mandrel_mgr.get_normal_at_z(target_z)
                total_off = r_tool + blank_thick + params.get("safety_clearance_roller_to_part", 0.5) + allowance
                p2_x = center_x + r_contact + (nx * total_off)
                p2_z = target_z + (nz * total_off)
                
                visual_shell_offset = shell_offset + (1.0 if is_finish else 0.0)
                pass_label = f"{op.get('type').capitalize()} {i+1}"
                
                prev_paths_len = len(toolpaths)
                
                if is_finish:
                    # [NEW] Adaptive Pass Logic: Check param (default False for now, user will toggle)
                    adaptive_mode = params.get("adaptive_finish_mode", False)
                    
                    if adaptive_mode:
                        self._create_adaptive_pass(start_h, end_h, mandrel_mgr, center_x, r_tool, blank_thick, visual_shell_offset, pass_label, toolpaths, projections, control_points, deviations, params)
                    else:
                        # Existing Sweeping Pass
                        self._create_sweeping_pass(start_h, end_h, mandrel_mgr, center_x, r_tool, blank_thick, visual_shell_offset, pass_label, toolpaths, projections, control_points, deviations)
                else:
                    adaptive_rough = params.get("adaptive_rough_mode", False)
                    # Standard Spline
                    self._create_and_store_pass(p1_x, p1_z, p3_z, gp_Pnt(p2_x, 0, p2_z), base_rot, auto_align, toolpaths, projections, control_points, deviations, mandrel_mgr, center_x, r_tool, blank_thick, visual_shell_offset, pass_label, params, debug_lines)
                
                # Check newly added path for Rapids
                if len(toolpaths) > prev_paths_len:
                    new_path = toolpaths[-1]
                    if len(new_path) > 0:
                        start_pt = new_path[0]
                        end_pt = new_path[-1]
                        
                        # 1. Rapid to Start (G0 X... Z...)
                        r_seg1 = np.array([current_pt, start_pt])
                        rapids.append(r_seg1)
                        sequence.append(("rapid", r_seg1))
                        
                        # Cut Path
                        sequence.append(("cut", new_path, r_tool))
                        
                        # 2. Retract to Safe X (Inter-pass)
                        # [UPDATED] Use Relative Offset (End X + OffX, End Z + OffZ)
                        retract_pt = np.array([end_pt[0] + retract_x_offset, 0, end_pt[2] + retract_z_offset])
                        r_seg2 = np.array([end_pt, retract_pt])
                        rapids.append(r_seg2)
                        sequence.append(("rapid", r_seg2))
                        
                        current_pt = retract_pt

                global_pass_idx += 1
        
        # [NEW] Final Return to Home
        # User requested roller to return to Safety Home Position at end.
        home_pt = np.array([home_x, 0, home_z])
        
        if np.linalg.norm(current_pt - home_pt) > 1.0:
            # Logic: We are likely at Safe X (from loop end).
            # Just move to Home Z. 
            final_rap = np.array([current_pt, home_pt])
            rapids.append(final_rap)
            sequence.append(("rapid", final_rap))
        
        self.last_calculated_paths = toolpaths
        self.last_calculated_sequence = sequence
        return toolpaths, projections, control_points, deviations, rapids, debug_lines

    def _create_adaptive_pass(self, start_z, end_z, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_name, t_list, p_list, c_list, d_list, params, additional_radial_offset=0.0):
        """
        Generates a dense G-Code path by offsetting the Mandrel Profile at fine intervals.
        Designed for complex geometries with sharp radius changes.
        """
        resolution = float(params.get("adaptive_resolution", 0.5))
        if resolution < 0.1: resolution = 0.1
        
        # Determine Z range and steps
        z_min = min(start_z, end_z)
        z_max = max(start_z, end_z)
        steps = int((z_max - z_min) / resolution) + 2
        
        # Decide direction
        forward = (start_z < end_z)
        z_vals = np.linspace(start_z, end_z, steps) if forward else np.linspace(start_z, end_z, steps)
        
        path_points = []
        
        # Safety Offset Calculation
        total_offset = r_tool + blank_thick + params.get("safety_clearance_roller_to_part", 0.5) + additional_radial_offset
        
        # Bow/Curve Parameters for Conformal Scalloping
        # User wants "Curved" passes. We apply a parabolic offset on top of the conformal shell.
        # Bow Height: 10mm (Adjustable?)
        bow_height = 20.0 
        
        # Calculate Center for Parabola
        z_min = np.min(z_vals)
        z_max = np.max(z_vals)
        z_len = z_max - z_min
        if z_len < 0.001: z_len = 1.0
        
        for z in z_vals:
            # 1. Get Mandrel Geometry at Z
            m_rad = mandrel_mgr.get_radius_fast(z)
            nx, nz = mandrel_mgr.get_normal_at_z(z)
            
            # 2. Calculate Parabolic Offset (Bow)
            # t goes from 0 to 1
            t = (z - z_min) / z_len
            # Parabola opening AWAY from mandrel: Max at ends (0, 1), Min at center (0.5)
            # Formula: bow * 4 * (t - 0.5)^2
            # At t=0.5 -> 0. At t=0 -> bow.
            parabolic_offset = bow_height * 4 * ((t - 0.5)**2)
            
            # 3. Calculate Contact Point (on shell surface)
            # Base Contact is m_rad + shell_offset.
            # We add parabolic_offset to "lift" the ends away.
            r_contact = m_rad + shell_offset + parabolic_offset
            
            # 4. Calculate Roller Center Position (Offset by Tool Radius + Thickness)
            p_roller_x = (center_x + r_contact) + (nx * total_offset)
            p_roller_z = z + (nz * total_offset)
            
            path_points.append([p_roller_x, 0, p_roller_z])

        # Store Result
        pts_arr = np.array(path_points)
        t_list.append(pts_arr)
        
        # Consistent Visualization Data
        # Projections: Trace contacting surface (r_contact)
        proj_pts = []
        for z in z_vals:
            m_rad = mandrel_mgr.get_radius_fast(z)
            # Projection is usually on the "Ideal Part Surface" (Mandrel + Blank + Shell)
            # Line 398 in spline: px = center_x + r_surf + shell_offset + blank_thick
            # In adaptive, r_contact = m_rad + shell_offset.
            # So let's project to r_contact + blank_thick?
            # Or just r_contact?
            # Creating projection at Mandrel Surface + Shell + Blank
            px = center_x + m_rad + shell_offset + blank_thick
            proj_pts.append([px, 0, z])
            
        p_list.append(np.array(proj_pts))        
        c_list.append(np.array([])) # Control Pts (None)
        
        # Deviations must match point count for scalars
        if len(pts_arr) > 0:
            # Calculate real deviations
            devs = []
            for pt in pts_arr:
                # pt is [x, 0, z]
                m_r = mandrel_mgr.get_radius_fast(pt[2])
                dist = math.sqrt((pt[0]-center_x)**2 + pt[1]**2) 
                
                # Limit = Mandrel + Blank + Shell + Tool (No safety or allowance in "Limit" usually? 
                # In standard calc (line 386): limit = m_r + blank_thick + shell_offset + r_tool
                # This deviation is "Distance from Ideal Surface".
                limit = m_r + blank_thick + shell_offset + r_tool
                devs.append(dist - limit)
            d_list.append(np.array(devs))
        else:
            d_list.append(np.array([]))
            logger.warning(f"Adaptive Pass '{pass_name}' generated 0 points! Range: {start_z:.2f} to {end_z:.2f}")

        logger.info(f"Generated Adaptive Pass '{pass_name}': {len(pts_arr)} points.") 

    def _calculate_adaptive_z_distribution(self, start_z, end_z, count, mandrel_mgr):
        return [] # Deprecated/Removed

    def _create_and_store_pass(self, p1_x_offset, p1_z_offset, p3_z_offset, initial_p2, base_rot, auto_align, t_list, p_list, c_list, d_list, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_name, params, debug_lines=None):
            # --- Smart Spline Optimization V6 (Morphing) ---
            # Instead of rigid shifting, independently adjust control points based on where collision occurs.
            
            # 1. Initialize Absolute Control Points
            p2 = initial_p2
            # P1/P3 start based on P2, preserving offset relationship initially
            calc_p1_z = p2.Z() - abs(p1_z_offset)
            p1 = gp_Pnt(p2.X() + abs(p1_x_offset), 0, calc_p1_z)
            
            calc_p3_z = p2.Z() + abs(p3_z_offset)
            p3 = gp_Pnt(p2.X() + abs(p1_x_offset), 0, calc_p3_z)
            
            final_points = []
            
            # Gouge Check Parameters
            max_iterations = 20
            safety_tolerance = 0.05 # mm
            
            # Resolution for Checking
            check_res = params.get("collision_resolution", 0.5)
            
            for attempt in range(max_iterations):
                # 2. Generate Spline (High Rez based on Check Res)
                # Estimate length for step count
                approx_len = p1.Distance(p2) + p2.Distance(p3)
                num_points = int(max(10, approx_len / check_res))
                
                pts_raw = self._generate_spline(p1, p2, p3, num_points)
                if len(pts_raw) == 0: break
                
                # 3. Apply Rotation (Aligned to P2 surface normal)
                nx, nz = mandrel_mgr.get_normal_at_z(p2.Z()) 
                final_rot = base_rot
                if auto_align:
                    surface_angle = math.degrees(math.atan2(nz, nx))
                    # Check sign convention
                    final_rot = -surface_angle + base_rot
                
                check_pts = pts_raw
                if abs(final_rot) > 0.01:
                    check_pts = self._apply_rotation(pts_raw, final_rot, p2)
                
                # 4. Calculate CLEARANCE at each point (not just collision)
                # Clearance = Distance to mandrel surface - required offset
                # We want UNIFORM clearance across all points
                
                target_clearance = params.get("target_clearance", 0.5)  # mm
                
                min_clearance = float('inf')
                clearances = []
                
                for pt in check_pts:
                    sim_x, sim_y, sim_z = pt
                    
                    if sim_z < mandrel_mgr.props.get("min_z", 0.0) or sim_z > mandrel_mgr.props.get("top_z", 100.0):
                        clearances.append(target_clearance)  # Skip out-of-bounds
                        continue

                    m_rad = mandrel_mgr.get_radius_fast(sim_z)
                    dist_to_axis = math.sqrt((sim_x - center_x)**2 + sim_y**2)
                    
                    # Required minimum distance from axis = mandrel + blank + shell + tool
                    required_dist = m_rad + blank_thick + shell_offset + r_tool
                    
                    # Clearance = how much EXTRA space we have beyond the required
                    clearance = dist_to_axis - required_dist
                    clearances.append(clearance)
                    
                    if clearance < min_clearance:
                        min_clearance = clearance
                
                # If minimum clearance is less than OR greater than target, adjust to EXACTLY match target
                # This ensures ALL passes have the SAME minimum clearance (uniform force)
                diff = target_clearance - min_clearance
                if abs(diff) > 0.01:  # Only adjust if difference is significant
                    # Shift by exact amount needed (positive = shift out, negative = shift in)
                    shift_amount = diff
                    
                    # UNIFORM SHIFT: Move ALL control points equally in +X direction
                    p1 = gp_Pnt(p1.X() + shift_amount, 0, p1.Z())
                    p2 = gp_Pnt(p2.X() + shift_amount, 0, p2.Z())
                    p3 = gp_Pnt(p3.X() + shift_amount, 0, p3.Z())
                    
                    logger.info(f"Uniform Correction '{pass_name}' Iter {attempt}: Min Clearance {min_clearance:.3f}mm < Target {target_clearance}mm. Shifting ALL points by +{shift_amount:.3f}mm")
                    continue
                
                # If we reach here, check passed or max iterations reached.
                # Generate Final Analysis Line - ONLY the MINIMUM clearance point
                if debug_lines is not None and len(check_pts) > 0:
                    min_cl = float('inf')
                    min_line = None
                    min_status = 0
                    
                    for pt in check_pts:
                         sim_x, sim_y, sim_z = pt
                         
                         m_rad = mandrel_mgr.get_radius_fast(sim_z)
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
                break

             
            if len(final_points) == 0: 
                final_points = check_pts # Fallback
            
            t_list.append(np.array(final_points))
            
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
            
            if proj_line: p_list.append(np.array(proj_line))

    def generate_gcode(self, feed: int = 1000, speed: int = 200, max_rpm: int = 2000, params: dict = None) -> str:
        """
        Generates CNC G-Code for the calculated toolpaths.
        """
        if not self.last_calculated_paths: return ""
        if params is None: return ""
        
        invert_x = params.get("machine_invert_x", False)
        invert_z = params.get("machine_invert_z", False)  # [NEW] Z axis inversion
        dia_mode = params.get("machine_output_diameter_mode", False)
        
        # [NEW] Machine Origin in Global Coords (Post-Processor)
        origin_x = params.get("machine_origin_x", 0.0)
        origin_z = params.get("machine_origin_z", 0.0)
        
        # Additional Work Offsets (G54 style, applied AFTER origin transformation)
        off_x = params.get("machine_gcode_offset_x", 0.0)
        off_z = params.get("machine_gcode_offset_z", 0.0)
        
        # Axis direction multipliers
        dir_x = -1.0 if invert_x else 1.0
        dir_z = -1.0 if invert_z else 1.0
        
        # Get Template Strings
        header_tmpl = params.get("gcode_header", "G21 G90 G18\nG54")
        
        # Tool & Operation Setup
        tc_active = params.get("tool_change_active", False)
        operations = self._ensure_ops_dict(params)
        
        # Split line by line
        gcode = ["%", f"O1001 (METAL SIVAMA - {len(self.last_calculated_paths)} PASO)"]
        gcode.extend(header_tmpl.splitlines())
        
        # Configurable Machine Home / Safe Pts
        home_x = params.get("home_x", 300.0)
        home_z = params.get("home_z", 150.0)
        
        # [NEW] Transform Home Position through post-processor
        home_x_machine = ((home_x - origin_x) * dir_x) + off_x
        home_z_machine = ((home_z - origin_z) * dir_z) + off_z
        if dia_mode: home_x_machine *= 2.0
        
        # Machine Settings Comment Block
        gcode.extend([
            "(--- MAKINE AYARLARI / POST-PROCESSOR ---)",
            f"(Machine Origin: X={origin_x}, Z={origin_z})",
            f"(Axis Direction: X={'INVERTED' if invert_x else 'NORMAL'}, Z={'INVERTED' if invert_z else 'NORMAL'})",
            f"(Output Mode: {'DIAMETER' if dia_mode else 'RADIUS'})",
            f"(Additional Offset: X={off_x}, Z={off_z})",
            "",
            f"G50 S{max_rpm} (Devir Siniri)", 
            f"G0 Z{home_z_machine:.3f} (Guvenli Z)",
            f"G0 X{home_x_machine:.3f} (Guvenli X)",
            ""
        ])
        
        safe_x_machine = home_x_machine  # Use transformed safe X
        current_tool = None
        global_path_idx = 0
        total_paths = len(self.last_calculated_paths)
        
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
                 # ALWAYS Retract if tool differs (Sim Consistency)
                 gcode.extend(["", "(--- TOOL CHANGE SAFETY ---)"])
                 gcode.append(f"G0 X{safe_x_machine:.3f} (Retract X)") 
                 gcode.append(f"G0 Z{home_z_machine:.3f} (Home Z)")
                 if tc_active: gcode.extend(["M5", "M1"])
            
            if (tc_active and tool_differs) or (current_tool is None):
                 gcode.append(f"M6 {op_tool} ({op_type})")
                 gcode.append(f"{code_speed} S{int(val_speed)} M3")
                 gcode.append(f"{code_feed} (Feed: {f_mode})")
                 gcode.append("")
                 current_tool = op_tool
                 
            elif tool_differs and not tc_active:
                 gcode.append(f"(Tool {op_tool} Active - No M6)")
                 gcode.append(f"{code_speed} S{int(val_speed)} M3")
                 gcode.append(f"{code_feed}")
                 current_tool = op_tool
            elif current_tool == op_tool:
                 gcode.append(f"(Update Params: {val_speed} {s_mode}, {val_feed} {f_mode})")
                 gcode.append(f"{code_speed} S{int(val_speed)} M3")
                 gcode.append(f"{code_feed}")

            for i in range(count):
                if global_path_idx >= total_paths: break
                
                path = self.last_calculated_paths[global_path_idx]
                gcode.append(f"(--- OP {op_idx+1}: {op_type} - PASO {i+1} ---)")
                
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

                s_x, s_z = transform_pt(path[0])
                gcode.append(f"G0 X{s_x:.3f} Z{s_z:.3f}") 
                
                zones = op.get("zones", [])
                current_s_val = val_speed 
                current_f_val = -1.0 
                
                for p in path[1:]:
                    tx, tz = transform_pt(p)
                    
                    # Check Zones
                    target_s = val_speed
                    target_f = val_feed
                    raw_z = p[2] 
                    
                    for zdata in zones:
                         try:
                             zstart = float(zdata.get("start_z", 0))
                             zend = float(zdata.get("end_z", 0))
                             if min(zstart, zend) <= raw_z <= max(zstart, zend):
                                  target_s = float(zdata.get("speed", val_speed))
                                  target_f = float(zdata.get("feed", val_feed))
                                  break 
                         except: pass
                    
                    s_suffix = ""
                    if target_s != current_s_val:
                         s_suffix = f" {code_speed} S{int(target_s)}"
                         current_s_val = target_s
                    
                    f_suffix = ""
                    if abs(target_f - current_f_val) > 0.001:
                        f_suffix = f" F{target_f:.3f}"
                        current_f_val = target_f

                    gcode.append(f"G1 X{tx:.3f} Z{tz:.3f}{f_suffix}{s_suffix}")
                
                if len(path) > 0:
                    last_pt = path[-1]
                    ret_x_off = float(params.get("retract_x", 50.0))
                    ret_z_off = float(params.get("retract_z", 50.0))
                    
                    raw_ret_x = last_pt[0] + ret_x_off
                    raw_ret_z = last_pt[2] + ret_z_off
                    
                    rx, rz = transform_pt([raw_ret_x, 0, raw_ret_z])
                    gcode.append(f"G0 X{rx:.3f} Z{rz:.3f} (Retract)")
                
                gcode.append("")
                global_path_idx += 1
            
        # Final Safety Return (Use transformed coordinates)
        gcode.append("(--- PROGRAM SONU GUVENLI DONUS ---)")
        gcode.append(f"G0 X{home_x_machine:.3f}")
        gcode.append(f"G0 Z{home_z_machine:.3f}")
        
        footer_tmpl = params.get("gcode_footer", "M5\nM30")
        gcode.extend(footer_tmpl.splitlines())
        gcode.append("%")
        return "\n".join(gcode)

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
                             except: pass
                        
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

    def _create_sweeping_pass(self, start_z, end_z, mandrel_mgr, center_x, r_tool, blank_thick, shell_offset, pass_name, t_list, p_list, c_list, d_list):
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
            
            m_rad = mandrel_mgr.get_radius_fast(current_z)
            nx, nz = mandrel_mgr.get_normal_at_z(current_z)
            
            total_off = r_tool + blank_thick
            
            rx = center_x + m_rad + (nx * total_off)
            rz = current_z + (nz * total_off)
            
            path_pts.append([rx, 0.0, rz])
            projs.append([center_x + m_rad, 0.0, current_z])
            devs.append(0.0) 
            
            current_z += (step_size * step_dir)
            if abs(current_z - end_z) < 0.1: break
            
        t_list.append(path_pts)
        p_list.append(projs)
        c_list.append([]) 
        d_list.append(devs)