class MachineAdapter:
    def get_available_op_types(self): return []
    def get_path_generator_class(self): return None
    def get_ui_sections(self): return []
    def get_export_formats(self): return []
    def get_kinematics(self): return "xz"
    def supports_heating(self): return False


class StandardTwoAxisSpinningAdapter(MachineAdapter):
    """Type code 111 — lathe / spinning / two-axis basic (cold)."""

    def get_available_op_types(self):
        return ["roughing", "finishing", "cutting", "bending"]

    def get_path_generator_class(self):
        from path_generator import PathGenerator
        return PathGenerator

    def get_ui_sections(self):
        return [
            "coords", "output_mode", "offsets", "home", "touch",
            "gcode_out", "workspace", "cylinder", "plc", "custom_cmds", "mcode_desc",
        ]

    def get_export_formats(self):
        return ["gcode", "scl", "recipe_csv", "pdf", "stl"]


class HotTiltArmSpinningAdapter(StandardTwoAxisSpinningAdapter):
    """Type code 112 — lathe / spinning / hot, tilt-arm kinematics.

    Z is linear like 111, but the X slide rides on a rotary (B) arm: tool tip
    position = f(B, X-on-arm, Z) and tool orientation follows B. Controller is a
    CODESYS-based IPC (Delta/Inovance) — the Siemens SCL pipeline does not apply.

    Phase 0 (infrastructure): inherits op types and the XZ path generator from
    111. Tilt-arm transform, heating commands and the CODESYS post-processor
    land in later phases (TODO.md #50-#52).
    """

    def get_ui_sections(self):
        # No Siemens-SCL-specific sections (plc / custom M-codes / M-code table).
        # "tilt_arm" = B-axis geometry section (only meaningful for this type).
        return [
            "coords", "output_mode", "offsets", "home", "touch",
            "gcode_out", "workspace", "cylinder", "tilt_arm",
        ]

    def get_export_formats(self):
        # No SCL / recipe CSV until the CODESYS post-processor exists.
        return ["gcode", "pdf", "stl"]

    def get_kinematics(self):
        return "tilt_arm"

    def supports_heating(self):
        return True


ADAPTERS = {
    "111": StandardTwoAxisSpinningAdapter,
    "112": HotTiltArmSpinningAdapter,
}

# Human-readable descriptions per type code: (category, process, variant)
TYPE_DESCRIPTIONS = {
    "111": ("Lathe", "Metal Spinning", "Two-Axis Basic"),
    "112": ("Lathe", "Metal Spinning", "Hot / Tilt-Arm"),
}


def parse_machine_id(machine_id: str) -> tuple:
    """'ID111-1' → ('111', '1')"""
    body = machine_id.removeprefix("ID")
    type_code, _, serial = body.partition("-")
    return type_code, serial


def get_type_description(type_code: str) -> tuple:
    """Returns (category, process, variant) strings for a type code."""
    return TYPE_DESCRIPTIONS.get(type_code, ("Unknown", "Unknown", "Unknown"))


def get_adapter(machine_id: str) -> MachineAdapter:
    type_code, _ = parse_machine_id(machine_id)
    cls = ADAPTERS.get(type_code, StandardTwoAxisSpinningAdapter)
    return cls()
