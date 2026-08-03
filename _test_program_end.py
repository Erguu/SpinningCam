"""Program End park point — resolver, emitter and simulation.

The point of these checks is that the DEFAULT stays exactly as it was: the final
move has always gone to Program Start, so a recipe that never touches the new
fields must produce the same motion it did before.
"""
import os
import sys
import unittest

import numpy as np

sys.path.append(os.getcwd())

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator, resolve_program_end


def base_params(**over):
    p = {
        "num_sweeping_passes": 2,
        "first_pass_p2_contact_z_abs": 30.0,
        "y_rotation_degrees": 10.0,
        "auto_align_rotation": False,
        "mandrel_pos_x_offset": 0.0,
        "final_part_thickness_on_mandrel": 2.0,
        "safety_clearance_roller_to_part": 0.5,
        "shell_thickness": 0.0,
        "roller_visual_radius": 25.0,
        "gcode_header": "G21 G90\nG54",
        "gcode_footer": "M5\nM30",
        "machine_invert_x": False,
        "machine_output_diameter_mode": False,
        "machine_gcode_offset_x": 0.0,
        "machine_gcode_offset_z": 0.0,
        "home_x": 300.0,
        "home_z": 150.0,
    }
    p.update(over)
    return p


def final_moves(gcode):
    """The two G0 lines of the closing park move, as (Z line, X line)."""
    lines = [l.strip() for l in gcode.splitlines()]
    i = lines.index("(--- PROGRAM SONU GUVENLI DONUS ---)")
    return lines[i + 1], lines[i + 2]


class TestResolver(unittest.TestCase):
    def test_defaults_to_program_start(self):
        self.assertEqual(resolve_program_end(base_params()), (300.0, 150.0))

    def test_absent_flag_defaults_to_program_start(self):
        p = base_params()
        p.pop("end_use_home", None)
        p["end_x"], p["end_z"] = 999.0, 999.0   # present but must be ignored
        self.assertEqual(resolve_program_end(p), (300.0, 150.0))

    def test_park_point_used_when_enabled(self):
        p = base_params(end_use_home=False, end_x=420.0, end_z=-30.0)
        self.assertEqual(resolve_program_end(p), (420.0, -30.0))

    def test_blank_field_falls_back_per_axis(self):
        p = base_params(end_use_home=False, end_x=420.0, end_z=None)
        self.assertEqual(resolve_program_end(p), (420.0, 150.0))
        p = base_params(end_use_home=False, end_x="", end_z="")
        self.assertEqual(resolve_program_end(p), (300.0, 150.0))

    def test_garbage_does_not_raise(self):
        p = base_params(end_use_home=False, end_x="abc", end_z=[1])
        self.assertEqual(resolve_program_end(p), (300.0, 150.0))


class TestEmitter(unittest.TestCase):
    def setUp(self):
        self.mgr = MandrelManager()
        self.pg = PathGenerator()
        self.mgr.create_default_cone()
        self.mgr.update_geometry(0, 0, 0, 0, 0)

    def _gcode(self, params):
        self.pg.calculate_paths(params, {}, self.mgr)
        return self.pg.generate_gcode(params=params)

    def test_default_end_matches_program_start(self):
        g = self._gcode(base_params())
        self.assertEqual(final_moves(g), ("G0 Z150.000", "G0 X300.000"))

    def test_motion_unchanged_when_flag_untouched(self):
        """Old recipe vs. same recipe carrying the new keys in default state."""
        a = self._gcode(base_params())
        b = self._gcode(base_params(end_use_home=True, end_x=42.0, end_z=42.0))
        strip = lambda s: [l for l in s.splitlines() if not l.startswith("(")]
        self.assertEqual(strip(a), strip(b))

    def test_park_point_emitted(self):
        g = self._gcode(base_params(end_use_home=False, end_x=420.0, end_z=-30.0))
        self.assertEqual(final_moves(g), ("G0 Z-30.000", "G0 X420.000"))

    def test_park_point_goes_through_post_processor(self):
        """The whole reason this is a parameter and not a footer line."""
        g = self._gcode(base_params(
            end_use_home=False, end_x=420.0, end_z=-30.0,
            machine_invert_x=True, machine_gcode_offset_x=5.0,
            machine_output_diameter_mode=True))
        # x = ((420 - 0) * -1 + 5) * 2
        self.assertEqual(final_moves(g), ("G0 Z-30.000", "G0 X-830.000"))

    def test_header_records_the_park_point(self):
        g = self._gcode(base_params(end_use_home=False, end_x=420.0, end_z=-30.0))
        self.assertIn("(Program End: X=420, Z=-30) (park position)", g)
        g = self._gcode(base_params())
        self.assertIn("(Program End: X=300, Z=150)", g)

    def test_footer_still_emitted_verbatim_after_park(self):
        g = self._gcode(base_params(end_use_home=False, end_x=420.0, end_z=-30.0))
        tail = [l for l in g.strip().splitlines()[-3:]]
        self.assertEqual(tail, ["M5", "M30", "%"])


class TestSimulation(unittest.TestCase):
    def setUp(self):
        self.mgr = MandrelManager()
        self.pg = PathGenerator()
        self.mgr.create_default_cone()
        self.mgr.update_geometry(0, 0, 0, 0, 0)

    def _last_rapid_end(self, params):
        _, _, _, _, rapids, _ = self.pg.calculate_paths(params, {}, self.mgr)
        return np.asarray(rapids[-1])[-1]

    def test_sim_parks_at_program_start_by_default(self):
        end = self._last_rapid_end(base_params())
        self.assertAlmostEqual(end[0], 300.0, places=3)
        self.assertAlmostEqual(end[2], 150.0, places=3)

    def test_sim_parks_at_park_point(self):
        end = self._last_rapid_end(
            base_params(end_use_home=False, end_x=420.0, end_z=-30.0))
        self.assertAlmostEqual(end[0], 420.0, places=3)
        self.assertAlmostEqual(end[2], -30.0, places=3)

    def test_sim_mirrors_park_point_on_negative_side(self):
        """Negative-X machines build canonically then mirror — the park point
        must ride along, exactly like the home point always has."""
        p = base_params(end_use_home=False, end_x=420.0, end_z=-30.0,
                        roller_positive_x_side=False)
        end = self._last_rapid_end(p)
        self.assertAlmostEqual(end[0], -420.0, places=3)
        self.assertAlmostEqual(end[2], -30.0, places=3)

    def test_sim_and_gcode_agree(self):
        """The failure mode this whole design avoids: sim showing one park
        position while the .nc drives to another."""
        p = base_params(end_use_home=False, end_x=420.0, end_z=-30.0)
        end = self._last_rapid_end(p)
        zl, xl = final_moves(self.pg.generate_gcode(params=p))
        self.assertAlmostEqual(end[0], float(xl.split("X")[1]), places=3)
        self.assertAlmostEqual(end[2], float(zl.split("Z")[1]), places=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
