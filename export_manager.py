"""
Export Manager for SpinningCam.
Provides STL export for part preview, PDF export for operation sheets,
Recipe export for PLC integration, and SCL export for TIA Portal.
"""
import os
import datetime
from typing import Optional, Tuple
import numpy as np
import pyvista as pv
from fpdf import FPDF
from gcode_to_recipe import GCodeToRecipeConverter
from recipe_to_scl import GCodeToSCLConverter


class ExportManager:
    """Handles exporting spun part preview and operation sheets."""

    @staticmethod
    def export_stl(shell_mesh, filepath: str) -> bool:
        """
        Export the shell mesh as an STL file.
        
        Args:
            shell_mesh: PyVista mesh (PolyData or StructuredGrid) of the spun part shell.
            filepath: Output STL file path.
            
        Returns:
            True if export successful, False otherwise.
        """
        try:
            if shell_mesh is None:
                return False
            
            # Convert StructuredGrid to PolyData surface if needed
            if hasattr(shell_mesh, 'extract_surface'):
                surface = shell_mesh.extract_surface()
            else:
                surface = shell_mesh
            
            # Ensure it's triangulated for STL
            triangulated = surface.triangulate()
            triangulated.save(filepath)
            return True
        except Exception as e:
            print(f"STL Export Error: {e}")
            return False

    @staticmethod
    def export_pdf(params: dict, paths: list, filepath: str, tools: list = None, mandrel_mgr=None,
                   tilt_angles: list = None) -> bool:
        """
        Export an operation sheet PDF for shop floor use.

        Args:
            params: Current parameters dictionary.
            paths: List of calculated toolpaths.
            filepath: Output PDF file path.
            tools: Optional list of tool definitions.
            tilt_angles: Optional per-path tilt arrays (path_gen.last_tilt_angles),
                index-aligned with paths; None on plain XZ machines.

        Returns:
            True if export successful, False otherwise.
        """
        try:
            pdf = SpinningCamPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()
            
            # Title
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "SpinningCam - Operation Sheet", ln=True, align="C")
            pdf.ln(5)
            
            # Date/Time
            pdf.set_font("Helvetica", "", 10)
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            pdf.cell(0, 6, f"Generated: {now}", ln=True)
            pdf.ln(5)
            
            # Geometry Section
            pdf.section_header("Geometry")
            pdf.info_row("Blank Radius", f"{params.get('blank_radius', 0):.1f} mm")
            pdf.info_row("Part Thickness", f"{params.get('final_part_thickness_on_mandrel', 0):.1f} mm")
            pdf.ln(3)

            # Operations Section
            operations = params.get("operations", [])
            pdf.section_header(f"Operations ({len(operations)} total)")

            for i, op in enumerate(operations):
                op_type = op.get("type", "unknown").capitalize()
                enabled = op.get("enabled", True)
                is_cb = op.get("type", "roughing") in ("cutting", "bending")
                count = op.get("count", 1)
                tool_id = op.get("tool_id", "T0101")
                r_tool = op.get("r_tool", 25.0)
                has_back = not is_cb and op.get("back_pass_enabled", False)

                label = f"{i+1}. {op_type}"
                if not enabled:
                    label += "  [DISABLED]"

                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, label, ln=True)
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(10)
                pass_desc = f"{count} passes"
                if has_back:
                    pass_desc += f" + {count} back"
                pdf.cell(0, 5, f"{pass_desc}  |  Tool: {tool_id}  |  Rr: {r_tool:.1f} mm", ln=True)

            pdf.ln(3)

            # Path Summary
            pdf.section_header("Path Summary")
            total_points = sum(len(p) for p in paths) if paths else 0
            total_fwd = 0
            total_back = 0
            for op in operations:
                if not op.get("enabled", True):
                    continue
                is_cb = op.get("type", "roughing") in ("cutting", "bending")
                c = 1 if is_cb else int(op.get("count", 1))
                total_fwd += c
                if not is_cb and op.get("back_pass_enabled", False):
                    total_back += c
            actual_total = len(paths)
            if total_back > 0:
                pdf.info_row("Total Passes", f"{actual_total}  ({total_fwd} forward + {total_back} back)")
            else:
                pdf.info_row("Total Passes", str(actual_total))
            pdf.info_row("Total Points", str(total_points))
            pdf.ln(3)

            # Tilt (B axis) per-pass reference — tilt-arm machines only
            if tilt_angles is not None and any(t is not None and len(t) > 0 for t in tilt_angles):
                _b_sign = float(params.get("tilt_b_sign", 1.0))
                _b_home = float(params.get("tilt_b_home", 0.0))
                pdf.section_header("Tilt B Axis - Per Pass (start -> end)")
                for pi, ta in enumerate(tilt_angles):
                    if ta is None or len(ta) == 0:
                        continue
                    b0 = float(ta[0]) * _b_sign + _b_home
                    b1 = float(ta[-1]) * _b_sign + _b_home
                    pdf.info_row(f"Pass {pi + 1}", f"B {b0:8.2f} deg  ->  {b1:8.2f} deg")
                pdf.ln(3)

            # Machine Settings
            pdf.section_header("Machine Settings")
            pdf.info_row("Program Start X", f"{params.get('home_x', 300):.1f} mm")
            pdf.info_row("Program Start Z", f"{params.get('home_z', 150):.1f} mm")
            pdf.info_row("Retract X", f"{params.get('retract_x', 50):.1f} mm (rel)")
            pdf.info_row("Retract Z", f"{params.get('retract_z', 50):.1f} mm (rel)")
            pdf.info_row("Invert X", "Yes" if params.get("machine_invert_x", False) else "No")
            pdf.ln(3)

            # Calibration
            pdf.section_header("Calibration")
            cal = params.get("calibration_last_session", {})
            if cal:
                saved_at = cal.get("saved_at", "")
                if saved_at:
                    pdf.info_row("Calibrated", saved_at)
                tz = cal.get("entry_z", "")
                tx = cal.get("entry_x", "")
                if tx and tz:
                    pdf.info_row("Touch Point (Machine)", f"X = {tx} mm   Z = {tz} mm")
                surface = cal.get("surface", "")
                if surface:
                    pdf.info_row("Touch Surface", surface.capitalize())
                tool_var = cal.get("tool_var", "")
                r_t = cal.get("entry_rt", "")
                if tool_var:
                    val = tool_var
                    if r_t:
                        val += f"   Rr = {r_t} mm"
                    pdf.info_row("Tool at Calibration", val)
                zref = cal.get("zref", "")
                cam_z = cal.get("entry_cam_z", "")
                if zref:
                    pdf.info_row("Z Reference", zref.replace("_", " "))
                if cam_z:
                    pdf.info_row("CAM Z at Touch", f"{cam_z} mm")
            else:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(120, 120, 120)
                pdf.cell(0, 5, "No calibration data recorded.", ln=True)
                pdf.set_text_color(0, 0, 0)
            pdf.ln(3)
            
            # G-Code Header/Footer
            pdf.section_header("G-Code Templates")
            pdf.set_font("Courier", "", 8)
            header = params.get("gcode_header", "")
            footer = params.get("gcode_footer", "")
            pdf.multi_cell(0, 4, f"Header:\n{header}")
            pdf.ln(2)
            pdf.multi_cell(0, 4, f"Footer:\n{footer}")
            
            # 2D Path Diagram
            if paths and any(len(p) >= 2 for p in paths):
                pdf.add_page()
                pdf.add_path_diagram(paths, params, mandrel_mgr)

            # Save
            pdf.output(filepath)
            return True
            
        except Exception as e:
            print(f"PDF Export Error: {e}")
            return False

    @staticmethod
    def export_recipe(gcode_filepath: str, recipe_filepath: Optional[str] = None) -> Tuple[bool, dict]:
        """
        Export G-code as PLC Recipe format (CSV).
        
        Converts text-based G-code to compact numerical recipe format for 
        Siemens S7-1200 PLC. This saves ~50% memory and eliminates string 
        parsing overhead on the PLC.
        
        Recipe Format:
            X,Z,F,CMD where CMD is:
            0  = G0 (Rapid move)
            1  = G1 (Linear interpolation)
            10 = Tool change
            99 = Program end
        
        Args:
            gcode_filepath: Path to the input .nc G-code file
            recipe_filepath: Output .csv path (auto-generated if None)
            
        Returns:
            Tuple of (success: bool, stats: dict with conversion statistics)
        """
        try:
            converter = GCodeToRecipeConverter()
            output_path = converter.convert_file(gcode_filepath, recipe_filepath)
            stats = converter.get_statistics()
            return True, stats
        except FileNotFoundError:
            print(f"Recipe Export Error: File not found: {gcode_filepath}")
            return False, {}
        except Exception as e:
            print(f"Recipe Export Error: {e}")
            return False, {}

    @staticmethod
    def export_scl(gcode_filepath: Optional[str] = None,
                   scl_filepath: Optional[str] = None,
                   db_name: str = "DB_RecipeProgram1",
                   program_title: str = "SpinningCam Program",
                   force: bool = False,
                   params: dict = None,
                   custom_array_size: int = None,
                   gcode_string: Optional[str] = None) -> Tuple[bool, dict]:
        """
        Export G-code as SCL Data Block for TIA Portal.
        
        Converts G-code to SCL format that can be imported into TIA Portal
        as an External Source File and generated as a Data Block.
        
        TIA Portal Import Steps:
            1. Copy .scl file to project folder
            2. Right-click "External Source Files" → Add new external file
            3. Select the .scl file
            4. Right-click imported file → Generate blocks from source
        
        Args:
            gcode_filepath: Path to the input .nc G-code file
            scl_filepath: Output .scl path (auto-generated if None)
            db_name: Data Block name (e.g., "DB_RecipeProgram1")
            program_title: Human-readable program title
            force: If True, ignore line count limit warnings
            
        Returns:
            Tuple of (success: bool, stats: dict with conversion statistics)
            If line limit exceeded and force=False, stats will contain 'limit_exceeded' key
        """
        try:
            converter = GCodeToSCLConverter()
            if gcode_string is not None:
                # In-memory path: no file read needed
                converter.parse_gcode(gcode_string)
                scl_code = converter.generate_scl(
                    db_name, program_title,
                    force=force, params=params,
                    custom_array_size=custom_array_size
                )
                from pathlib import Path
                out_path = Path(scl_filepath)
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(scl_code)
                rapid_count  = sum(1 for l in converter.lines if l.cmd == 0)
                linear_count = sum(1 for l in converter.lines if l.cmd == 1)
                tool_count   = sum(1 for l in converter.lines if l.cmd == 10)
                stats = {
                    'total_lines': len(converter.lines),
                    'rapid_moves': rapid_count,
                    'linear_moves': linear_count,
                    'tool_changes': tool_count,
                    'db_name': db_name,
                    'scl_size_bytes': len(scl_code.encode('utf-8')),
                    'estimated_plc_bytes': len(converter.lines) * 12,
                }
                return True, stats
            output_path, stats = converter.convert_file(
                gcode_filepath,
                scl_filepath,
                db_name=db_name,
                program_title=program_title,
                force=force,
                params=params,
                custom_array_size=custom_array_size
            )
            return True, stats
        except FileNotFoundError:
            print(f"SCL Export Error: File not found: {gcode_filepath}")
            return False, {}
        except ValueError as e:
            error_msg = str(e)
            # Check if this is a limit exceeded error
            if error_msg.startswith("LIMIT_EXCEEDED:"):
                parts = error_msg.split(":")
                return False, {
                    'limit_exceeded': True,
                    'actual_lines': int(parts[1]),
                    'max_lines': int(parts[2])
                }
            print(f"SCL Export Error: {e}")
            return False, {}
        except Exception as e:
            print(f"SCL Export Error: {e}")
            return False, {}

    @staticmethod
    def auto_fit_plc_tolerance(path_gen, params, target_lines, floor_clearance,
                               tol_min=0.05, tol_max=8.0, iters=18):
        """Find the SMALLEST plc_tolerance whose emitted SCL recipe line count is
        <= target_lines, then verify the decimated path's clearance is no worse
        than the full-resolution path (floor_clearance).

        The recipe line count is monotonically non-increasing in tolerance, and the
        smallest tolerance that fits the budget also retains the MOST clearance —
        so we bisect on the budget alone and check clearance once at the result.

        Returns a dict:
          status : 'no_reduction_needed' | 'ok' | 'clearance_limited' | 'infeasible_budget'
          tolerance, lines, min_clearance, floor
        Pure/read-only w.r.t. persistent state (operates on a params copy).
        """
        from recipe_to_scl import GCodeToSCLConverter
        base = dict(params)
        base["plc_mode"] = True
        eps = 1e-6

        def _eval(tol):
            p = dict(base)
            p["plc_tolerance"] = tol
            p["plc_exit_tolerance"] = tol
            gcode = path_gen.generate_gcode(params=p)
            conv = GCodeToSCLConverter()
            conv.parse_gcode(gcode)
            cl = path_gen.measure_min_clearance(
                getattr(path_gen, "last_plc_paths", None) or [], p)
            return len(conv.lines), cl

        # Finest tolerance already within budget → no coarsening needed.
        n_fine, cl_fine = _eval(tol_min)
        if n_fine <= target_lines:
            return {"status": "no_reduction_needed", "tolerance": tol_min,
                    "lines": n_fine, "min_clearance": cl_fine, "floor": floor_clearance}

        # Even the coarsest tolerance cannot reach the budget.
        n_coarse, cl_coarse = _eval(tol_max)
        if n_coarse > target_lines:
            return {"status": "infeasible_budget", "tolerance": tol_max,
                    "lines": n_coarse, "min_clearance": cl_coarse, "floor": floor_clearance}

        # Bisect for the smallest tolerance that fits the budget.
        lo, hi = tol_min, tol_max      # count(lo) > target, count(hi) <= target
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            n, _cl = _eval(mid)
            if n <= target_lines:
                hi = mid               # fits → try finer (smaller tol = more fidelity)
            else:
                lo = mid               # too many lines → need coarser
        tol_star = hi
        n_star, cl_star = _eval(tol_star)
        status = "ok" if cl_star >= floor_clearance - eps else "clearance_limited"
        return {"status": status, "tolerance": tol_star, "lines": n_star,
                "min_clearance": cl_star, "floor": floor_clearance}


class SpinningCamPDF(FPDF):
    """Custom PDF class with helper methods for operation sheets."""
    
    def section_header(self, title: str):
        """Add a section header with background color."""
        self.set_fill_color(70, 130, 180)  # Steel blue
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"  {title}", ln=True, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)
    
    def info_row(self, label: str, value: str):
        """Add a label: value row."""
        self.set_font("Helvetica", "", 9)
        self.cell(50, 5, f"{label}:")
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 5, value, ln=True)

    def _draw_diagram(self, title: str, valid_paths: list, x_min_data: float, x_max_data: float,
                      z_min_data: float, z_max_data: float, draw_h: float,
                      center_x: float, mandrel_mgr, pad_factor: float = 0.06,
                      path_colors: list = None):
        """Shared helper — draws one labelled XZ diagram at the current Y position."""
        x_rng0 = max(x_max_data - x_min_data, 1.0)
        z_rng0 = max(z_max_data - z_min_data, 1.0)
        x_pad  = x_rng0 * pad_factor
        z_pad  = z_rng0 * pad_factor
        x_min  = x_min_data - x_pad;  x_max = x_max_data + x_pad
        z_min  = z_min_data - z_pad;  z_max = z_max_data + z_pad
        x_rng  = x_max - x_min
        z_rng  = z_max - z_min

        lm        = self.l_margin
        tick_lw   = 16.0
        draw_left = lm + tick_lw
        draw_w    = self.w - self.l_margin - self.r_margin - tick_lw

        # --- Diagram title (drawn before capturing draw_top) ---
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(40, 40, 40)
        self.set_x(draw_left)
        self.cell(0, 5, title, ln=True)

        draw_top = self.get_y()
        sz = draw_w / z_rng
        sx = draw_h / x_rng

        def to_pdf(x, z):
            return draw_left + (z - z_min) * sz, draw_top + draw_h - (x - x_min) * sx

        # --- Grid ---
        self.set_line_width(0.15)
        self.set_draw_color(220, 220, 220)
        for i in range(6):
            px, _ = to_pdf(x_min, z_min + i * z_rng / 5)
            self.line(px, draw_top, px, draw_top + draw_h)
        for i in range(5):
            _, py = to_pdf(x_min + i * x_rng / 4, z_min)
            self.line(draw_left, py, draw_left + draw_w, py)

        # --- Mandrel profile ---
        if mandrel_mgr is not None and mandrel_mgr.profile_z is not None and len(mandrel_mgr.profile_z) > 1:
            self.set_draw_color(80, 80, 80)
            self.set_line_width(1.2)
            prev = None
            for mz, mr in zip(mandrel_mgr.profile_z, mandrel_mgr.profile_r):
                px, py = to_pdf(center_x + float(mr), float(mz))
                if prev:
                    self.line(prev[0], prev[1], px, py)
                prev = (px, py)

        # --- Toolpaths ---
        pal = [(65,105,225),(210,50,50),(40,160,40),(200,110,0),(120,0,180),(0,150,150)]
        self.set_line_width(0.4)
        for idx, path in enumerate(valid_paths):
            color_key = path_colors[idx] if (path_colors and idx < len(path_colors)) else idx
            r, g, b = pal[color_key % len(pal)]
            self.set_draw_color(r, g, b)
            prev = None
            for pt in path:
                px, py = to_pdf(float(pt[0]), float(pt[2]))
                if prev:
                    self.line(prev[0], prev[1], px, py)
                prev = (px, py)

        # --- Border ---
        self.set_draw_color(80, 80, 80)
        self.set_line_width(0.5)
        self.rect(draw_left, draw_top, draw_w, draw_h)

        # --- Z tick labels ---
        self.set_font("Helvetica", "", 6)
        self.set_text_color(60, 60, 60)
        for i in range(6):
            z_val = z_min + i * z_rng / 5
            px, _ = to_pdf(x_min, z_val)
            self.set_xy(px - 6, draw_top + draw_h + 1)
            self.cell(12, 3, f"{z_val:.0f}", align="C")

        # --- X tick labels ---
        for i in range(5):
            x_val = x_min + i * x_rng / 4
            _, py = to_pdf(x_val, z_min)
            self.set_xy(lm, py - 1.5)
            self.cell(tick_lw - 2, 3, f"{x_val:.0f}", align="R")

        # --- Axis titles ---
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(40, 40, 40)
        self.set_xy(draw_left + draw_w / 2 - 8, draw_top + draw_h + 5)
        self.cell(16, 4, "Z (mm)", align="C")
        self.set_xy(lm, draw_top + draw_h / 2 - 2)
        self.cell(tick_lw - 2, 4, "X (mm)", align="C")

        # Advance cursor past diagram + labels
        self.set_xy(lm, draw_top + draw_h + 11)

    def add_path_diagram(self, paths: list, params: dict, mandrel_mgr=None):
        """Draw two XZ-plane diagrams: general view (full mandrel) + close view (passes only)."""
        valid_paths = [p for p in paths if len(p) >= 2]
        if not valid_paths:
            return

        self.section_header("2D Path Diagram (XZ Plane)")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(80, 80, 80)
        self.cell(0, 4, "Z = spindle axis (horizontal)   X = radial distance from center (vertical)", ln=True)
        self.ln(4)

        center_x = params.get("mandrel_pos_x_offset", 0.0)

        # Build per-path color index (same operation = same color)
        operations = params.get("operations", [])
        path_colors = []
        op_color_idx = 0
        for op in operations:
            if not op.get("enabled", True):
                continue
            is_cb = op.get("type", "roughing") in ("cutting", "bending")
            count = 1 if is_cb else int(op.get("count", 1))
            has_back = not is_cb and op.get("back_pass_enabled", False)
            for _ in range(count):
                path_colors.append(op_color_idx)
                if has_back:
                    path_colors.append(op_color_idx)
            op_color_idx += 1
        if len(path_colors) != len(valid_paths):
            path_colors = None  # fallback: color by index

        # Passes-only bounding box
        all_pts = np.vstack(valid_paths)
        xs, zs = all_pts[:, 0], all_pts[:, 2]
        px_min, px_max = float(xs.min()), float(xs.max())
        pz_min, pz_max = float(zs.min()), float(zs.max())

        # General view: start from mandrel axis, include full mandrel Z range
        gx_min = center_x
        gx_max = px_max
        gz_min, gz_max = pz_min, pz_max
        if mandrel_mgr is not None and mandrel_mgr.profile_z is not None and len(mandrel_mgr.profile_z) > 1:
            gx_max = max(gx_max, center_x + float(mandrel_mgr.profile_r.max()))
            gz_min = min(gz_min, float(mandrel_mgr.profile_z.min()))
            gz_max = max(gz_max, float(mandrel_mgr.profile_z.max()))

        draw_h = 85.0

        # --- General view ---
        self._draw_diagram(
            "General View", valid_paths,
            gx_min, gx_max, gz_min, gz_max,
            draw_h, center_x, mandrel_mgr,
            path_colors=path_colors,
        )
        self.ln(12)

        # --- Close view (passes only) ---
        self._draw_diagram(
            "Close View - Passes", valid_paths,
            px_min, px_max, pz_min, pz_max,
            draw_h, center_x, mandrel_mgr,
            path_colors=path_colors,
        )
        self.ln(6)

        # --- Stats line ---
        self.set_font("Helvetica", "", 7)
        self.set_text_color(80, 80, 80)
        self.cell(0, 3,
            f"Passes: {len(valid_paths)}   "
            f"Z: {pz_min:.1f} to {pz_max:.1f} mm   "
            f"X: {px_min:.1f} to {px_max:.1f} mm"
        )
