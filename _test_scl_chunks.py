# -*- coding: utf-8 -*-
"""Chunked recipe arrays (Lines1..LinesN) — headless proof.

Covers the three failure modes named in letter_spinningcam_chunked_recipes.md:
wrong array count (loud in TIA), too many arrays (silent tail loss), and right
count / wrong size (compiles, scrambles). The last one is why generate_scl
re-validates its own output before returning it.

Run:  python _test_scl_chunks.py
"""
import re
import sys

from recipe_to_scl import (GCodeToSCLConverter, chunk_geometry,
                           check_scl_geometry, DEFAULT_CHUNK_SIZE,
                           CMD_PROGRAM_END)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


TURRET = {"turret_slots": [{"code": 101, "angle": 0.0}, {"code": 0, "angle": 0.0},
                           {"code": 0, "angle": 0.0}, {"code": 0, "angle": 0.0}],
          "turret_auto_angles": True}


def make_gcode(n_moves):
    out = ["M3 S1000", "M6 T101"]
    for i in range(n_moves):
        out.append(f"G1 X{10.0 + i * 0.5:.3f} Z{50.0 - i * 0.25:.3f} F300")
    out.append("M30")
    return "\n".join(out)


def build(n_moves, chunk_size=DEFAULT_CHUNK_SIZE, capacity=None, force=False):
    conv = GCodeToSCLConverter()
    conv.parse_gcode(make_gcode(n_moves))
    scl = conv.generate_scl(db_name="DB_RecipeProgram3", program_title="Program 3",
                            params=TURRET, custom_array_size=capacity,
                            chunk_size=chunk_size, force=force)
    return conv, scl


# ── 1. geometry maths ────────────────────────────────────────────────────────
print("\n[1] chunk_geometry")
g = chunk_geometry(999, None, 100)
check("999 lines -> 10 x 100", (g["chunk_count"], g["chunk_size"]) == (10, 100))
check("capacity 1000", g["capacity"] == 1000)
check("END of 999 lines at Lines10[98]", (g["end_array"], g["end_index"]) == (10, 98),
      f'got Lines{g["end_array"]}[{g["end_index"]}]')
check("line 207 rule", chunk_geometry(208, None, 100)["end_array"] == 3
      and chunk_geometry(208, None, 100)["end_index"] == 7)
check("halved geometry 50 x 20", (lambda q: (q["chunk_count"], q["chunk_size"]))(
      chunk_geometry(999, 1000, 50)) == (20, 50))
check("capacity rounds up to whole arrays",
      chunk_geometry(10, 350, 100)["capacity"] == 400)
check("capacity never below line count",
      chunk_geometry(1200, 300, 100)["capacity"] >= 1200)
check("chunk_size 0 = legacy", chunk_geometry(38, None, 0)["chunked"] is False)
check("legacy capacity keeps the old min-1000 rule",
      chunk_geometry(38, None, 0)["capacity"] == 1000)

# ── 2. emitted declarations + mapping ────────────────────────────────────────
print("\n[2] emitted SCL (chunked)")
conv, scl = build(400)
n = len(conv.lines)
decls = re.findall(r'^\s*(Lines\d+)\s*:\s*Array\[0\.\.(\d+)\]', scl, re.M)
check("10 arrays declared", len(decls) == 10, f"got {len(decls)}")
check("named Lines1..Lines10", [d[0] for d in decls] == [f"Lines{i}" for i in range(1, 11)])
check("all Array[0..99]", {d[1] for d in decls} == {"99"})
check("no un-numbered Lines array", not re.search(r'^\s*Lines\s*:\s*Array', scl, re.M))
check("CHUNKS header present", "// CHUNKS: 10 x 100" in scl)
check("Optimized_Access FALSE kept", "{ S7_Optimized_Access := 'FALSE' }" in scl)
check("UNLINKED before NON_RETAIN",
      scl.index("\nUNLINKED") < scl.index("\nNON_RETAIN"))
check(f"Header.LineCount is global ({n})", f"Header.LineCount := {n};" in scl)

# positional mapping, read back from the text
refs = [(int(a), int(b)) for a, b in re.findall(r'\bLines(\d+)\[(\d+)\]\.X\s*:=', scl)]
check("one assignment per line", len(refs) == n, f"{len(refs)} vs {n}")
check("mapping g -> Lines[g//100+1][g%100]",
      refs == [(i // 100 + 1, i % 100) for i in range(n)])
check("first line is Lines1[0]", refs[0] == (1, 0))
check("crosses into Lines2 at global 100", refs[100] == (2, 0))

end_ref = re.findall(r'\bLines(\d+)\[(\d+)\]\.CMD := %d;' % CMD_PROGRAM_END, scl)
exp = chunk_geometry(n, None, 100)
check("END marker at global LineCount-1",
      end_ref == [(str(exp["end_array"]), str(exp["end_index"]))], f"got {end_ref}")

# ── 3. self-validation ───────────────────────────────────────────────────────
print("\n[3] check_scl_geometry")
rep = check_scl_geometry(scl)
check("clean file validates", rep["ok"], str(rep["errors"]))
check("reports 10 x 100", (rep["chunk_count"], rep["chunk_size"]) == (10, 100))

# Right count, WRONG size — compiles in TIA, scrambles the recipe. Must be caught.
bad = scl.replace("Array[0..99]", "Array[0..124]")
r = check_scl_geometry(bad)
check("wrong chunk size refused", not r["ok"])
check("...and names the mismatch", any("CHUNKS" in e for e in r["errors"]), str(r["errors"]))

# Fewer arrays than the data needs.
bad2 = re.sub(r'^\s*Lines10\s*:.*$', '', scl, flags=re.M)
check("missing trailing array refused", not check_scl_geometry(bad2)["ok"])

# A hole in the middle (what a dropped line would look like).
bad3 = scl.replace("Lines2[5].X :=", "Lines2[6].X :=", 1)
check("non-contiguous lines refused", not check_scl_geometry(bad3)["ok"])

# END marker moved off the last line.
bad4 = scl.replace(f".CMD := {CMD_PROGRAM_END};", ".CMD := 21;", 1)
check("missing END marker refused", not check_scl_geometry(bad4)["ok"])

# LineCount that disagrees with the written lines.
bad5 = re.sub(r'Header\.LineCount := \d+;', 'Header.LineCount := 500;', scl)
check("LineCount mismatch refused", not check_scl_geometry(bad5)["ok"])

# ── 4. edge cases ────────────────────────────────────────────────────────────
print("\n[4] edges")
_, s38 = build(35)                       # the 38-line program from the letter
r38 = check_scl_geometry(s38)
check("short program still validates", r38["ok"], str(r38["errors"]))
check("short program still declares 10 x 100",
      (r38["chunk_count"], r38["chunk_size"]) == (10, 100))
check("unused arrays get no assignments",
      not re.search(r'\bLines(5|6|7|8|9|10)\[', s38))

_, s50 = build(400, chunk_size=50)       # the retune the PLC team floated
r50 = check_scl_geometry(s50)
check("50 x 20 geometry validates", r50["ok"] and r50["chunk_size"] == 50)
check("50-line header emitted", f"// CHUNKS: {r50['chunk_count']} x 50" in s50)

_, sleg = build(35, chunk_size=0)        # legacy path unchanged
rleg = check_scl_geometry(sleg)
check("legacy single array validates", rleg["ok"], str(rleg["errors"]))
check("legacy declares Lines : Array[0..999]", "Lines : Array[0..999]" in sleg)
check("legacy emits no CHUNKS header", "// CHUNKS:" not in sleg)

_, sbig = build(1200, force=True)        # over the 1000-line limit, forced
rbig = check_scl_geometry(sbig)
check("oversized program still self-consistent", rbig["ok"], str(rbig["errors"]))
check("capacity grew past the line count", rbig["capacity"] >= rbig["line_count"])

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED: " + ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
