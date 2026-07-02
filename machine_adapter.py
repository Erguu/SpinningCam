class MachineAdapter:
    def get_available_op_types(self): return []
    def get_path_generator_class(self): return None
    def get_ui_sections(self): return []


class StandardTwoAxisSpinningAdapter(MachineAdapter):
    """Type code 111 — lathe / spinning / two-axis basic."""

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


ADAPTERS = {
    "111": StandardTwoAxisSpinningAdapter,
}

# Human-readable descriptions per type code: (category, process, variant)
TYPE_DESCRIPTIONS = {
    "111": ("Lathe", "Metal Spinning", "Two-Axis Basic"),
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
