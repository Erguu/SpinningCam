"""End-to-end: suggested ops -> PathGenerator.calculate_paths -> generate_gcode."""
from mandrel_analyzer import MandrelManager
from process_planner import load_materials, suggest_operations
from path_generator import PathGenerator

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)

params = {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0,
          "max_spin_rpm": 2000}
tools = [{"id": "T0101", "r_tool": 30.0, "radius": 28.0},
         {"id": "T0202", "r_tool": None, "radius": 22.5}]

mat = load_materials()[0]
res = suggest_operations(mgr, params, mat, tools)
params["operations"] = res["ops"]

pg = PathGenerator()
tps = pg.calculate_paths(params, {}, mgr)[0]
print("toolpaths:", len(tps), "| points per path:", [len(p) for p in tps])
# steep cone -> back pass suggested ON, doubling the roughing path entries
_stride = 2 if res["ops"][0]["back_pass_enabled"] else 1
expected = res["ops"][0]["count"] * _stride + 1
assert len(tps) == expected, f"expected {expected} paths, got {len(tps)}"
assert all(len(p) >= 2 for p in tps), "degenerate path"

gc = pg.generate_gcode(params=params)
lines = gc.splitlines()
print("gcode lines:", len(lines))
assert any(l.strip().startswith("G1") for l in lines), "no cutting moves in gcode"
assert len(lines) <= 1000, "exceeds PLC 1000-line limit for default cone"
print("END-TO-END: suggested ops -> paths -> gcode OK")

# Fan end angle: lowering progressive_angle_end must change the LAST roughing
# pass geometry (fan stops early) while the first pass stays identical.
import numpy as np
n_rough = res["ops"][0]["count"]
last_180 = np.array(tps[(n_rough - 1) * 2])   # back passes interleave: fwd at even idx
first_180 = np.array(tps[0])
params["operations"][0]["progressive_angle_end"] = 120.0
tps_fan = pg.calculate_paths(params, {}, mgr)[0]
last_120 = np.array(tps_fan[(n_rough - 1) * 2])
first_120 = np.array(tps_fan[0])
assert np.allclose(first_180[-1], first_120[-1]), "first pass changed by fan end angle"
assert not np.allclose(last_180[-1], last_120[-1]), "fan end angle had no effect on last pass"
params["operations"][0]["progressive_angle_end"] = 180.0
print("FAN END ANGLE: 120 deg stops the fan early, first pass untouched OK")

# Passivate the roughing op (the On/Off compare workflow): its passes must
# drop out of the calculation without deleting the op.
n_all = len(tps)
params["operations"][0]["enabled"] = False
tps2 = pg.calculate_paths(params, {}, mgr)[0]
assert len(tps2) < n_all, "disabling an op did not remove its paths"
assert len(tps2) == 1, f"expected only the finishing path, got {len(tps2)}"
params["operations"][0]["enabled"] = True
print("PASSIVATE: disabled op excluded from calculation OK")
