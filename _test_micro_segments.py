# -*- coding: utf-8 -*-
"""Lines shorter than the PLC's 0.01 mm limit (path_generator._drop_microsegments).

Why this exists: the PLC skips a move under 0.01 mm, but a CONTINUOUS (CMD=2) one
makes it refuse the WHOLE recipe at pre-scan ("CMD=2 zero-length: repeats previous
point" - the same 0.01 mm test lives in FB_RecipeHandler and in the PLC team's
split_recipe_db.py --check). Such a point is therefore dropped when the PLC path is
built, and ONLY in velocity mode (user, 2026-09-16: with every line an exact stop
there is nothing to fix, so that file must not change).

Measured 2026-09-16: never exactly zero - always ~0.006 mm, from a P2 radius that
collapses because there is almost no corner to round. 1 line in v1.ssp, 1 in
bigsheet2.ssp, none in the six other real programs.

Run:  python _test_micro_segments.py
"""
import copy
import math
import os
import sys

import numpy as np

from path_generator import MICRO_SEGMENT_MM, PathGenerator, _drop_microsegments

FAILED = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


print("A. the filter itself")
check("the limit is the PLC's own 0.01 mm", MICRO_SEGMENT_MM == 0.01)

a = np.array([[0, 0, 0], [0, 0, 0.006], [0, 0, 5.0]], float)
check("a point 0.006 mm from the previous one is dropped",
      _drop_microsegments(a).tolist() == [[0, 0, 0], [0, 0, 5.0]], _drop_microsegments(a).tolist())

b = np.array([[0, 0, 0], [0, 0, 0.02], [0, 0, 5.0]], float)
check("a point 0.02 mm away is kept (only at or under the limit goes)",
      len(_drop_microsegments(b)) == 3)

c = np.array([[0, 0, 0], [0, 0, 5.0], [0, 0, 5.004]], float)
out = _drop_microsegments(c)
check("the END point always survives - it replaces the point it is too close to",
      out.tolist() == [[0, 0, 0], [0, 0, 5.004]], out.tolist())

d = np.array([[1, 0, 1], [1, 0, 1.004]], float)
check("a two-point path is never emptied", len(_drop_microsegments(d)) == 2)

e = np.array([[0, 0, 0], [0, 0, 0.004], [0, 0, 0.008], [0, 0, 9.0]], float)
check("a chain of tiny steps collapses to the first point and the real one",
      _drop_microsegments(e).tolist() == [[0, 0, 0], [0, 0, 9.0]])

f = np.array([[0, 0, 0], [0, 0, 1.0], [0, 0, 2.0]], float)
check("a path with nothing tiny is returned unchanged",
      _drop_microsegments(f).tolist() == f.tolist())


print("\nB. on the real programs that have one")
try:
    import golden_snapshot as gs
    from recipe_to_scl import (GCodeToSCLConverter, continuous_settings,
                               CMD_LINEAR, CMD_LINEAR_CONTINUOUS, CMD_RAPID)
except Exception as exc:                                   # pragma: no cover
    gs = None
    print(f"  SKIP - cannot import the engine ({exc})")

FEED = (CMD_LINEAR, CMD_LINEAR_CONTINUOUS)
CONT = {"plc_continuous": True, "plc_scan_time_s": 0.045, "plc_corner_tol_mm": 0.1,
        "plc_feed_min": 180, "plc_reversal_deg": 90.0}


def recipe(params, ov, mgr, velocity):
    p = copy.deepcopy(params)
    p["plc_mode"] = True
    if velocity:
        p.update(CONT)
    pg = PathGenerator()
    pg.calculate_paths(p, ov, mgr)
    text = pg.generate_gcode(params=p, for_recipe=True)
    conv = GCodeToSCLConverter(continuous_motion=continuous_settings(p))
    conv.parse_gcode(text)
    return pg, p, conv.lines, text


def shortest_cut(lines):
    pos, worst = None, math.inf
    for ln in lines:
        if ln.cmd not in (CMD_RAPID,) + FEED:
            continue
        if pos is not None and ln.cmd in FEED:
            worst = min(worst, math.hypot(ln.x - pos[0], ln.z - pos[1]))
        pos = (ln.x, ln.z)
    return worst


names = ["v1.ssp", "bigsheet2.ssp", "kalin2.ssp"] if gs is not None else []
for name in names:
    path = os.path.join(getattr(gs, "FIXTURE_DIR", ""), name)
    if not os.path.isfile(path):
        print(f"  SKIP - {name} not on this computer")
        continue
    params, ov, step = gs.load_program(path)
    mgr, _ = gs.build_mandrel(params, gs.resolve_step(step))

    pg_off, p_off, lines_off, text_off = recipe(params, ov, mgr, velocity=False)
    pg_on, p_on, lines_on, text_on = recipe(params, ov, mgr, velocity=True)

    check(f"{name}: velocity mode ON has no cut line at or under 0.01 mm",
          shortest_cut(lines_on) > MICRO_SEGMENT_MM, round(shortest_cut(lines_on), 4))
    # Velocity mode OFF must be untouched: every line is an exact stop there, the
    # PLC skips a tiny one, and the golden files are taken with the option off. So
    # a program that HAS a tiny line must still have it with the option off.
    tiny_off = shortest_cut(lines_off) <= MICRO_SEGMENT_MM
    dropped = (sum(len(q) for q in pg_off.last_plc_paths)
               - sum(len(q) for q in pg_on.last_plc_paths))
    if name in ("v1.ssp", "bigsheet2.ssp"):
        check(f"{name}: velocity mode OFF still writes the tiny line (file unchanged)",
              tiny_off, round(shortest_cut(lines_off), 4))
        check(f"{name}: exactly the tiny point is dropped, nothing else",
              dropped == 1, dropped)
    else:
        check(f"{name}: nothing to drop, so nothing is dropped", dropped == 0, dropped)
    # The end of every pass still sits exactly where it did.
    same_ends = all(np.allclose(np.asarray(a)[-1], np.asarray(b)[-1])
                    for a, b in zip(pg_off.last_plc_paths, pg_on.last_plc_paths))
    check(f"{name}: every pass still ends on exactly the same point", same_ends)
    # Clearance may not get worse.
    cl_off = pg_off.measure_min_clearance(pg_off.last_plc_paths, p_off)
    cl_on = pg_on.measure_min_clearance(pg_on.last_plc_paths, p_on)
    check(f"{name}: clearance is not made worse ({cl_off:.4f} -> {cl_on:.4f} mm)",
          cl_on >= cl_off - 1e-9)

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1)
print("All micro-segment checks passed.")
