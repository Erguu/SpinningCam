"""Headless verification for the straight-line finishing flatness advisory.

Covers:
  - the pure metric _straight_line_flatness_dev (cone/cylinder = 0, barrel = +,
    dish = -, slope-change flagged, zero span = None)
  - calculate_paths populates last_flatness_warnings for a straight_line finishing
    op over a curved surface, and NOT for a cone, roughing, adaptive mode, or when
    the feature flag is off
Advisory only: the metric is read-only and never changes a toolpath.
"""
import math
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

pg = PathGenerator()


class FakeMandrel:
    """Minimal stand-in exposing only get_radius_fast for the pure-metric tests."""
    def __init__(self, fn):
        self._fn = fn

    def get_radius_fast(self, z):
        return self._fn(z)


# --- 1. pure metric --------------------------------------------------------
S, E = 0.0, 50.0

# cone: linear radius -> chord matches exactly -> ~0
cone = FakeMandrel(lambda z: 60.0 - 0.4 * z)
d = pg._straight_line_flatness_dev(cone, S, E)
assert d is not None and abs(d) < 1e-6, d
print(f"cone dev={d:.6f}: OK (~0)")

# cylinder: constant radius -> 0
cyl = FakeMandrel(lambda z: 55.0)
d = pg._straight_line_flatness_dev(cyl, S, E)
assert d is not None and abs(d) < 1e-6, d
print(f"cylinder dev={d:.6f}: OK (~0)")

# barrel (convex, bulges toward tool): + deviation ~ +5
barrel = FakeMandrel(lambda z: 60.0 + 5.0 * math.sin(math.pi * (z - S) / (E - S)))
d = pg._straight_line_flatness_dev(barrel, S, E)
assert d is not None and d > 4.5, d
print(f"barrel dev={d:+.3f}: OK (>0, toward tool)")

# dish (concave, dips away): - deviation ~ -5
dish = FakeMandrel(lambda z: 60.0 - 5.0 * math.sin(math.pi * (z - S) / (E - S)))
d = pg._straight_line_flatness_dev(dish, S, E)
assert d is not None and d < -4.5, d
print(f"dish dev={d:+.3f}: OK (<0, away)")

# slope change (two cones meeting) -> a kink off the chord, flagged
def _kink(z):
    return (60.0 - 0.2 * z) if z <= 25.0 else (55.0 - 1.0 * (z - 25.0))
d = pg._straight_line_flatness_dev(FakeMandrel(_kink), S, E)
assert d is not None and abs(d) > 5.0, d
print(f"slope-change dev={d:+.3f}: OK (flagged)")

# zero-length span -> None
assert pg._straight_line_flatness_dev(cone, 20.0, 20.0) is None
print("zero span -> None: OK")

# tiny bow below a 0.15 tol -> metric small (integration would not warn)
tiny = FakeMandrel(lambda z: 60.0 + 0.05 * math.sin(math.pi * (z - S) / (E - S)))
d = pg._straight_line_flatness_dev(tiny, S, E)
assert d is not None and abs(d) < 0.15, d
print(f"tiny bow dev={d:+.3f}: OK (< tol)")

# radius unavailable at a sample -> skipped, does not crash
holey = FakeMandrel(lambda z: None if 20.0 < z < 30.0 else 60.0 - 0.4 * z)
d = pg._straight_line_flatness_dev(holey, S, E)
assert d is not None
print(f"missing-radius samples skipped: OK (dev={d:+.3f})")

# --- 2. integration through calculate_paths --------------------------------
mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"]); top_z = float(mgr.props["top_z"])
s_z = min_z + (top_z - min_z) * 0.1
e_z = min_z + (top_z - min_z) * 0.8

base = {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0,
        "max_spin_rpm": 2000}


def finish_op(straight=True):
    return {"type": "finishing", "count": 1, "tool_id": "T0101", "r_tool": 30.0,
            "clearance": 2.0, "start_z": s_z, "end_z": e_z,
            "straight_line_mode": straight}


# cone (real) + straight-line finishing -> no false positive
p = dict(base); p["operations"] = [finish_op()]
pg.calculate_paths(p, {}, mgr)
assert len(pg.last_flatness_warnings) == 0, pg.last_flatness_warnings
print("cone + straight-line finish -> no warning: OK")

# inject a barrel profile (override radius only; normals stay real) -> warn, +dev
_real_radius = mgr.get_radius_fast
mid = 0.5 * (s_z + e_z)
mgr.get_radius_fast = lambda z: 60.0 + 5.0 * math.sin(math.pi * (z - s_z) / (e_z - s_z)) \
    if s_z <= z <= e_z else _real_radius(z)

p = dict(base); p["operations"] = [finish_op()]
pg.calculate_paths(p, {}, mgr)
assert len(pg.last_flatness_warnings) == 1, pg.last_flatness_warnings
w = pg.last_flatness_warnings[0]
assert w["max_dev"] > 0 and w["op_index"] == 0, w
print("barrel + straight-line finish -> warning (toward tool): OK", round(w["max_dev"], 2))

# same barrel but ROUGHING (not straight-line) -> no warning (gating)
p = dict(base); p["operations"] = [{"type": "roughing", "count": 1, "tool_id": "T0101",
                                    "r_tool": 30.0, "clearance": 2.0,
                                    "start_z": s_z, "end_z": e_z}]
pg.calculate_paths(p, {}, mgr)
assert len(pg.last_flatness_warnings) == 0, pg.last_flatness_warnings
print("barrel + roughing -> no warning (mode gated): OK")

# straight-line finish but global adaptive/trace mode ON -> no warning (branch gated)
p = dict(base); p["operations"] = [finish_op()]; p["finish_trace_mandrel_profile"] = True
pg.calculate_paths(p, {}, mgr)
assert len(pg.last_flatness_warnings) == 0, pg.last_flatness_warnings
print("barrel + adaptive mode -> no warning (branch gated): OK")

# feature flag off -> no warning even on the barrel
p = dict(base); p["operations"] = [finish_op()]; p["straight_line_flatness_warn"] = False
pg.calculate_paths(p, {}, mgr)
assert len(pg.last_flatness_warnings) == 0, pg.last_flatness_warnings
print("flag off -> no warning: OK")

mgr.get_radius_fast = _real_radius  # restore
print("ALL STRAIGHT-LINE FLATNESS TESTS PASSED")
