"""Headless verification for TODO #62 clamp / counter-press zone (phase 1).

Covers:
  - effective_clamp_length resolution (override vs machine baseline, junk-safe)
  - calculate_paths records last_clamp_warnings when an op starts inside the zone
  - no warning when the op starts above the zone, or when no zone is set
  - per-part override of 0 inherits the machine baseline
"""
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator, effective_clamp_length

# --- 1. effective_clamp_length unit tests ---------------------------------
assert effective_clamp_length({}) == 0.0
assert effective_clamp_length({"clamp_zone_baseline": 8.0}) == 8.0
assert effective_clamp_length({"clamp_zone_length": 5.0, "clamp_zone_baseline": 8.0}) == 5.0
assert effective_clamp_length({"clamp_zone_length": 0.0, "clamp_zone_baseline": 8.0}) == 8.0
assert effective_clamp_length({"clamp_zone_length": None, "clamp_zone_baseline": 8.0}) == 8.0
assert effective_clamp_length({"clamp_zone_length": "bad", "clamp_zone_baseline": 8.0}) == 8.0
assert effective_clamp_length({"clamp_zone_length": -3.0, "clamp_zone_baseline": 8.0}) == 8.0
print("effective_clamp_length: OK")

# --- mandrel fixture ------------------------------------------------------
mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])
top_z = float(mgr.props["top_z"])
span = top_z - min_z
print(f"cone min_z={min_z:.2f} top_z={top_z:.2f} span={span:.2f}")

clamp = span * 0.2                 # clamp_top_z = min_z + clamp
start_below = min_z + span * 0.05  # inside the zone -> warn
start_above = min_z + span * 0.40  # above the zone  -> no warn
end_z = min_z + span * 0.80

pg = PathGenerator()
base = {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0,
        "max_spin_rpm": 2000}


def make_op(start_z):
    return {"type": "roughing", "count": 1, "tool_id": "T0101", "r_tool": 30.0,
            "clearance": 2.0, "start_z": start_z, "end_z": end_z}


# op starts BELOW clamp top -> warn
p = dict(base); p["clamp_zone_baseline"] = clamp
p["operations"] = [make_op(start_below)]
pg.calculate_paths(p, {}, mgr)
assert len(pg.last_clamp_warnings) == 1, pg.last_clamp_warnings
w = pg.last_clamp_warnings[0]
assert abs(w["clamp_top_z"] - (min_z + clamp)) < 1e-6, w
print("warn fires when op starts inside clamp zone: OK", w)

# op starts ABOVE clamp top -> no warn
p["operations"] = [make_op(start_above)]
pg.calculate_paths(p, {}, mgr)
assert len(pg.last_clamp_warnings) == 0, pg.last_clamp_warnings
print("no warn when op starts above clamp zone: OK")

# no clamp zone configured -> never warn (even for a very low start)
p2 = dict(base); p2["operations"] = [make_op(min_z + span * 0.01)]
pg.calculate_paths(p2, {}, mgr)
assert len(pg.last_clamp_warnings) == 0, pg.last_clamp_warnings
print("no clamp zone -> no warn: OK")

# per-part override of 0 inherits the machine baseline
p3 = dict(base); p3["clamp_zone_baseline"] = clamp; p3["clamp_zone_length"] = 0.0
p3["operations"] = [make_op(start_below)]
pg.calculate_paths(p3, {}, mgr)
assert len(pg.last_clamp_warnings) == 1, pg.last_clamp_warnings
print("override 0 inherits baseline: OK")

# per-part override wins over baseline (smaller zone -> start now above it)
p4 = dict(base); p4["clamp_zone_baseline"] = clamp; p4["clamp_zone_length"] = span * 0.02
p4["operations"] = [make_op(start_below)]
pg.calculate_paths(p4, {}, mgr)
assert len(pg.last_clamp_warnings) == 0, pg.last_clamp_warnings
print("per-part override wins over baseline: OK")

print("ALL CLAMP ZONE TESTS PASSED")
