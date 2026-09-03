"""Predicted blank-edge overlay: the engine recorder + the 3D layer's contract.

The point of the recorder is that the edge is measured at the pass's REAL contact
height (target_z + p2_z_extend), not at the anchor. With Extend ramping and the
anchor pinned — exactly how the Mexico field program is built — measuring at the
anchor returns one frozen value for every pass.
"""
import math
import unittest

import numpy as np

from path_generator import PathGenerator, exit_end_direction
from process_planner import estimate_flange_reach, flange_edge_along_exit


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


class TestFlangeFollowsTheExitDirection(unittest.TestCase):
    """The flange trails along P2→P3, it does not lie flat (user, 2026-09-03)."""

    R1 = 60.0
    Z0 = 40.0
    FR = 25.0

    def _area_over_pi(self, r1, fr):
        """Leftover blank area / pi that the flat model implies."""
        return 2.0 * r1 * fr + fr * fr

    def test_flat_exit_reproduces_the_old_answer_exactly(self):
        """dx=1 is the flat disc; the new model must not move those parts."""
        r, z = flange_edge_along_exit(self.R1, self.Z0, self.FR, 1.0, 0.0)
        self.assertAlmostEqual(r, self.R1 + self.FR, places=9)
        self.assertAlmostEqual(z, self.Z0, places=9)

    def test_area_is_conserved_whatever_the_exit_angle(self):
        """Same sheet, tilted: the frustum must hold the same material."""
        want = self._area_over_pi(self.R1, self.FR)
        for deg in (0, 15, 30, 45, 60, 75, 89):
            dx, dz = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            r2, z2 = flange_edge_along_exit(self.R1, self.Z0, self.FR, dx, dz)
            L = math.hypot(r2 - self.R1, z2 - self.Z0)
            got = (self.R1 + r2) * L        # frustum lateral area / pi
            self.assertAlmostEqual(got, want, places=6,
                                   msg=f"material lost/gained at {deg} deg")

    def test_a_climbing_exit_lifts_the_edge_and_pulls_it_inboard(self):
        flat_r, _ = flange_edge_along_exit(self.R1, self.Z0, self.FR, 1.0, 0.0)
        r, z = flange_edge_along_exit(self.R1, self.Z0, self.FR, 0.5, 0.866)
        self.assertGreater(z, self.Z0, "a climbing pass must raise the sheet edge")
        self.assertLess(r, flat_r, "tilted material cannot reach as far out")
        self.assertGreater(r, self.R1, "edge is still outside the contact radius")

    def test_a_vertical_exit_keeps_the_radius_and_stands_the_flange_up(self):
        r, z = flange_edge_along_exit(self.R1, self.Z0, self.FR, 0.0, 1.0)
        self.assertAlmostEqual(r, self.R1, places=9, msg="a cylinder does not open out")
        expected_L = self._area_over_pi(self.R1, self.FR) / (2.0 * self.R1)
        self.assertAlmostEqual(z - self.Z0, expected_L, places=9)

    def test_the_flange_never_folds_back_over_the_formed_part(self):
        """Past ~90 deg the exit points inward. Unclamped, a 128 deg pass walks a 97mm
        flange in to r=15mm — not a real sheet. It must clamp at vertical instead."""
        vert_r, vert_z = flange_edge_along_exit(self.R1, self.Z0, self.FR, 0.0, 1.0)
        for deg in (95, 120, 150, 179):
            dx, dz = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            r, z = flange_edge_along_exit(self.R1, self.Z0, self.FR, dx, dz)
            self.assertTrue(math.isfinite(r) and math.isfinite(z), f"{deg} deg blew up")
            self.assertAlmostEqual(r, vert_r, places=9,
                                   msg=f"{deg} deg folded inboard past vertical")
            self.assertAlmostEqual(z, vert_z, places=9)
            self.assertGreaterEqual(r, self.R1 - 1e-9,
                                    "edge can never be inside the contact radius")

    def test_the_clamp_still_conserves_material(self):
        """Clamping the DIRECTION must not quietly lose or invent sheet."""
        want = self._area_over_pi(self.R1, self.FR)
        for deg in (95, 130, 170):
            dx, dz = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            r2, z2 = flange_edge_along_exit(self.R1, self.Z0, self.FR, dx, dz)
            L = math.hypot(r2 - self.R1, z2 - self.Z0)
            self.assertAlmostEqual((self.R1 + r2) * L, want, places=6)

    def test_no_flange_left_means_the_edge_is_the_contact_point(self):
        r, z = flange_edge_along_exit(self.R1, self.Z0, 0.0, 0.5, 0.866)
        self.assertAlmostEqual(r, self.R1, places=9)
        self.assertAlmostEqual(z, self.Z0, places=9)

    def test_a_degenerate_exit_vector_falls_back_to_flat(self):
        r, z = flange_edge_along_exit(self.R1, self.Z0, self.FR, 0.0, 0.0)
        self.assertAlmostEqual(r, self.R1 + self.FR, places=9)
        self.assertAlmostEqual(z, self.Z0, places=9)


def _pass_path(angle_deg, length=40.0, curve_deg=0.0, n=120, x0=60.0, z0=40.0):
    """A pass tip: a straight exit at ``angle_deg``, optionally curling a further
    ``curve_deg`` by the time it reaches the end (an arc, sampled like a real path)."""
    a0 = math.radians(angle_deg)
    a1 = math.radians(angle_deg + curve_deg)
    pts, x, z = [[x0, 0.0, z0]], x0, z0
    for k in range(1, n + 1):
        a = a0 + (a1 - a0) * (k / n)
        x += (length / n) * math.cos(a)
        z += (length / n) * math.sin(a)
        pts.append([x, 0.0, z])
    return np.array(pts)


class TestExitEndDirection(unittest.TestCase):
    """The overlay asks the BUILT path which way the tip points (user, 2026-09-03)."""

    def test_a_straight_pass_reports_its_own_angle(self):
        for deg in (0.0, 30.0, 60.0, 90.0):
            dx, dz = exit_end_direction(_pass_path(deg))
            self.assertAlmostEqual(math.degrees(math.atan2(dz, dx)), deg, places=3,
                                   msg=f"straight {deg} deg pass misread")

    def test_a_curved_exit_reports_the_TIP_not_the_chord(self):
        """A curling exit ends steeper than the straight line from start to end."""
        path = _pass_path(30.0, curve_deg=40.0)
        dx, dz = exit_end_direction(path)
        tip = math.degrees(math.atan2(dz, dx))
        chord = math.degrees(math.atan2(path[-1][2] - path[0][2],
                                        path[-1][0] - path[0][0]))
        self.assertGreater(tip, chord + 5.0, "tangent collapsed onto the chord")
        self.assertAlmostEqual(tip, 70.0, delta=3.0, msg="tip angle is wrong")

    def test_a_curved_exit_bends_the_sheet_edge_further_than_a_straight_one(self):
        """The whole point: curved passes curl the free edge up, straight ones do not."""
        r1, z0, fr = 60.0, 40.0, 25.0
        straight = flange_edge_along_exit(r1, z0, fr, *exit_end_direction(_pass_path(30.0)))
        curved = flange_edge_along_exit(r1, z0, fr,
                                        *exit_end_direction(_pass_path(30.0, curve_deg=40.0)))
        self.assertGreater(curved[1], straight[1], "curved exit must lift the edge more")
        self.assertLess(curved[0], straight[0], "and pull it further inboard")

    def test_it_survives_paths_it_cannot_measure(self):
        self.assertIsNone(exit_end_direction(np.zeros((0, 3))))
        self.assertIsNone(exit_end_direction(np.array([[1.0, 0.0, 2.0]])))
        self.assertIsNone(exit_end_direction(np.zeros((8, 3))), "degenerate path")

    def test_a_path_shorter_than_the_span_still_measures(self):
        """Tiny passes must not silently vanish from the overlay."""
        d = exit_end_direction(_pass_path(45.0, length=1.0, n=4))
        self.assertIsNotNone(d)
        self.assertAlmostEqual(math.degrees(math.atan2(d[1], d[0])), 45.0, places=3)


class TestExhaustedFlangeDrawsNothing(unittest.TestCase):
    """A pass anchored where the blank is fully formed has no free edge to show."""

    def test_the_edge_collapses_onto_the_contact_point(self):
        mgr, R = FakeMandrel(), 150.0
        z_top = 149.0
        self.assertEqual(estimate_flange_reach(mgr, R, z_top), 0.0,
                         "precondition: flange is used up this high")
        r, z = flange_edge_along_exit(mgr.get_radius_fast(z_top), z_top, 0.0, 0.5, 0.866)
        self.assertAlmostEqual(r, mgr.get_radius_fast(z_top), places=9)
        self.assertAlmostEqual(z, z_top, places=9)

    def test_the_recorder_skips_it_rather_than_drawing_on_the_mandrel(self):
        """Guards the 0.5mm floor in calculate_paths: a ring hugging the mandrel would
        read as 'the sheet edge is here' when there is no loose sheet at all."""
        with open("path_generator.py", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("_fr_e > 0.5", src, "exhausted-flange guard is gone")


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


class TestRingsAreDrawnCheaply(unittest.TestCase):
    """The 3D layer builds the rings by hand instead of pv.Circle + a VTK filter.

    The filter version cost ~4.4 ms PER RING on every redraw of the 3D view — 240 ms
    for a 60-pass program (measured 2026-09-03). These tests pin the fast path AND
    prove it draws the identical picture, so nobody "simplifies" it back.
    """

    EDGES = [(10.0 + 5.0 * k, 100.0 - 1.5 * k) for k in range(20)]   # (z, r)
    CX = 7.5

    @classmethod
    def setUpClass(cls):
        import pyvista as pv
        pv.OFF_SCREEN = True
        import main
        cls.pv = pv
        cls.COS = main.SpinningApp._RING_COS
        cls.SIN = main.SpinningApp._RING_SIN

    def _new(self, edges):
        """Same construction as main.update_blank_edge."""
        n = len(self.COS)
        pts, lines, off = [], [], 0
        for z, r in edges:
            if r <= 0.1:
                continue
            pts.append(np.column_stack((self.CX + r * self.COS, r * self.SIN,
                                        np.full(n, float(z)))))
            lines.append(np.concatenate(([n + 1], np.arange(off, off + n), (off,))))
            off += n
        if not pts:
            return None
        return self.pv.PolyData(np.vstack(pts).astype(float),
                                lines=np.concatenate(lines).astype(np.int64))

    def _old(self, edges):
        """The pv.Circle + extract_feature_edges version this replaced."""
        rings = [self.pv.Circle(radius=float(r), resolution=len(self.COS))
                 .translate((self.CX, 0.0, float(z)), inplace=False)
                 .extract_feature_edges(boundary_edges=True, feature_edges=False,
                                        manifold_edges=False, non_manifold_edges=False)
                 for z, r in edges if r > 0.1]
        return rings[0].merge(rings[1:]) if len(rings) > 1 else rings[0]

    def test_same_points_as_the_filter_version(self):
        a, b = self._old(self.EDGES), self._new(self.EDGES)
        self.assertEqual(a.n_points, b.n_points)
        sa = np.array(sorted(map(tuple, np.round(a.points, 6))))
        sb = np.array(sorted(map(tuple, np.round(b.points, 6))))
        self.assertTrue(np.allclose(sa, sb, atol=1e-6),
                        "fast rings moved: the picture changed")

    def test_every_ring_is_a_closed_loop(self):
        n = len(self.COS)
        mesh = self._new(self.EDGES)
        self.assertEqual(mesh.n_cells, len(self.EDGES))
        for c in range(mesh.n_cells):
            ids = mesh.get_cell(c).point_ids
            self.assertEqual(len(ids), n + 1)
            self.assertEqual(ids[0], ids[-1], f"ring {c} is not closed")

    def test_used_up_flange_draws_nothing(self):
        self.assertEqual(self._new([(0.0, 0.05), (10.0, 50.0)]).n_cells, 1)
        self.assertIsNone(self._new([(0.0, 0.05)]))

    def test_the_filter_is_gone_from_the_overlay(self):
        with open("main.py", encoding="utf-8") as f:
            src = f.read()
        block = src.split("def update_blank_edge", 1)[1].split("\n    def ", 1)[0]
        block = block.split('"""', 2)[2]        # skip the docstring, which NAMES them
        self.assertNotIn("extract_feature_edges", block,
                         "the slow VTK filter is back in the blank-edge overlay")
        self.assertNotIn("pv.Circle", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
