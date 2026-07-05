"""Headless verification of the operation suggester (process_planner.py).

Run inside the spinning_cam conda env. Covers: default cone profile,
materials table, op-dict validity, PLC limit clamps, warning triggers.
"""
import math
import sys

from mandrel_analyzer import MandrelManager
from process_planner import (analyze_profile, load_materials,
                             suggest_operations, PLC_MAX_RPM, PLC_MAX_FEED)

FAIL = []

def check(cond, label):
    print(("  OK  " if cond else "  FAIL") + " - " + label)
    if not cond:
        FAIL.append(label)

# ── Setup: default cone (60 -> 10 over 100mm) ────────────────────────────
mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)

params = {
    "final_part_thickness_on_mandrel": 2.0,
    "mandrel_pos_x_offset": 0.0,
    "max_spin_rpm": 2000,
    "workspace_x_max": 170.0,
}
tools = [
    {"id": "T0101", "r_tool": 30.0, "radius": 28.0},
    {"id": "T0202", "r_tool": None, "radius": 22.5},
]

print("== analyze_profile ==")
info = analyze_profile(mgr)
print(f"   {info}")
check(95.0 < info["height"] < 105.0, "height ~100")
check(55.0 < info["r_max"] < 65.0, "r_max ~60")
check(info["r_min"] < 15.0, "r_min ~10")
# cone slope: dr=50 over dz=100 -> bend = atan2(100,50) = 63.4 deg
check(55.0 < info["max_bend_deg"] < 80.0, f"bend angle plausible ({info['max_bend_deg']:.1f})")
check(info["blank_radius_suggested"] > info["r_max"], "blank estimate > part radius")

print("== materials ==")
mats = load_materials()
check(len(mats) >= 5, f"material table has entries ({len(mats)})")
al = next(m for m in mats if m["id"] == "alu_soft")
ss = next(m for m in mats if m["id"] == "stainless_304")

print("== suggest: aluminum ==")
res = suggest_operations(mgr, params, al, tools)
ops = res["ops"]
a = res["analysis"]
print(f"   analysis: passes={a['n_rough_passes']} rpm={a['rpm']:.0f} "
      f"feeds={a['feed_rough']}/{a['feed_finish']} pass_angle={a['pass_angle']}")
for k, kw in res["warnings"]:
    print(f"   warn: {k} {kw}")
check(abs(a["spinning_ratio"] - a["blank_diameter"] / (2 * info["r_max"])) < 1e-6,
      "spinning ratio uses mandrel MAJOR diameter")
check("sug_warn_ratio" not in [k for k, _ in res["warnings"]],
      "no ratio warning for area-equivalent blank on plain cone")
check(len(ops) == 2, "two ops (rough + finish)")
check(ops[0]["type"] == "roughing" and ops[1]["type"] == "finishing", "op types")
check(ops[0]["count"] == math.ceil(a["max_bend_deg"] / al["angle_per_pass_deg"]),
      "pass count = ceil(bend/angle_per_pass)")
check(ops[0]["progressive_angle_enabled"] is True, "progressive fan on (multi-pass)")
check(ops[0]["progressive_angle_end"] == 180.0, "fan end angle explicit 180 (editable)")
check(60.0 <= ops[0]["pass_angle"] <= 170.0, "pass_angle in range")
check(ops[0]["tool_id"] == "T0101" and ops[0]["r_tool"] == 30.0, "rough tool calibrated r_tool")
check(ops[1]["tool_id"] == "T0202" and ops[1]["r_tool"] == 22.5, "finish tool falls back to radius (r_tool None)")
check(ops[0]["speed"] <= min(2000, PLC_MAX_RPM), "rpm within machine limit")
check(20.0 <= ops[0]["feed"] <= PLC_MAX_FEED, "rough feed within PLC limit")
check(20.0 <= ops[1]["feed"] <= PLC_MAX_FEED, "finish feed within PLC limit")
check(ops[1]["feed"] < ops[0]["feed"], "finish feed finer than rough")
check(ops[0]["start_z"] >= info["z_min"] and ops[0]["end_z"] <= info["z_max"] + 1e-6,
      "Z span inside profile")
check(ops[0]["clearance"] == al["rough_clearance_mm"], "rough clearance from material")
check(ops[1]["clearance"] == al["finish_clearance_mm"], "finish clearance from material")
required = {"type", "enabled", "count", "tool_id", "r_tool", "p1_x", "p1_z", "p3_z",
            "start_z", "end_z", "clearance", "rot", "feed", "feed_mode", "speed",
            "speed_mode", "pass_shape", "direction", "back_pass_enabled"}
check(required.issubset(ops[0].keys()) and required.issubset(ops[1].keys()),
      "op dicts carry all required keys")
# cone bend 63.4 deg > 45 threshold -> ironing back pass suggested on roughing only
check(ops[0]["back_pass_enabled"] is True, "back pass ON for steep wall (63 deg > 45)")
check(ops[0]["back_pass_feed"] == ops[0]["feed"], "back pass feed = rough feed")
check(ops[1]["back_pass_enabled"] is False, "no back pass on finishing")
check(ops[0]["direction"] == "forward" and ops[1]["direction"] == "forward",
      "direction explicit forward")
note_keys = [k for k, _ in res["notes"]]
check("sug_note_backpass_on" in note_keys, "back-pass rationale note present")
check(len(note_keys) >= 7, f"why-notes cover the main values ({len(note_keys)})")
from i18n import STRINGS
check(all(k in STRINGS for k in note_keys), "all note keys have i18n strings")
for k, kw in res["notes"] + res["warnings"]:
    STRINGS[k]["EN"].format(**kw)  # raises if placeholders mismatch
check(True, "EN note/warning templates format without error")
for k, kw in res["notes"] + res["warnings"]:
    STRINGS[k]["TR"].format(**kw); STRINGS[k]["ES"].format(**kw)
check(True, "TR/ES note/warning templates format without error")

print("== suggest: stainless needs more passes than aluminum ==")
res_ss = suggest_operations(mgr, params, ss, tools)
check(res_ss["ops"][0]["count"] >= ops[0]["count"], "stainless passes >= aluminum passes")

print("== warnings: excessive blank -> ratio + workspace ==")
res_w = suggest_operations(mgr, params, al, tools, blank_diameter=400.0)
wkeys = [k for k, _ in res_w["warnings"]]
check("sug_warn_ratio" in wkeys, "spinning-ratio warning fires")
check("sug_warn_workspace" in wkeys, "workspace warning fires")

print("== warnings: tiny part -> rpm clamp ==")
mgr2 = MandrelManager()  # keep profile arrays default (60->10) but shrink via params limit
res_c = suggest_operations(mgr, {**params, "max_spin_rpm": 200}, al, tools)
check(res_c["ops"][0]["speed"] <= 200, "rpm respects low machine limit")
check("sug_warn_rpm_clamped" in [k for k, _ in res_c["warnings"]], "rpm clamp warning fires")

print()
if FAIL:
    print(f"RESULT: {len(FAIL)} FAILURES"); sys.exit(1)
print("RESULT: ALL CHECKS PASSED")
