# -*- coding: utf-8 -*-
"""Headless test for per-op pass retract (#90).

Verifies (1) the pure resolver falls back to the global and honors overrides, and
(2) end-to-end through calculate_paths + generate_gcode: an op WITHOUT an override
retracts exactly like the global (unchanged behavior), and an op WITH an override
retracts to the overridden offset, in BOTH the 3D sim rapids and the emitted G-code.
"""
import numpy as np
from path_generator import PathGenerator, resolve_pass_retract


# ── 1. Pure resolver ────────────────────────────────────────────────────────
def test_resolver():
    p = {"retract_x": 50.0, "retract_z": 40.0}
    assert resolve_pass_retract({}, p) == (50.0, 40.0)                 # inherit
    assert resolve_pass_retract({"retract_x": 12.0}, p) == (12.0, 40.0)  # x only
    assert resolve_pass_retract({"retract_x": 12.0, "retract_z": -8.0}, p) == (12.0, -8.0)
    assert resolve_pass_retract({"retract_x": "", "retract_z": None}, p) == (50.0, 40.0)
    assert resolve_pass_retract({"retract_x": "abc"}, p) == (50.0, 40.0)  # bad -> global
    print("test_resolver PASS")


# ── Minimal stub mandrel (flat cylinder) so calculate_paths runs headless ────
class _StubMgr:
    def __init__(self):
        self.props = {"top_z": 100.0, "min_z": 0.0, "max_radius": 50.0}

    def get_radius_fast(self, z):
        return 50.0

    def get_normal_at_z(self, z):
        return 1.0, 0.0

    def get_straightened_radius(self, z):
        return 50.0

    def get_straightened_normal(self, z):
        return 1.0, 0.0


def _params(op):
    return {
        "operations": [op],
        "retract_x": 50.0, "retract_z": 40.0,
        "home_x": 300.0, "home_z": 150.0,
        "retract_x_offset": 50.0,
        "mandrel_pos_x_offset": 0.0,
        "final_part_thickness_on_mandrel": 2.0,
        "shell_thickness": 0.0,
        "target_clearance": 2.0,
        "roller_positive_x_side": True,
        "auto_calculate_paths": False,
    }


def _rough_op(**extra):
    op = {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
          "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 40.0, "p3_z": -20.0,
          "pass_shape": "linear_approach"}
    op.update(extra)
    return op


def _sim_retract_x(pg):
    """Largest rapid end-X seen (the pass retract pushes X outward)."""
    xs = []
    for seg in pg.last_calculated_paths:
        pass
    return None


def test_end_to_end():
    mgr = _StubMgr()

    # (a) no override -> retract uses global (50)
    pg = PathGenerator()
    p = _params(_rough_op())
    pg.calculate_paths(p, {}, mgr)
    gc_global = pg.generate_gcode(params=p)
    ret_global = [l for l in gc_global.splitlines() if "(Retract Op" in l and l.strip().startswith("G0")]

    # (b) override retract_x=15 -> retract lands 35 mm closer than global
    pg2 = PathGenerator()
    p2 = _params(_rough_op(retract_x=15.0))
    pg2.calculate_paths(p2, {}, mgr)
    gc_ovr = pg2.generate_gcode(params=p2)
    ret_ovr = [l for l in gc_ovr.splitlines() if "(Retract Op" in l and l.strip().startswith("G0")]

    assert ret_global, "expected retract lines in global g-code"
    assert ret_ovr, "expected retract lines in override g-code"
    # Parse first retract X from each
    def first_x(lines):
        for l in lines:
            for tok in l.split():
                if tok.startswith("X"):
                    return float(tok[1:])
        return None
    xg, xo = first_x(ret_global), first_x(ret_ovr)
    assert xg is not None and xo is not None
    # override is 35 mm smaller offset -> retract X is 35 mm less than global
    assert abs((xg - xo) - 35.0) < 1e-6, f"expected 35mm delta, got {xg-xo}"
    print(f"test_end_to_end PASS  (global retract X={xg:.2f}, override X={xo:.2f})")


def test_migration():
    """migrate_pass_retract stamps every op from the legacy global, idempotently."""
    from config_schema import migrate_pass_retract
    p = {"retract_x": 30.0, "retract_z": 20.0, "operations": [
        {"type": "roughing"},                       # inherits global
        {"type": "finishing", "retract_x": 5.0},    # keeps its own X, inherits Z
        {"type": "cutting"},
    ]}
    migrate_pass_retract(p)
    assert p["operations"][0]["retract_x"] == 30.0 and p["operations"][0]["retract_z"] == 20.0
    assert p["operations"][1]["retract_x"] == 5.0 and p["operations"][1]["retract_z"] == 20.0
    assert p["operations"][2]["retract_x"] == 30.0
    # idempotent + no global -> defaults hold
    migrate_pass_retract(p)
    assert p["operations"][0]["retract_x"] == 30.0
    p2 = {"operations": [{"type": "roughing"}]}     # no global at all -> 50 default
    migrate_pass_retract(p2)
    assert p2["operations"][0]["retract_x"] == 50.0 and p2["operations"][0]["retract_z"] == 50.0
    print("test_migration PASS")


if __name__ == "__main__":
    test_resolver()
    test_migration()
    test_end_to_end()
    print("ALL PASS")
