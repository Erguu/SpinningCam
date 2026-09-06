"""Pass markers (CMD=50 / CMD=51) — letter_spinningcam_pass_markers.md.

The promises being pinned here, in the order they matter:

1. OFF is byte-identical. The whole reason this is an option is that a recipe
   without markers must stay a supported, permanent state — not a legacy one.
2. The numbers on the operator's screen match the "[Op5 P2]" tags in the same
   file. They are read out of those comments, never recomputed, so they cannot
   drift apart.
3. Markers are ordinary recipe lines: counted in LineCount, folded into the
   checksum, subject to the 1000-line ceiling.

Run:  python _test_pass_markers.py
"""
import sys

from recipe_to_scl import (
    GCodeToSCLConverter, scan_pass_markers, count_pass_markers,
    recipe_checksum, CMD_OP_MARKER, CMD_PASS_MARKER, MAX_MARKER_NUMBER,
)

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILED.append(name)


# A program shaped like the real DB_RecipeProgram1: an op list of 5 rows where
# row 4 is switched OFF (so it emits nothing), a two-pass op with a back pass,
# and a Point op that produces no passes at all.
GCODE = """\
(--- OPERASYONLAR ---)
(Op1: ROUGHING, 2 paso, T004, R=44.56mm, RPM=600.0, mm_min=300.0)
(Op2: FINISHING, 1 paso, T004, R=44.56mm, RPM=800.0, mm_min=200.0)
(Op3: POINT, 1 paso, T004, R=44.56mm, RPM=800.0, mm_min=200.0)
(Op4: ROUGHING, 3 paso, T004, R=44.56mm, RPM=0.0, mm_min=300.0)
(Op5: BENDING, 1 paso, T004, R=44.56mm, RPM=0.0, mm_min=300.0)

(--- OP 1 START: ROUGHING ---)
M40 P1
M6 T004 (ROUGHING)
G97 S600 M3
(--- OP 1: ROUGHING - PASO 1 ---)
G0 X100.000 Z10.000
G1 X90.000 Z20.000 F300
(--- OP 1: ROUGHING - BACK PASS 1 ---)
G1 X100.000 Z10.000 F300
(--- OP 1: ROUGHING - PASO 2 ---)
G0 X95.000 Z10.000
G1 X85.000 Z20.000 F300
(--- OP 2 START: FINISHING ---)
G97 S800 M3
(--- OP 2: FINISHING - PASO 1 ---)
G0 X80.000 Z10.000
G1 X75.000 Z25.000 F200
(--- OP 3 START: POINT ---)
(--- OP 3: POINT ---)
G0 X300.000 Z150.000 (Point Op3)
M30
"""


def convert(gcode, markers):
    c = GCodeToSCLConverter(emit_pass_markers=markers)
    c.parse_gcode(gcode)
    return c


# --- 1. OFF changes nothing -------------------------------------------------
off = convert(GCODE, False)
on = convert(GCODE, True)

check("off emits no markers",
      not any(l.cmd in (CMD_OP_MARKER, CMD_PASS_MARKER) for l in off.lines))

off_scl = convert(GCODE, False).generate_scl("DB_RecipeProgram1", "T", params={
    "turret_slots": [{"code": 4, "angle": 0.0}]})
baseline = convert(GCODE, False).generate_scl("DB_RecipeProgram1", "T", params={
    "turret_slots": [{"code": 4, "angle": 0.0}]})
check("off is byte-identical run to run", off_scl == baseline)

stripped = [l for l in on.lines if l.cmd not in (CMD_OP_MARKER, CMD_PASS_MARKER)]
check("markers are purely additive — nothing else moves",
      [(l.cmd, l.param, l.f, round(l.x, 3), round(l.z, 3)) for l in stripped]
      == [(l.cmd, l.param, l.f, round(l.x, 3), round(l.z, 3)) for l in off.lines],
      f"{len(stripped)} vs {len(off.lines)}")


# --- 2. The numbers match the comments --------------------------------------
total_ops, passes = scan_pass_markers(GCODE)
check("total ops counts LIST rows, including the switched-off ones",
      total_ops == 5, f"got {total_ops}")
check("passes per op read from the PASO headers",
      passes == {1: 2, 2: 1}, f"got {passes}")
check("a back pass gets no pass number of its own",
      passes.get(1) == 2, f"got {passes.get(1)}")

op_marks = [(l.param, l.f) for l in on.lines if l.cmd == CMD_OP_MARKER]
check("one op marker per op that runs, numbered by list row",
      op_marks == [(1, 5), (2, 5), (3, 5)], f"got {op_marks}")

pass_marks = [(l.param, l.f) for l in on.lines if l.cmd == CMD_PASS_MARKER]
check("pass markers carry pass no + passes in that op",
      pass_marks == [(1, 2), (2, 2), (1, 1)], f"got {pass_marks}")

check("a Point op gets an op marker but no pass marker",
      (3, 5) in op_marks and len(pass_marks) == 3)

check("markers carry no motion",
      all(l.x == 0.0 and l.z == 0.0
          for l in on.lines if l.cmd in (CMD_OP_MARKER, CMD_PASS_MARKER)))


# --- 3. Placement -----------------------------------------------------------
seq = [(l.cmd, l.param) for l in on.lines]
i_op1 = seq.index((CMD_OP_MARKER, 1))
i_tool = next(i for i, l in enumerate(on.lines) if l.cmd == 10)
i_pass1 = seq.index((CMD_PASS_MARKER, 1))
check("op marker sits BEFORE the tool change / spindle block", i_op1 < i_tool)
check("pass marker sits AFTER it", i_pass1 > i_tool)

# The op marker must not land before the cylinder line that opens the op.
i_cyl = next(i for i, l in enumerate(on.lines) if l.cmd == 40)
check("op marker opens the operation", i_op1 < i_cyl)


# --- 4. Ordinary recipe lines -----------------------------------------------
check("markers are counted in the line count",
      len(on.lines) == len(off.lines) + 6, f"{len(on.lines)} vs {len(off.lines)}")
check("count_pass_markers predicts the cost without converting",
      count_pass_markers(GCODE) == 6, f"got {count_pass_markers(GCODE)}")
check("checksum changes once markers are folded in",
      recipe_checksum(on.lines, len(on.lines))
      != recipe_checksum(off.lines, len(off.lines)))

# The checksum must be computed over the lines AS WRITTEN — markers included —
# or the PLC re-derives a different number and refuses to run (16#0316).
_scl = convert(GCODE, True).generate_scl(
    "DB_RecipeProgram1", "T", params={"turret_slots": [{"code": 4, "angle": 0.0}]})
_ck = recipe_checksum(on.lines, len(on.lines))
check("the written file carries the marker-inclusive checksum",
      f"Header.Checksum := {_ck};" in _scl)
check("LineCount in the file includes the markers",
      f"Header.LineCount := {len(on.lines)};" in _scl)
check("marker lines reach the SCL body",
      ".CMD := 50;" in _scl and ".CMD := 51;" in _scl)
check("marker comment is readable", "OPERATION 1 of 5" in _scl and "PASS 2 of 2" in _scl)


# --- 5. The byte ceiling ----------------------------------------------------
big = "(--- OPERASYONLAR ---)\n"
big += "".join(f"(Op{i}: ROUGHING, 1 paso, T004, R=1mm, RPM=1.0, mm_min=1.0)\n"
               for i in range(1, MAX_MARKER_NUMBER + 2))
big += "(--- OP 1 START: ROUGHING ---)\nM6 T004\n(--- OP 1: ROUGHING - PASO 1 ---)\nG1 X1.000 Z1.000 F300\nM30\n"
try:
    convert(big, True)
    check("an op number past 255 is refused, not wrapped", False, "no error raised")
except ValueError as e:
    check("an op number past 255 is refused, not wrapped",
          str(e).startswith("MARKER_RANGE:"), str(e))
try:
    convert(big, False)
    check("...and only when markers are on", True)
except ValueError as e:
    check("...and only when markers are on", False, str(e))


print()
if FAILED:
    print(f"{len(FAILED)} FAILED: " + ", ".join(FAILED))
    sys.exit(1)
print("all pass-marker tests pass")
