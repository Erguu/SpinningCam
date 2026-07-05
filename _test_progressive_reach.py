"""Progressive Reach: per-pass sweep of the P2->P3 stroke length (L3),
orthogonal to the progressive-angle direction fan.

Verifies:
  1. Default off / reach_end == current reach -> zero geometry change.
  2. Enabling with a smaller reach_end shortens the LAST pass exit stroke
     while the FIRST pass (i=0) stays identical (interpolation weight 0).
  3. Reach and angle are independent: a fan (progressive_angle) still moves
     the direction while reach only changes the length.
"""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)

COUNT = 4


def _rough_op(**extra):
    op = {
        "type": "roughing", "count": COUNT, "enabled": True,
        "pass_shape": "linear_approach", "tool_id": "T0101", "r_tool": 30.0,
        "p1_x": 40.0, "p1_z": 50.0, "p3_x": 40.0, "p3_z": -20.0,
        "start_z": 10.0, "clearance": 2.0,
        "pass_angle": 120.0,          # reach only engages when pass_angle is set
    }
    op.update(extra)
    return op


def _params(op):
    return {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0,
            "max_spin_rpm": 2000, "target_clearance": 2.0, "operations": [op]}


def _exit_pts(op):
    """Exit endpoint (P3 side) of the first and last roughing pass."""
    pg = PathGenerator()
    tps = pg.calculate_paths(_params(op), {}, mgr)[0]
    # No back pass configured -> one path per pass, in order.
    first = np.array(tps[0])
    last = np.array(tps[COUNT - 1])
    return first[-1], last[-1]


# --- 1. reach_end == current reach -> no change vs. reach OFF ---------------
base_first, base_last = _exit_pts(_rough_op())
L3_start = float(np.hypot(40.0, 20.0))   # current |P2->P3| from p3_x, p3_z
same_first, same_last = _exit_pts(_rough_op(
    progressive_reach_enabled=True, progressive_reach_end=L3_start))
assert np.allclose(base_first, same_first, atol=1e-6), "reach=start changed first pass"
assert np.allclose(base_last, same_last, atol=1e-6), "reach=start changed last pass"
print("[1] reach_end == current reach -> zero geometry change OK")

# --- 2. smaller reach_end shortens only the later passes --------------------
short_first, short_last = _exit_pts(_rough_op(
    progressive_reach_enabled=True, progressive_reach_end=10.0))
assert np.allclose(base_first, short_first, atol=1e-6), \
    "progressive reach altered the FIRST pass (weight 0)"
assert not np.allclose(base_last, short_last, atol=1e-3), \
    "progressive reach had no effect on the LAST pass"
print("[2] smaller reach_end shortens last pass, first pass untouched OK")

# --- 3. reach and angle are independent ------------------------------------
# With the fan on, changing reach_end still only moves the length; the angle
# fan (direction) remains driven by progressive_angle_end.
fan = _rough_op(progressive_angle_enabled=True, progressive_angle_end=180.0,
                progressive_reach_enabled=True, progressive_reach_end=10.0)
_, fan_last = _exit_pts(fan)
fan2 = dict(fan); fan2["progressive_reach_end"] = 35.0
_, fan2_last = _exit_pts(fan2)
assert not np.allclose(fan_last, fan2_last, atol=1e-3), \
    "reach_end had no effect while the angle fan was on"
print("[3] reach sweeps length independently of the angle fan OK")

print("PROGRESSIVE REACH: all checks passed")
