
import sys
import os
import unittest
import math
import numpy as np

# Add project root to path
sys.path.append(os.getcwd())

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from OCC.Core.gp import gp_Pnt

class TestGeometry(unittest.TestCase):
    def setUp(self):
        # Setup a simple cone: Base Radius 60, Top Radius 10, Height 100
        # By default MandrelManager initializes with this exact profile
        self.mgr = MandrelManager()
        # Explicitly set for clarity in text
        self.mgr.profile_z = np.array([0.0, 100.0])
        self.mgr.profile_r = np.array([60.0, 10.0])
        self.mgr.scan_resolution = 1.0
        
        self.pg = PathGenerator()

    def test_mandrel_radius_interpolation(self):
        """Test radius calculation within the mandrel bounds"""
        # Middle of the cone (Z=50 should have R=35)
        # linear interpolation between (0, 60) and (100, 10)
        r_mid = self.mgr.get_radius_fast(50.0)
        self.assertAlmostEqual(r_mid, 35.0, places=3)

    def test_mandrel_radius_extrapolation_bottom(self):
        """Test radius extrapolation below the mandrel start"""
        # Below Z=0. Slope is (10-60)/(100-0) = -0.5
        # At Z=-10: 60 + (-0.5 * (-10 - 0)) -> 60 + 5 = 65
        r_bottom = self.mgr.get_radius_fast(-10.0)
        self.assertAlmostEqual(r_bottom, 65.0, places=3)

    def test_mandrel_radius_extrapolation_top(self):
        """Test radius extrapolation above the mandrel top"""
        # Above Z=100.
        # At Z=110: 10 + (-0.5 * (110 - 100)) -> 10 - 5 = 5
        r_top = self.mgr.get_radius_fast(110.0)
        self.assertAlmostEqual(r_top, 5.0, places=3)

    def test_normal_vector_direction(self):
        """Test if normal vector components have correct signs for a cone"""
        # For a cone narrowing upwards (dr/dz < 0), the surface normal pointing outwards
        # should have a positive X component (out from axis) and positive Z component (upwards)
        nx, nz = self.mgr.get_normal_at_z(50.0)
        
        self.assertGreater(nx, 0, "Normal X component should be positive (outwards)")
        self.assertGreater(nz, 0, "Normal Z component should be positive (since radius decreases going up)")
        
        # Check normalization
        length = math.sqrt(nx*nx + nz*nz)
        self.assertAlmostEqual(length, 1.0, places=5)

    def test_spline_generation(self):
        """Test OCC spline generation wrapper"""
        p1 = gp_Pnt(0, 0, 0)
        p2 = gp_Pnt(50, 0, 50)
        p3 = gp_Pnt(100, 0, 100)
        
        points = self.pg._generate_spline(p1, p2, p3)
        
        # Should return a numpy array
        self.assertTrue(isinstance(points, np.ndarray))
        # Should have points
        self.assertGreater(len(points), 0)
        # Should have 3 coordinates (x,y,z)
        self.assertEqual(points.shape[1], 3) 

if __name__ == '__main__':
    unittest.main()
