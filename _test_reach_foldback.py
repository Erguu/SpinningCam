"""Fold-back + overlap guard (#61): near a ~180° fan angle the exit X shrinks to ~0, and
the clearance-independent-reach subtraction (p3_x -= clearance) used to flip it negative,
folding the pass backward past vertical (>180°). The guard must:
  (a) never let the exit point INWARD (no fold), and
  (b) never collapse distinct near-vertical passes onto the SAME line (no overlap) — i.e.
      when the clearance subtraction would go negative it KEEPS the commanded exit rather
      than clamping the component to 0.
"""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])
pg = PathGenerator()
base = {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0,
        "max_spin_rpm": 2000, "auto_calc_angle": False}

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


# ---- (a) no inward fold at a clearance that would flip p3_x negative ------------------
op = {"type": "roughing", "count": 1, "tool_id": "T0101", "r_tool": 30.0,
      "start_z": min_z + 30, "end_z": min_z + 30, "p3_x": 20.0, "p3_z": -15.0,
      "rot": 0.0, "reach": 40.0, "pass_angle": 175.0, "pass_shape": "linear_approach"}


def exit_dx(clearance):
    p = dict(base); p["operations"] = [dict(op, clearance=clearance)]
    tp = pg.calculate_paths(p, {}, mgr)[0][0]
    return tp[-1][0] - tp[-2][0], tp


dx0, _ = exit_dx(0.0)
dx8, tp8 = exit_dx(8.0)
check(dx0 >= -1e-6, f"clearance=0: exit not inward (dx={dx0:+.4f})")
check(dx8 >= -1e-6, f"clearance=8: exit not folded inward (dx={dx8:+.4f})")
maxx = float(np.max(tp8[:, 0]))
check(tp8[-1][0] >= maxx - 8.0 - 1e-6, "clearance=8: endpoint not inside surface contact")

# ---- (b) two near-vertical passes must stay DISTINCT (no overlap) ---------------------
# Both passes' commanded exit-X is below the clearance, so the old max(...,0) clamp would
# collapse BOTH exits to vertical (identical direction). The keep-commanded guard must
# preserve their different angles.
op2 = {"type": "roughing", "count": 2, "tool_id": "T0101", "r_tool": 30.0,
       "start_z": min_z + 30, "end_z": min_z + 40, "p3_x": 20.0, "p3_z": -15.0,
       "rot": 0.0, "reach": 40.0, "clearance": 8.0,
       "pass_angle": 176.0, "progressive_angle_enabled": True,
       "progressive_angle_end": 179.0, "pass_shape": "linear_approach"}
p = dict(base); p["operations"] = [op2]
tps = pg.calculate_paths(p, {}, mgr)[0]
pass_a, pass_b = tps[0], tps[1]
dxa = pass_a[-1][0] - pass_a[-2][0]
dxb = pass_b[-1][0] - pass_b[-2][0]
check(dxa > 1e-4 and dxb > 1e-4, f"both near-180 exits stay outward (dxa={dxa:.4f}, dxb={dxb:.4f})")
check(abs(dxa - dxb) > 1e-4,
      f"the two passes keep DISTINCT exit directions, not collapsed (|dxa-dxb|={abs(dxa-dxb):.4f})")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
