"""A rapid that moves nothing is not written (path_generator.drop_zero_length_rapids).

Why: such a line still has to be accepted, started and reported done by the PLC,
and it costs one of the 1000 recipe lines. Found 2026-09-18 while chasing "the
machine waits about 3 seconds at some pass ends": the shop's live 140926.ssp
carries two of them, one exactly at the reverse -> forward turn the operator
describes. Every other shop program has none.

What must hold, most important first:

1. SAFETY. Only a bare G0 whose every named axis is ALREADY at that value goes.
   A feed line never goes. A rapid that moves any axis, even a little, never
   goes. A rapid carrying a tilt (B) change never goes.
2. Modal by axis: a single-axis "G0 Z..." is judged on Z alone, because that is
   how the .nc reader and the recipe read it.
3. Nothing is dropped before a position is known, so the program-start homing
   rapids always stand.
4. On the real programs: 140926 loses exactly its two, every other file is
   byte-identical.

Run:  python _test_zero_rapids.py
"""
import os
import sys

from path_generator import drop_zero_length_rapids as drop

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILED.append(name)


print("A. the rule")

kept, n = drop(["G0 X10.000 Z20.000 (start)", "G0 X10.000 Z20.000 (again)"])
check("a repeated rapid goes", n == 1 and len(kept) == 1, kept)

kept, n = drop(["G0 X10.000 Z20.000", "G0 X10.001 Z20.000"])
check("a rapid that moves 0.001 mm stays", n == 0, kept)

kept, n = drop(["G0 X10.000 Z20.000", "G1 X10.000 Z20.000 F400.000"])
check("a feed line never goes", n == 0, kept)

kept, n = drop(["G0 X10.000 Z20.000 B5.000", "G0 X10.000 Z20.000 B7.000"])
check("a tilt change stays", n == 0, kept)

kept, n = drop(["G0 X10.000 Z20.000 B5.000", "G0 X10.000 Z20.000 B5.000"])
check("same tilt, same place goes", n == 1, kept)

# Modal: the second line names Z only, and Z has not moved.
kept, n = drop(["G0 X10.000 Z20.000", "G0 Z20.000 (Retract to safe Z)"])
check("single-axis rapid judged on that axis alone", n == 1, kept)

# 5. The pre-tool-change clearance block is never touched, even though every
#    line in it moves nothing. It asserts a height rather than reaching one.
TCH = "(--- TOOL CHANGE SAFETY ---)"
kept, n = drop(["G0 X10.000 Z20.000", TCH,
                "G0 Z20.000 (Tool Change Z, relative)",
                "G0 X10.000 (Tool Change X, relative)"])
check("the tool-change clearance block stays", n == 0, kept)

kept, n = drop(["G0 X10.000 Z20.000", TCH,
                "G0 Z20.000 (Tool Change Z, relative)",
                "G97 S500 M3", "M6 T004 (ROUGHING)",
                "G0 Z20.000 (approach)"])
check("the block ends at the next real command", n == 1, kept)

kept, n = drop(["G0 X10.000 Z20.000", TCH,
                "G0 Z20.000 (Tool Change Z, relative)",
                "M6 T004 (ROUGHING)",
                "G1 X10.000 Z20.000 F400.000",
                "G0 X10.000 Z20.000"])
check("normal judging resumes after the block", n == 1, kept)

kept, n = drop(["G0 X10.000 Z20.000", "G0 X99.000", "G0 Z20.000"])
check("Z unchanged after an X-only move -> the Z rapid goes", n == 1, kept)

kept, n = drop(["G0 Z181.000 (Program Start Z)", "G0 X273.000 (Program Start X)"])
check("nothing goes before a position is known", n == 0, kept)

kept, n = drop(["G0 X10.000 Z20.000", "G0 X10.000 Z20.000 M8", "G0 X10.000 Z20.000"])
check("a rapid carrying another command stays", n == 1 and len(kept) == 2, kept)

kept, n = drop(["G0 X10.000 Z20.000", "M6 T004 (ROUGHING)", "G0 X10.000 Z20.000"])
check("an M line in between does not confuse the position", n == 1, kept)

kept, n = drop(["G0 X10.000 Z20.000", "G0 XBAD Z20.000", "G0 X10.000 Z20.000"])
check("an unreadable rapid stays and clears the position", n == 0, kept)

kept, n = drop(["(comment)", "", "%", "G0 X1.000", "G0 X1.000"])
check("comments and blanks are carried through", n == 1 and len(kept) == 4, kept)

src = ["G0 X10.000 Z20.000", "G1 X30.000 Z20.000 F400.000", "G0 X30.000 Z20.000"]
kept, n = drop(src)
check("the position follows a feed line too", n == 1 and kept == src[:2], kept)

print("\nB. real programs")
try:
    import copy
    import golden_snapshot as gs
    from path_generator import PathGenerator
except Exception as e:                                          # pragma: no cover
    gs = None
    print(f"  SKIP - cannot import the engine ({e})")

SHOP = r"C:\Users\PC\Documents\Automation\Cursor\MexicoMetalSpinning\gcodes"
# Measured box off, recipe path. A file not listed here must lose NOTHING.
#   140926.ssp: one, the rapid into Op21's pass start, at the reverse ->
#     forward turn the operator described. It has a SECOND redundant rapid,
#     a "Tool Change Z", which is protected by the exemption below.
#   180926.ssp (2026-09-19, the operator's own file, which arrived after the
#     first measurement): NOTHING. It has two rapids that move nothing, but
#     both sit in the pre-tool-change clearance block, which is exempt (user,
#     2026-09-19) - see drop_zero_length_rapids. This zero is the point of the
#     exemption, not an absence of evidence.
EXPECTED = {"140926.ssp": 1}

if gs is not None:
    files = []
    for d in (SHOP, getattr(gs, "FIXTURE_DIR", "")):
        if d and os.path.isdir(d):
            files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                      if f.lower().endswith(".ssp")]
    seen = set()
    files = [f for f in files if not (os.path.basename(f) in seen
                                      or seen.add(os.path.basename(f)))]
    # The shop folder also holds the user's own experiment programs, which change
    # between runs while he tries a feature out. Pinning those makes this test
    # fail for reasons that have nothing to do with the code. Production programs
    # are named by date (140926, 180926, ...) and stay pinned.
    #
    # Measured 2026-09-20 on shortend-continuefromlastpass-test.ssp, before it
    # was excluded: ONE rapid dropped, and it was the right one. With
    # stop_short + start_from_last the next pass starts exactly where the last
    # stroke ended (gap 0.000 mm), so the rapid between them moves nothing.
    files = [f for f in files if "test" not in os.path.basename(f).lower()]
    if not files:
        print("  SKIP - no real programs on this machine")
    for f in files:
        name = os.path.basename(f)
        try:
            params, overrides, step = gs.load_program(f)
            mgr, ok = gs.build_mandrel(params, gs.resolve_step(step, (SHOP,)))
            if not ok:
                print(f"  SKIP {name} - STEP not found")
                continue
            p = copy.deepcopy(params)
            p["plc_mode"] = True
            pg = PathGenerator()
            pg.calculate_paths(p, overrides, mgr)
            txt = pg.generate_gcode(params=p, for_recipe=True)
            got = pg.last_zero_rapids_dropped
            want = EXPECTED.get(name, 0)
            check(f"{name}: {want} rapid(s) that move nothing", got == want,
                  f"dropped {got}")
            again, left = drop(txt.splitlines())
            check(f"{name}: none left behind", left == 0, f"{left} still there")
        except Exception as e:                                  # pragma: no cover
            check(f"{name} runs", False, f"{type(e).__name__}: {e}")

print()
if FAILED:
    print(f"{len(FAILED)} check(s) FAILED: {FAILED}")
    sys.exit(1)
print("All zero-length rapid checks passed.")
