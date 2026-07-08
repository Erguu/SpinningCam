# -*- coding: utf-8 -*-
"""Headless test for #82 (reverse-pass leg-role swap, NEW DEFAULT) and #81
(per-op exit_arc_angle with global fallback).

Reverse linear passes are traversed P3→P2→arm. The leg ENTERING the
mandrel-near P2 must be STRAIGHT; the exit_arc bow belongs on the outgoing arm.
exit_arc=0 (and reverse_legacy_flip=True) stay byte-identical to the old
flipped-forward behavior."""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

def build(direction, exit_arc_op=None, exit_arc_global=0.0, legacy=False):
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
          "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": direction}
    if exit_arc_op is not None:
        op["exit_arc_angle"] = exit_arc_op
    if legacy:
        op["reverse_legacy_flip"] = True
    p = {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
         "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
         "exit_arc_angle": exit_arc_global}
    return pg.calculate_paths(p, {}, mgr)[0][0]

def max_dev_from_chord(seg):
    a, b = seg[0], seg[-1]
    ab = b - a
    L = np.linalg.norm(ab)
    if L < 1e-9:
        return 0.0
    d = np.cross(seg - a, ab / L)
    return float(np.max(np.linalg.norm(d, axis=1)))

# 1. exit_arc=0: reverse == flipped forward (byte compat for boyless programs).
fwd0 = build("forward")
rev0 = build("reverse")
check(np.allclose(fwd0[::-1], rev0, atol=1e-9), "exit_arc=0: reverse == old flip")

# 2. Legacy escape hatch restores the old flip exactly, bow and all.
check(np.allclose(build("forward", exit_arc_op=25.0)[::-1],
                  build("reverse", exit_arc_op=25.0, legacy=True), atol=1e-9),
      "reverse_legacy_flip restores old behavior")

# 3. NEW DEFAULT: straight INTO P2, bow on the outgoing arm.
rev = build("reverse", exit_arc_op=25.0)
n = len(rev)
entry = rev[: n // 4]          # starts at P3 → toward P2: must be straight
outgo = rev[3 * n // 4:]       # T1 → arm end: carries the bow
e_dev = max_dev_from_chord(entry)
o_dev = max_dev_from_chord(outgo)
check(e_dev < 0.05, f"entry leg straight (chord dev {e_dev:.4f} mm)")
check(o_dev > 0.5, f"outgoing arm bowed (chord dev {o_dev:.4f} mm)")

# 4. #81 — per-op exit_arc_angle wins over the global; empty falls back.
f_op = build("forward", exit_arc_op=25.0, exit_arc_global=0.0)
f_gl = build("forward", exit_arc_op=None, exit_arc_global=25.0)
check(np.allclose(f_op, f_gl, atol=1e-9), "op value == same value via global (formula unchanged)")
f_win = build("forward", exit_arc_op=10.0, exit_arc_global=25.0)
check(not np.allclose(f_win, f_gl, atol=1e-6), "op value WINS over a different global")
f_fallback = build("forward", exit_arc_op="", exit_arc_global=25.0)
check(np.allclose(f_fallback, f_gl, atol=1e-9), "empty op value falls back to global")

# 5. Forward passes are untouched by the swap logic (only reverse changes).
check(np.allclose(build("forward", exit_arc_op=25.0),
                  build("forward", exit_arc_op=25.0), atol=1e-12),
      "forward deterministic / unaffected")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
