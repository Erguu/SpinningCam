# -*- coding: utf-8 -*-
"""Headless test for #89 Phase 1 — anchored sweep (fixed start, growing end).

Verifies that with sweep_anchor_start ON every roughing pass roots its approach at
the SAME Z (start_z), while the contact still climbs to end_z; and that OFF is
identical to today (contact + approach both step). Also checks the pass-table
mirror (compute_pass_rows) agrees with the engine and that last_op_end_z is
unchanged (still reaches end_z)."""
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


def _params(anchored):
    return {
        "operations": [{
            "type": "roughing", "enabled": True, "count": 3, "tool_id": "T0101",
            "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0,
            "p1_x": 40.0, "p1_z": 50.0, "p3_x": 40.0, "p3_z": -20.0,
            "pass_shape": "linear_approach", "retract_x": 40.0, "retract_z": 50.0,
            "sweep_anchor_start": anchored,
        }],
        "final_part_thickness_on_mandrel": 2.0, "shell_thickness": 0.0,
        "target_clearance": 2.0, "home_x": 300.0, "home_z": 150.0,
        "mandrel_pos_x_offset": 0.0, "roller_positive_x_side": True,
    }


def _approach_root_zs(pg):
    """First point Z of each forming pass = the approach root."""
    return [float(p[0][2]) for p in pg.last_calculated_paths]


def test_engine():
    mgr = _StubMgr()

    pg_n = PathGenerator(); pg_n.calculate_paths(_params(False), {}, mgr)
    pg_a = PathGenerator(); pg_a.calculate_paths(_params(True), {}, mgr)

    roots_n = _approach_root_zs(pg_n)
    roots_a = _approach_root_zs(pg_a)
    assert len(roots_n) == 3 and len(roots_a) == 3

    # Normal: approach root steps up per pass (all distinct, increasing).
    assert roots_n[0] < roots_n[1] < roots_n[2], f"normal roots should step: {roots_n}"
    # Anchored: every pass roots at the SAME Z (fixed start).
    assert max(roots_a) - min(roots_a) < 1e-6, f"anchored roots should be equal: {roots_a}"

    # Both reach the same end (last forming contact = end_z + base p2_z_extend = 60).
    assert abs(pg_n.last_op_end_z[0] - 60.0) < 1e-6, pg_n.last_op_end_z
    assert abs(pg_a.last_op_end_z[0] - 60.0) < 1e-6, pg_a.last_op_end_z
    print(f"test_engine PASS  (normal roots={[round(z,1) for z in roots_n]}, "
          f"anchored roots={[round(z,1) for z in roots_a]})")


def test_pass_table_mirror():
    """The pass table's contact Z must match either mode; contact climbs in BOTH."""
    mgr = _StubMgr()
    for anchored in (False, True):
        p = _params(anchored)
        rows = compute_pass_rows(p["operations"][0], p, mgr)
        zs = [r["z"] for r in rows]
        assert zs == [10.0, 35.0, 60.0], f"contact z (anchored={anchored}): {zs}"
    print("test_pass_table_mirror PASS  (contact climbs 10->35->60 in both modes)")


def test_off_is_identical():
    """Absent flag == flag False == today's paths, bit-for-bit."""
    mgr = _StubMgr()
    p_absent = _params(False)
    del p_absent["operations"][0]["sweep_anchor_start"]
    pg1 = PathGenerator(); pg1.calculate_paths(p_absent, {}, mgr)
    pg2 = PathGenerator(); pg2.calculate_paths(_params(False), {}, mgr)
    for a, b in zip(pg1.last_calculated_paths, pg2.last_calculated_paths):
        assert np.allclose(a, b), "absent flag must equal explicit False"
    print("test_off_is_identical PASS")


if __name__ == "__main__":
    test_engine()
    test_pass_table_mirror()
    test_off_is_identical()
    print("ALL PASS")
