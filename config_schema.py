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
    
    # Mandrel
    mandrel_rot_x: Optional[float] = None
    mandrel_rot_y: Optional[float] = None
    mandrel_rot_z: Optional[float] = None
    mandrel_pos_x_offset: Optional[float] = None
    mandrel_pos_z_offset: Optional[float] = None
    
    # Roller
    roller_visual_radius: Optional[float] = Field(default=25.0, ge=0)
    roller_visual_x_offset: Optional[float] = None
    roller_visual_z_offset: Optional[float] = None
    
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
    
    # Tool Change
    tool_change_active: Optional[Any] = None  # Can be bool or float (legacy)
    rough_tool_number: Optional[str] = None
    finish_tool_number: Optional[str] = None
    
    # Operations list
    operations: Optional[List[OperationSchema]] = None
    
    # Camera
    camera: Optional[CameraSchema] = None
    saved_camera_pos: Optional[List[List[float]]] = None
    
    class Config:
        extra = "allow"  # Allow unknown fields for forward compatibility


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
