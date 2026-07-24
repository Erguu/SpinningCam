# -*- coding: utf-8 -*-
"""#89 Phase 2 — per-pass Contact-Z (extent) + Clearance pins via pass_edits.

Verifies the pass table mirror (compute_pass_rows) reflects the pins and that the
engine applies them to the pinned pass only, leaving the others bit-for-bit."""
import numpy as np
from path_generator import PathGenerator
from ui.dialogs.pass_table import compute_pass_rows


class _StubMgr:
    profile_z = None
    profile_r = None

    def __init__(self):
        self.props = {"top_z": 100.0, "min_z": 0.0, "max_radius": 50.0}

    def get_radius_fast(self, z): return 50.0
    def get_normal_at_z(self, z): return 1.0, 0.0
    def get_straightened_radius(self, z): return 50.0
    def get_straightened_normal(self, z): return 1.0, 0.0


def _op(pass_edits=None):
    op = {"type": "roughing", "enabled": True, "count": 3, "tool_id": "T0101",
          "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 40.0, "p3_z": -20.0,
          "pass_shape": "linear_approach", "retract_x": 40.0, "retract_z": 50.0}
    if pass_edits is not None:
        op["pass_edits"] = pass_edits
    return op


def _params(op):
    return {"operations": [op], "final_part_thickness_on_mandrel": 2.0,
            "shell_thickness": 0.0, "target_clearance": 2.0, "home_x": 300.0,
            "home_z": 150.0, "mandrel_pos_x_offset": 0.0, "roller_positive_x_side": True}


def test_mirror():
    mgr = _StubMgr()
    # Pin pass 1: anchor Z 45, extend 10, clearance 10 → contact = 45 + 10 = 55.
    op = _op({"1": {"clearance": 10.0, "target_z": 45.0, "p2_z_extend": 10.0}})
    rows = compute_pass_rows(op, _params(op), mgr)
    assert rows[1]["anchor"] == 45.0, rows[1]["anchor"]
    assert rows[1]["extend"] == 10.0, rows[1]["extend"]
    assert rows[1]["z"] == 55.0, rows[1]["z"]                  # contact = anchor + extend
    assert rows[1]["clr"] == 10.0, rows[1]["clr"]
    assert rows[0]["z"] == 10.0 and rows[2]["z"] == 60.0       # unchanged contacts
    assert rows[0]["clr"] == 2.0 and rows[2]["clr"] == 2.0     # default op clearance
    print("test_mirror PASS  (pass1 anchor=45 extend=10 z=55 clr=10; others default)")


def test_engine_isolated():
    mgr = _StubMgr()
    op_pin = _op({"1": {"clearance": 10.0, "target_z": 45.0, "p2_z_extend": 10.0}})
    op_no = _op()
    pg_pin = PathGenerator(); pg_pin.calculate_paths(_params(op_pin), {}, mgr)
    pg_no = PathGenerator(); pg_no.calculate_paths(_params(op_no), {}, mgr)
    p_pin, p_no = pg_pin.last_calculated_paths, pg_no.last_calculated_paths
    assert len(p_pin) == 3 and len(p_no) == 3
    # Pass 0 + pass 2 untouched; pass 1 (pinned) differs.
    assert np.allclose(p_pin[0], p_no[0]), "pass 0 must be unchanged"
    assert np.allclose(p_pin[2], p_no[2]), "pass 2 must be unchanged"
    assert not np.allclose(p_pin[1], p_no[1]), "pass 1 (pinned) must change"
    print("test_engine_isolated PASS  (only pinned pass 1 changed)")


def test_no_pins_identical():
    mgr = _StubMgr()
    pg1 = PathGenerator(); pg1.calculate_paths(_params(_op()), {}, mgr)
    pg2 = PathGenerator(); pg2.calculate_paths(_params(_op({})), {}, mgr)  # empty edits
    for a, b in zip(pg1.last_calculated_paths, pg2.last_calculated_paths):
        assert np.allclose(a, b)
    print("test_no_pins_identical PASS")


if __name__ == "__main__":
    test_mirror()
    test_engine_isolated()
    test_no_pins_identical()
    print("ALL PASS")
