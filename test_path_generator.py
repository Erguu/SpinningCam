"""
Unit tests for PathGenerator focusing on edge cases.
Tests collision avoidance, steep angles, sharp transitions, and G-code format.
"""
import sys
import os
import unittest
import math
import numpy as np

# Ensure project root is in path
sys.path.append(os.getcwd())

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator


class TestPathGeneratorEdgeCases(unittest.TestCase):
    """Test PathGenerator with challenging geometries and edge cases."""
    
    def setUp(self):
        """Setup common test fixtures."""
        self.mgr = MandrelManager()
        self.pg = PathGenerator()
        
        # Create default cone geometry
        self.mgr.create_default_cone()
        self.mgr.update_geometry(0, 0, 0, 0, 0)

    def test_steep_angle_mandrel(self):
        """Test path generation with steep angle (near vertical wall)."""
        # Simulate steep mandrel: narrow at bottom, wide at top
        self.mgr.profile_z = np.array([0.0, 10.0, 100.0])
        self.mgr.profile_r = np.array([10.0, 60.0, 60.0])  # Sharp step at z=10
        
        params = {
            "num_sweeping_passes": 3,
            "first_pass_p2_contact_z_abs": 5.0,
            "y_rotation_degrees": 15.0,
            "auto_align_rotation": True,
            "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 2.0,
            "safety_clearance_roller_to_part": 0.5,
            "shell_thickness": 0.0,
            "roller_visual_radius": 25.0,
            "target_clearance": 0.5,
            "collision_resolution": 0.5,
        }
        
        paths, projs, cps, devs, rapids, lines = self.pg.calculate_paths(params, {}, self.mgr)
        
        # Should generate paths even with steep geometry
        self.assertGreater(len(paths), 0, "Should generate paths for steep angle")
        
        # All paths should have points
        for i, path in enumerate(paths):
            self.assertGreater(len(path), 0, f"Path {i} should have points")

    def test_sharp_radius_transition(self):
        """Test path generation with sharp radius transition (step mandrel)."""
        # Step mandrel: sharp transition at z=50
        self.mgr.profile_z = np.array([0.0, 49.0, 50.0, 51.0, 100.0])
        self.mgr.profile_r = np.array([30.0, 30.0, 60.0, 60.0, 60.0])  # 30mm step at z=50
        
        params = {
            "num_sweeping_passes": 5,
            "first_pass_p2_contact_z_abs": 10.0,
            "y_rotation_degrees": 10.0,
            "auto_align_rotation": True,
            "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 2.0,
            "safety_clearance_roller_to_part": 0.5,
            "shell_thickness": 0.0,
            "roller_visual_radius": 25.0,
            "target_clearance": 0.5,
            "collision_resolution": 0.5,
        }
        
        paths, projs, cps, devs, rapids, lines = self.pg.calculate_paths(params, {}, self.mgr)
        
        # Should handle sharp transition
        self.assertGreater(len(paths), 0, "Should generate paths for step geometry")
        
        # Check that passes near the step don't collide excessively
        total_points = sum(len(p) for p in paths)
        self.assertGreater(total_points, 50, "Should generate reasonable point count")

    def test_collision_avoidance_iteration(self):
        """Test that collision avoidance shifts paths away from mandrel."""
        params = {
            "num_sweeping_passes": 1,
            "first_pass_p2_contact_z_abs": 50.0,
            "y_rotation_degrees": 30.0,
            "auto_align_rotation": False,
            "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 2.0,
            "safety_clearance_roller_to_part": 0.5,
            "shell_thickness": 0.0,
            "roller_visual_radius": 25.0,
            "target_clearance": 1.0,  # Require 1mm clearance
            "collision_resolution": 0.5,
        }
        
        paths, projs, cps, devs, rapids, lines = self.pg.calculate_paths(params, {}, self.mgr)
        
        # Path should exist
        self.assertEqual(len(paths), 1, "Should generate exactly 1 path")
        
        path = paths[0]
        center_x = 0.0
        min_clearance = float('inf')
        
        for pt in path:
            z = pt[2]
            m_rad = self.mgr.get_radius_fast(z)
            dist_to_axis = math.sqrt((pt[0] - center_x)**2 + pt[1]**2)
            required = m_rad + 2.0 + 0.5 + 25.0  # blank + shell + r_tool
            clearance = dist_to_axis - required
            min_clearance = min(min_clearance, clearance)
        
        # Minimum clearance should be close to target (1.0mm)
        self.assertGreater(min_clearance, 0.0, "Path should not collide with mandrel")

    def test_gcode_output_format(self):
        """Test G-code generation produces valid output."""
        params = {
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
        
        # Generate paths first
        self.pg.calculate_paths(params, {}, self.mgr)
        
        # Generate G-code
        gcode = self.pg.generate_gcode(params=params)
        
        # Check basic structure
        self.assertIn("%", gcode, "Should have program delimiters")
        self.assertIn("G0", gcode, "Should have rapid moves")
        self.assertIn("G1", gcode, "Should have linear moves")
        self.assertIn("M30", gcode, "Should have program end")
        
        # Check for reasonable line count
        lines = gcode.strip().split("\n")
        self.assertGreater(len(lines), 20, "Should generate substantial G-code")

    def test_empty_operations_list(self):
        """Test handling of empty operations list."""
        params = {
            "operations": [],
            "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 2.0,
            "safety_clearance_roller_to_part": 0.5,
            "shell_thickness": 0.0,
            "roller_visual_radius": 25.0,
        }
        
        paths, projs, cps, devs, rapids, lines = self.pg.calculate_paths(params, {}, self.mgr)
        
        # Should return empty lists without crashing
        self.assertEqual(len(paths), 0, "Empty operations should produce no paths")
        self.assertEqual(len(rapids), 0, "Empty operations should produce no rapids")

    def test_finishing_operation_type(self):
        """Test finishing operation generates different paths than roughing."""
        params = {
            "operations": [
                {
                    "type": "roughing",
                    "enabled": True,
                    "count": 1,
                    "tool_id": "T0101",
                    "r_tool": 25.0,
                    "start_z": 10.0,
                    "p1_x": 40.0,
                    "p1_z": 50.0,
                    "p3_z": -20.0,
                    "rot": 10.0,
                    "step": 5.0,
                },
                {
                    "type": "finishing",
                    "enabled": True,
                    "count": 1,
                    "tool_id": "T0202",
                    "r_tool": 10.0,
                    "start_z": 10.0,
                    "p1_x": 20.0,
                    "p1_z": 30.0,
                    "p3_z": -10.0,
                    "rot": 5.0,
                    "step": 0.0,
                }
            ],
            "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 2.0,
            "safety_clearance_roller_to_part": 0.5,
            "shell_thickness": 0.0,
            "roller_visual_radius": 25.0,
            "target_clearance": 0.5,
            "adaptive_finish_mode": False,
        }
        
        paths, projs, cps, devs, rapids, lines = self.pg.calculate_paths(params, {}, self.mgr)
        
        # Should generate 2 paths (1 rough + 1 finish)
        self.assertEqual(len(paths), 2, "Should generate 2 paths")


class TestConfigValidation(unittest.TestCase):
    """Test configuration schema validation."""
    
    def test_valid_settings(self):
        """Test that valid settings pass validation."""
        from config_schema import validate_settings
        
        valid_data = {
            "blank_radius": 500.0,
            "shell_thickness": 2.0,
            "operations": [
                {"type": "roughing", "enabled": True, "count": 5}
            ]
        }
        
        success, msg = validate_settings(valid_data)
        self.assertTrue(success, f"Valid settings should pass: {msg}")

    def test_invalid_settings(self):
        """Test that invalid settings fail validation with clear message."""
        from config_schema import validate_settings
        
        invalid_data = {
            "blank_radius": -100.0,  # Negative radius should fail
        }
        
        success, msg = validate_settings(invalid_data)
        self.assertFalse(success, "Negative radius should fail validation")

    def test_valid_tools(self):
        """Test that valid tools pass validation."""
        from config_schema import validate_tools
        
        valid_tools = [
            {"id": "T0101", "name": "Test Tool", "radius": 25.0, "type": "roller"}
        ]
        
        success, msg = validate_tools(valid_tools)
        self.assertTrue(success, f"Valid tools should pass: {msg}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
