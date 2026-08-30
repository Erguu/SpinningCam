import json
import os
import glob

MACHINE_PROFILE_KEYS = [
    "kinematics",
    "tilt_pivot_x", "tilt_pivot_z",
    "tilt_b_min", "tilt_b_max", "tilt_b_home", "tilt_b_sign",
    "machine_origin_x", "machine_origin_z",
    "machine_invert_x", "machine_invert_z",
    "machine_gcode_offset_x", "machine_gcode_offset_z",
    "output_mode", "origin_use_home", "roller_positive_x_side",
    "home_x", "home_z", "retract_x", "retract_z",
    "end_use_home", "end_x", "end_z",
    "rapid_rate_mm_min",
    "workspace_show", "workspace_x_min", "workspace_x_max",
    "workspace_z_min", "workspace_z_max",
    "clamp_zone_baseline",
    "cylinder_enabled", "cylinder_show", "cylinder_position_mm",
    "cylinder_x_pos", "cylinder_z_base",
    "plc_mode", "plc_tolerance", "plc_exit_tolerance",
    "plc_auto_tune", "plc_target_lines",
    # Recipe DB layout — belongs to the PLC on the other end, not to one program,
    # so both halves live on the machine profile. `scl_capacity` used to be
    # re-derived (and re-asked) on every export; remembering it is what lets the
    # layout dialog stop opening by itself.
    "scl_chunk_size", "scl_capacity",
    "turret_slots", "turret_auto_angles",
    "gcode_resolution", "gcode_header", "gcode_footer",
    "max_spin_rpm",
    "custom_commands", "mcode_descriptions",
    "calibration_view",
]


def list_machine_profiles(base_dir: str) -> list:
    machines_dir = os.path.join(base_dir, "machines")
    if not os.path.isdir(machines_dir):
        return []
    profiles = []
    for fpath in sorted(glob.glob(os.path.join(machines_dir, "*.json"))):
        # Skip the tracked "<id>.default.json" seeds — first_run_seed copies each to
        # its live "<id>.json". Loading both would duplicate every machine_id (and
        # crash the machine-selector tree with "Item ID111-1 already exists").
        if fpath.endswith(".default.json"):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                p = json.load(f)
            if "machine_id" in p:
                p["_path"] = fpath
                profiles.append(p)
        except Exception:
            pass
    return profiles


def get_unique_types(base_dir: str) -> list:
    """Return list of (type_code, sample_profile) for each unique type code found in machines/."""
    from machine_adapter import parse_machine_id
    profiles = list_machine_profiles(base_dir)
    seen = {}
    for p in profiles:
        tc, _ = parse_machine_id(p["machine_id"])
        if tc not in seen:
            seen[tc] = p
    return list(seen.items())   # [(type_code, profile), ...]


def _same_value(a, b) -> bool:
    """True when two saved param values mean the same thing.

    JSON round-trips turn 1000 into 1000.0 and lists/dicts into fresh objects, so
    a bare ``!=`` would report differences that are not differences. Numbers are
    compared numerically (with a hair of tolerance for float noise), bools
    strictly (True must not equal 1.0 — plc_mode is stored both ways in the wild),
    and containers by their JSON text.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b) and isinstance(a, bool) == isinstance(b, bool)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-9
    if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
        try:
            return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        except (TypeError, ValueError):
            return a == b
    return a == b


def diff_machine_params(current: dict, loaded: dict) -> list:
    """Machine-profile settings that a loaded .ssp disagrees with.

    A saved program stores the WHOLE params dict, machine settings included, so
    opening an old program used to silently restore that day's machine setup —
    program start position, PLC/recipe settings, turret table (field incident,
    2026-08-14). Those belong to the machine in front of the operator, not to the
    program, so the loader now asks instead of assuming.

    Only keys actually present in the file are considered: programs saved by old
    builds carry none, and a missing key is not a disagreement.

    Returns ``[{'key', 'current', 'loaded'}, ...]`` in MACHINE_PROFILE_KEYS order
    (stable, so the dialog does not reshuffle between loads).
    """
    out = []
    for k in MACHINE_PROFILE_KEYS:
        if k not in loaded or k not in current:
            continue
        if not _same_value(current[k], loaded[k]):
            out.append({"key": k, "current": current[k], "loaded": loaded[k]})
    return out


def strip_machine_params(loaded: dict) -> dict:
    """A copy of a loaded program's params with every machine-profile key removed."""
    return {k: v for k, v in loaded.items() if k not in set(MACHINE_PROFILE_KEYS)}


def load_machine_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        p = json.load(f)
    if "machine_id" not in p:
        raise ValueError(f"Profile missing machine_id: {path}")
    p["_path"] = path
    return p


def find_or_create_profile(machine_id: str, base_dir: str) -> dict:
    """Load the profile for machine_id; create from same-type template if it doesn't exist."""
    from machine_adapter import parse_machine_id as _parse
    machines_dir = os.path.join(base_dir, "machines")
    path = os.path.join(machines_dir, f"{machine_id}.json")
    if os.path.exists(path):
        return load_machine_profile(path)
    # Create from a same-type template
    type_code, _ = _parse(machine_id)
    profiles = list_machine_profiles(base_dir)
    template = next(
        (p for p in profiles if _parse(p["machine_id"])[0] == type_code),
        profiles[0] if profiles else {}
    )
    new_profile = {k: v for k, v in template.items() if not k.startswith("_")}
    new_profile["machine_id"] = machine_id
    new_profile.setdefault("machine_name", f"Machine {machine_id}")
    os.makedirs(machines_dir, exist_ok=True)
    save_machine_profile(path, new_profile)
    new_profile["_path"] = path
    return new_profile


def save_machine_profile(path: str, profile: dict):
    data = {k: v for k, v in profile.items() if not k.startswith("_")}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def migrate_from_settings(settings: dict, base_dir: str) -> list:
    """Create machines/ID111-1.json from current settings dict (first-run migration)."""
    machines_dir = os.path.join(base_dir, "machines")
    os.makedirs(machines_dir, exist_ok=True)
    profile = {
        "machine_id": "ID111-1",
        "machine_name": "EMS Spinning Lathe #1",
    }
    for k in MACHINE_PROFILE_KEYS:
        if k in settings:
            profile[k] = settings[k]
    out_path = os.path.join(machines_dir, "ID111-1.json")
    save_machine_profile(out_path, profile)
    profile["_path"] = out_path
    return [profile]
