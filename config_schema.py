"""
Configuration schema validation for SpinningCam.
Uses pydantic for type-safe validation of settings.json and tools.json.
"""
from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator
import json


class ToolSchema(BaseModel):
    """Schema for individual tool entries in tools.json."""
    id: str = Field(..., description="Tool ID like T0101")
    name: str = Field(..., description="Tool display name")
    radius: float = Field(..., ge=0, description="Tool radius in mm")
    type: str = Field(default="roller", description="Tool type")
    color: Optional[str] = Field(default="red", description="Display color")


class OperationSchema(BaseModel):
    """Schema for individual operation entries."""
    type: str = Field(..., description="Operation type: roughing, finishing, sweeping")
    enabled: bool = Field(default=True)
    count: int = Field(default=1, ge=1)
    tool_id: str = Field(default="T0101")
    r_tool: float = Field(default=25.0, ge=0)
    start_z: float = Field(default=10.0)
    p1_x: Optional[float] = None
    p1_z: Optional[float] = None
    p3_z: Optional[float] = None
    rot: Optional[float] = None
    step: Optional[float] = None
    clearance: Optional[float] = None  # unified roller-to-blank gap (mm)
    zones: Optional[List[dict]] = None


class CameraSchema(BaseModel):
    """Schema for camera position data."""
    pos: List[float] = Field(..., min_length=3, max_length=3)
    foc: List[float] = Field(..., min_length=3, max_length=3)
    up: List[float] = Field(..., min_length=3, max_length=3)


class SettingsSchema(BaseModel):
    """
    Schema for settings.json validation.
    All fields are optional with defaults to support partial configs.
    """
    # Core params
    num_sweeping_passes: Optional[float] = None
    first_pass_p2_contact_z_abs: Optional[float] = None
    y_rotation_degrees: Optional[float] = None
    
    # Geometry
    blank_radius: Optional[float] = Field(default=500.0, ge=0)
    shell_thickness: Optional[float] = Field(default=0.0, ge=0)
    final_part_thickness_on_mandrel: Optional[float] = Field(default=2.0, ge=0)
    min_safety_gap: Optional[float] = Field(default=0.0, ge=0)  # one-way collision floor
    target_clearance: Optional[float] = None  # legacy (pre-unification); migrated to min_safety_gap
    
    # Mandrel
    mandrel_rot_x: Optional[float] = None
    mandrel_rot_y: Optional[float] = None
    mandrel_rot_z: Optional[float] = None
    mandrel_pos_x_offset: Optional[float] = None
    mandrel_pos_z_offset: Optional[float] = None
    
    # Roller
    roller_visual_radius: Optional[float] = Field(default=25.0, ge=0)
    
    # Machine
    machine_gcode_offset_x: Optional[float] = None
    machine_gcode_offset_z: Optional[float] = None
    home_x: Optional[float] = None
    home_z: Optional[float] = None
    retract_x: Optional[float] = None
    retract_z: Optional[float] = None
    
    # G-Code
    gcode_header: Optional[str] = None
    gcode_footer: Optional[str] = None
    
    # Operations list
    operations: Optional[List[OperationSchema]] = None
    
    # Camera
    camera: Optional[CameraSchema] = None
    saved_camera_pos: Optional[List[List[float]]] = None
    
    class Config:
        extra = "allow"  # Allow unknown fields for forward compatibility


class MachineProfileSchema(BaseModel):
    """Schema for machine profile files in machines/*.json."""
    machine_id: str
    machine_name: str
    kinematics: Optional[str] = None  # "xz" (default) | "tilt_arm" (ID112)
    tilt_pivot_x: Optional[float] = None   # tilt-arm machines only (kinematics.py)
    tilt_pivot_z: Optional[float] = None
    tilt_b_min: Optional[float] = None
    tilt_b_max: Optional[float] = None
    tilt_b_home: Optional[float] = None
    tilt_b_sign: Optional[float] = None
    machine_origin_x: Optional[float] = None
    machine_origin_z: Optional[float] = None
    machine_invert_x: Optional[Any] = None
    machine_invert_z: Optional[Any] = None
    machine_gcode_offset_x: Optional[float] = None
    machine_gcode_offset_z: Optional[float] = None
    output_mode: Optional[str] = None
    origin_use_home: Optional[Any] = None
    home_x: Optional[float] = None
    home_z: Optional[float] = None
    retract_x: Optional[float] = None
    retract_z: Optional[float] = None
    roller_positive_x_side: Optional[Any] = None
    workspace_show: Optional[Any] = None
    workspace_x_min: Optional[float] = None
    workspace_x_max: Optional[float] = None
    workspace_z_min: Optional[float] = None
    workspace_z_max: Optional[float] = None
    cylinder_enabled: Optional[Any] = None
    cylinder_show: Optional[Any] = None
    cylinder_position_mm: Optional[float] = None
    cylinder_x_pos: Optional[float] = None
    cylinder_z_base: Optional[float] = None
    plc_mode: Optional[Any] = None
    plc_tolerance: Optional[float] = None
    plc_exit_tolerance: Optional[float] = None
    gcode_resolution: Optional[float] = None
    gcode_header: Optional[str] = None
    gcode_footer: Optional[str] = None
    max_spin_rpm: Optional[float] = None
    custom_commands: Optional[List[dict]] = None
    mcode_descriptions: Optional[dict] = None
    calibration_view: Optional[dict] = None

    class Config:
        extra = "allow"


def validate_machine_profile(data: dict) -> tuple[bool, str]:
    try:
        MachineProfileSchema(**data)
        return True, "Machine profile validated successfully."
    except Exception as e:
        return False, f"Machine profile validation error: {str(e)}"


def migrate_clearance(params: dict) -> dict:
    """Upgrade a pre-unification recipe to the unified `clearance` model, in place.

    Before unification the roller-to-blank gap came from different knobs per pass type:
      - roughing  : target_clearance (its correction loop forced the contact there)
      - finishing : finish_allowance + safety_clearance_roller_to_part
    Now every operation carries one `clearance`, and `min_safety_gap` is the one-way
    collision floor (formerly target_clearance). Idempotent — only fills missing keys.
    """
    if not isinstance(params, dict):
        return params
    if "min_safety_gap" not in params:
        params["min_safety_gap"] = float(params.get("target_clearance") or 0.0)
    safety = float(params.get("safety_clearance_roller_to_part") or 0.0)
    target = float(params.get("target_clearance") or 0.0)
    for op in (params.get("operations") or []):
        if isinstance(op, dict) and "clearance" not in op:
            if op.get("type") == "finishing":
                op["clearance"] = float(op.get("finish_allowance") or 0.0) + safety
            else:
                op["clearance"] = target
    return params


def validate_settings(data: dict) -> tuple[bool, str]:
    """
    Validate settings.json data.
    
    Args:
        data: Dictionary loaded from settings.json
        
    Returns:
        (success: bool, message: str)
    """
    try:
        SettingsSchema(**data)
        return True, "Settings validated successfully."
    except Exception as e:
        return False, f"Settings validation error: {str(e)}"


def validate_tools(data: list) -> tuple[bool, str]:
    """
    Validate tools.json data.
    
    Args:
        data: List of tool dictionaries loaded from tools.json
        
    Returns:
        (success: bool, message: str)
    """
    try:
        if not isinstance(data, list):
            return False, "Tools data must be a list."
        
        for i, tool in enumerate(data):
            try:
                ToolSchema(**tool)
            except Exception as e:
                return False, f"Tool #{i+1} validation error: {str(e)}"
        
        return True, f"Validated {len(data)} tools successfully."
    except Exception as e:
        return False, f"Tools validation error: {str(e)}"


def validate_settings_file(filepath: str) -> tuple[bool, str]:
    """Load and validate a settings.json file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return validate_settings(data)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in settings file: {e}"
    except FileNotFoundError:
        return False, f"Settings file not found: {filepath}"
    except Exception as e:
        return False, f"Error reading settings file: {e}"


def validate_tools_file(filepath: str) -> tuple[bool, str]:
    """Load and validate a tools.json file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return validate_tools(data)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in tools file: {e}"
    except FileNotFoundError:
        return False, f"Tools file not found: {filepath}"
    except Exception as e:
        return False, f"Error reading tools file: {e}"
