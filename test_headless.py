
import sys
import os
import json
import numpy as np

# Ensure the current directory is in the path
sys.path.append(os.getcwd())

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

def test_headless_execution():
    print("--- Starting Headless Test ---")
    
    # 1. Initialize Managers
    try:
        mandrel_mgr = MandrelManager()
        path_gen = PathGenerator()
        print("[OK] Managers initialized.")
    except Exception as e:
        print(f"[FAIL] Initialization failed: {e}")
        return

    # 2. Create Default Mandrel (Cone)
    # Since we might not have a STEP file, we use the internal default cone generator
    try:
        mandrel_mgr.create_default_cone()
        mandrel_mgr.update_geometry(0,0,0, 0,0)
        print("[OK] Default cone created and updated.")
    except Exception as e:
        print(f"[FAIL] Geometry creation failed: {e}")
        return

    # 3. Load Default Parameters
    # We'll mock the params dictionary usually loaded from settings.json
    params = {
        "num_sweeping_passes": 5,
        "first_pass_p2_contact_z_abs": 10.0, 
        "y_rotation_degrees": 10.0,
        "auto_align_rotation": False,
        "mandrel_pos_x_offset": 0.0, 
        "p1_p3_x_offset_from_p2": 40.0, 
        "p1_z_offset_from_p2": 50.0, 
        "p3_z_offset_from_p2": -20.0,
        "roughing_step_radial": 1.0,
        "last_pass_extension_z": 0.0,
        "roller_nose_radius_param": 10.0, 
        "final_part_thickness_on_mandrel": 2.0, 
        "safety_clearance_roller_to_part": 0.5,
        "shell_thickness": 2.0,
        "roller_visual_radius": 25.0
    }
    
    gui_pass_overrides = {}

    # 4. Generate Paths
    try:
        paths, projs, cps, devs, rapids, debug_lines = path_gen.calculate_paths(params, gui_pass_overrides, mandrel_mgr)
        print(f"[OK] Path calculation completed. {len(paths)} paths generated.")
    except Exception as e:
        print(f"[FAIL] Path calculation crashed: {e}")
        # Print traceback for debugging
        import traceback
        traceback.print_exc()
        return

    # 5. Verify Results
    if len(paths) == params["num_sweeping_passes"]:
        print("[PASS] Number of paths matches request.")
    else:
        print(f"[FAIL] Expected {params['num_sweeping_passes']} paths, got {len(paths)}")

    # Check if paths have points
    total_points = sum(len(p) for p in paths)
    print(f"Total points generated: {total_points}")
    if total_points > 0:
        print("[PASS] Paths contain data points.")
    else:
        print("[FAIL] Paths are empty.")
    
    # 6. Generate G-Code (Dry Run)
    try:
        gcode = path_gen.generate_gcode(params=params)
        if len(gcode) > 100 and "%" in gcode:
             print("[PASS] G-Code generation successful.")
        else:
             print(f"[FAIL] G-Code generation suspiciously short or invalid. Length: {len(gcode)}")
    except Exception as e:
        print(f"[FAIL] G-Code generation failed: {e}")

    print("--- Test Completed ---")

if __name__ == "__main__":
    test_headless_execution()
