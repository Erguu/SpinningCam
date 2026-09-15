"""Stop dots in the 3D view (motion_stops.py, 2026-09-16).

What must hold, most important first:

1. A dot is drawn ONLY where the machine stops, by the PLC's own rule on the
   recipe the export writes - including the markers between lines.
2. Every dot sits exactly on a point of the toolpath it is drawn on (checked
   against the full-resolution path, of which the PLC points are a subset).
   This is what proves the line -> point counting is right.
3. When the recipe does not line up with the paths: NO dots (never wrong ones).
4. Continuous motion off -> no dots.
5. The app's own path generator is not touched (last_plc_paths identity).

Part A needs nothing. Part B uses real programs (golden fixtures / shop folder)
and SKIPS what is not there.

Run:  python _test_motion_stops.py
"""
import os
import sys
import time

import numpy as np

import motion_stops as ms
from recipe_to_scl import (RecipeLineData, CMD_RAPID, CMD_LINEAR,
                           CMD_LINEAR_CONTINUOUS, CMD_PASS_MARKER, CMD_SPINDLE_ON)

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILED.append(name)


def L(cmd, f=0, exact=False):
    return RecipeLineData(x=0.0, z=0.0, f=f, cmd=cmd, param=0, exact=exact)


print("A. rule + counting (synthetic)")

# -- stop_flags: the PLC rule, next-line based
lines = [L(CMD_RAPID),
         L(CMD_LINEAR_CONTINUOUS, 300),   # -> CMD=2 F>0: blends
         L(CMD_LINEAR_CONTINUOUS, 300),   # -> CMD=1 F>0: blends
         L(CMD_LINEAR, 300),              # CMD=1: stop
         L(CMD_LINEAR_CONTINUOUS, 300),   # -> marker: stop
         L(CMD_PASS_MARKER, 10),
         L(CMD_LINEAR_CONTINUOUS, 300),   # -> CMD=2 with F=0: stop
         L(CMD_LINEAR_CONTINUOUS, 0),     # F=0 never blends
         L(CMD_SPINDLE_ON)]
check("rule: rapid / CMD=1 / CMD=2-before-marker / F=0 stop; CMD=2 into feed blends",
      ms.stop_flags(lines) == [True, False, False, True, True, False, True, True, False],
      ms.stop_flags(lines))

# -- map_stops: two passes, a marker between, a Point op in the middle
p0 = np.zeros((3, 3))                      # start + 2 cut lines
p1 = np.zeros((2, 3))                      # start + 1 cut line
lines = [L(CMD_RAPID),                                        # to p0 start
         L(CMD_LINEAR_CONTINUOUS, 300), L(CMD_LINEAR, 300),   # p0 k1 blends, k2 stops
         L(CMD_RAPID),                                        # retract
         L(CMD_LINEAR, 500, exact=True),                      # a Point op: on no path
         L(CMD_PASS_MARKER, 2),
         L(CMD_RAPID),                                        # to p1 start
         L(CMD_LINEAR_CONTINUOUS, 300),                       # last line before END: stops
         L(CMD_SPINDLE_ON)]
flags = ms.stop_flags(lines)
check("mapping: starts reached by rapid + stopping cut lines, Point op skipped",
      ms.map_stops(lines, flags, [p0, p1]) == [(0, 0), (0, 2), (1, 0), (1, 1)],
      ms.map_stops(lines, flags, [p0, p1]))

# -- back pass flowing out of its forward pass: no duplicate dot at the turn
fwd, bp = np.zeros((3, 3)), np.zeros((3, 3))
lines = [L(CMD_RAPID), L(CMD_LINEAR_CONTINUOUS, 300), L(CMD_LINEAR, 300),   # forward, U-turn stop
         L(CMD_LINEAR_CONTINUOUS, 300), L(CMD_LINEAR, 300), L(CMD_RAPID)]   # back pass, no G0 in
check("mapping: back pass start after a stopping forward end is not drawn twice",
      ms.map_stops(lines, ms.stop_flags(lines), [fwd, bp]) == [(0, 0), (0, 2), (1, 2)],
      ms.map_stops(lines, ms.stop_flags(lines), [fwd, bp]))

# -- a path of one point ships a G0 and no cut line
lines = [L(CMD_RAPID), L(CMD_LINEAR, 300), L(CMD_RAPID), L(CMD_RAPID), L(CMD_LINEAR, 300)]
check("mapping: one-point paths are stepped over",
      ms.map_stops(lines, ms.stop_flags(lines),
                   [np.zeros((2, 3)), np.zeros((1, 3)), np.zeros((2, 3))]) is not None)

# -- mismatch both ways -> None
lines = [L(CMD_RAPID), L(CMD_LINEAR, 300), L(CMD_LINEAR, 300)]
check("mismatch: more cut lines than points -> no dots",
      ms.map_stops(lines, ms.stop_flags(lines), [np.zeros((2, 3))]) is None)
check("mismatch: fewer cut lines than points -> no dots",
      ms.map_stops(lines, ms.stop_flags(lines), [np.zeros((4, 3))]) is None)

# -- off -> None; cache returns the same object while nothing changed
class _PG:
    last_calculated_paths = [np.zeros((2, 3))]
check("continuous motion off -> None",
      ms.compute(_PG(), {"plc_mode": True, "plc_continuous": False}) is None)
check("PLC mode off -> None (continuous needs PLC mode)",
      ms.compute(_PG(), {"plc_mode": False, "plc_continuous": True}) is None)
cache = ms.StopCache()
pg = _PG()
calls = []
_orig = ms.compute
ms.compute = lambda a, b: calls.append(1) or {"stops": 0}
try:
    a = cache.get(pg, {"plc_mode": True, "x": 1})
    b = cache.get(pg, {"plc_mode": True, "x": 1, "show_rapids": False})   # view switch only
    pg.last_calculated_paths = [np.zeros((2, 3))]                           # recalculated
    c = cache.get(pg, {"plc_mode": True, "x": 1})
    d = cache.get(pg, {"plc_mode": True, "x": 2})                            # program edit
finally:
    ms.compute = _orig
check("cache: view switch keeps the answer, new paths or a program edit recompute",
      len(calls) == 3 and a is b, f"calls={len(calls)}")


print("\nB. real programs")
try:
    import golden_snapshot as gs
    from path_generator import PathGenerator
except Exception as e:                                        # pragma: no cover
    gs = None
    print(f"  SKIP - cannot import the engine ({e})")

SHOP = r"C:\Users\PC\Documents\Automation\Cursor\MexicoMetalSpinning\gcodes"
PROGRAM1 = {"plc_mode": True, "plc_continuous": True, "plc_scan_time_s": 0.045,
            "plc_corner_tol_mm": 0.1, "plc_feed_min": 180, "plc_reversal_deg": 90.0,
            "plc_stop_slowdown": False}

cases = []
if gs is not None:
    for name, extra in (("140926.ssp", {"plc_pass_markers": True}),
                        ("bundan devam geçerli olan.ssp", {"plc_pass_markers": False}),
                        ("kalin2.ssp", {"plc_pass_markers": True}),
                        ("020926.ssp", {})):          # 020926 is saved with auto-tune on
        for d in (SHOP, gs.FIXTURE_DIR):
            if os.path.isfile(os.path.join(d, name)):
                cases.append((os.path.join(d, name), extra))
                break
    if not cases:
        print("  SKIP - no real programs on this computer")

for path, extra in cases:
    name = os.path.basename(path)
    params, overrides, step = gs.load_program(path)
    mgr, loaded = gs.build_mandrel(params, gs.resolve_step(step, (SHOP,)))
    pg = PathGenerator()
    pg.calculate_paths(params, overrides, mgr)
    p = dict(params)
    p.update(PROGRAM1)
    p.update(extra)
    before_plc = pg.last_plc_paths
    t0 = time.perf_counter()
    res = ms.compute(pg, p)
    dt = time.perf_counter() - t0
    auto = bool(p.get("plc_auto_tune"))
    print(f"  {name}: {dt*1000:.0f} ms, auto-tune={auto}, "
          f"{None if res is None else res['stops']} dots, "
          f"{None if res is None else res['recipe_lines']} recipe lines")
    check(f"{name}: dots computed", res is not None)
    if res is None:
        continue
    check(f"{name}: the app's path generator is untouched", pg.last_plc_paths is before_plc)
    full = pg.last_calculated_paths
    off = []
    for i, pt in res["points"]:
        d = np.min(np.linalg.norm(np.asarray(full[i], float) - pt, axis=1))
        if d > 1e-6:
            off.append((i, round(float(d), 4)))
    check(f"{name}: every dot sits on a point of ITS OWN toolpath", not off, off[:5])
    n_paths = len([q for q in full if len(q) > 1])
    check(f"{name}: at least one dot per pass (every pass starts from a stop)",
          res["stops"] >= n_paths, f"{res['stops']} dots, {n_paths} passes")
    q = dict(p)
    q["plc_continuous"] = False
    check(f"{name}: continuous off -> no dots", ms.compute(pg, q) is None)

print("\nC. drawing into the 3D view (stub plotter)")
if cases and gs is not None:
    from main import SpinningApp

    class _Plot:
        def __init__(self):
            self.meshes = []

        def add_mesh(self, mesh, **kw):
            self.meshes.append((mesh, kw))
            return object()

    # the last real program measured above: pg, p and res are still in scope
    app = SpinningApp.__new__(SpinningApp)
    app.params = dict(p)
    # A saved program can carry the tip view ON (it is saved inside params), so
    # the centre drawing must switch it off explicitly.
    app.params["show_tip_paths"] = False
    app.path_gen = pg
    app.plotter = _Plot()
    app.actors = {"paths": []}
    want = ms.compute(pg, app.params)

    app._draw_motion_stops()
    drawn = app.plotter.meshes
    check("one dot mesh is drawn, black, with one point per stop",
          len(drawn) == 1 and drawn[0][0].n_points == want["stops"]
          and drawn[0][1].get("color") == "black" and len(app.actors["paths"]) == 1,
          f"{len(drawn)} meshes")
    centre = np.array(drawn[0][0].points)

    app.params["show_tip_paths"] = True
    app.plotter, app.actors = _Plot(), {"paths": []}
    app._draw_motion_stops()
    tip = np.array(app.plotter.meshes[0][0].points)
    cx = float(app.params.get("mandrel_pos_x_offset", 0.0))
    moved = np.abs(np.abs(centre[:, 0] - cx) - np.abs(tip[:, 0] - cx))
    r_expected = np.array([app._rtool_for_pass(i) for i, _ in want["points"]])
    check("'draw at roller tip' pulls the dots in by the pass's r_tool, like the paths",
          np.allclose(moved, r_expected, atol=1e-6) and np.allclose(centre[:, 2], tip[:, 2]),
          f"moved {np.round(moved[:6], 3)} expected {np.round(r_expected[:6], 3)} "
          f"cx {cx} centre x {np.round(centre[:6, 0], 2)}")

    app.params["show_tip_paths"] = False
    app.params["show_motion_stops"] = False
    app.plotter, app.actors = _Plot(), {"paths": []}
    app._draw_motion_stops()
    check("switch off -> nothing drawn", not app.plotter.meshes)

    app.params["show_motion_stops"] = True
    app._calc_running = True
    app._draw_motion_stops()
    check("background calculation running -> nothing drawn", not app.plotter.meshes)
else:
    print("  SKIP - needs a real program")

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1)
print("All motion-stop checks passed.")
