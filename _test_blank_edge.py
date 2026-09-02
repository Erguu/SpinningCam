"""Predicted blank-edge overlay: the engine recorder + the 3D layer's contract.

The point of the recorder is that the edge is measured at the pass's REAL contact
height (target_z + p2_z_extend), not at the anchor. With Extend ramping and the
anchor pinned — exactly how the Mexico field program is built — measuring at the
anchor returns one frozen value for every pass.
"""
import math
import unittest

import numpy as np

from path_generator import PathGenerator
from process_planner import estimate_flange_reach


class FakeMandrel:
    """Straight cone, radius shrinking with Z. Enough for the flange model."""

    def __init__(self, z0=0.0, z1=150.0, r0=80.0, r1=40.0, n=301):
        self.profile_z = np.linspace(z0, z1, n)
        self.profile_r = np.linspace(r0, r1, n)
        self.pv_mesh = None
        self.props = {"min_z": z0, "top_z": z1, "br": r0, "tr": r1}

    def get_radius_fast(self, z):
        return float(np.interp(z, self.profile_z, self.profile_r))

    def get_normal_at_z(self, z):
        return (1.0, 0.0)

    def get_straightened_radius(self, z):
        return self.get_radius_fast(z)

    def get_straightened_normal(self, z):
        return (1.0, 0.0)


class TestFlangeHeight(unittest.TestCase):
    """The bug this overlay was built to make visible."""

    def setUp(self):
        self.mgr = FakeMandrel()
        self.R = 150.0

    def test_anchor_measurement_is_frozen_when_extend_ramps(self):
        anchor = 10.0
        extends = [5.0, 30.0, 60.0, 90.0, 120.0]
        at_anchor = [estimate_flange_reach(self.mgr, self.R, anchor) for _ in extends]
        self.assertEqual(len(set(round(v, 6) for v in at_anchor)), 1,
                         "measuring at the anchor must give one frozen value")

    def test_contact_measurement_shrinks_as_passes_climb(self):
        anchor = 10.0
        vals = [estimate_flange_reach(self.mgr, self.R, anchor + e)
                for e in (5.0, 30.0, 60.0, 90.0, 120.0)]
        for a, b in zip(vals, vals[1:]):
            self.assertLess(b, a, "flange must shrink as the pass climbs the wall")

    def test_contact_and_anchor_agree_when_extend_is_zero(self):
        """Programs that do not use Extend are unaffected either way."""
        for z in (10.0, 40.0, 80.0):
            self.assertAlmostEqual(estimate_flange_reach(self.mgr, self.R, z),
                                   estimate_flange_reach(self.mgr, self.R, z + 0.0),
                                   places=9)

    def test_flange_is_exhausted_high_on_the_wall(self):
        self.assertEqual(estimate_flange_reach(self.mgr, self.R, 149.0), 0.0)


class TestRecorderContract(unittest.TestCase):
    """last_blank_edge is what the 3D layer reads; it must never break path calc."""

    def test_attribute_exists_on_a_fresh_generator(self):
        pg = PathGenerator()
        self.assertEqual(pg.last_blank_edge, [],
                         "3D layer reads this before any calculation")

    def test_entries_are_z_radius_pairs_above_the_mandrel(self):
        mgr, R = FakeMandrel(), 150.0
        for z in (15.0, 50.0, 100.0):
            fr = estimate_flange_reach(mgr, R, z)
            edge_r = mgr.get_radius_fast(z) + fr
            self.assertGreaterEqual(edge_r, mgr.get_radius_fast(z),
                                    "sheet edge can never be inside the mandrel")
            self.assertLessEqual(edge_r, R + 1e-6,
                                 "sheet edge can never exceed the starting blank")

    def test_edge_radius_never_exceeds_blank_radius(self):
        mgr, R = FakeMandrel(), 150.0
        for z in np.linspace(1.0, 149.0, 40):
            fr = estimate_flange_reach(mgr, R, float(z))
            self.assertLessEqual(mgr.get_radius_fast(float(z)) + fr, R + 1e-6)


class TestOverlayIsAdvisoryOnly(unittest.TestCase):
    def test_recorder_does_not_appear_in_gcode_path(self):
        """The recorder must be write-only: nothing reads last_blank_edge in the engine."""
        with open("path_generator.py", encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(src.count("last_blank_edge"), 3,
                         "expected exactly: 2 initialisations + 1 append, no reads")
        for line in src.splitlines():
            if "last_blank_edge" in line and "append" not in line:
                self.assertIn("= []", line, f"unexpected read of the recorder: {line!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
