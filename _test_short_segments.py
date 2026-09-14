"""Short-line warning for continuous motion — short_segments.py.

Pinned, in the order they matter:

1. The emitter's feed record lines up with the recipe: feeds[k] of path i is
   exactly the F of the G1 into point k. If this drifts, every number in the
   warning is about the wrong line.
2. Lines are put in the right section (approach / P2 radius / exit), forward
   and reverse, because the suggestion names a section's setting.
3. The suggested point count is floor(length / suggested length) + 1 on the
   shortest pass, never below 2, and only offered when it is smaller than what
   is set now.
4. On a real program, typing the suggestion in really removes short lines.

Run:  python _test_short_segments.py
"""
import copy
import os
import sys
from types import SimpleNamespace

import numpy as np

import short_segments as ss
from i18n import set_language, t

FAILED = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  -- {detail}"))
    if not cond:
        FAILED.append(name)


# --- 1. the rule --------------------------------------------------------------
print("rule")
check("5 x v x T: F300, T=0.1 -> 2.5 mm", abs(ss.suggested_length(300, 0.1) - 2.5) < 1e-12)
check("F60 -> 0.5 mm", abs(ss.suggested_length(60, 0.1) - 0.5) < 1e-12)
check("cap_value: empty / 0 / text -> None (no cap)",
      [ss.cap_value({"k": v}, "k") for v in ("", 0, "off", None)] == [None] * 4)
check("cap_value: '6' -> 6", ss.cap_value({"k": "6"}, "k") == 6)


# --- 2. synthetic pass ----------------------------------------------------------
def pass_points(exit_len_mm=5.0):
    """P1 -> T1 straight 40 mm; P2 radius 5 mm in 0.5 mm steps; exit in 1 mm steps."""
    pts = [[10.0, 0.0, 0.0], [10.0, 0.0, 40.0]]                  # P1, T1 (index 1)
    pts += [[10.0, 0.0, 40.0 + 0.5 * k] for k in range(1, 11)]  # ... T2 at index 11
    n_exit = int(round(exit_len_mm))
    pts += [[10.0, 0.0, 45.0 + 1.0 * k * (exit_len_mm / n_exit)] for k in range(1, n_exit + 1)]
    return np.array(pts)


def fake_pg(paths, feed=300, split=(1, 11), op=None, reverse=False):
    op = op if op is not None else {"type": "roughing"}
    stored = [p[::-1].copy() if reverse else p for p in paths]
    n = len(paths[0])
    return SimpleNamespace(
        last_plc_paths=stored,
        last_calculated_paths=stored,
        last_render_split_idx={} if (reverse or split is None) else {i: split for i in range(len(paths))},
        last_reverse_split_idx=({i: (n - 1 - split[1], n - 1 - split[0]) for i in range(len(paths))}
                                if reverse and split else {}),
        last_path_point_feeds={i: {"op_idx": 0, "op": op,
                                   "feeds": [None] + [feed] * (len(p) - 1)}
                               for i, p in enumerate(stored)},
    )


print("sections")
rep = ss.analyze(fake_pg([pass_points()]), 0.1)
check("one report", len(rep) == 1, rep)
r = rep[0]
check("10 short lines in the P2 radius, 5 in the exit, approach arm not short",
      r["sections"] == {"fillet": 10, "exit": 5}, r["sections"])
check("mostly in the P2 radius", r["main"] == "fillet")
check("shortest 0.5 mm, suggested 2.5 mm", abs(r["shortest"] - 0.5) < 1e-9 and abs(r["need"] - 2.5) < 1e-9)
check("suggested P2 Max Points = floor(5 / 2.5) + 1 = 3", r["suggest"].get("fillet") == 3, r["suggest"])
check("suggested Exit Max Points = floor(5 / 2.5) + 1 = 3", r["suggest"].get("exit") == 3, r["suggest"])
check("current caps read as none", r["current"] == {"fillet": None, "exit": None})

rev = ss.analyze(fake_pg([pass_points()], reverse=True), 0.1)[0]
check("reverse pass: same sections and suggestions",
      (rev["sections"], rev["suggest"]) == (r["sections"], r["suggest"]),
      (rev["sections"], rev["suggest"]))

short_exit = ss.analyze(fake_pg([pass_points(exit_len_mm=2.0)]), 0.1)[0]
check("an exit leg shorter than 2.5 mm is flagged, not given a count",
      short_exit["too_short"].get("exit") and "exit" not in short_exit["suggest"], short_exit)

two = ss.analyze(fake_pg([pass_points(exit_len_mm=10.0), pass_points(exit_len_mm=5.0)]), 0.1)[0]
check("one number per operation: the shortest pass decides (10 mm -> 5, 5 mm -> 3)",
      two["suggest"].get("exit") == 3, two["suggest"])

check("F60: 0.5 mm lines are long enough, nothing reported",
      ss.analyze(fake_pg([pass_points()], feed=60), 0.1) == [])
check("T=0.02: 5 x 5 mm/s x 0.02 = 0.5 mm, nothing reported",
      ss.analyze(fake_pg([pass_points()]), 0.02) == [])

uneven = np.array([[10.0, 0.0, 0.0], [10.0, 0.0, 40.0],
                   [10.0, 0.0, 50.0], [10.0, 0.0, 50.5], [10.0, 0.0, 60.0]])
un = ss.analyze(fake_pg([uneven], split=(1, 1)), 0.1)[0]
check("a long exit leg with ONE short line gets a cap below its current points "
      "(20 mm would allow 9, but it only has 4 points, so 3 re-spaces it)",
      un["suggest"].get("exit") == 3 and un["sections"] == {"exit": 1}, un)


# v1.ssp shape: on the pass with the short line the P2 radius is ALREADY one
# line (T1 -> T2); another pass would allow 2 points. "→ 2" changes nothing.
one_line = np.array([[10.0, 0.0, 0.0], [10.0, 0.0, 40.0], [10.0, 0.0, 40.3],
                     [10.0, 0.0, 50.0]])                    # fillet = one 0.3 mm line
roomy = np.array([[10.0, 0.0, 0.0], [10.0, 0.0, 40.0], [10.0, 0.0, 41.0],
                  [10.0, 0.0, 42.0], [10.0, 0.0, 52.0]])     # fillet 2 mm, lines 1 mm
pg_ol = fake_pg([one_line, roomy], feed=60)
pg_ol.last_render_split_idx = {0: (1, 2), 1: (1, 3)}
ol = ss.analyze(pg_ol, 0.1)[0]
txt_ol = ss.format_report([ol], t, 0.1)
check("no 'Try' when the suggestion cannot change the pass that has the short line",
      f"{t('lbl_p2_max_pts')}  ∞" not in txt_ol and "no point count reaches it" in txt_ol, txt_ol)


def no_radius_points():
    """P1 -> T1 = T2 (no P2 radius) -> exit in 1 mm steps."""
    return np.array([[10.0, 0.0, 0.0], [10.0, 0.0, 40.0]]
                    + [[10.0, 0.0, 40.0 + k] for k in range(1, 6)])


fwd_nr = ss.analyze(fake_pg([no_radius_points()], split=(1, 1)), 0.1)[0]
check("no P2 radius, forward: the 1 mm lines are exit, not approach",
      fwd_nr["sections"] == {"exit": 5}, fwd_nr["sections"])
rev_nr = ss.analyze(fake_pg([no_radius_points()], split=(1, 1), reverse=True), 0.1)[0]
check("no P2 radius, REVERSE: still exit (T1 == T2 must not flip the direction) "
      "— the bug found on bundan devam",
      rev_nr["sections"] == {"exit": 5}, rev_nr["sections"])

short_arm = np.array([[10.0, 0.0, 39.0], [10.0, 0.0, 40.0]]
                     + [[10.0, 0.0, 40.0 + 5.0 * k] for k in range(1, 4)])
arm = ss.analyze(fake_pg([short_arm], split=(1, 1)), 0.1)[0]
check("a 1 mm approach arm is its own section", arm["sections"] == {"approach": 1}, arm["sections"])
arm_rev = ss.analyze(fake_pg([short_arm], split=(1, 1), reverse=True), 0.1)[0]
check("... also on a reverse pass (it comes last there)",
      arm_rev["sections"] == {"approach": 1}, arm_rev["sections"])

no_split = ss.analyze(fake_pg([pass_points()], split=None), 0.1)[0]
check("no P2/exit split: everything is 'other', no cap suggested",
      set(no_split["sections"]) == {"other"} and not no_split["suggest"], no_split)

pg = fake_pg([pass_points()])
pg.last_path_point_feeds = {}
check("a path the emitter did not record (e.g. a Point op) is ignored", ss.analyze(pg, 0.1) == [])

zero = pass_points()
zero = np.vstack([zero[:5], zero[4:5], zero[5:]])      # a duplicated point
zr = ss.analyze(fake_pg([zero], split=(1, 12)), 0.1)[0]
check("a zero-length line is not counted as short", zr["sections"].get("fillet") == 10, zr["sections"])

# --- 3. the message ------------------------------------------------------------
print("message")
set_language("EN")
txt = ss.format_report([r], t, 0.1)
check("names the setting with current and suggested value",
      f"{t('lbl_p2_max_pts')}  ∞ → 3" in txt and f"{t('lbl_exit_max_pts')}  ∞ → 3" in txt, txt)
check("shows the rule and T", "5 × feed × T" in txt and "T = 0.1 s" in txt, txt)
check("shortest length has two decimals (a 0.007 mm line must not read 0.0)",
      "shortest 0.50 mm" in txt, txt)
capped = copy.deepcopy(r)
capped["current"] = {"fillet": 3, "exit": 8}
txt2 = ss.format_report([capped], t, 0.1)
check("no suggestion when the current cap is already as small",
      f"{t('lbl_p2_max_pts')}  3" not in txt2 and f"{t('lbl_exit_max_pts')}  8 → 3" in txt2, txt2)
txt3 = ss.format_report([no_split], t, 0.1)
check("lines outside P2 radius / exit get a plain note and NO 'Try' "
      "(lowering the auto-tune target was measured not to help, v1.ssp)",
      t("msg_short_other_info") in txt3 and "Try" not in txt3 and "auto-tune" not in txt3, txt3)
txt5 = ss.format_report([short_exit], t, 0.1)
check("too-short section is explained", "no point count reaches it" in txt5, txt5)
txt6 = ss.format_report([arm], t, 0.1)
check("a short approach line is explained, with no setting offered",
      t("msg_short_approach_info") in txt6 and "Try" not in txt6, txt6)
for lang in ("EN", "TR", "ES"):
    set_language(lang)
    try:
        ss.format_report([r, short_exit, no_split, arm] * 3, t, 0.1)
        ok = True
    except Exception as e:
        ok = False
        print("   ", e)
    check(f"formats in {lang} (and caps the list at 8 ops)", ok)
set_language("EN")

# --- 4. a real program -----------------------------------------------------------
print("real program")
try:
    import golden_snapshot as gs
    fx = [p for p in gs.fixtures() if os.path.basename(p) == "bigsheet2.ssp"]
except Exception:
    fx = []
if not fx:
    print("  SKIP no golden fixture bigsheet2.ssp")
else:
    import logging
    logging.disable(logging.CRITICAL)
    from path_generator import PathGenerator
    from recipe_to_scl import GCodeToSCLConverter

    params0, overrides, step = gs.load_program(fx[0])
    mgr, _ = gs.build_mandrel(params0, gs.resolve_step(step))

    def run(fillet_cap=None):
        p = copy.deepcopy(params0)
        p.update({"plc_mode": True, "plc_tolerance": 0.01, "plc_exit_tolerance": 0.01})
        for op in p.get("operations", []):
            op["p2_radius_max_points"] = fillet_cap or ""
        pg = PathGenerator()
        pg.calculate_paths(p, copy.deepcopy(overrides), mgr)
        gcode = pg.generate_gcode(params=p, for_recipe=True)
        conv = GCodeToSCLConverter()
        conv.parse_gcode(gcode)
        return pg, conv

    pg, conv = run()
    recorded = []
    for i in range(len(pg.last_plc_paths)):
        rec = pg.last_path_point_feeds.get(i)
        if rec:
            recorded += [int(f) for f in rec["feeds"][1:]]
    recipe_f = [l.f for l in conv.lines if l.cmd == 1]
    check("recorded feeds == the recipe's G1 feeds, line for line",
          recorded == recipe_f, (len(recorded), len(recipe_f)))
    check("every G1 point is recorded", len(recorded) == len(recipe_f))

    reps = ss.analyze(pg, 0.1)
    check("bigsheet2 at tol 0.01 has short lines in the P2 radius",
          reps and reps[0]["sections"].get("fillet", 0) > 0, reps)
    if reps and reps[0]["suggest"].get("fillet"):
        sug = reps[0]["suggest"]["fillet"]
        before = reps[0]["sections"].get("fillet", 0)
        pg2, _ = run(fillet_cap=sug)
        after_reps = ss.analyze(pg2, 0.1)
        after = after_reps[0]["sections"].get("fillet", 0) if after_reps else 0
        refused = pg2.last_point_cap_warnings
        check(f"typing the suggestion (P2 Max Points {sug}) removes short P2-radius lines "
              f"({before} -> {after}) or the gap check refuses it and says so",
              after < before or refused, (before, after, refused))
    else:
        check("a P2 Max Points suggestion is offered", False, reps)

print()
if FAILED:
    print(f"FAILED {len(FAILED)}: {FAILED}")
    sys.exit(1)
print("ALL OK")
