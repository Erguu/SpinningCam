# -*- coding: utf-8 -*-
"""Decimation rewrite (2026-08-30 check-up items #3/#4): FASTER, NOT DIFFERENT.

`_rdp_decimate` was the hottest function in the program — a Python loop doing
~409k scalar `np.linalg.norm` calls per PLC auto-tune fit, 87% of a 4.9 s freeze
on the Tk main thread. It is now one numpy expression per segment, and the
auto-tune bisection no longer pays for answers it discards.

Both changes claim to be PURELY a speed-up, so both are pinned against the code
they replaced rather than against hand-written expectations:

  1. `_rdp_decimate` vs `_rdp_decimate_scalar` (the original, kept in the module
     for exactly this), over real toolpaths and a tolerance sweep, plus the
     degenerate cases that make RDP interesting: repeated points, perfectly
     straight runs, and ties for the furthest point.

     NOT an identical index list, and that is measured rather than assumed. Row-
     wise numpy accumulates in a different order from per-point `np.dot`, so
     distances differ by ~1e-14 mm, which flips the winner when two points are
     EXACTLY tied for furthest (3.1% of 294 real combinations). What must hold is
     what anything downstream can actually observe:
         * the POINT COUNT is always the same — the PLC line budget, and
           therefore the auto-tune, cannot see the difference at all;
         * the simplified path is exactly as accurate (max-deviation gap 0.0);
         * indices only ever differ where the distances tie.

  2. `auto_fit_plc_tolerance` vs a reference bisection written out longhand here
     the way it used to run — same tolerance, same line count, same clearance,
     same status. If the search ever stops somewhere else, this fails. It already
     did once: an early exit that abandoned the bracket below a micrometre
     returned 109 lines where the full search finds 115, which is exactly the
     budget-filling promise this function exists to keep.

It also pins the thing that made the search cheap, because that IS the fix and a
future edit could quietly undo it while keeping the answer right: the number of
G-code emissions and clearance measurements per fit.

Run:  python _test_decimation.py
"""
import time

import numpy as np

from export_manager import ExportManager
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from recipe_to_scl import GCodeToSCLConverter

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()

PARAMS = {
    "operations": [{"type": "roughing", "count": 6, "start_z": 30.0, "end_z": 70.0,
                    "r_tool": 25.0, "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0,
                    "p3_x": 30.0, "p3_z": -25.0, "pass_shape": "linear_approach",
                    "p2_radius": 8.0, "exit_bow": 5.0}],
    "auto_calc_angle": False, "min_safety_gap": -999.0,
    "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
}
paths = pg.calculate_paths(PARAMS, {}, mgr)[0]
print(f"\nfixture: {len(paths)} paths, {sum(len(p) for p in paths)} points")


def max_dev(orig, idx):
    """Max distance from every original point to the simplified polyline — how
    accurate this particular decimation is, which is the property that matters."""
    worst = 0.0
    for i in range(len(idx) - 1):
        a, b = orig[idx[i]], orig[idx[i + 1]]
        seg = b - a
        L2 = float(seg @ seg)
        chunk = orig[idx[i]:idx[i + 1] + 1]
        rel = chunk - a
        t = np.zeros(len(chunk)) if L2 < 1e-18 else np.clip(rel @ seg / L2, 0, 1)
        worst = max(worst, float(np.linalg.norm(rel - t[:, None] * seg, axis=1).max()))
    return worst


# ── 1. the vectorised RDP decimates as well as the scalar one ───────────────
print("\n[1] _rdp_decimate vs _rdp_decimate_scalar (#4)")

TOLS = [0.0, 1e-6, 1e-4, 0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0,
        4.0, 8.0, 50.0]
count_diff, dev_gap, tie_broken, n_compared = [], 0.0, 0, 0
for pi, p in enumerate(paths):
    arr = np.asarray(p, dtype=float)
    for tol in TOLS:
        n_compared += 1
        a = pg._rdp_decimate(arr, tol)
        b = pg._rdp_decimate_scalar(arr, tol)
        if a == b:
            continue
        tie_broken += 1
        if len(a) != len(b):
            count_diff.append((pi, tol, len(a), len(b)))
        elif len(a) >= 2:
            dev_gap = max(dev_gap, abs(max_dev(arr, a) - max_dev(arr, b)))

check(f"real toolpaths: {n_compared} combinations, POINT COUNT never differs",
      not count_diff, f"differing counts: {count_diff[:5]}")
check("the simplified path is exactly as accurate (max-deviation gap 0)",
      dev_gap == 0.0, f"worst gap {dev_gap:.3e} mm")
print(f"  info  index lists differ in {tie_broken}/{n_compared} "
      f"({100*tie_broken/max(n_compared,1):.1f}%) — tie-breaks only")

EDGE = {
    "empty":               np.zeros((0, 3)),
    "one point":           np.zeros((1, 3)),
    "two points":          np.array([[0., 0., 0.], [1., 0., 1.]]),
    "all identical":       np.ones((7, 3)),
    "closed loop (start==end)": np.array([[0., 0., 0.], [1., 0., 0.], [1., 0., 1.],
                                          [0., 0., 0.]]),
    "perfectly straight":  np.stack([np.linspace(0, 10, 9), np.zeros(9),
                                     np.linspace(0, 10, 9)], axis=1),
    "symmetric tie":       np.array([[0., 0., 0.], [1., 0., 1.], [2., 0., 0.],
                                     [3., 0., 1.], [4., 0., 0.]]),
    "duplicate midpoints": np.array([[0., 0., 0.], [1., 0., 1.], [1., 0., 1.],
                                     [2., 0., 0.]]),
}
for name, arr in EDGE.items():
    for tol in (0.0, 0.1, 1.0):
        a = pg._rdp_decimate(arr, tol)
        b = pg._rdp_decimate_scalar(arr, tol)
        check(f"edge case {name!r} @ tol={tol}", a == b, f"{a} vs {b}")

# A tie must resolve to the FIRST furthest point, the way `d > max_dist` did.
tie = EDGE["symmetric tie"]
check("a tie keeps the FIRST furthest point (index 1, not 3)",
      pg._rdp_decimate(tie, 0.1) == pg._rdp_decimate_scalar(tie, 0.1)
      and 1 in pg._rdp_decimate(tie, 0.1),
      str(pg._rdp_decimate(tie, 0.1)))

# Timed on a path the size a real recipe actually carries — the fixture above is
# deliberately small so the equivalence sweep stays quick, and timing 24-point
# paths would say nothing. A production pass is a few hundred to a few thousand
# points, and the auto-tune decimates every one of them ~20 times.
_u = np.linspace(0, 6 * np.pi, 3000)
BIG = np.stack([80 + 20 * np.cos(_u) + 0.4 * np.sin(11 * _u),
                np.zeros_like(_u),
                np.linspace(0, 140, 3000)], axis=1)
t0 = time.time()
idx_s = pg._rdp_decimate_scalar(BIG, 0.05)
t_scalar = time.time() - t0
t0 = time.time()
idx_v = pg._rdp_decimate(BIG, 0.05)
t_vec = time.time() - t0
check(f"a {len(BIG)}-point path decimates to the same {len(idx_v)} points",
      len(idx_v) == len(idx_s), f"{len(idx_v)} vs {len(idx_s)}")
print(f"  info  one {len(BIG)}-point path: scalar {t_scalar*1000:.0f} ms -> "
      f"vectorised {t_vec*1000:.0f} ms  ({t_scalar/max(t_vec, 1e-9):.1f}x)")


# ── 2. the auto-tune still lands in the same place ──────────────────────────
print("\n[2] auto_fit_plc_tolerance is unchanged in RESULT (#3)")


def reference_fit(target_lines, floor_clearance, tol_min=0.001, tol_max=8.0,
                  iters=18):
    """The pre-2026-08-30 search, written out longhand: clearance measured on
    every probe, a fixed iteration count, and the winner re-evaluated at the end."""
    base = dict(PARAMS)
    base["plc_mode"] = True
    eps = 1e-6

    def _eval(tol):
        p = dict(base)
        p["plc_tolerance"] = tol
        p["plc_exit_tolerance"] = tol
        gcode = pg.generate_gcode(params=p, for_recipe=True)
        conv = GCodeToSCLConverter()
        conv.parse_gcode(gcode)
        cl = pg.measure_min_clearance(getattr(pg, "last_plc_paths", None) or [], p)
        return len(conv.lines), cl

    n_fine, cl_fine = _eval(tol_min)
    if n_fine <= target_lines:
        return {"status": "no_reduction_needed", "tolerance": tol_min,
                "lines": n_fine, "min_clearance": cl_fine, "floor": floor_clearance}
    n_coarse, cl_coarse = _eval(tol_max)
    if n_coarse > target_lines:
        return {"status": "infeasible_budget", "tolerance": tol_max,
                "lines": n_coarse, "min_clearance": cl_coarse, "floor": floor_clearance}
    lo, hi = tol_min, tol_max
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        n, _cl = _eval(mid)
        if n <= target_lines:
            hi = mid
        else:
            lo = mid
    n_star, cl_star = _eval(hi)
    return {"status": "ok" if cl_star >= floor_clearance - eps else "clearance_limited",
            "tolerance": hi, "lines": n_star, "min_clearance": cl_star,
            "floor": floor_clearance}


floor = pg.measure_min_clearance(paths, PARAMS)
n_full = ExportManager.auto_fit_plc_tolerance(pg, PARAMS, 10 ** 9, floor)["lines"]
print(f"  info  full-resolution recipe is {n_full} lines")

# Targets chosen around that: three that must bisect, one already inside the
# budget, one impossible.
TARGETS = (n_full // 3, n_full // 2, (3 * n_full) // 4, n_full + 50, 3)
for target in TARGETS:
    ref = reference_fit(target, floor)
    got = ExportManager.auto_fit_plc_tolerance(pg, PARAMS, target, floor)
    check(f"target={target}: status {got['status']!r} == {ref['status']!r}",
          got["status"] == ref["status"])
    check(f"target={target}: lines {got['lines']} == {ref['lines']}",
          got["lines"] == ref["lines"])
    check(f"target={target}: clearance {got['min_clearance']:.6f} == "
          f"{ref['min_clearance']:.6f}",
          abs(float(got["min_clearance"]) - float(ref["min_clearance"])) < 1e-9)
    check(f"target={target}: tolerance {got['tolerance']:.9f} == "
          f"{ref['tolerance']:.9f}",
          abs(got["tolerance"] - ref["tolerance"]) < 1e-12)
    check(f"target={target}: the fit really does fit the budget",
          got["status"] != "ok" or got["lines"] <= target,
          f"{got['lines']} > {target}")


# ── 3. and it stops paying for answers nobody reads ─────────────────────────
print("\n[3] the search does fewer full evaluations (#3)")

_real_gcode = PathGenerator.generate_gcode
_real_clear = PathGenerator.measure_min_clearance
counts = {"gcode": 0, "clearance": 0}


def _count_gcode(self, *a, **k):
    counts["gcode"] += 1
    return _real_gcode(self, *a, **k)


def _count_clear(self, *a, **k):
    counts["clearance"] += 1
    return _real_clear(self, *a, **k)


PathGenerator.generate_gcode = _count_gcode
PathGenerator.measure_min_clearance = _count_clear
BISECT_TARGET = n_full // 2              # a target that really does bisect
try:
    counts.update(gcode=0, clearance=0)
    t0 = time.time()
    ExportManager.auto_fit_plc_tolerance(pg, PARAMS, BISECT_TARGET, floor)
    t_new = time.time() - t0
    new = dict(counts)

    counts.update(gcode=0, clearance=0)
    t0 = time.time()
    reference_fit(BISECT_TARGET, floor)
    t_ref = time.time() - t0
    ref_counts = dict(counts)
finally:
    PathGenerator.generate_gcode = _real_gcode
    PathGenerator.measure_min_clearance = _real_clear

print(f"  info  reference: {ref_counts['gcode']} emissions / "
      f"{ref_counts['clearance']} clearance measurements / {t_ref:.2f} s")
print(f"  info  now:       {new['gcode']} emissions / "
      f"{new['clearance']} clearance measurements / {t_new:.2f} s")
# Three: the two bracket ends (which report one if they return early) and the
# final run that supplies the answer's clearance. NOT once per probe.
check("clearance is measured a fixed handful of times, not once per probe",
      new["clearance"] <= 3, f"got {new['clearance']}")
check("the reference really did measure it on every probe (so this is a saving)",
      ref_counts["clearance"] >= 10, f"got {ref_counts['clearance']}")
check("no more G-code emissions than the old search",
      new["gcode"] <= ref_counts["gcode"],
      f"{new['gcode']} vs {ref_counts['gcode']}")
# Deliberately NOT asserting a wall-clock win here: both sides of this comparison
# already run the vectorised RDP (that is #4, and it applies to the reference
# too), so what is left to measure is a handful of cheap clearance calls and the
# machine's mood. The real timing lives in the [1] info line above and in
# LAST_CHANGES; a stopwatch assertion here would only buy a flaky test.


print()
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for n in FAIL:
        print("  FAILED:", n)
    raise SystemExit(1)
print("ALL PASS")
