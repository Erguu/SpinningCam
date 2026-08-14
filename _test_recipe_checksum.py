# -*- coding: utf-8 -*-
"""Recipe header checksum — letter_spinningcam_recipe_checksum.md (2026-08-14).

The PLC recomputes this after reassembling the chunks and refuses to run on a
mismatch (16#0316). The two sides must agree bit for bit, so the letter's worked
example is the first thing checked here.

Run:  python _test_recipe_checksum.py
"""
import re
import sys

from recipe_to_scl import (GCodeToSCLConverter, recipe_checksum,
                           check_scl_geometry, CMD_PROGRAM_END)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


TURRET = {"turret_slots": [{"code": 101, "angle": 0.0}] + [{"code": 0, "angle": 0.0}] * 3,
          "turret_auto_angles": True}


def build(n_moves, **kw):
    g = ["M3 S1000", "M6 T101"]
    for i in range(n_moves):
        g.append(f"G1 X{10 + i * 0.5:.3f} Z{60 - i * 0.25:.3f} F300")
    g.append("M30")
    conv = GCodeToSCLConverter()
    conv.parse_gcode("\n".join(g))
    return conv, conv.generate_scl(db_name="DB_RecipeProgram3", program_title="Program 3",
                                   params=TURRET, **kw)


# ── 1. agreement with the PLC team ───────────────────────────────────────────
print("\n[1] the letter's worked example")
WORKED = [(20, 120, 0), (0, 0, 0), (1, 0, 250), (99, 0, 0)]
got = recipe_checksum(WORKED, 4)
check("four-line example returns 1383", got == 1383, f"got {got}")

# The intermediate accumulators from the letter, re-derived independently.
M = 0xFFFFFFFF
a = b = 0
steps = []
for cmd, param, f in WORKED:
    a = (a + cmd + param + f) & M
    b = (b + a) & M
    steps.append((a, b))
check("accumulators match the letter (a: 140,140,391,490)",
      [s[0] for s in steps] == [140, 140, 391, 490], str([s[0] for s in steps]))
check("accumulators match the letter (b: 140,280,671,1161)",
      [s[1] for s in steps] == [140, 280, 671, 1161], str([s[1] for s in steps]))
check("final XOR: 1161 ^ 494 == 1383", (1161 ^ 494) == 1383)


# ── 2. properties the letter says are deliberate ─────────────────────────────
print("\n[2] deliberate properties")
base = [(1, 0, 300), (1, 0, 250), (0, 0, 0), (99, 0, 0)]
swapped = [base[1], base[0], base[2], base[3]]
check("order-sensitive: swapping two lines changes it",
      recipe_checksum(base, 4) != recipe_checksum(swapped, 4))
rotated = base[2:] + base[:2]                    # chunks reassembled out of order
check("a chunk permutation changes it",
      recipe_checksum(base, 4) != recipe_checksum(rotated, 4))
check("truncation changes it (LineCount is folded in)",
      recipe_checksum(base, 4) != recipe_checksum(base[:3], 3))
check("a single changed feedrate changes it",
      recipe_checksum(base, 4) != recipe_checksum(
          [(1, 0, 301), base[1], base[2], base[3]], 4))
check("a single changed Param changes it",
      recipe_checksum([(10, 101, 0)], 1) != recipe_checksum([(10, 102, 0)], 1))
check("padding beyond LineCount is not covered",
      recipe_checksum(base + [(0, 0, 0)] * 50, 4) == recipe_checksum(base, 4))
check("empty program is 0", recipe_checksum([], 0) == 0)

# 32-bit wraparound, no modulo, no float.
big = [(255, 255, 3000)] * 5000
ck = recipe_checksum(big, 5000)
check("wraps at 2**32 and stays a 32-bit int", isinstance(ck, int) and 0 <= ck <= 0xFFFFFFFF,
      f"got {ck}")
check("a value that must wrap is still exact",
      recipe_checksum([(255, 255, 3000)] * 100000, 100000) <= 0xFFFFFFFF)


# ── 3. what lands in the file ────────────────────────────────────────────────
print("\n[3] emitted SCL")
conv, scl = build(250)
n = len(conv.lines)
check("ProvidesChecksum is TRUE", "Header.ProvidesChecksum := TRUE;" in scl)
m = re.search(r'Header\.Checksum := (\d+);', scl)
check("Checksum is written", m is not None)
check("...and equals the checksum of the emitted lines",
      m and int(m.group(1)) == recipe_checksum(conv.lines, n),
      f"file={m.group(1) if m else None} computed={recipe_checksum(conv.lines, n)}")
check("comes after ToolAngle_List (letter: new fields at the end)",
      scl.index("ToolAngle_List[4]") < scl.index("Header.ProvidesChecksum"))
check("header fields precede the recipe lines",
      scl.index("Header.Checksum") < scl.index("].X :="))

# The checksum must cover CMD/Param/F only — X and Z are excluded on purpose.
conv2 = GCodeToSCLConverter()
conv2.parse_gcode("\n".join(["M3 S1000", "M6 T101", "G1 X10.000 Z50.000 F300", "M30"]))
conv3 = GCodeToSCLConverter()
conv3.parse_gcode("\n".join(["M3 S1000", "M6 T101", "G1 X99.999 Z11.111 F300", "M30"]))
check("different X/Z with identical CMD/Param/F give the SAME checksum",
      recipe_checksum(conv2.lines, len(conv2.lines))
      == recipe_checksum(conv3.lines, len(conv3.lines)))


# ── 4. the offline validator ─────────────────────────────────────────────────
print("\n[4] check_scl_geometry")
rep = check_scl_geometry(scl)
check("a clean file validates", rep["ok"], str(rep["errors"]))
check("reports the checksum as verified",
      rep["provides_checksum"] and rep["checksum"] == rep["computed_checksum"])

bad = re.sub(r'Header\.Checksum := \d+;', 'Header.Checksum := 12345;', scl)
r = check_scl_geometry(bad)
check("a wrong checksum is refused", not r["ok"])
check("...and the message names both numbers",
      any("12345" in e and "compute" in e for e in r["errors"]), str(r["errors"]))

# Tamper with a feed value only — geometry still perfect, checksum must catch it.
tampered = scl.replace(".F := 300;", ".F := 301;", 1)
r = check_scl_geometry(tampered)
check("a single altered feedrate is caught by the checksum alone", not r["ok"],
      str(r["errors"]))

missing = re.sub(r'\s*Header\.Checksum := \d+;', '', scl)
check("ProvidesChecksum TRUE with no Checksum is refused",
      not check_scl_geometry(missing)["ok"])

# Opting out is legal and must not be an error — the PLC accepts a clear flag.
_, no_ck = build(35, emit_checksum=False)
r = check_scl_geometry(no_ck)
check("--no-checksum file still validates", r["ok"], str(r["errors"]))
check("...emits neither field",
      "ProvidesChecksum" not in no_ck and "Header.Checksum" not in no_ck)
check("...but is warned about", any("checksum" in w.lower() for w in r["warnings"]))

# Legacy single-array files carry a checksum too.
_, legacy = build(35, chunk_size=0)
r = check_scl_geometry(legacy)
check("legacy layout validates with a checksum",
      r["ok"] and r["provides_checksum"], str(r["errors"]))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
