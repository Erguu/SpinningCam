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
    - CHUNKED (default, 2026-08-14): Lines1..LinesN, each Array[0..chunk-1] of
      RecipeLine. Global line g lives at Lines[(g // chunk) + 1][g % chunk].
      Required because READ_DBL silently delivers short copies of a ~12 KB block
      on the S7-1214C, so the PLC pulls the recipe one declared array at a time —
      and READ_DBL's VARIANT source resolves at compile time, so a sub-range can
      only be transferred if it IS its own declaration. See
      letter_spinningcam_chunked_recipes.md.
    - LEGACY (chunk_size=0): one Lines : Array[0..N-1] — dynamic size, min 999,
      matching DB_SelectedRecipe. Kept only for older PLC firmware.

Author: SpinningCam Project
Version: 2.1 - Chunked recipe arrays (Lines1..LinesN)
"""

import re
import math
import argparse
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass, field


def resolve_speed_mode(op):
    """Speed mode for the SCL header comment — the one that will actually run.

    CSS is disabled (path_generator.CSS_SPEED_MODE_ENABLED), so an old op still
    carrying "CSS" runs as RPM; the header must not claim otherwise. Imported
    lazily: this module doubles as a standalone CLI and must not drag in OCC.
    """
    try:
        from path_generator import resolve_speed_mode as _resolve
    except Exception:  # pragma: no cover - standalone CLI use
        return str((op or {}).get("speed_mode", "RPM") or "RPM").upper()
    return _resolve(op)


# CMD Constants (matching PLC spec)
CMD_RAPID = 0           # G0 - Rapid positioning
CMD_LINEAR = 1          # G1 - Linear interpolation with feedrate
CMD_TOOL_CHANGE = 10    # M6 Tn - Tool change
CMD_SPINDLE_ON = 20     # M3 Snnn - Spindle on
CMD_SPINDLE_OFF = 21    # M5 - Spindle off
CMD_DWELL = 30          # G4 P - Dwell/pause
CMD_CYLINDER_GOTO = 40  # M40 Pnnn - Cylinder GOTO; Param = P exactly as typed,
                        # scaling/units are the PLC's business (2026-08-07)
CMD_OP_MARKER = 50      # Operation start; Param = op no, F = total ops  (opt-in)
CMD_PASS_MARKER = 51    # Pass start;      Param = pass no, F = passes in op (opt-in)
CMD_PROGRAM_END = 99    # M30 - Program end

# Pass markers (letter_spinningcam_pass_markers.md, PLC team 2026-09-06).
# Zero-motion lines so the HMI can show "Op 2 of 5 / Pass 3 of 10" instead of a
# line number nobody can read. OFF by default and the export is byte-identical
# when off — the PLC treats 0 as "no pass information" and blanks the display,
# so an unmarked recipe is a permanently supported state, not a legacy one.
#
# Param is a Byte on the PLC side: an op or pass number above this cannot be
# sent without wrapping to a silently wrong number, so we refuse instead.
MAX_MARKER_NUMBER = 255

# Constraints from spec
MAX_LINES = 1000
MAX_SPINDLE_RPM = 2550
MAX_FEEDRATE = 3000

# Chunked recipe geometry (letter_spinningcam_chunked_recipes.md, 2026-08-14).
# The PLC's loader and these declarations must agree EXACTLY: too few arrays is a
# TIA compile error (loud), too many is a silently truncated program, and the
# right count with the wrong size reassembles the recipe scrambled and compiles
# cleanly. That last one is why the geometry is written into the file as a
# parseable "// CHUNKS: n x m" line and re-validated after generation.
DEFAULT_CHUNK_SIZE = 100
CHUNK_HEADER_RE = re.compile(r'^//\s*CHUNKS:\s*(\d+)\s*x\s*(\d+)\s*$')

# Recipe-carried tool table (CAM_TOOL_TABLE_HANDOVER.md). The PLC turret has a
# fixed 4 physical slots; the recipe header now carries the slot->tool-code map so
# the PLC no longer relies on an HMI-entered mapping ("recipe always wins").
MAX_TURRET_SLOTS = 4


def tool_code_from_id(tool_id) -> int:
    """External PLC tool code (a byte) from a CAM tool_id, e.g. 'T0103' -> 103.

    Mirrors the recipe parser's ``T(\\d+)`` rule (int of the digit run) so the
    header ``ToolCode_List`` values match the ``CMD=10 Param`` values exactly.
    """
    digits = "".join(ch for ch in str(tool_id) if ch.isdigit())
    return int(digits) if digits else 0


def normalize_turret(params: dict):
    """Resolve the turret setup from ``params`` into fixed 4-slot arrays.

    Returns ``(codes, angles, auto_angles, tool_count)`` where ``codes`` and
    ``angles`` are length-4 lists for slots 1..4 (``code == 0`` = empty slot),
    ``auto_angles`` is the AutoCalcAngles flag, and ``tool_count`` is the highest
    populated slot index (min 1) so every used code sits within ``[1..ToolCount]``.

    When ``auto_angles`` is true the angles are evenly spaced across ``tool_count``
    (1->0, 2->0/180, 3->0/120/240, 4->0/90/180/270), matching the PLC's own
    auto-spacing; empty trailing slots get 0.0.
    """
    slots = params.get("turret_slots") or []
    auto = bool(params.get("turret_auto_angles", True))
    codes = [0, 0, 0, 0]
    angles = [0.0, 0.0, 0.0, 0.0]
    for i in range(MAX_TURRET_SLOTS):
        if i < len(slots) and isinstance(slots[i], dict):
            try:
                codes[i] = int(float(slots[i].get("code", 0) or 0))
            except (TypeError, ValueError):
                codes[i] = 0
            try:
                angles[i] = float(slots[i].get("angle", 0.0) or 0.0)
            except (TypeError, ValueError):
                angles[i] = 0.0
    populated = [i + 1 for i, c in enumerate(codes) if c != 0]
    tool_count = max(populated) if populated else 1
    if auto:
        n = tool_count
        for i in range(MAX_TURRET_SLOTS):
            angles[i] = round(i * 360.0 / n, 3) if i < n else 0.0
    return codes, angles, auto, tool_count


# Comment forms generate_gcode writes, and the ONLY source of the marker numbers.
# Reusing them rather than recomputing is deliberate: whatever the file says in
# "[Op1 P2]" is what the operator sees on the HMI, so the two can never disagree.
_OP_LIST_RE   = re.compile(r'^\(Op(\d+):')                        # header block, ALL rows
_OP_START_RE  = re.compile(r'^\(--- OP (\d+) START:')             # for_recipe only
_PASS_HDR_RE  = re.compile(r'^\(--- OP (\d+): \w+ - PASO (\d+) ---\)')


def scan_pass_markers(gcode: str):
    """Read the op/pass structure out of the G-code comments.

    Returns ``(total_ops, {op_no: passes_in_that_op})``.

    ``total_ops`` counts the rows in the operation LIST, including ones switched
    off, because the numbers we emit are row numbers (an op tagged ``[Op5 …]`` is
    the 5th row). Counting only the rows that run would produce "Op 5 of 4" the
    moment somebody disables a middle row — which is why we do NOT follow the
    letter's ``TotalOps`` instruction here. See the reply letter.

    A BACK PASS gets no entry of its own: the ``[OpN PM]`` tag on a return pass
    is the one from its forward pass, so the two stay in step.
    """
    total_ops = 0
    passes = {}
    for raw in gcode.split('\n'):
        line = raw.strip()
        if not line.startswith('('):
            continue
        m = _OP_LIST_RE.match(line)
        if m:
            total_ops = max(total_ops, int(m.group(1)))
            continue
        m = _PASS_HDR_RE.match(line)
        if m:
            op_no, pass_no = int(m.group(1)), int(m.group(2))
            passes[op_no] = max(passes.get(op_no, 0), pass_no)
            total_ops = max(total_ops, op_no)
            continue
        m = _OP_START_RE.match(line)
        if m:
            total_ops = max(total_ops, int(m.group(1)))
    return total_ops, passes


def count_pass_markers(gcode: str) -> int:
    """How many extra recipe lines markers would cost this program.

    Independent of decimation tolerance — thinning removes points *inside* a
    pass and never changes how many ops or passes there are. That property is
    what makes the cost predictable, and it is why the auto-tune can simply
    count markers on every probe (``auto_fit_plc_tolerance``) instead of
    subtracting an estimate from the target afterwards.

    Answering "what would markers cost me?" without running a conversion —
    reporting, or a UI preview. The export path does NOT call this; it counts
    the real lines it just built, so the two cannot drift.
    """
    ops = set()
    n_pass = 0
    for raw in gcode.split('\n'):
        line = raw.strip()
        if not line.startswith('(--- OP '):
            continue
        m = _OP_START_RE.match(line)
        if m:
            ops.add(int(m.group(1)))
            continue
        if _PASS_HDR_RE.match(line):
            n_pass += 1
    return len(ops) + n_pass


def recipe_checksum(lines, line_count: int = None) -> int:
    """Order-sensitive 32-bit checksum over the emitted recipe lines.

    Spec + reference implementation: letter_spinningcam_recipe_checksum.md
    (PLC team, 2026-08-14). The PLC recomputes this after reassembling the chunks
    and refuses to run on a mismatch (16#0316).

    Two accumulators with natural wraparound at 2**32 — no modulo (a division per
    line is the most expensive thing on this CPU), no floating point. ``sumB``
    makes it order-sensitive, so chunks reassembled in the wrong order or at the
    wrong stride change the result; ``LineCount`` is folded in so a truncated
    recipe cannot coincidentally match.

    ``lines`` is a sequence of ``(CMD, Param, F)`` triples, or of RecipeLineData.
    Only the first ``line_count`` are covered — emitted lines only, never the
    padding up to the declared capacity.

    X and Z are deliberately excluded: they are IEEE-754 Reals, computed here in
    float64 and on the PLC in float32, so any value-based scheme eventually
    disagrees on a perfectly valid recipe. A checksum that cries wolf gets
    ignored on the day it is real. (The letter offers a separate ``ChecksumXZ``
    over the raw bit patterns as a later, independent field — deliberately NOT
    folded in here.)
    """
    M = 0xFFFFFFFF
    a = b = 0
    n = 0
    for item in lines:
        if line_count is not None and n >= line_count:
            break
        if isinstance(item, RecipeLineData):
            cmd, param, f = item.cmd, item.param, item.f
        else:
            cmd, param, f = item
        a = (a + int(cmd) + int(param) + int(f)) & M
        b = (b + a) & M
        n += 1
    return (b ^ ((a + (line_count if line_count is not None else n)) & M)) & M


def chunk_geometry(line_count: int, capacity: int = None,
                   chunk_size: int = DEFAULT_CHUNK_SIZE) -> dict:
    """Resolve the declared array geometry for ``line_count`` recipe lines.

    ``capacity`` is the total number of recipe elements the DB should declare
    (what the operator calls "recipe database size"); ``None`` means the usual
    max(line_count, 1000). The declared capacity is rounded UP to a whole number
    of arrays, because a partial trailing array would give the PLC a chunk of a
    different length than every other one.

    ``chunk_size <= 0`` selects the legacy single-array layout.

    Returns a dict: ``chunked``, ``chunk_size``, ``chunk_count``, ``capacity``,
    ``used_chunks`` (arrays that actually hold a line), ``end_array``,
    ``end_index`` (where the mandatory CMD=99 marker lands).
    """
    line_count = max(int(line_count), 0)
    if capacity is None:
        capacity = max(line_count, 1000)
    capacity = max(int(capacity), line_count, 1)

    if not chunk_size or int(chunk_size) <= 0:
        return {"chunked": False, "chunk_size": 0, "chunk_count": 0,
                "capacity": capacity, "used_chunks": 0,
                "end_array": 0, "end_index": max(line_count - 1, 0)}

    chunk_size = int(chunk_size)
    chunk_count = max(math.ceil(capacity / chunk_size), 1)
    g_end = max(line_count - 1, 0)
    return {
        "chunked": True,
        "chunk_size": chunk_size,
        "chunk_count": chunk_count,
        "capacity": chunk_count * chunk_size,
        "used_chunks": max(math.ceil(line_count / chunk_size), 0),
        "end_array": g_end // chunk_size + 1,
        "end_index": g_end % chunk_size,
    }


# Regexes for reading a generated .scl back — the validator below is the CAM-side
# twin of the PLC team's split_recipe_db.py --check.
_DECL_RE = re.compile(r'^\s*Lines(\d*)\s*:\s*Array\[\s*0\s*\.\.\s*(\d+)\s*\]\s*of\s*"RecipeLine"\s*;',
                      re.IGNORECASE)
_ASSIGN_RE = re.compile(r'\bLines(\d*)\[\s*(\d+)\s*\]\.X\s*:=', re.IGNORECASE)
_CMD_RE = re.compile(r'\bLines(\d*)\[\s*(\d+)\s*\]\.CMD\s*:=\s*(\d+)', re.IGNORECASE)
_LINECOUNT_RE = re.compile(r'\bHeader\.LineCount\s*:=\s*(\d+)', re.IGNORECASE)
_FIELD_RE = re.compile(r'\bLines(\d*)\[\s*(\d+)\s*\]\.(F|CMD|Param)\s*:=\s*(-?\d+)', re.IGNORECASE)
_PROVIDES_CK_RE = re.compile(r'\bHeader\.ProvidesChecksum\s*:=\s*(TRUE|FALSE)', re.IGNORECASE)
_CHECKSUM_RE = re.compile(r'\bHeader\.Checksum\s*:=\s*(\d+)', re.IGNORECASE)
_DBNAME_RE = re.compile(r'^\s*DATA_BLOCK\s+"([^"]+)"', re.IGNORECASE)


def check_scl_geometry(scl_text: str) -> dict:
    """Validate a generated recipe .scl against its own declared geometry.

    Checks what the TIA compiler cannot: that every global line 0..LineCount-1 is
    written exactly once, that each one lands in the array and index the
    positional mapping demands, that the arrays are declared Lines1..LinesN with
    one uniform size, that the ``// CHUNKS: n x m`` header agrees with the
    declarations, and that the mandatory CMD=99 END marker sits at global line
    LineCount-1. A "right count, wrong chunk size" mismatch compiles cleanly and
    scrambles the recipe — this is what catches it.

    Returns ``{'ok': bool, 'errors': [...], 'warnings': [...], ...geometry}``.
    """
    errors, warnings = [], []
    declared = {}          # array number (0 = legacy unnumbered "Lines") -> upper bound
    header_geo = None
    db_name = None
    for raw in scl_text.split("\n"):
        line = raw.strip()
        m = CHUNK_HEADER_RE.match(line)
        if m:
            header_geo = (int(m.group(1)), int(m.group(2)))
            continue
        if line.startswith("//"):
            continue
        m = _DBNAME_RE.match(raw)
        if m and db_name is None:
            db_name = m.group(1)
        m = _DECL_RE.match(raw)
        if m:
            declared[int(m.group(1)) if m.group(1) else 0] = int(m.group(2))

    m = _LINECOUNT_RE.search(scl_text)
    line_count = int(m.group(1)) if m else None
    if line_count is None:
        errors.append("Header.LineCount is missing.")

    if not declared:
        errors.append('No Lines array declaration found.')
        return {"ok": False, "errors": errors, "warnings": warnings,
                "chunked": False, "chunk_count": 0, "chunk_size": 0,
                "capacity": 0, "line_count": line_count, "db_name": db_name}

    chunked = 0 not in declared
    if not chunked and len(declared) > 1:
        errors.append('Mixed layout: both "Lines" and "Lines<n>" are declared.')

    if chunked:
        nums = sorted(declared)
        chunk_count = len(nums)
        if nums != list(range(1, chunk_count + 1)):
            errors.append(f"Array names are not contiguous Lines1..Lines{chunk_count}: "
                          + ", ".join(f"Lines{n}" for n in nums))
        sizes = {declared[n] + 1 for n in nums}
        if len(sizes) > 1:
            errors.append("Chunk arrays have different sizes: "
                          + ", ".join(str(s) for s in sorted(sizes)))
        chunk_size = sorted(sizes)[0]
    else:
        chunk_count = 1
        chunk_size = declared[0] + 1

    capacity = chunk_count * chunk_size if chunked else chunk_size

    if chunked:
        if header_geo is None:
            warnings.append("No '// CHUNKS: n x m' header — geometry can only be inferred.")
        elif header_geo != (chunk_count, chunk_size):
            errors.append(f"Header says CHUNKS: {header_geo[0]} x {header_geo[1]} but "
                          f"{chunk_count} array(s) of {chunk_size} are declared.")
    elif header_geo is not None:
        errors.append("A '// CHUNKS:' header is present but the DB declares a single "
                      "un-numbered Lines array.")

    # Positional mapping: walk the assignments in file order and demand global
    # line g == the running counter.
    globals_seen = []
    for m in _ASSIGN_RE.finditer(scl_text):
        arr = int(m.group(1)) if m.group(1) else 0
        idx = int(m.group(2))
        if chunked:
            if arr < 1 or arr > chunk_count:
                errors.append(f"Lines{arr}[{idx}] refers to an array that is not declared.")
                continue
            if idx >= chunk_size:
                errors.append(f"Lines{arr}[{idx}] is outside the declared "
                              f"Array[0..{chunk_size - 1}].")
                continue
            globals_seen.append((arr - 1) * chunk_size + idx)
        else:
            if idx >= chunk_size:
                errors.append(f"Lines[{idx}] is outside the declared "
                              f"Array[0..{chunk_size - 1}].")
                continue
            globals_seen.append(idx)

    if line_count is not None:
        if len(globals_seen) != line_count:
            errors.append(f"Header.LineCount is {line_count} but {len(globals_seen)} "
                          f"recipe line(s) are written.")
        if globals_seen != list(range(len(globals_seen))):
            bad = next((i for i, g in enumerate(globals_seen) if g != i), 0)
            errors.append(f"Recipe lines are not contiguous from 0: element #{bad} "
                          f"maps to global line {globals_seen[bad]}.")
        if line_count > capacity:
            errors.append(f"Header.LineCount {line_count} exceeds the declared "
                          f"capacity of {capacity}.")

        # END marker must be the last global line.
        end_cmds = [((int(m.group(1)) if m.group(1) else 1) - 1) * chunk_size + int(m.group(2))
                    for m in _CMD_RE.finditer(scl_text) if int(m.group(3)) == CMD_PROGRAM_END]
        if not end_cmds:
            errors.append(f"No CMD := {CMD_PROGRAM_END} END marker found.")
        elif line_count - 1 not in end_cmds:
            errors.append(f"END marker (CMD := {CMD_PROGRAM_END}) is not at global line "
                          f"{line_count - 1}.")

    # Header checksum: recompute from the lines actually written, so a bad export
    # is caught at the desk instead of at the machine (the PLC would stop with
    # 16#0316). Only meaningful once the mapping above holds.
    m = _PROVIDES_CK_RE.search(scl_text)
    provides_ck = (m.group(1).upper() == "TRUE") if m else False
    m = _CHECKSUM_RE.search(scl_text)
    stated_ck = int(m.group(1)) if m else None
    computed_ck = None
    if provides_ck and line_count is not None and not errors:
        fields = {}
        for m in _FIELD_RE.finditer(scl_text):
            arr = int(m.group(1)) if m.group(1) else 1
            g = (arr - 1) * chunk_size + int(m.group(2))
            fields.setdefault(g, {})[m.group(3).upper()] = int(m.group(4))
        try:
            triples = [(fields[g]["CMD"], fields[g]["PARAM"], fields[g]["F"])
                       for g in range(line_count)]
        except KeyError as e:
            triples = None
            errors.append(f"Cannot verify the checksum: a line is missing field {e}.")
        if triples is not None:
            computed_ck = recipe_checksum(triples, line_count)
            if stated_ck is None:
                errors.append("Header.ProvidesChecksum is TRUE but Header.Checksum is missing.")
            elif stated_ck != computed_ck:
                errors.append(f"Header.Checksum is {stated_ck} but the emitted lines "
                              f"compute to {computed_ck}.")
    elif not provides_ck:
        warnings.append("No checksum (Header.ProvidesChecksum is not TRUE) — the PLC "
                        "will load this but cannot verify what it reassembled.")

    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "chunked": chunked, "chunk_count": chunk_count, "chunk_size": chunk_size,
            "capacity": capacity, "line_count": line_count, "db_name": db_name,
            "provides_checksum": provides_ck, "checksum": stated_ck,
            "computed_checksum": computed_ck}


@dataclass
class RecipeLineData:
    """Single recipe line data matching PLC RecipeLine structure (12 bytes)."""
    x: float = 0.0
    z: float = 0.0
    f: int = 0          # Feedrate mm/min (Int = 2 bytes)
    cmd: int = 0        # Command type (Byte)
    param: int = 0      # Parameter (Byte) - meaning depends on CMD
    pass_label: str = ""  # e.g. "Op1 P2" — for comments only, not sent to PLC
    
    def get_cmd_comment(self, mcode_descriptions: dict = None) -> str:
        """Get human-readable comment for CMD type."""
        cmd_names = {
            CMD_RAPID: "G0 Rapid",
            CMD_LINEAR: "G1 Linear",
            CMD_TOOL_CHANGE: f"Tool Change T{self.param}",
            CMD_SPINDLE_ON: f"Spindle ON {self.param * 10} RPM",
            CMD_SPINDLE_OFF: "Spindle OFF",
            CMD_DWELL: f"Dwell {self.param * 0.1:.1f}s",
            # Param is passed through verbatim from the M40 you typed — this
            # comment must NOT invent a unit the PLC may not agree with.
            CMD_CYLINDER_GOTO: f"Cylinder GOTO P{self.param}",
            CMD_OP_MARKER: f"OPERATION {self.param} of {self.f}",
            CMD_PASS_MARKER: f"PASS {self.param} of {self.f}",
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
    
    def __init__(self, default_spindle_rpm: int = 1000, default_feedrate: int = 300,
                 emit_pass_markers: bool = False):
        """
        Initialize converter.

        Args:
            default_spindle_rpm: Default spindle speed if not specified in G-code
            default_feedrate: Default feed rate if not specified in G-code
            emit_pass_markers: Insert CMD=50/51 op and pass markers. Default False
                keeps the output byte-identical to a build without this feature.
        """
        self.default_spindle_rpm = min(default_spindle_rpm, MAX_SPINDLE_RPM)
        self.default_feedrate = min(default_feedrate, MAX_FEEDRATE)
        self.emit_pass_markers = bool(emit_pass_markers)
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
        current_pass_label = ""
        _pass_header_re = re.compile(r'\(--- OP (\d+): \w+ - PASO (\d+) ---\)')

        # Pass markers: totals come from one pre-scan of the same comments the
        # per-line labels come from, so screen and file cannot drift apart.
        _marker_total_ops, _marker_passes = (
            scan_pass_markers(gcode) if self.emit_pass_markers else (0, {}))
        if self.emit_pass_markers:
            _too_big = [n for n in ([_marker_total_ops] + list(_marker_passes.values()))
                        if n > MAX_MARKER_NUMBER]
            if _too_big:
                raise ValueError(
                    f"MARKER_RANGE:{max(_too_big)}:{MAX_MARKER_NUMBER}")

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

            # Detect pass header comments before skipping
            if line.startswith('(--- OP '):
                m = _pass_header_re.match(line)
                if m:
                    current_pass_label = f"Op{m.group(1)} P{m.group(2)}"
                    if self.emit_pass_markers:
                        # AFTER the setup lines (cylinder / tool change / spindle),
                        # which is where this comment already sits in the stream —
                        # the operator's pass number changes when the pass does.
                        _op_no = int(m.group(1))
                        self.lines.append(RecipeLineData(
                            x=0.0, z=0.0,
                            f=_marker_passes.get(_op_no, int(m.group(2))),
                            cmd=CMD_PASS_MARKER, param=int(m.group(2)),
                            pass_label=current_pass_label
                        ))
                elif self.emit_pass_markers:
                    m = _OP_START_RE.match(line)
                    if m:
                        # BEFORE the setup lines, so nothing on the HMI is blank
                        # while the turret is indexing and the spindle spins up.
                        self.lines.append(RecipeLineData(
                            x=0.0, z=0.0, f=_marker_total_ops,
                            cmd=CMD_OP_MARKER, param=int(m.group(1)),
                            pass_label=f"Op{m.group(1)}"
                        ))

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
                        cmd=CMD_SPINDLE_ON, param=param,
                        pass_label=current_pass_label
                    ))
                    spindle_started = True
                    continue
                    
                # M5 - Spindle OFF
                elif m_code == 5:
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_SPINDLE_OFF, param=0,
                        pass_label=current_pass_label
                    ))
                    continue
                    
                # M6 - Tool Change
                elif m_code == 6:
                    t_match = t_pattern.search(line)
                    tool_num = int(t_match.group(1)) if t_match else 1
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_TOOL_CHANGE, param=min(tool_num, 255),
                        pass_label=current_pass_label
                    ))
                    continue

                # M30 - Program End
                elif m_code == 30:
                    # Will be added at the end
                    continue

                # Generic fallback — any other Mxx (M40 included): CMD=m_code,
                # Param=P exactly as written. The CAM does not reinterpret or
                # rescale a custom command's P; deciding what it means is the
                # PLC's job. Param is a Byte, so the only value the CAM may not
                # be able to honour is one outside 0..255 — refuse it loudly
                # rather than shipping a silently different number.
                else:
                    p_match = p_pattern.search(line)
                    if p_match:
                        p_raw = float(p_match.group(1))
                        if p_raw > 255 or p_raw != int(p_raw):
                            raise ValueError(f"PARAM_RANGE:M{m_code}:{p_match.group(1)}")
                        param = int(p_raw)
                    else:
                        param = 0
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=m_code, param=param,
                        pass_label=current_pass_label
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
                            cmd=CMD_DWELL, param=param,
                            pass_label=current_pass_label
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
                        cmd=CMD_RAPID, param=0,
                        pass_label=current_pass_label
                    ))
                else:  # CMD_LINEAR
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=current_f,
                        cmd=CMD_LINEAR, param=0,
                        pass_label=current_pass_label
                    ))
            
            # Handle standalone T command (tool select without M6)
            elif 'T' in line.upper() and not m_match:
                t_match = t_pattern.search(line)
                if t_match:
                    tool_num = int(t_match.group(1))
                    self.lines.append(RecipeLineData(
                        x=current_x, z=current_z, f=0,
                        cmd=CMD_TOOL_CHANGE, param=min(tool_num, 255),
                        pass_label=current_pass_label
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
        
    def _tool_table_scl(self, params: dict) -> List[str]:
        """Build the CAM-authored tool-table header lines and validate them against
        the tool codes the program actually uses (every ``CMD=10 Param``).

        Emits the 5 fields the PLC's ``RecipeHeader`` v0.2 expects
        (``ProvidesToolConfig``, ``ToolCount``, ``AutoCalcAngles``,
        ``ToolCode_List[1..4]``, ``ToolAngle_List[1..4]``). See
        CAM_TOOL_TABLE_HANDOVER.md.

        Raises ``ValueError('TOOL_TABLE:<msg>')`` on a setup the PLC would reject
        (unmapped tool code -> pre-scan / 16#0311, or a code outside the byte range),
        so the export layer can surface a clear message and abort.
        """
        codes, angles, auto, tool_count = normalize_turret(params or {})

        # Param is a single byte — every configured code must fit 0..255.
        bad = [c for c in codes if c < 0 or c > 255]
        if bad:
            raise ValueError(
                "TOOL_TABLE:Turret tool code(s) "
                + ", ".join(str(c) for c in bad)
                + " are outside the valid 0-255 range (PLC Param is one byte).")

        # Rule #2: every code the program changes to must be mapped to a slot,
        # else the PLC pre-scan fails (16#0308) / the recipe is rejected.
        used = sorted({l.param for l in self.lines
                       if l.cmd == CMD_TOOL_CHANGE and l.param != 0})
        configured = {codes[i] for i in range(tool_count) if codes[i] != 0}
        missing = [c for c in used if c not in configured]
        if missing:
            raise ValueError(
                "TOOL_TABLE:Tool code(s) "
                + ", ".join(str(c) for c in missing)
                + " are used by this program but not assigned to any turret slot.\n"
                + "Set them up in Machine ▸ Turret / Tool Table before exporting.")

        lines = [
            "    ",
            "    // --- Tool table (CAM-authored) ---",
            "    Header.ProvidesToolConfig := TRUE;",
            f"    Header.ToolCount := {tool_count};",
            f"    Header.AutoCalcAngles := {'TRUE' if auto else 'FALSE'};",
        ]
        for i in range(MAX_TURRET_SLOTS):
            note = "  // unused" if codes[i] == 0 else ""
            lines.append(f"    Header.ToolCode_List[{i + 1}] := {codes[i]};{note}")
        for i in range(MAX_TURRET_SLOTS):
            lines.append(f"    Header.ToolAngle_List[{i + 1}] := {angles[i]:.1f};")
        return lines

    def generate_scl(self,
                     db_name: str = "DB_RecipeProgram1",
                     program_title: str = "Untitled Program",
                     force: bool = False,
                     params: dict = None,
                     custom_array_size: int = None,
                     chunk_size: int = None,
                     emit_checksum: bool = True) -> str:
        """
        Generate SCL Data Block code matching PLC spec.

        Args:
            db_name: Name of the Data Block (e.g., "DB_RecipeProgram1")
            program_title: Human-readable program title (max 20 chars)
            force: If True, generate SCL even if line count exceeds limit
            custom_array_size: If set, overrides the auto-calculated capacity.
                CAUTION: READ_DBL copies the recipe into DB_SelectedRecipe, whose
                layout is Array[0..999] — a different total size must be matched
                on the PLC side or the copy fails at STATE_RECIPE_LOAD.
            chunk_size: Lines per declared array. ``None``/0 emits the legacy
                single ``Lines`` array; a positive value emits
                ``Lines1..LinesN``, each ``Array[0..chunk_size-1]``, with global
                line g at ``Lines[(g // chunk_size) + 1][g % chunk_size]``. The
                PLC's chunked loader must use the SAME size — see the
                ``// CHUNKS: n x m`` header line this emits.
            emit_checksum: Write ``Header.ProvidesChecksum`` + ``Header.Checksum``
                (letter_spinningcam_recipe_checksum.md). Escape hatch only: the
                fields must exist in the PLC's ``RecipeHeader`` UDT before such a
                file will import, so pass False if the PLC side has not been
                updated yet. FALSE is a valid answer to the PLC — it accepts the
                flag being clear and skips the check, which is how recipes
                exported before this change still load.

        Returns:
            SCL code as string

        Raises:
            ValueError: If line count exceeds MAX_LINES and force=False, or if
                the generated file fails its own geometry self-check
                ('GEOMETRY:...').
        """
        if not self.lines:
            raise ValueError("No recipe lines loaded. Call parse_gcode() first.")
            
        line_count = len(self.lines)
        
        # Validate line count (unless forced)
        if line_count > MAX_LINES and not force:
            raise ValueError(f"LIMIT_EXCEEDED:{line_count}:{MAX_LINES}")
            
        # Truncate title to 20 chars (PLC String[20] limit)
        safe_title = program_title.replace("'", "''")[:20]

        # Declared array geometry (chunked by default on the caller's side).
        geo = chunk_geometry(line_count, custom_array_size, chunk_size)

        # Build SCL code
        scl_lines = []

        # Header comment
        import datetime
        gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scl_lines.append("// ============================================")
        scl_lines.append(f"// {db_name} - {safe_title}")
        scl_lines.append(f"// Lines: {line_count}")
        if geo["chunked"]:
            # Machine-readable geometry: the PLC side validates its loader against
            # this line, so keep the exact "// CHUNKS: n x m" spelling.
            scl_lines.append(f"// CHUNKS: {geo['chunk_count']} x {geo['chunk_size']}")
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
            scl_lines.append(f"// Min Safety Gap  : {params.get('min_safety_gap', params.get('target_clearance', 0.0))} mm")
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
                    op_s_mode = resolve_speed_mode(op)
                    op_feed = op.get("feed", 0)
                    op_f_mode = op.get("feed_mode", "mm_min")
                    op_r = op.get("r_tool", 0)
                    scl_lines.append(
                        f"// Op{i+1}: {op_type}, {op_count} paso, {op_tool}, "
                        f"R={op_r}mm, {op_s_mode}={op_speed}, {op_f_mode}={op_feed}"
                    )
            scl_lines.append("// ============================================")
        scl_lines.append("")
        
        # Data Block declaration. The attribute block must match
        # 02b_RecipePrograms.scl exactly (TIA V17 / S7-1214C, verified 2026-08-04):
        #   - S7_Optimized_Access FALSE: READ_DBL needs source and destination on
        #     the same access type, and an optimized DB may not contain a STRUCT.
        #   - UNLINKED must come BEFORE NON_RETAIN (reversed order fails to
        #     generate; omitting UNLINKED silently keeps the DB in work memory).
        scl_lines.append(f'DATA_BLOCK "{db_name}"')
        scl_lines.append("{ S7_Optimized_Access := 'FALSE' }")
        scl_lines.append("VERSION : 0.2")
        scl_lines.append("UNLINKED")
        scl_lines.append("NON_RETAIN")
        scl_lines.append("    VAR ")
        scl_lines.append('        Header : "RecipeHeader";')
        if geo["chunked"]:
            # One declaration per chunk. READ_DBL's VARIANT source is resolved at
            # compile time and accepts a whole declared member only — no slice, no
            # variable index — so a sub-range can only be transferred if it IS a
            # declaration of its own. Names must stay Lines1..LinesN: the PLC's
            # loader addresses them by name.
            width = len(f"Lines{geo['chunk_count']}")
            for k in range(1, geo["chunk_count"] + 1):
                g0 = (k - 1) * geo["chunk_size"]
                scl_lines.append(
                    f'        {("Lines%d" % k).ljust(width)} : '
                    f'Array[0..{geo["chunk_size"] - 1}] of "RecipeLine";'
                    f'  // global lines {g0}..{g0 + geo["chunk_size"] - 1}')
        else:
            # Legacy single array: user-specified or auto-calculated (minimum 999
            # so the default matches DB_SelectedRecipe's Array[0..999]).
            scl_lines.append(
                f'        Lines : Array[0..{geo["capacity"] - 1}] of "RecipeLine";')
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
        # Recipe-carried tool table (validates against used tool codes; may raise
        # ValueError('TOOL_TABLE:...')).
        scl_lines.extend(self._tool_table_scl(params or {}))
        # Checksum LAST, after ToolAngle_List — the PLC team asked for the new
        # RecipeHeader fields at the end of the struct so their diff stays
        # reviewable, and this mirrors that order.
        if emit_checksum:
            scl_lines.append("    ")
            scl_lines.append("    // --- Integrity ---")
            scl_lines.append("    // Order-sensitive sum over CMD+Param+F of lines 0..LineCount-1.")
            scl_lines.append("    // The PLC recomputes it after reassembling the chunks and refuses")
            scl_lines.append("    // to run on a mismatch (16#0316). X/Z are excluded on purpose:")
            scl_lines.append("    // float32-vs-float64 rounding would eventually cry wolf.")
            scl_lines.append("    Header.ProvidesChecksum := TRUE;")
            scl_lines.append(f"    Header.Checksum := {recipe_checksum(self.lines, line_count)};")
        scl_lines.append("    ")
        scl_lines.append(f"    // Recipe Lines ({line_count} total)")

        # Generate recipe lines. Global line g -> Lines[(g // chunk) + 1][g % chunk];
        # Header.LineCount keeps counting in GLOBAL lines either way, so the END
        # marker still sits at global line LineCount-1 — just written under its
        # chunk's name.
        mcode_descriptions = (params or {}).get("mcode_descriptions", {})
        cs = geo["chunk_size"]
        for i, line in enumerate(self.lines):
            if geo["chunked"]:
                idx = i % cs
                if idx == 0:
                    scl_lines.append("    ")
                    scl_lines.append(f"    // --- Lines{i // cs + 1} "
                                     f"(global lines {i}..{min(i + cs - 1, line_count - 1)}) ---")
                ref = f"Lines{i // cs + 1}[{idx}]"
            else:
                ref = f"Lines[{i}]"
            comment = line.get_cmd_comment(mcode_descriptions)
            pass_info = f" [{line.pass_label}]" if line.pass_label else ""
            scl_lines.append(
                f"    {ref}.X := {line.x:.3f}; "
                f"{ref}.Z := {line.z:.3f}; "
                f"{ref}.F := {line.f}; "
                f"{ref}.CMD := {line.cmd}; "
                f"{ref}.Param := {line.param}; "
                f"// {comment}{pass_info}"
            )

        scl_lines.append("END_DATA_BLOCK")

        scl_code = "\n".join(scl_lines)

        # Self-check before the file ever reaches TIA. A wrong-but-compilable
        # geometry (right array count, wrong chunk size) reassembles the recipe
        # scrambled on the PLC and nothing downstream would catch it, so refuse to
        # hand back output that fails its own mapping rules.
        report = check_scl_geometry(scl_code)
        if not report["ok"]:
            raise ValueError("GEOMETRY:" + "; ".join(report["errors"]))

        return scl_code
        
    def convert_file(self,
                     nc_path: str,
                     scl_path: Optional[str] = None,
                     db_name: str = "DB_RecipeProgram1",
                     program_title: str = "Untitled Program",
                     force: bool = False,
                     params: dict = None,
                     custom_array_size: int = None,
                     chunk_size: int = None,
                     emit_checksum: bool = True) -> Tuple[str, dict]:
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
                                     custom_array_size=custom_array_size,
                                     chunk_size=chunk_size,
                                     emit_checksum=emit_checksum)

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
            'pass_markers': sum(1 for line in self.lines
                                if line.cmd in (CMD_OP_MARKER, CMD_PASS_MARKER)),
            'db_name': db_name,
            'scl_size_bytes': len(scl_code.encode('utf-8')),
            'estimated_plc_bytes': len(self.lines) * 12,  # 12 bytes per line
            'geometry': chunk_geometry(len(self.lines), custom_array_size, chunk_size),
            'checksum': recipe_checksum(self.lines, len(self.lines)) if emit_checksum else None,
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
    
    parser.add_argument('input', help='Input G-code file (.nc), or an .scl file with --check')
    parser.add_argument('output', nargs='?', help='Output SCL file (default: same name with .scl)')
    parser.add_argument('--check', action='store_true',
                       help='Validate an existing .scl against its own declared chunk '
                            'geometry and exit (no conversion)')
    parser.add_argument('--chunk-size', type=int, default=DEFAULT_CHUNK_SIZE,
                       help=f'Recipe lines per declared array (default: {DEFAULT_CHUNK_SIZE}); '
                            f'0 = legacy single Lines array')
    parser.add_argument('--array-size', type=int, default=None,
                       help='Total recipe capacity in elements (default: max(lines, 1000), '
                            'rounded up to a whole number of chunks)')
    parser.add_argument('--no-checksum', action='store_true',
                       help='Do not write Header.ProvidesChecksum / Header.Checksum. '
                            'Use only while the PLC RecipeHeader UDT still lacks the fields.')
    parser.add_argument('--pass-markers', action='store_true',
                       help='Insert CMD=50 operation and CMD=51 pass markers so the HMI '
                            'can show "Op 2 of 5 / Pass 3 of 10". Costs one recipe line '
                            'per op and per pass; off by default.')
    parser.add_argument('--name', '-n', default='DB_RecipeProgram1',
                       help='Data Block name (default: DB_RecipeProgram1)')
    parser.add_argument('--title', '-t', default='SpinningCam Program',
                       help='Program title for header (max 20 chars)')
    parser.add_argument('--spindle', '-s', type=int, default=1000,
                       help='Default spindle speed in RPM (default: 1000)')
    parser.add_argument('--feedrate', '-f', type=int, default=300,
                       help='Default feedrate in mm/min (default: 300)')
    
    args = parser.parse_args()

    if args.check:
        with open(args.input, 'r', encoding='utf-8') as f:
            report = check_scl_geometry(f.read())
        layout = (f"{report['chunk_count']} x {report['chunk_size']}"
                  if report["chunked"] else f"single Array[0..{report['chunk_size'] - 1}]")
        ck = report.get("checksum")
        ck_txt = (f", checksum={ck} (verified)" if report.get("provides_checksum") and ck is not None
                  else ", no checksum")
        print(f"{args.input}: {report.get('db_name') or '?'} — {layout}, "
              f"LineCount={report.get('line_count')}{ck_txt}")
        for w in report["warnings"]:
            print(f"  ! {w}")
        for e in report["errors"]:
            print(f"  ✗ {e}")
        print("✓ Geometry OK" if report["ok"] else "✗ REFUSED — do not import this file")
        return 0 if report["ok"] else 1

    try:
        converter = GCodeToSCLConverter(
            default_spindle_rpm=args.spindle,
            default_feedrate=args.feedrate,
            emit_pass_markers=args.pass_markers
        )

        output_path, stats = converter.convert_file(
            args.input,
            args.output,
            db_name=args.name,
            program_title=args.title,
            custom_array_size=args.array_size,
            chunk_size=args.chunk_size,
            emit_checksum=not args.no_checksum
        )

        geo = stats.get('geometry', {})
        print(f"✓ Generated: {output_path}")
        if geo.get('chunked'):
            print(f"Layout: CHUNKS {geo['chunk_count']} x {geo['chunk_size']} "
                  f"(Lines1..Lines{geo['chunk_count']}, capacity {geo['capacity']}); "
                  f"END marker at Lines{geo['end_array']}[{geo['end_index']}]")
        else:
            print(f"Layout: legacy single Lines Array[0..{geo.get('capacity', 1000) - 1}]")
        if stats.get('checksum') is not None:
            print(f"Checksum: {stats['checksum']}  (Header.ProvidesChecksum := TRUE)")
        print(f"\n--- SCL Statistics ---")
        print(f"Data Block: {stats['db_name']}")
        print(f"Total Lines: {stats['total_lines']} / {MAX_LINES}")
        print(f"Rapid (G0): {stats['rapid_moves']}")
        print(f"Linear (G1): {stats['linear_moves']}")
        print(f"Tool Changes: {stats['tool_changes']}")
        print(f"Spindle Ops: {stats['spindle_operations']}")
        if stats.get('pass_markers'):
            print(f"Pass Markers: {stats['pass_markers']} (CMD 50/51)")
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
