#!/usr/bin/env python3
"""
G-Code to Recipe Converter
===========================
Converts standard G-code (.nc) files to compact recipe format (.csv) for PLC.

This converter addresses the memory limitation of the S7-1200 CPU 1214C by
transforming text-based G-code into a numerical recipe format that is:
- ~50% more memory efficient (16 bytes vs ~30 bytes per move)
- Eliminates runtime string parsing on the PLC
- Direct array-based data access

Recipe Format:
    X     = Target X position (mm, REAL)
    Z     = Target Z position (mm, REAL)  
    F     = Feedrate (mm/min, INT 0-9999)
    CMD   = Command type:
            0  = G0 (Rapid move)
            1  = G1 (Linear interpolation)
            10 = Tool change (M6/T command)
            99 = Program end (M30/M2)

Usage:
    python gcode_to_recipe.py input.nc output.csv
    
    Or as a module:
        from gcode_to_recipe import GCodeToRecipeConverter
        converter = GCodeToRecipeConverter()
        converter.convert_file("input.nc", "output.csv")

Author: SpinningCam Project
Version: 1.0
"""

import re
import sys
import argparse
from typing import Optional, Tuple, List, NamedTuple
from pathlib import Path
from dataclasses import dataclass


class RecipeLine(NamedTuple):
    """Represents a single recipe line with all parameters."""
    x: float
    z: float
    f: int
    cmd: int
    comment: Optional[str] = None


@dataclass
class ParserState:
    """Maintains modal G-code state during parsing."""
    current_x: float = 0.0
    current_z: float = 0.0
    current_f: int = 0
    modal_g: int = 0  # 0=G0, 1=G1
    absolute_mode: bool = True  # G90=True, G91=False
    

class GCodeToRecipeConverter:
    """
    Converts G-code files to the compact recipe format.
    
    This converter handles:
    - G0/G00: Rapid positioning (CMD=0)
    - G1/G01: Linear interpolation (CMD=1)
    - G90: Absolute positioning mode
    - G91: Incremental positioning mode
    - M6/T: Tool change commands (CMD=10)
    - M30/M2/M5: Program end commands (CMD=99)
    - Modal feedrate (F value persists across lines)
    - Comments (lines starting with ; or enclosed in parentheses)
    """
    
    # Command code mapping
    CMD_RAPID = 0       # G0
    CMD_LINEAR = 1      # G1
    CMD_TOOL_CHANGE = 10  # M6, T
    CMD_END = 99        # M30, M2
    
    # Regex patterns for parsing G-code
    PATTERNS = {
        'g_code': re.compile(r'G\s*([0-9]+)', re.IGNORECASE),
        'x_value': re.compile(r'X\s*([+-]?[0-9]*\.?[0-9]+)', re.IGNORECASE),
        'z_value': re.compile(r'Z\s*([+-]?[0-9]*\.?[0-9]+)', re.IGNORECASE),
        'f_value': re.compile(r'F\s*([0-9]+)', re.IGNORECASE),
        'm_code': re.compile(r'M\s*([0-9]+)', re.IGNORECASE),
        't_code': re.compile(r'T\s*([0-9]+)', re.IGNORECASE),
        'comment_paren': re.compile(r'\(([^)]*)\)'),
        'comment_semi': re.compile(r';(.*)$'),
    }
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the converter.
        
        Args:
            verbose: If True, print detailed parsing information.
        """
        self.verbose = verbose
        self.state = ParserState()
        self.recipe_lines: List[RecipeLine] = []
        self.line_count = 0
        self.warnings: List[str] = []
        
    def reset(self):
        """Reset the converter state for a new file."""
        self.state = ParserState()
        self.recipe_lines = []
        self.line_count = 0
        self.warnings = []
        
    def _log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(f"[DEBUG] {message}")
            
    def _warn(self, line_num: int, message: str):
        """Record a warning message."""
        warning = f"Line {line_num}: {message}"
        self.warnings.append(warning)
        if self.verbose:
            print(f"[WARN] {warning}")
            
    def _extract_comment(self, line: str) -> Tuple[str, Optional[str]]:
        """
        Extract and remove comments from a G-code line.
        
        Args:
            line: The G-code line
            
        Returns:
            Tuple of (cleaned line, extracted comment or None)
        """
        comment = None
        
        # Check for parentheses comments
        paren_match = self.PATTERNS['comment_paren'].search(line)
        if paren_match:
            comment = paren_match.group(1).strip()
            line = self.PATTERNS['comment_paren'].sub('', line)
            
        # Check for semicolon comments
        semi_match = self.PATTERNS['comment_semi'].search(line)
        if semi_match:
            if comment:
                comment += " | " + semi_match.group(1).strip()
            else:
                comment = semi_match.group(1).strip()
            line = self.PATTERNS['comment_semi'].sub('', line)
            
        return line.strip(), comment
        
    def _parse_line(self, line: str, line_num: int) -> Optional[RecipeLine]:
        """
        Parse a single G-code line and return a RecipeLine if motion is detected.
        
        Args:
            line: The G-code line to parse
            line_num: Line number for error reporting
            
        Returns:
            RecipeLine if the line produces motion, None otherwise
        """
        # Remove comments and clean the line
        cleaned_line, comment = self._extract_comment(line)
        
        # Skip empty lines and comment-only lines
        if not cleaned_line or cleaned_line.startswith('%') or cleaned_line.startswith('O'):
            return None
            
        # Check for M-codes first
        m_match = self.PATTERNS['m_code'].findall(cleaned_line)
        for m_code in m_match:
            m_val = int(m_code)
            if m_val in (2, 30):  # Program end
                return RecipeLine(0.0, 0.0, 0, self.CMD_END, "Program End")
            elif m_val == 6:  # Tool change
                return RecipeLine(0.0, 0.0, 0, self.CMD_TOOL_CHANGE, "Tool Change")
                
        # Check for T-code (tool change)
        t_match = self.PATTERNS['t_code'].search(cleaned_line)
        if t_match and 'M' not in cleaned_line.upper():
            # Standalone T command
            return RecipeLine(0.0, 0.0, 0, self.CMD_TOOL_CHANGE, f"Tool T{t_match.group(1)}")
            
        # Check for G-codes
        g_matches = self.PATTERNS['g_code'].findall(cleaned_line)
        for g_code in g_matches:
            g_val = int(g_code)
            if g_val == 0:  # G0 - Rapid
                self.state.modal_g = 0
            elif g_val == 1:  # G1 - Linear
                self.state.modal_g = 1
            elif g_val == 90:  # Absolute mode
                self.state.absolute_mode = True
                self._log(f"Switched to absolute mode (G90)")
            elif g_val == 91:  # Incremental mode
                self.state.absolute_mode = False
                self._log(f"Switched to incremental mode (G91)")
            # Skip other G-codes (G17, G21, G54, G50, G96, etc.)
            
        # Extract X, Z, F values
        x_match = self.PATTERNS['x_value'].search(cleaned_line)
        z_match = self.PATTERNS['z_value'].search(cleaned_line)
        f_match = self.PATTERNS['f_value'].search(cleaned_line)
        
        # Update feedrate (modal)
        if f_match:
            self.state.current_f = int(float(f_match.group(1)))
            
        # If no motion values, skip this line
        if not x_match and not z_match:
            return None
            
        # Calculate new positions
        new_x = self.state.current_x
        new_z = self.state.current_z
        
        if x_match:
            x_val = float(x_match.group(1))
            if self.state.absolute_mode:
                new_x = x_val
            else:
                new_x = self.state.current_x + x_val
                
        if z_match:
            z_val = float(z_match.group(1))
            if self.state.absolute_mode:
                new_z = z_val
            else:
                new_z = self.state.current_z + z_val
                
        # Determine command type
        cmd = self.CMD_RAPID if self.state.modal_g == 0 else self.CMD_LINEAR
        
        # Get feedrate (use 0 for rapids)
        feed = 0 if cmd == self.CMD_RAPID else self.state.current_f
        
        # Update state
        self.state.current_x = new_x
        self.state.current_z = new_z
        
        return RecipeLine(new_x, new_z, feed, cmd, comment)
        
    def convert_string(self, gcode: str) -> List[RecipeLine]:
        """
        Convert a G-code string to recipe format.
        
        Args:
            gcode: The G-code content as a string
            
        Returns:
            List of RecipeLine objects
        """
        self.reset()
        
        lines = gcode.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
                
            result = self._parse_line(line, line_num)
            if result:
                self.recipe_lines.append(result)
                self.line_count += 1
                self._log(f"Line {line_num}: X={result.x:.3f}, Z={result.z:.3f}, "
                         f"F={result.f}, CMD={result.cmd}")
                         
        # Ensure program ends with CMD=99
        if not self.recipe_lines or self.recipe_lines[-1].cmd != self.CMD_END:
            self.recipe_lines.append(RecipeLine(0.0, 0.0, 0, self.CMD_END, "Auto-added End"))
            self._log("Added automatic program end (CMD=99)")
            
        return self.recipe_lines
        
    def convert_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert a G-code file to recipe format CSV.
        
        Args:
            input_path: Path to the input .nc file
            output_path: Path for output .csv file (auto-generated if None)
            
        Returns:
            Path to the output file
        """
        input_path = Path(input_path)
        
        if output_path is None:
            output_path = input_path.with_suffix('.csv')
        else:
            output_path = Path(output_path)
            
        # Read input file
        with open(input_path, 'r', encoding='utf-8') as f:
            gcode = f.read()
            
        # Convert
        self.convert_string(gcode)
        
        # Write output
        self._write_csv(output_path)
        
        return str(output_path)
        
    def _write_csv(self, output_path: Path):
        """Write the recipe lines to a CSV file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header comments
            f.write("# Recipe Format - Auto-generated from G-code\n")
            f.write("# X,Z,F,CMD\n")
            f.write("# CMD: 0=G0(Rapid), 1=G1(Linear), 10=ToolChange, 99=End\n")
            f.write("#\n")
            
            # Write CSV header
            f.write("X,Z,F,CMD\n")
            
            # Write data lines
            for recipe in self.recipe_lines:
                # Add comment if present
                if recipe.comment:
                    f.write(f"# --- {recipe.comment} ---\n")
                    
                f.write(f"{recipe.x:.3f},{recipe.z:.3f},{recipe.f},{recipe.cmd}\n")
                
    def get_statistics(self) -> dict:
        """
        Get statistics about the conversion.
        
        Returns:
            Dictionary with conversion statistics
        """
        rapid_count = sum(1 for r in self.recipe_lines if r.cmd == self.CMD_RAPID)
        linear_count = sum(1 for r in self.recipe_lines if r.cmd == self.CMD_LINEAR)
        tool_count = sum(1 for r in self.recipe_lines if r.cmd == self.CMD_TOOL_CHANGE)
        
        return {
            'total_lines': len(self.recipe_lines),
            'rapid_moves': rapid_count,
            'linear_moves': linear_count,
            'tool_changes': tool_count,
            'warnings': len(self.warnings),
            'estimated_bytes': len(self.recipe_lines) * 16,  # 4 x 4-byte values
        }


def main():
    """Command-line interface for the converter."""
    parser = argparse.ArgumentParser(
        description='Convert G-code to PLC recipe format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python gcode_to_recipe.py spinning_output.nc
    python gcode_to_recipe.py input.nc output.csv -v
    python gcode_to_recipe.py *.nc --batch
        """
    )
    
    parser.add_argument('input', help='Input G-code file (.nc)')
    parser.add_argument('output', nargs='?', help='Output recipe file (.csv)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    parser.add_argument('--stats', action='store_true',
                       help='Print conversion statistics')
    
    args = parser.parse_args()
    
    converter = GCodeToRecipeConverter(verbose=args.verbose)
    
    try:
        output_path = converter.convert_file(args.input, args.output)
        print(f"✓ Converted: {args.input} -> {output_path}")
        
        if args.stats:
            stats = converter.get_statistics()
            print(f"\n--- Conversion Statistics ---")
            print(f"Total recipe lines: {stats['total_lines']}")
            print(f"Rapid moves (G0):   {stats['rapid_moves']}")
            print(f"Linear moves (G1):  {stats['linear_moves']}")
            print(f"Tool changes:       {stats['tool_changes']}")
            print(f"Estimated PLC memory: {stats['estimated_bytes']:,} bytes")
            
            if stats['warnings'] > 0:
                print(f"\n⚠ Warnings: {stats['warnings']}")
                for w in converter.warnings:
                    print(f"  - {w}")
                    
    except FileNotFoundError:
        print(f"✗ Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
