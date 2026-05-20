#!/usr/bin/env python3
"""
Recipe to SCL Converter v2.0
=============================
Converts G-code NC files to SCL Data Block format for TIA Portal.
Follows PLC_Recipe_Format_Spec v2.0 specification.

Usage:
    python recipe_to_scl.py input.nc output.scl --name "DB_RecipeProgram1" --title "Test Urun" --spindle 1000
    
SCL Output Format:
    Creates a DATA_BLOCK with:
    - Header: RecipeHeader UDT (Name, LineCount, Valid, PreScanned, MinX, MaxX, MinZ, MaxZ)
    - Lines: Array[0..N-1] of RecipeLine UDT (X, Z, F, CMD, Param) — dynamic size, min 999

Author: SpinningCam Project
Version: 2.0 - Updated to match PLC_Recipe_Format_Spec
"""

import re
import argparse
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass, field


# CMD Constants (matching PLC spec)
CMD_RAPID = 0           # G0 - Rapid positioning
CMD_LINEAR = 1          # G1 - Linear interpolation with feedrate
CMD_TOOL_CHANGE = 10    # M6 Tn - Tool change
CMD_SPINDLE_ON = 20     # M3 Snnn - Spindle on
CMD_SPINDLE_OFF = 21    # M5 - Spindle off
CMD_DWELL = 30          # G4 P - Dwell/pause
CMD_CYLINDER_GOTO = 40  # M40 Pnnn - Cylinder extend to position (Param * 10 = mm)
CMD_PROGRAM_END = 99    # M30 - Program end

# Constraints from spec
MAX_LINES = 1000
MAX_SPINDLE_RPM = 2550
MAX_FEEDRATE = 3000


@dataclass
class RecipeLineData:
    """Single recipe line data matching PLC RecipeLine structure (12 bytes)."""
    x: float = 0.0
    z: float = 0.0
    f: int = 0          # Feedrate mm/min (Int = 2 bytes)
    cmd: int = 0        # Command type (Byte)
    param: int = 0      # Parameter (Byte) - meaning depends on CMD
    
    def get_cmd_comment(self, mcode_descriptions: dict = None) -> str:
        """Get human-readable comment for CMD type."""
        cmd_names = {
            CMD_RAPID: "G0 Rapid",
            CMD_LINEAR: "G1 Linear",
            CMD_TOOL_CHANGE: f"Tool Change T{self.param}",
            CMD_SPINDLE_ON: f"Spindle ON {self.param * 10} RPM",
            CMD_SPINDLE_OFF: "Spindle OFF",
            CMD_DWELL: f"Dwell {self.param * 0.1:.1f}s",
            CMD_CYLINDER_GOTO: f"Cylinder GOTO {self.param * 10} mm",
            CMD_PROGRAM_END: "Program END"
        }
        if self.cmd in cmd_names:
            return cmd_names[self.cmd]
        if mcode_descriptions:
            desc = mcode_descriptions.get(str(self.cmd), "")
            if desc:
                return f"M{self.cmd} ({desc}) P{self.param}"
        return f"M{self.cmd} P{self.param}"


class GCodeToSCLConverter:
    """
    Converts G-code to SCL Data Block format.
    
    Follows PLC_Recipe_Format_Spec v2.0:
    - 12 bytes per RecipeLine (X:Real, Z:Real, F:Int, CMD:Byte, Param:Byte)
    - Dynamic array size: max(line_count-1, 999) — minimum [0..999] for TIA Portal compatibility
    - Supports RAPID, LINEAR, TOOL_CHANGE, SPINDLE_ON/OFF, DWELL, PROGRAM_END
    """
    
    def __init__(self, default_spindle_rpm: int = 1000, default_feedrate: int = 300):
        """
        Initialize converter.
        
        Args:
            default_spindle_rpm: Default spindle speed if not specified in G-code
            default_feedrate: Default feed rate if not specified in G-code
        """
        self.default_spindle_rpm = min(default_spindle_rpm, MAX_SPINDLE_RPM)
        self.default_feedrate = min(default_feedrate, MAX_FEEDRATE)
        self.lines: List[RecipeLineData] = []
        
        # Bounding box tracking
        self.min_x = float('inf')
        self.max_x = float('-inf')
        self.min_z = float('inf')
        self.max_z = float('-inf')
        
    def _update_bounds(self, x: float, z: float):
        """Update bounding box with new coordinates."""
        self.min_x = min(self.min_x, x)
        self.max_x = max(self.max_x, x)
        self.min_z = min(self.min_z, z)
        self.max_z = max(self.max_z, z)
        
    def _encode_spindle_speed(self, rpm: int) -> int:
        """Encode spindle RPM to Param byte (RPM / 10)."""
        rpm = min(max(0, rpm), MAX_SPINDLE_RPM)
        return rpm // 10
        
    def _encode_dwell_time(self, seconds: float) -> int:
        """Encode dwell time to Param byte (time in 100ms units)."""
        # Param = time in 100ms, max 255 = 25.5 seconds
        return min(int(seconds * 10), 255)
        
    def parse_gcode(self, gcode: str) -> List[RecipeLineData]:
        """
        Parse G-code string and convert to recipe lines.
        
        Supported G-codes:
            G0 Xnnn Znnn       -> CMD=0 (RAPID)
            G1 Xnnn Znnn Fnnn  -> CMD=1 (LINEAR)
            M3 Snnn            -> CMD=20 (SPINDLE_ON), Param=S/10
            M5                 -> CMD=21 (SPINDLE_OFF)
            M6 Tn              -> CMD=10 (TOOL_CHANGE), Param=tool#
            G4 Pnnn            -> CMD=30 (DWELL), Param=P*10 (in 100ms)
            M30                -> CMD=99 (PROGRAM_END)
        """
        self.lines = []
        self.min_x = float('inf')
        self.max_x = float('-inf')
        self.min_z = float('inf')
        self.max_z = float('-inf')
        
        # Current modal state
        current_x = 0.0
        current_z = 0.0
        current_f = self.default_feedrate
        current_mode = CMD_RAPID  # G0 or G1
        spindle_started = False
        
        # Regex patterns
        g_pattern = re.compile(r'G(\d+)', re.IGNORECASE)
        x_pattern = re.compile(r'X([+-]?\d*\.?\d+)', re.IGNORECASE)
        z_pattern = re.compile(r'Z([+-]?\d*\.?\d+)', re.IGNORECASE)
        f_pattern = re.compile(r'F(\d*\.?\d+)', re.IGNORECASE)
        s_pattern = re.compile(r'S(\d+)', re.IGNORECASE)
        t_pattern = re.compile(r'T(\d+)', re.IGNORECASE)
        m_pattern = re.compile(r'M(\d+)', re.IGNORECASE)
        p_pattern = re.compile(r'P(\d*\.?\d+)', re.IGNORECASE)
        
        for line in gcode.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('(') or line.startswith(';') or line.startswith('%'):
                continue
                
            # Check for M codes first
            m_match = m_pattern.search(line)
            if m_match:
                m_code = int(m_match.group(1))
                
                # M3 - Spindle ON
                if m_code == 3:
                    s_match = s_pattern.search(line)
                    rpm = int(s_match.group(1)) if s_match else self.default_spindle_rpm
                    param = self._encode_spindle_speed(rpm)
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_SPINDLE_ON, param=param
                    ))
                    spindle_started = True
                    continue
                    
                # M5 - Spindle OFF
                elif m_code == 5:
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_SPINDLE_OFF, param=0
                    ))
                    continue
                    
                # M6 - Tool Change
                elif m_code == 6:
                    t_match = t_pattern.search(line)
                    tool_num = int(t_match.group(1)) if t_match else 1
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_TOOL_CHANGE, param=min(tool_num, 255)
                    ))
                    continue
                    
                # M40 - Cylinder GOTO
                elif m_code == 40:
                    p_match = p_pattern.search(line)
                    pos_mm = float(p_match.group(1)) if p_match else 0.0
                    param = min(int(round(pos_mm / 10)), 255)
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_CYLINDER_GOTO, param=param
                    ))
                    continue

                # M30 - Program End
                elif m_code == 30:
                    # Will be added at the end
                    continue

                # Generic fallback — any other Mxx: CMD=m_code, Param=P value
                else:
                    p_match = p_pattern.search(line)
                    param = int(float(p_match.group(1))) if p_match else 0
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=m_code, param=min(param, 255)
                    ))
                    continue
            
            # Check for G codes
            g_match = g_pattern.search(line)
            if g_match:
                g_code = int(g_match.group(1))
                
                # G0 - Rapid
                if g_code == 0:
                    current_mode = CMD_RAPID
                    
                # G1 - Linear
                elif g_code == 1:
                    current_mode = CMD_LINEAR
                    
                # G4 - Dwell
                elif g_code == 4:
                    p_match = p_pattern.search(line)
                    if p_match:
                        dwell_sec = float(p_match.group(1))
                        param = self._encode_dwell_time(dwell_sec)
                        self.lines.append(RecipeLineData(
                            x=current_x, z=current_z, f=0,
                            cmd=CMD_DWELL, param=param
                        ))
                    continue
            
            # Parse coordinates
            x_match = x_pattern.search(line)
            z_match = z_pattern.search(line)
            f_match = f_pattern.search(line)
            
            # Update feedrate if specified
            if f_match:
                current_f = min(int(float(f_match.group(1))), MAX_FEEDRATE)
            
            # Only create motion line if X or Z changed
            if x_match or z_match:
                if x_match:
                    current_x = float(x_match.group(1))
                if z_match:
                    current_z = float(z_match.group(1))
                    
                # Update bounding box
                self._update_bounds(current_x, current_z)
                
                # Create motion line
                if current_mode == CMD_RAPID:
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_RAPID, param=0
                    ))
                else:  # CMD_LINEAR
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=current_f,
                        cmd=CMD_LINEAR, param=0
                    ))
            
            # Handle standalone T command (tool select without M6)
            elif 'T' in line.upper() and not m_match:
                t_match = t_pattern.search(line)
                if t_match:
                    tool_num = int(t_match.group(1))
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_TOOL_CHANGE, param=min(tool_num, 255)
                    ))
        
        # Add spindle ON at start if not present
        if not spindle_started and len(self.lines) > 0:
            param = self._encode_spindle_speed(self.default_spindle_rpm)
            self.lines.insert(0, RecipeLineData(
                x=0.0, z=0.0, f=0,
                cmd=CMD_SPINDLE_ON, param=param
            ))
        
        # Add spindle OFF before program end
        if len(self.lines) > 0:
            last_line = self.lines[-1]
            self.lines.append(RecipeLineData(
                x=last_line.x, z=last_line.z, f=0,
                cmd=CMD_SPINDLE_OFF, param=0
            ))
        
        # Add program end
        self.lines.append(RecipeLineData(
            x=0.0, z=0.0, f=0,
            cmd=CMD_PROGRAM_END, param=0
        ))
        
        # Handle edge case for bounding box
        if self.min_x == float('inf'):
            self.min_x = self.max_x = 0.0
            self.min_z = self.max_z = 0.0
            
        return self.lines
        
    def generate_scl(self,
                     db_name: str = "DB_RecipeProgram1",
                     program_title: str = "Untitled Program",
                     force: bool = False,
                     params: dict = None,
                     custom_array_size: int = None) -> str:
        """
        Generate SCL Data Block code matching PLC spec.
        
        Args:
            db_name: Name of the Data Block (e.g., "DB_RecipeProgram1")
            program_title: Human-readable program title (max 20 chars)
            force: If True, generate SCL even if line count exceeds limit
            custom_array_size: If set, overrides the auto-calculated array upper bound

        Returns:
            SCL code as string

        Raises:
            ValueError: If line count exceeds MAX_LINES and force=False
        """
        if not self.lines:
            raise ValueError("No recipe lines loaded. Call parse_gcode() first.")
            
        line_count = len(self.lines)
        
        # Validate line count (unless forced)
        if line_count > MAX_LINES and not force:
            raise ValueError(f"LIMIT_EXCEEDED:{line_count}:{MAX_LINES}")
            
        # Truncate title to 20 chars (PLC String[20] limit)
        safe_title = program_title.replace("'", "''")[:20]
        
        # Build SCL code
        scl_lines = []
        
        # Header comment
        import datetime
        gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scl_lines.append("// ============================================")
        scl_lines.append(f"// {db_name} - {safe_title}")
        scl_lines.append(f"// Lines: {line_count}")
        scl_lines.append(f"// Generated by SpinningCam  [{gen_time}]")
        scl_lines.append("// ============================================")
        if params:
            scl_lines.append("//")
            scl_lines.append("// --- MAKINE AYARLARI ---")
            scl_lines.append(f"// Machine Origin  : X={params.get('machine_origin_x', 0.0)}, Z={params.get('machine_origin_z', 0.0)}")
            inv_x = "INVERTED" if params.get("machine_invert_x", False) else "NORMAL"
            inv_z = "INVERTED" if params.get("machine_invert_z", False) else "NORMAL"
            scl_lines.append(f"// Axis Direction  : X={inv_x}, Z={inv_z}")
            dia = "DIAMETER" if params.get("machine_output_diameter_mode", False) else "RADIUS"
            scl_lines.append(f"// Output Mode     : {dia}")
            scl_lines.append(f"// G54 Offset      : X={params.get('machine_gcode_offset_x', 0.0)}, Z={params.get('machine_gcode_offset_z', 0.0)}")
            scl_lines.append(f"// Home            : X={params.get('home_x', 300.0)}, Z={params.get('home_z', 150.0)}")
            scl_lines.append(f"// Retract         : X={params.get('retract_x', 50.0)}, Z={params.get('retract_z', 50.0)}")
            scl_lines.append("//")
            scl_lines.append("// --- PARCA / BLANK ---")
            scl_lines.append(f"// Blank Radius    : {params.get('blank_radius', 0.0)} mm")
            scl_lines.append(f"// Blank Z Shift   : {params.get('blank_z_shift', 0.0)} mm")
            scl_lines.append(f"// Final Thickness : {params.get('final_part_thickness_on_mandrel', 2.0)} mm")
            scl_lines.append(f"// Safety Clear.   : {params.get('safety_clearance_roller_to_part', 0.5)} mm")
            scl_lines.append("//")
            scl_lines.append("// --- MANDREL POZISYON ---")
            scl_lines.append(f"// Mandrel Offset  : X={params.get('mandrel_pos_x_offset', 0.0)}, Z={params.get('mandrel_pos_z_offset', 0.0)}")
            scl_lines.append(f"// Mandrel Rot     : Rx={params.get('mandrel_rot_x', 0.0)}, Ry={params.get('mandrel_rot_y', 0.0)}, Rz={params.get('mandrel_rot_z', 0.0)}")
            operations = params.get("operations", [])
            if operations:
                scl_lines.append("//")
                scl_lines.append("// --- OPERASYONLAR ---")
                for i, op in enumerate(operations):
                    op_type = op.get("type", "Process").upper()
                    op_count = op.get("count", 1)
                    op_tool = op.get("tool_id", "T0101")
                    op_speed = op.get("speed", 0)
                    op_s_mode = op.get("speed_mode", "CSS")
                    op_feed = op.get("feed", 0)
                    op_f_mode = op.get("feed_mode", "mm_min")
                    op_r = op.get("r_tool", 0)
                    scl_lines.append(
                        f"// Op{i+1}: {op_type}, {op_count} paso, {op_tool}, "
                        f"R={op_r}mm, {op_s_mode}={op_speed}, {op_f_mode}={op_feed}"
                    )
            scl_lines.append("// ============================================")
        scl_lines.append("")
        
        # Data Block declaration
        scl_lines.append(f'DATA_BLOCK "{db_name}"')
        scl_lines.append("{ S7_Optimized_Access := 'TRUE' }")
        scl_lines.append("VERSION : 0.1")
        scl_lines.append("NON_RETAIN")
        scl_lines.append("    VAR ")
        scl_lines.append('        Header : "RecipeHeader";')
        # Array size: user-specified or auto-calculated (minimum 999 for compatibility)
        if custom_array_size is not None:
            array_max = max(custom_array_size - 1, line_count - 1)
        else:
            array_max = max(line_count - 1, 999)
        scl_lines.append(f'        Lines : Array[0..{array_max}] of "RecipeLine";')
        scl_lines.append("    END_VAR")
        
        # BEGIN block with initial values
        scl_lines.append("BEGIN")
        scl_lines.append("    // Header")
        scl_lines.append(f"    Header.sName := '{safe_title}';")
        scl_lines.append(f"    Header.LineCount := {line_count};")
        scl_lines.append("    Header.Valid := TRUE;")
        scl_lines.append("    Header.PreScanned := FALSE;")
        scl_lines.append(f"    Header.MinX := {self.min_x:.3f};")
        scl_lines.append(f"    Header.MaxX := {self.max_x:.3f};")
        scl_lines.append(f"    Header.MinZ := {self.min_z:.3f};")
        scl_lines.append(f"    Header.MaxZ := {self.max_z:.3f};")
        scl_lines.append("    ")
        scl_lines.append(f"    // Recipe Lines ({line_count} total)")
        
        # Generate recipe lines
        mcode_descriptions = (params or {}).get("mcode_descriptions", {})
        for i, line in enumerate(self.lines):
            comment = line.get_cmd_comment(mcode_descriptions)
            scl_lines.append(
                f"    Lines[{i}].X := {line.x:.3f}; "
                f"Lines[{i}].Z := {line.z:.3f}; "
                f"Lines[{i}].F := {line.f}; "
                f"Lines[{i}].CMD := {line.cmd}; "
                f"Lines[{i}].Param := {line.param}; "
                f"// {comment}"
            )
            
        scl_lines.append("END_DATA_BLOCK")
        
        return "\n".join(scl_lines)
        
    def convert_file(self,
                     nc_path: str,
                     scl_path: Optional[str] = None,
                     db_name: str = "DB_RecipeProgram1",
                     program_title: str = "Untitled Program",
                     force: bool = False,
                     params: dict = None,
                     custom_array_size: int = None) -> Tuple[str, dict]:
        """
        Convert G-code file to SCL file.
        
        Args:
            nc_path: Input NC file path
            scl_path: Output SCL file path (auto-generated if None)
            db_name: Data Block name
            program_title: Program title for header
            force: If True, ignore line count limit
            
        Returns:
            Tuple of (output_path, stats_dict)
        """
        nc_path = Path(nc_path)
        
        if scl_path is None:
            scl_path = nc_path.with_suffix('.scl')
        else:
            scl_path = Path(scl_path)
            
        # Read and parse G-code
        with open(nc_path, 'r', encoding='utf-8') as f:
            gcode = f.read()
            
        self.parse_gcode(gcode)
        
        # Generate SCL
        scl_code = self.generate_scl(db_name, program_title, force=force, params=params,
                                     custom_array_size=custom_array_size)
        
        # Write output
        with open(scl_path, 'w', encoding='utf-8') as f:
            f.write(scl_code)
            
        # Statistics
        rapid_count = sum(1 for line in self.lines if line.cmd == CMD_RAPID)
        linear_count = sum(1 for line in self.lines if line.cmd == CMD_LINEAR)
        tool_count = sum(1 for line in self.lines if line.cmd == CMD_TOOL_CHANGE)
        spindle_ops = sum(1 for line in self.lines if line.cmd in (CMD_SPINDLE_ON, CMD_SPINDLE_OFF))
        
        stats = {
            'total_lines': len(self.lines),
            'rapid_moves': rapid_count,
            'linear_moves': linear_count,
            'tool_changes': tool_count,
            'spindle_operations': spindle_ops,
            'db_name': db_name,
            'scl_size_bytes': len(scl_code.encode('utf-8')),
            'estimated_plc_bytes': len(self.lines) * 12,  # 12 bytes per line
            'bounds': {
                'min_x': self.min_x,
                'max_x': self.max_x,
                'min_z': self.min_z,
                'max_z': self.max_z
            }
        }
        
        return str(scl_path), stats


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description='Convert G-code to SCL Data Block (PLC_Recipe_Format_Spec v2.0)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python recipe_to_scl.py spinning.nc output.scl --name "DB_RecipeProgram1"
    python recipe_to_scl.py spinning.nc --spindle 1200 --title "Konik Parca"
    
TIA Portal Import:
    1. Copy the generated .scl file to your TIA Portal project folder
    2. In TIA Portal, right-click "External Source Files" → Add new external file
    3. Select the .scl file
    4. Right-click the imported file → Generate blocks from source
        """
    )
    
    parser.add_argument('input', help='Input G-code file (.nc)')
    parser.add_argument('output', nargs='?', help='Output SCL file (default: same name with .scl)')
    parser.add_argument('--name', '-n', default='DB_RecipeProgram1',
                       help='Data Block name (default: DB_RecipeProgram1)')
    parser.add_argument('--title', '-t', default='SpinningCam Program',
                       help='Program title for header (max 20 chars)')
    parser.add_argument('--spindle', '-s', type=int, default=1000,
                       help='Default spindle speed in RPM (default: 1000)')
    parser.add_argument('--feedrate', '-f', type=int, default=300,
                       help='Default feedrate in mm/min (default: 300)')
    
    args = parser.parse_args()
    
    try:
        converter = GCodeToSCLConverter(
            default_spindle_rpm=args.spindle,
            default_feedrate=args.feedrate
        )
        
        output_path, stats = converter.convert_file(
            args.input,
            args.output,
            db_name=args.name,
            program_title=args.title
        )
        
        print(f"✓ Generated: {output_path}")
        print(f"\n--- SCL Statistics ---")
        print(f"Data Block: {stats['db_name']}")
        print(f"Total Lines: {stats['total_lines']} / {MAX_LINES}")
        print(f"Rapid (G0): {stats['rapid_moves']}")
        print(f"Linear (G1): {stats['linear_moves']}")
        print(f"Tool Changes: {stats['tool_changes']}")
        print(f"Spindle Ops: {stats['spindle_operations']}")
        print(f"SCL File Size: {stats['scl_size_bytes']:,} bytes")
        print(f"Est. PLC Memory: {stats['estimated_plc_bytes']:,} bytes")
        print(f"\n--- Bounding Box ---")
        print(f"X: {stats['bounds']['min_x']:.3f} to {stats['bounds']['max_x']:.3f} mm")
        print(f"Z: {stats['bounds']['min_z']:.3f} to {stats['bounds']['max_z']:.3f} mm")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1
        
    return 0


if __name__ == "__main__":
    exit(main())
