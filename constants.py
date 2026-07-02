"""
Constants module for SpinningCam.
Provides type-safe constants for parameter keys, eliminating magic strings.

Usage:
    from constants import ParamKeys
    value = params.get(ParamKeys.BLANK_RADIUS, 500.0)
"""



class ParamKeys:
    """
    Constants for parameter dictionary keys.
    All values match the exact strings used in settings.json - DO NOT CHANGE VALUES.
    This class is purely for IDE autocomplete and preventing typos.
    """
    
    # === Sweeping / Roughing ===
    NUM_SWEEPING_PASSES = "num_sweeping_passes"
    FIRST_PASS_P2_CONTACT_Z_ABS = "first_pass_p2_contact_z_abs"
    Y_ROTATION_DEGREES = "y_rotation_degrees"
    AUTO_ALIGN_ROTATION = "auto_align_rotation"
    
    # === Calculation ===
    CALC_ACTIVE = "calc_active"
    
    # === Camera ===
    CAM_AZIMUTH = "cam_azimuth"
    CAM_ELEVATION = "cam_elevation"
    CAM_ROLL = "cam_roll"
    CAMERA = "camera"  # Camera dict with pos/foc/up
    SAVED_CAMERA_POS = "saved_camera_pos"
    
    # === Mandrel Geometry ===
    MANDREL_ROT_X = "mandrel_rot_x"
    MANDREL_ROT_Y = "mandrel_rot_y"
    MANDREL_ROT_Z = "mandrel_rot_z"
    MANDREL_POS_X_OFFSET = "mandrel_pos_x_offset"
    MANDREL_POS_Z_OFFSET = "mandrel_pos_z_offset"
    
    # === Spline Control Points ===
    P1_P3_X_OFFSET_FROM_P2 = "p1_p3_x_offset_from_p2"
    P1_Z_OFFSET_FROM_P2 = "p1_z_offset_from_p2"
    P3_Z_OFFSET_FROM_P2 = "p3_z_offset_from_p2"
    ROUGHING_STEP_RADIAL = "roughing_step_radial"
    # === Roller ===
    ROLLER_VISUAL_RADIUS = "roller_visual_radius"
    
    # === Part Geometry ===
    FINAL_PART_THICKNESS_ON_MANDREL = "final_part_thickness_on_mandrel"
    SAFETY_CLEARANCE_ROLLER_TO_PART = "safety_clearance_roller_to_part"
    MIN_SAFETY_GAP = "min_safety_gap"  # one-way collision floor (replaces target_clearance setter)
    SHELL_THICKNESS = "shell_thickness"
    BLANK_RADIUS = "blank_radius"
    BLANK_Z_SHIFT = "blank_z_shift"
    
    # === UI State ===
    SHOW_ADVANCED_SLIDERS = "show_advanced_sliders"
    SHOW_VISUAL_SLIDERS = "show_visual_sliders"
    LAST_SCROLL_VAL = "last_scroll_val"
    SHOW_HEATMAP = "show_heatmap"
    AUTO_CALC_ANGLE = "auto_calc_angle"
    
    # === Machine Settings (Post-Processor) ===
    MACHINE_ORIGIN_X = "machine_origin_x"  # Machine origin X in global coords
    MACHINE_ORIGIN_Z = "machine_origin_z"  # Machine origin Z in global coords
    MACHINE_INVERT_X = "machine_invert_x"  # Invert X axis direction
    MACHINE_INVERT_Z = "machine_invert_z"  # Invert Z axis direction
    MACHINE_OUTPUT_DIAMETER_MODE = "machine_output_diameter_mode"
    MACHINE_GCODE_OFFSET_X = "machine_gcode_offset_x"  # Additional G54 offset
    MACHINE_GCODE_OFFSET_Z = "machine_gcode_offset_z"  # Additional G54 offset
    
    # === G-Code ===
    GCODE_HEADER = "gcode_header"
    GCODE_FOOTER = "gcode_footer"
    
    # === Finishing Pass ===
    FINISH_P1_P3_X_OFFSET_FROM_P2 = "finish_p1_p3_x_offset_from_p2"
    FINISH_P1_Z_OFFSET_FROM_P2 = "finish_p1_z_offset_from_p2"
    FINISH_P3_Z_OFFSET_FROM_P2 = "finish_p3_z_offset_from_p2"
    FINISH_Y_ROTATION_DEGREES = "finish_y_rotation_degrees"
    FINISH_STEP_RADIAL = "finish_step_radial"
    # === Operations (List of dicts) ===
    OPERATIONS = "operations"
    
    # === Safety/Home/Retract ===
    HOME_Z = "home_z"
    HOME_X = "home_x"
    RETRACT_X = "retract_x"
    RETRACT_Z = "retract_z"


class OpKeys:
    """
    Constants for operation dictionary keys (items in "operations" list).
    """
    TYPE = "type"
    ENABLED = "enabled"
    COUNT = "count"
    TOOL_ID = "tool_id"
    R_TOOL = "r_tool"
    START_Z = "start_z"
    P1_X = "p1_x"
    P1_Z = "p1_z"
    P3_Z = "p3_z"
    ROT = "rot"
    STEP = "step"
    CLEARANCE = "clearance"  # unified roller-to-blank gap (per op); replaces finish_allowance


class OpTypes:
    """
    Constants for operation type values.
    """
    ROUGHING = "roughing"
    FINISHING = "finishing"
    SWEEPING = "sweeping"
