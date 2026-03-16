
import numpy as np
import math
from logger_config import logger
from path_generator import PathGenerator

# Mock MandrelManager
class MockMandrelManager:
    def __init__(self):
        self.props = {"top_z": 100.0}
    def get_radius_fast(self, z):
        return 50.0 # Return scalar
    def get_normal_at_z(self, z):
        return 0.707, 0.707

def test_pg():
    print("Initializing PG...")
    pg = PathGenerator()
    params = {
        "num_sweeping_passes": 2,
        "mandrel_pos_x_offset": 0.0,
        "final_part_thickness_on_mandrel": 1.0,
        "shell_thickness": 0.0,
        "last_pass_extension_z": 0.0,
        "auto_align_rotation": False,
        "roller_visual_radius": 25.0,
        "tool_change_active": True,
        "finish_tool_radius": 5.0,
        "safety_clearance_roller_to_part": 2.0,
        "p1_p3_x_offset_from_p2": 10.0,
        "p1_z_offset_from_p2": 10.0,
        "p3_z_offset_from_p2": 10.0,
        "roughing_step_radial": 5.0,
        "y_rotation_degrees": 0.0,
        "first_pass_p2_contact_z_abs": 10.0
    }
    
    overrides = {}
    mandrel_mgr = MockMandrelManager()
    
    print("Calculating...")
    paths, projs, cps = pg.calculate_paths(params, overrides, mandrel_mgr)
    
    print(f"Num Paths: {len(paths)}")
    print(f"Num Projs: {len(projs)}")
    
    for i, pr in enumerate(projs):
        print(f"Proj {i} type: {type(pr)}")
        if isinstance(pr, np.ndarray):
            print(f"Proj {i} shape: {pr.shape}")
            print(f"Proj {i} dtype: {pr.dtype}")
            if pr.size > 0:
                 print(f"Proj {i} first point: {pr[0]}")
        else:
            print(f"Proj {i} content: {pr}")

if __name__ == "__main__":
    test_pg()
