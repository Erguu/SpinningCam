"""
Rule-based operation suggester (process planner) for metal spinning.

Analyzes the cached mandrel profile and a small material heuristic table
(materials.json) and proposes a roughing + finishing operation sequence with
pass count, pass angle fan, feeds and speeds. The output is ADVISORY ONLY:
it is shown to the user for review and only inserted into
params["operations"] when explicitly applied (see ui/dialogs/op_suggester.py).

All heuristic constants live in materials.json next to the executable so they
can be tuned from field experience without a code change. If the file is
missing (fresh install / packaged exe without it), the embedded
DEFAULT_MATERIALS below are used and the file is created on first save.

Heuristic model (conventional cold spinning rules of thumb):
- bend angle   = 90° minus the steepest surface angle from the radial plane;
  a flat disc is 0°, a cylindrical wall is 90°.
- pass count   = ceil(bend_angle / angle_per_pass(material)), clamped 1..12.
- pass fan     = one roughing op with `count` passes, `pass_angle` for the
  first pass and progressive_angle_enabled=True so the built-in fan spreads
  the exit direction to 180° on the last pass.
- speeds       = RPM from the material surface speed at the largest part
  diameter, clamped to the machine / PLC spindle limit.
- feeds        = mm/rev from the table converted to mm/min at that RPM,
  clamped to the PLC feed limit.
- blank Ø      = surface-area equivalence (constant thickness assumption).
"""

import json
import math
import os

import numpy as np

from logger_config import logger

# PLC hard limits (mirrors recipe_to_scl.py MAX_SPINDLE_RPM / MAX_FEEDRATE)
PLC_MAX_RPM = 2550
PLC_MAX_FEED = 3000.0

MATERIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "materials.json")

# Conservative starting values from cold-spinning practice. Deliberately on
# the gentle side — the operator can raise them in materials.json once a
# part/material combination is proven on the machine.
DEFAULT_MATERIALS = [
    {
        "id": "alu_soft",
        "name": {"EN": "Aluminum 1050/3003 (soft)", "TR": "Alüminyum 1050/3003 (yumuşak)", "ES": "Aluminio 1050/3003 (blando)"},
        "angle_per_pass_deg": 25.0,
        "surface_speed_m_min": 350.0,
        "feed_mm_rev_rough": 0.6,
        "feed_mm_rev_finish": 0.3,
        "max_spinning_ratio": 1.9,
        "rough_clearance_mm": 0.5,
        "finish_clearance_mm": 0.0,
    },
    {
        "id": "alu_5xxx",
        "name": {"EN": "Aluminum 5754/5083", "TR": "Alüminyum 5754/5083", "ES": "Aluminio 5754/5083"},
        "angle_per_pass_deg": 20.0,
        "surface_speed_m_min": 300.0,
        "feed_mm_rev_rough": 0.5,
        "feed_mm_rev_finish": 0.25,
        "max_spinning_ratio": 1.7,
        "rough_clearance_mm": 0.5,
        "finish_clearance_mm": 0.0,
    },
    {
        "id": "steel_dc04",
        "name": {"EN": "Mild steel DC04 / AISI 1008", "TR": "Yumuşak çelik DC04 / AISI 1008", "ES": "Acero dulce DC04 / AISI 1008"},
        "angle_per_pass_deg": 20.0,
        "surface_speed_m_min": 250.0,
        "feed_mm_rev_rough": 0.4,
        "feed_mm_rev_finish": 0.2,
        "max_spinning_ratio": 1.7,
        "rough_clearance_mm": 0.5,
        "finish_clearance_mm": 0.0,
    },
    {
        "id": "stainless_304",
        "name": {"EN": "Stainless 304 / 316", "TR": "Paslanmaz 304 / 316", "ES": "Inoxidable 304 / 316"},
        "angle_per_pass_deg": 15.0,
        "surface_speed_m_min": 150.0,
        "feed_mm_rev_rough": 0.3,
        "feed_mm_rev_finish": 0.15,
        "max_spinning_ratio": 1.6,
        "rough_clearance_mm": 0.5,
        "finish_clearance_mm": 0.0,
    },
    {
        "id": "copper",
        "name": {"EN": "Copper (annealed)", "TR": "Bakır (tavlanmış)", "ES": "Cobre (recocido)"},
        "angle_per_pass_deg": 25.0,
        "surface_speed_m_min": 300.0,
        "feed_mm_rev_rough": 0.5,
        "feed_mm_rev_finish": 0.25,
        "max_spinning_ratio": 1.9,
        "rough_clearance_mm": 0.5,
        "finish_clearance_mm": 0.0,
    },
    {
        "id": "brass",
        "name": {"EN": "Brass CuZn37", "TR": "Pirinç CuZn37", "ES": "Latón CuZn37"},
        "angle_per_pass_deg": 20.0,
        "surface_speed_m_min": 250.0,
        "feed_mm_rev_rough": 0.4,
        "feed_mm_rev_finish": 0.2,
        "max_spinning_ratio": 1.75,
        "rough_clearance_mm": 0.5,
        "finish_clearance_mm": 0.0,
    },
]

MAX_ROUGH_PASSES = 12

# Above this total bend angle the flange sees enough compression that
# wrinkling becomes likely — suggest an ironing back pass on the return
# stroke (cost: doubles the roughing cycle time).
BACK_PASS_BEND_THRESHOLD_DEG = 45.0


def load_materials() -> list:
    """Loads the heuristic material table, falling back to built-in defaults."""
    try:
        with open(MATERIALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        mats = data.get("materials", [])
        if mats:
            return mats
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"materials.json unreadable ({e}) — using built-in defaults")
    return [dict(m) for m in DEFAULT_MATERIALS]


def save_default_materials() -> None:
    """Writes the built-in table to materials.json if it does not exist yet,
    so the operator has a file to tune."""
    if os.path.exists(MATERIALS_FILE):
        return
    try:
        with open(MATERIALS_FILE, "w", encoding="utf-8") as f:
            json.dump({"materials": DEFAULT_MATERIALS}, f, indent=2, ensure_ascii=False)
        logger.info(f"Created default materials table: {MATERIALS_FILE}")
    except Exception as e:
        logger.warning(f"Could not write materials.json: {e}")


def _pick_tool(tool_library, preferred_id):
    """Same semantics as ProgramTab.add_op: prefer the calibrated r_tool
    (explicit-None check — 0.0 is a valid calibration), fall back to the
    geometric disc radius, then to the first library tool, then to 25.0."""
    tool = None
    for tl in tool_library or []:
        if tl.get("id") == preferred_id:
            tool = tl
            break
    if tool is None and tool_library:
        tool = tool_library[0]
    if tool is None:
        return preferred_id, 25.0
    rt = tool.get("r_tool")
    r_tool = rt if rt is not None else tool.get("radius", 25.0)
    return tool.get("id", preferred_id), float(r_tool)


def analyze_profile(mandrel_mgr) -> dict:
    """Extracts the planner's geometric inputs from the cached mandrel profile.

    Returns dict with: z_min, z_max, height, r_max, r_min, max_bend_deg,
    surface_len, blank_radius_suggested. Angles are measured from the radial
    plane (flat blank = 0°, cylinder wall = 90°).
    """
    z = np.asarray(mandrel_mgr.profile_z, dtype=float)
    r = np.asarray(mandrel_mgr.profile_r, dtype=float)
    if len(z) < 2:
        raise ValueError("mandrel profile not available")

    # Light smoothing so scan noise doesn't fake a steep segment.
    if len(r) >= 5:
        kernel = np.ones(5) / 5.0
        r_s = np.convolve(r, kernel, mode="same")
        r_s[:2], r_s[-2:] = r[:2], r[-2:]
    else:
        r_s = r

    dz = np.diff(z)
    dr = np.diff(r_s)
    ds = np.sqrt(dz * dz + dr * dr)
    r_mid = (r_s[:-1] + r_s[1:]) / 2.0

    # Bend angle per segment: 0° = radial (flat disc), 90° = axial (cylinder).
    seg_bend = np.degrees(np.arctan2(np.abs(dz), np.abs(dr)))
    # Ignore segments shorter than the scan resolution (edge artifacts).
    valid = ds > 1e-6
    max_bend = float(seg_bend[valid].max()) if valid.any() else 0.0

    surface_len = float(ds.sum())
    r_min = float(r.min())
    r_max = float(r.max())

    # Area equivalence: blank disc area = nose face + wall surface (constant
    # thickness assumption): pi*R^2 = pi*r_min^2 + 2*pi*sum(r*ds)
    blank_r = math.sqrt(max(0.0, r_min * r_min + 2.0 * float((r_mid * ds).sum())))

    return {
        "z_min": float(z[0]),
        "z_max": float(z[-1]),
        "height": float(z[-1] - z[0]),
        "r_max": r_max,
        "r_min": r_min,
        "max_bend_deg": max_bend,
        "surface_len": surface_len,
        "blank_radius_suggested": blank_r,
    }


def suggest_operations(mandrel_mgr, params, material, tool_library,
                       blank_diameter=None, blank_thickness=None) -> dict:
    """Builds a suggested op sequence for the loaded mandrel + material.

    Args:
        mandrel_mgr: MandrelManager with a cached profile.
        params: app params dict (read-only here).
        material: one entry from load_materials().
        tool_library: list of tool dicts (tools.json entries).
        blank_diameter: blank Ø in mm; None = use the area-equivalent estimate.
        blank_thickness: sheet thickness in mm; None = params value.

    Returns:
        {"ops": [op_dict, ...], "analysis": {...},
         "warnings": [(key, kwargs), ...], "notes": [(key, kwargs), ...]}
        Warning/note keys map to i18n string keys (sug_warn_* / sug_note_*).
        Notes are one-line "why this value" explanations for the preview.
    """
    warnings = []
    notes = []
    info = analyze_profile(mandrel_mgr)

    if getattr(mandrel_mgr, "pv_mesh", None) is None:
        warnings.append(("sug_warn_no_mesh", {}))

    if blank_thickness is None:
        blank_thickness = float(params.get("final_part_thickness_on_mandrel", 2.0))
    if not blank_diameter or blank_diameter <= 0:
        blank_diameter = 2.0 * info["blank_radius_suggested"]

    # ── Pass count from total bend angle ─────────────────────────────────
    angle_per_pass = float(material.get("angle_per_pass_deg", 20.0))
    bend = info["max_bend_deg"]
    n_rough = max(1, math.ceil(bend / max(angle_per_pass, 1.0)))
    if n_rough > MAX_ROUGH_PASSES:
        n_rough = MAX_ROUGH_PASSES
        warnings.append(("sug_warn_many_passes", {"bend": bend}))

    # ── Spinning ratio check ─────────────────────────────────────────────
    # Classic spinnability ratio β = D_blank / d_mandrel, with d_mandrel the
    # mandrel MAJOR diameter (the open end the blank wraps over).
    d_mandrel = max(2.0 * info["r_max"], 1e-3)
    ratio = blank_diameter / d_mandrel
    max_ratio = float(material.get("max_spinning_ratio", 1.8))
    if ratio > max_ratio:
        warnings.append(("sug_warn_ratio", {"ratio": ratio, "limit": max_ratio}))

    # ── Spindle speed from surface speed at the largest part diameter ────
    v_surf = float(material.get("surface_speed_m_min", 250.0))
    d_ref = max(2.0 * info["r_max"], 1.0)
    rpm_raw = v_surf * 1000.0 / (math.pi * d_ref)
    rpm_limit = min(float(params.get("max_spin_rpm", PLC_MAX_RPM)), PLC_MAX_RPM)
    rpm = min(max(rpm_raw, 60.0), rpm_limit)
    if rpm < rpm_raw - 0.5:
        warnings.append(("sug_warn_rpm_clamped", {"raw": rpm_raw, "clamped": rpm}))

    # ── Feeds: mm/rev → mm/min at the suggested RPM ──────────────────────
    def _feed(mm_rev):
        raw = mm_rev * rpm
        clamped = min(max(raw, 20.0), PLC_MAX_FEED)
        if clamped < raw - 0.5:
            warnings.append(("sug_warn_feed_clamped", {"raw": raw, "clamped": clamped}))
        return round(clamped, 1)

    feed_rough = _feed(float(material.get("feed_mm_rev_rough", 0.4)))
    feed_finish = _feed(float(material.get("feed_mm_rev_finish", 0.2)))

    # ── Workspace sanity: blank rim must fit inside the X travel ─────────
    ws_x_max = params.get("workspace_x_max")
    center_x = float(params.get("mandrel_pos_x_offset", 0.0))
    if ws_x_max is not None and float(ws_x_max) > 0:
        if center_x + blank_diameter / 2.0 > float(ws_x_max):
            warnings.append(("sug_warn_workspace", {
                "rim": center_x + blank_diameter / 2.0, "limit": float(ws_x_max)}))

    # ── Approach-arm geometry: default arm scaled to the part height ─────
    p1_x = 40.0
    p1_z = min(50.0, max(15.0, 0.5 * info["height"]))
    p3_z = -20.0
    # First-pass exit direction: theta_A is the approach-arm angle from +X;
    # pass_angle = -theta_A puts the exit radially outward (material still
    # flat), + one material angle increment bends it by the first pass.
    # progressive_angle_enabled spreads the fan to 180° on the last pass.
    theta_a = math.degrees(math.atan2(-p1_z, p1_x))
    pass_angle = round(min(170.0, max(60.0, -theta_a + angle_per_pass)), 1)

    start_z = info["z_min"] + 0.5
    end_z = info["z_max"]

    rough_tool, rough_r = _pick_tool(tool_library, "T0101")
    fin_tool, fin_r = _pick_tool(tool_library, "T0202")

    # Back pass (ironing return stroke) when the wall is steep enough that
    # flange wrinkling is a real risk. Explicit False otherwise, so the user
    # sees the decision in the op editor instead of an absent key.
    use_back_pass = bend > BACK_PASS_BEND_THRESHOLD_DEG
    rough_clr = float(material.get("rough_clearance_mm", 0.5))
    finish_clr = float(material.get("finish_clearance_mm", 0.0))

    rough_op = {
        "type": "roughing", "enabled": True,
        "count": n_rough,
        "tool_id": rough_tool, "r_tool": rough_r,
        "p1_x": p1_x, "p1_z": p1_z, "p3_z": p3_z,
        "start_z": round(start_z, 2), "end_z": round(end_z, 2),
        "step": 1.0,
        "clearance": rough_clr,
        "rot": 0.0,
        "pass_angle": pass_angle,
        "progressive_angle_enabled": n_rough > 1,
        "progressive_angle_end": 180.0,
        "pass_shape": "spline",
        "direction": "forward",
        "back_pass_enabled": use_back_pass,
        "back_pass_feed": feed_rough,
        "back_pass_arc_x": 0.0, "back_pass_arc_z": 0.0,
        "feed": feed_rough, "feed_mode": "mm_min",
        "speed": round(rpm), "speed_mode": "RPM",
    }
    finish_op = {
        "type": "finishing", "enabled": True,
        "count": 1,
        "tool_id": fin_tool, "r_tool": fin_r,
        "p1_x": p1_x, "p1_z": p1_z, "p3_z": p3_z,
        "start_z": round(start_z, 2), "end_z": round(end_z, 2),
        "step": 1.0,
        "clearance": finish_clr,
        "rot": 0.0,
        "pass_shape": "spline",
        "direction": "forward",
        "back_pass_enabled": False,
        "feed": feed_finish, "feed_mode": "mm_min",
        "speed": round(rpm), "speed_mode": "RPM",
    }

    # One-line rationale per suggested value (rendered under the preview).
    notes.append(("sug_note_passes", {"n": n_rough, "bend": bend, "per": angle_per_pass}))
    notes.append(("sug_note_passangle", {"first": pass_angle}))
    notes.append(("sug_note_rpm", {"rpm": rpm, "v": v_surf, "d": d_ref}))
    notes.append(("sug_note_feed", {"mmrev": float(material.get("feed_mm_rev_rough", 0.4)),
                                    "rpm": rpm, "fr": feed_rough, "ff": feed_finish}))
    notes.append(("sug_note_blank", {"d": blank_diameter}))
    notes.append(("sug_note_clearance", {"rc": rough_clr, "fc": finish_clr}))
    if use_back_pass:
        notes.append(("sug_note_backpass_on", {"bend": bend,
                                               "thr": BACK_PASS_BEND_THRESHOLD_DEG}))
    else:
        notes.append(("sug_note_backpass_off", {"bend": bend,
                                                "thr": BACK_PASS_BEND_THRESHOLD_DEG}))
    notes.append(("sug_note_finish", {}))

    analysis = dict(info)
    analysis.update({
        "blank_diameter": blank_diameter,
        "blank_thickness": blank_thickness,
        "spinning_ratio": ratio,
        "n_rough_passes": n_rough,
        "rpm": rpm,
        "feed_rough": feed_rough,
        "feed_finish": feed_finish,
        "pass_angle": pass_angle,
    })
    logger.info(
        f"[PLANNER] material={material.get('id')} bend={bend:.1f}° passes={n_rough} "
        f"pass_angle={pass_angle}° rpm={rpm:.0f} feed_r={feed_rough} feed_f={feed_finish} "
        f"blank_d={blank_diameter:.1f} ratio={ratio:.2f}"
    )
    return {"ops": [rough_op, finish_op], "analysis": analysis,
            "warnings": warnings, "notes": notes}
