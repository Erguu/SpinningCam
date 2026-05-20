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
    def export_pdf(params: dict, paths: list, filepath: str, tools: list = None) -> bool:
        """
        Export an operation sheet PDF for shop floor use.
        
        Args:
            params: Current parameters dictionary.
            paths: List of calculated toolpaths.
            filepath: Output PDF file path.
            tools: Optional list of tool definitions.
            
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
            pdf.info_row("Shell Thickness", f"{params.get('shell_thickness', 0):.1f} mm")
            pdf.info_row("Part Thickness", f"{params.get('final_part_thickness_on_mandrel', 0):.1f} mm")
            pdf.ln(3)
            
            # Operations Section
            operations = params.get("operations", [])
            pdf.section_header(f"Operations ({len(operations)} total)")
            
            for i, op in enumerate(operations):
                op_type = op.get("type", "unknown").capitalize()
                enabled = "YES" if op.get("enabled", True) else "NO"
                count = op.get("count", 1)
                tool_id = op.get("tool_id", "T0101")
                r_tool = op.get("r_tool", 25.0)
                
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, f"{i+1}. {op_type} [{enabled}]", ln=True)
                pdf.set_font("Helvetica", "", 9)
                pdf.cell(10)  # indent
                pdf.cell(0, 5, f"Passes: {count}  |  Tool: {tool_id}  |  Radius: {r_tool:.1f}mm", ln=True)
                
                # Zone info if present
                zones = op.get("zones", [])
                if zones:
                    pdf.cell(10)
                    pdf.cell(0, 5, f"Zones: {len(zones)}", ln=True)
            
            pdf.ln(3)
            
            # Path Summary
            pdf.section_header("Path Summary")
            total_points = sum(len(p) for p in paths) if paths else 0
            pdf.info_row("Total Passes", str(len(paths)))
            pdf.info_row("Total Points", str(total_points))
            pdf.ln(3)
            
            # Machine Settings
            pdf.section_header("Machine Settings")
            pdf.info_row("Program Start X", f"{params.get('home_x', 300):.1f} mm")
            pdf.info_row("Program Start Z", f"{params.get('home_z', 150):.1f} mm")
            pdf.info_row("Retract X", f"{params.get('retract_x', 50):.1f} mm (rel)")
            pdf.info_row("Retract Z", f"{params.get('retract_z', 50):.1f} mm (rel)")
            pdf.info_row("Invert X", "Yes" if params.get("machine_invert_x", False) else "No")
            pdf.ln(3)
            
            # G-Code Header/Footer
            pdf.section_header("G-Code Templates")
            pdf.set_font("Courier", "", 8)
            header = params.get("gcode_header", "")
            footer = params.get("gcode_footer", "")
            pdf.multi_cell(0, 4, f"Header:\n{header}")
            pdf.ln(2)
            pdf.multi_cell(0, 4, f"Footer:\n{footer}")
            
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
