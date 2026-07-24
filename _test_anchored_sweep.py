# -*- coding: utf-8 -*-
"""#89 — anchored sweep built by hand via per-pass pins (Set-all Anchor Z +
Progressive Extend). Verifies that pinning every pass's target_z to the same value
and ramping p2_z_extend reproduces the fixed-start / growing-contact motion, while
the normal (unpinned) op steps its approach root."""
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


def _roots(pg):
    return [float(p[0][2]) for p in pg.last_calculated_paths]


def test_manual_anchored_sweep():
    mgr = _StubMgr()
    # Set-all Anchor Z = 10, Progressive Extend 0 -> 50 across the 3 passes.
    edits = {"0": {"target_z": 10.0, "p2_z_extend": 0.0},
             "1": {"target_z": 10.0, "p2_z_extend": 25.0},
             "2": {"target_z": 10.0, "p2_z_extend": 50.0}}
    pg_a = PathGenerator(); pg_a.calculate_paths(_params(_op(edits)), {}, mgr)
    pg_n = PathGenerator(); pg_n.calculate_paths(_params(_op()), {}, mgr)

    roots_a, roots_n = _roots(pg_a), _roots(pg_n)
    # Anchored: every approach root at the SAME Z (fixed start = 10 - p1_z = -40).
    assert max(roots_a) - min(roots_a) < 1e-6, f"anchored roots not equal: {roots_a}"
    assert abs(roots_a[0] - (-40.0)) < 1e-6, roots_a
    # Normal: roots step.
    assert roots_n[0] < roots_n[1] < roots_n[2], f"normal roots should step: {roots_n}"

    # Contacts climb 10 -> 35 -> 60 in the anchored case (mirror check).
    rows = compute_pass_rows(_op(edits), _params(_op(edits)), mgr)
    assert [r["z"] for r in rows] == [10.0, 35.0, 60.0], [r["z"] for r in rows]
    assert [r["anchor"] for r in rows] == [10.0, 10.0, 10.0]
    assert [r["extend"] for r in rows] == [0.0, 25.0, 50.0]
    # Last-pass end reflects the pinned contact.
    assert abs(pg_a.last_op_end_z[0] - 60.0) < 1e-6, pg_a.last_op_end_z
    print(f"test_manual_anchored_sweep PASS  (anchored roots={[round(z,1) for z in roots_a]}, "
          f"normal={[round(z,1) for z in roots_n]})")


def test_no_pins_identical():
    mgr = _StubMgr()
    pg1 = PathGenerator(); pg1.calculate_paths(_params(_op()), {}, mgr)
    pg2 = PathGenerator(); pg2.calculate_paths(_params(_op({})), {}, mgr)
    for a, b in zip(pg1.last_calculated_paths, pg2.last_calculated_paths):
        assert np.allclose(a, b)
    print("test_no_pins_identical PASS")


if __name__ == "__main__":
    test_manual_anchored_sweep()
    test_no_pins_identical()
    print("ALL PASS")
