"""
Regression: a Linear (full) pass with a back pass on a -X machine.

Field report ID111-1 (2026-09-24): the back pass of a linear_full pass has no
forming part, so its projection is an EMPTY array. The -X mirror at the end of
calculate_paths indexed it as (N,3) and raised, so the whole calculation died:
no passes drawn, and the STEP auto-load on startup "failed" and asked for the
file every launch.

The projection is empty when the whole back pass sits above the mandrel top
(the field pass runs at Z~179). Rather than depend on a geometry that makes
that happen, the back-pass projection is forced empty - the exact array the
field produced.

Checks:
  1. The same op on a +X machine calculates (it never mirrors - baseline).
  2. On a -X machine it calculates too, with the same number of paths.
  3. The empty projection stays empty, and every real path is mirrored.
"""
import sys, os
sys.path.append(os.getcwd())

import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator


def build(positive_side):
    mgr = MandrelManager()
    mgr.create_default_cone()
    mgr.update_geometry(0, 0, 0, 0, 0)

    pg = PathGenerator()
    _real = pg._compute_proj_and_devs          # here: back passes only (no start_from_last)

    def _empty_proj(*a, **k):
        return np.array([]), _real(*a, **k)[1]
    pg._compute_proj_and_devs = _empty_proj

    op = {
        "type": "roughing",
        "tool_id": "T0101",
        "passes": 2,
        "feed": 800,
        "speed": 200,
        "r_tool": 30.0,
        "pass_shape": "linear_full",
        "back_pass_enabled": True,
        "back_pass_feed": 800,
    }
    params = {
        "mandrel_pos_x_offset": 0.0,
        "shell_thickness": 2.0,
        "operations": [op],
        "feed": 800,
        "speed": 200,
        "roller_positive_x_side": positive_side,
    }
    projections = pg.calculate_paths(params, {}, mgr)[1]
    pg.generate_gcode(params=params)
    return pg, projections


pos, pos_proj = build(True)
empty = [i for i, p in enumerate(pos_proj)
         if np.asarray(p).size == 0]
assert empty, ("[SETUP] no empty projection on +X - the test no longer "
               "exercises the field case, rebuild it")
print(f"[PASS] +X: {len(pos.last_calculated_paths)} paths, empty projections at {empty}")

neg, neg_proj = build(False)
assert len(neg.last_calculated_paths) == len(pos.last_calculated_paths), \
    "[FAIL] -X produced a different number of paths"
print(f"[PASS] -X calculates: {len(neg.last_calculated_paths)} paths")

for i in empty:
    assert np.asarray(neg_proj[i]).size == 0, \
        f"[FAIL] projection {i} should stay empty"
for i, (a, b) in enumerate(zip(pos.last_calculated_paths, neg.last_calculated_paths)):
    a, b = np.asarray(a), np.asarray(b)
    assert np.allclose(a[:, 0], -b[:, 0]) and np.allclose(a[:, 2], b[:, 2]), \
        f"[FAIL] path {i} is not the X mirror of the +X one"
print("[PASS] Empty projection stays empty; every path is the X mirror.")

print("\n--- ALL CHECKS PASSED ---")
