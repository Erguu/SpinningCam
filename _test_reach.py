"""Headless verification for TODO #61 step 1 — single 'reach' exit magnitude.

Guarantees:
  - backward compat: reach unset / None / 0 => byte-identical geometry (legacy)
  - raw mode: reach scales |p3| to the set value, preserving direction (angle)
  - raw mode: setting reach actually changes the toolpath
  - pass-angle mode: reach overrides the _L3 magnitude
"""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"]); top_z = float(mgr.props["top_z"])
pg = PathGenerator()
base = {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0, "max_spin_rpm": 2000}

op_raw = {"type": "roughing", "count": 1, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
          "start_z": min_z + 30, "end_z": min_z + 60, "p3_x": 20.0, "p3_z": -15.0}


def run(op):
    p = dict(base); p["operations"] = [op]
    tps = pg.calculate_paths(p, {}, mgr)[0]
    return tps, pg.last_op_reach.get(0), pg.last_op_end_angle.get(0)


def same(ta, tb):
    if len(ta) != len(tb):
        return False
    return all(a.shape == b.shape and np.allclose(a, b) for a, b in zip(ta, tb))


# --- backward compat -----------------------------------------------------
t0, _, _ = run(dict(op_raw))                 # no reach key
t1, _, _ = run(dict(op_raw, reach=None))     # explicit None
t2, _, _ = run(dict(op_raw, reach=0))        # 0 = disabled
t3, _, _ = run(dict(op_raw, reach="bad"))    # junk = disabled
assert same(t0, t1), "reach=None changed geometry"
assert same(t0, t2), "reach=0 changed geometry"
assert same(t0, t3), "reach=junk changed geometry"
print("backward-compat (unset/None/0/junk identical): OK")

# --- raw mode: scale magnitude, preserve direction -----------------------
_, r_base, a_base = run(dict(op_raw))
assert abs(r_base - np.hypot(20.0, 15.0)) < 1e-6, r_base   # legacy magnitude = |p3|
target = r_base * 2.0
_, r_set, a_set = run(dict(op_raw, reach=target))
assert abs(r_set - target) < 1e-6, (r_set, target)
assert abs(a_set - a_base) < 1e-6, (a_set, a_base)         # direction preserved
assert not same(run(dict(op_raw))[0], run(dict(op_raw, reach=target))[0]), "reach had no effect"
print(f"raw reach: base={r_base:.3f} angle={a_base:.2f} -> set={r_set:.3f} angle={a_set:.2f}: OK")

# --- pass-angle mode: reach overrides _L3 --------------------------------
op_pa = dict(op_raw); op_pa["pass_angle"] = 120.0
_, rpa_base, _ = run(dict(op_pa))
_, rpa_set, _ = run(dict(op_pa, reach=40.0))
assert abs(rpa_base - np.hypot(20.0, 15.0)) < 1e-6, rpa_base
assert abs(rpa_set - 40.0) < 1e-6, rpa_set
print(f"pass-angle reach override: base={rpa_base:.3f} -> set={rpa_set:.3f} (target 40): OK")

# --- reach is clearance-independent: same reach + diff clearance -> same END --------
# Use base_rot=0 (auto_calc_angle off, rot 0) so the endpoint anchoring is exact.
base_ci = dict(base); base_ci["auto_calc_angle"] = False
op_ci = {"type": "roughing", "count": 1, "tool_id": "T0101", "r_tool": 30.0,
         "start_z": min_z + 30, "end_z": min_z + 60, "p3_x": 20.0, "p3_z": -15.0,
         "rot": 0.0, "reach": 40.0}


def run_pass(op, clr):
    p = dict(base_ci); p["operations"] = [dict(op, clearance=clr)]
    return pg.calculate_paths(p, {}, mgr)[0][0]


# Use two larger, non-gouging clearances so the safety-floor correction (which would
# legitimately override the anchor when a low clearance gouges) does not interfere.
pA, pB = run_pass(op_ci, 8.0), run_pass(op_ci, 14.0)
end_match = np.allclose(pA[-1], pB[-1], atol=1e-6)
start_match = np.allclose(pA[0], pB[0], atol=1e-6)
# The exit END (P3) must be pinned across clearance; the contact/approach end moves.
assert end_match and not start_match, (pA[0], pA[-1], pB[0], pB[-1])
print("reach clearance-independent: exit end pinned, contact end moves with clearance: OK")

# Legacy (reach unset): p3 is a fixed offset from the moving contact -> BOTH ends move.
op_leg = dict(op_ci); op_leg.pop("reach")
qA, qB = run_pass(op_leg, 2.0), run_pass(op_leg, 8.0)
assert not np.allclose(qA[0], qB[0], atol=1e-6) and not np.allclose(qA[-1], qB[-1], atol=1e-6)
print("legacy (no reach): both ends shift with clearance (contrast): OK")

print("ALL REACH TESTS PASSED")
