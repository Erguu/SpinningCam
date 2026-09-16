# -*- coding: utf-8 -*-
"""Long-chord warning for continuous motion (short_segments.analyze_long, 2026-09-16).

The PLC team asks for 2-3 mm chords on curves; a real export (DB_RecipeProgram1)
had exit curves in ~8.4 mm chords turning 10-15 deg each, which slows every corner
and cuts ~0.2 mm inside the curve. This warning names that and says what to change.

Pinned, in the order they matter:

1. It speaks only about CURVES: a long line with no chord error (a straight exit,
   the approach arm) is never reported, however long.
2. Its advice works: typing the suggested value removes every long chord.
3. It names the right knob: a FULL point limit -> raise that limit; otherwise the
   tolerance of that section; with auto-tune on -> the line target.
4. Looking never changes the program: the trial re-thinning runs on a copy.
5. It stays quiet on the shop's real programs that have no such curves.

Run:  python _test_long_chords.py
"""
import math
import os
import sys

import numpy as np

import short_segments as ss
from i18n import set_language, t

FAILED = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  -- {detail}"))
    if not cond:
        FAILED.append(name)


print("A. helpers")
check("target length: 2.5 mm, or 5 x feed x T when longer",
      ss.target_length(300, 0.045) == 2.5 and abs(ss.target_length(800, 0.1) - 6.6667) < 1e-3)

R = 40.0
ang = np.linspace(0.0, 0.5, 51)
arc = np.stack([R * np.cos(ang), np.zeros_like(ang), R * np.sin(ang)], axis=1)
err = ss._chord_error(arc, 0, 50)
L = float(np.linalg.norm(arc[50, [0, 2]] - arc[0, [0, 2]]))
sag = R * (1.0 - math.cos(0.25))          # exact sagitta of a 0.5 rad arc
check("chord error of an arc is its sagitta, R(1 - cos(theta/2))", abs(err - sag) < 1e-3, (err, sag))
line = np.stack([np.linspace(0, 20, 21), np.zeros(21), np.zeros(21)], axis=1)
check("a straight run has no chord error", ss._chord_error(line, 0, 20) < 1e-12)
check("shipped points are found in the full path, in order",
      ss._full_indices(arc, arc[[0, 10, 50]]) == [0, 10, 50])
check("a point that is not on the full path is reported as None",
      ss._full_indices(arc, np.array([[0.0, 0.0, 0.0], [99.0, 0.0, 99.0]]))[1] is None)


print("\nB. on the engine")
PROJ = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(PROJ, "_test_param_wiring.py"), encoding="utf-8").read()
ns = {}
exec(compile(src[:src.index("# ── probe values")], "wiring_head", "exec"), ns)
from path_generator import PathGenerator                                  # noqa: E402

set_language("EN")


def run(op_over=None, params_over=None):
    op = dict(ns["BASE_ROUGH"])
    op.update({"back_pass_enabled": False, "count": 2, "exit_max_points": ""})
    op.update(op_over or {})
    p = dict(ns["PARAMS"])
    p.update({"plc_mode": True, "plc_tolerance": 0.02, "plc_exit_tolerance": 0.02,
              "plc_continuous": True})
    p.update(params_over or {})
    p["operations"] = [op]
    pg = PathGenerator()
    pg.calculate_paths(p, {}, ns["mgr"])
    pg.generate_gcode(params=p, for_recipe=True)
    return pg, p


pg, p = run()
check("a curve already in short chords: nothing to say", ss.analyze_long(pg, 0.045, p) == [])

# A long straight line and a coarsely cut arc side by side (synthetic, so the
# shapes are exactly what they claim to be).
from types import SimpleNamespace                                         # noqa: E402
straight_full = np.stack([np.zeros(31), np.zeros(31), np.linspace(0, 30, 31)], axis=1)
arc_full = arc.copy()
fake = SimpleNamespace(
    last_calculated_paths=[straight_full, arc_full],
    last_plc_paths=[straight_full[[0, 30]], arc_full[[0, 25, 50]]],
    last_path_point_feeds={0: {"op_idx": 0, "op": {"name": "straight"}, "feeds": [None, 300]},
                           1: {"op_idx": 1, "op": {"name": "curve"}, "feeds": [None, 300, 300]}},
    last_render_split_idx={}, last_reverse_split_idx={})
reps = ss.analyze_long(fake, 0.045, {"plc_tolerance": 0.5})
check("a 30 mm STRAIGHT line is never reported; a coarsely cut arc is",
      [r["name"] for r in reps] == ["curve"] and reps[0]["count"] == 2, reps)

# A full point limit made the chords long -> raise the limit.
pg, p = run({"exit_max_points": 4})
reps = ss.analyze_long(pg, 0.045, p)
check("a full Exit Max Points is named as the cause", len(reps) == 1
      and reps[0]["cap_suggest"].get("exit", 0) > 4 and not reps[0]["tol_suggest"], reps)
if reps:
    n = reps[0]["cap_suggest"]["exit"]
    txt = ss.format_long_report(reps, t)
    check("the message says it plainly", f"→ Change {t('lbl_exit_max_pts')}: 4 → {n}" in txt
          and "too long on a curve" in txt, txt)
    pg2, p2 = run({"exit_max_points": n})
    check(f"typing the suggestion ({n}) removes every long chord",
          ss.analyze_long(pg2, 0.045, p2) == [], ss.analyze_long(pg2, 0.045, p2))

# No limit, a coarse exit tolerance -> lower that tolerance, found by trial.
pg, p = run(None, {"plc_exit_tolerance": 0.5})
before_plc = pg.last_plc_paths
before_warn = pg.last_point_cap_warnings
reps = ss.analyze_long(pg, 0.045, p)
check("looking does not touch the app's path generator (trial runs on a copy)",
      pg.last_plc_paths is before_plc and pg.last_point_cap_warnings is before_warn)
sug = reps[0]["tol_suggest"].get("plc_exit_tolerance") if reps else None
check("the exit tolerance is named, with a smaller value", sug is not None and sug[1] == 0.5
      and sug[2] is not None and sug[2] < 0.5, reps)
if sug and sug[2]:
    check("the suggestion is not needlessly small (0.02 is enough here, so >= 0.02)",
          sug[2] >= 0.02, sug)
    pg2, p2 = run(None, {"plc_exit_tolerance": sug[2]})
    check(f"typing the suggestion ({sug[2]}) removes every long chord",
          ss.analyze_long(pg2, 0.045, p2) == [], ss.analyze_long(pg2, 0.045, p2))
    txt = ss.format_long_report(reps, t)
    check("the message names the tolerance with current and suggested value",
          f"→ Change {t('lbl_plc_exit_tol')}: 0.5 → {sug[2]:g}" in txt, txt)

# Auto-tune owns the tolerance -> point at its line target.
pg, p = run(None, {"plc_exit_tolerance": 0.5, "plc_auto_tune": True})
reps = ss.analyze_long(pg, 0.045, p)
txt = ss.format_long_report(reps, t) if reps else ""
check("with auto-tune on, the advice is its line target, not a tolerance",
      t("msg_long_autotune").strip() in txt and "Exit Tolerance" not in txt, txt)

for lang in ("EN", "TR", "ES"):
    set_language(lang)
    try:
        ss.format_long_report(reps * 10, t)
        ok = True
    except Exception as e:                                     # pragma: no cover
        ok = False
        print("   ", e)
    check(f"formats in {lang} (and caps the list)", ok)
set_language("EN")


print("\nC. the shop's real programs")
try:
    import copy
    import golden_snapshot as gs
except Exception as e:                                         # pragma: no cover
    gs = None
    print(f"  SKIP - {e}")
SHOP = r"C:\Users\PC\Documents\Automation\Cursor\MexicoMetalSpinning\gcodes"
if gs is not None:
    path = os.path.join(SHOP, "140926.ssp")
    if not os.path.isfile(path):
        print("  SKIP - 140926.ssp not on this computer")
    else:
        params, ov, step = gs.load_program(path)
        mgr, _ = gs.build_mandrel(params, gs.resolve_step(step, (SHOP,)))
        q = copy.deepcopy(params)
        q.update({"plc_mode": True, "plc_continuous": True, "plc_scan_time_s": 0.045})
        g = PathGenerator()
        g.calculate_paths(q, ov, mgr)
        g.generate_gcode(params=q, for_recipe=True)
        check("140926 (straight exits) raises no long-chord warning",
              ss.analyze_long(g, 0.045, q) == [], ss.analyze_long(g, 0.045, q))

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1)
print("All long-chord checks passed.")
