# -*- coding: utf-8 -*-
"""Headless test for the two-pass comparison model (pass_compare.py, #104).

Covers what the dialog cannot check for itself:
  * two passes of ONE op differ only where the fan/pins make them differ;
  * a cross-operation and a forward-vs-reverse comparison find the op-level
    difference (that is the whole point of the feature);
  * a value equal to its documented default does NOT count as a difference
    against an unset field — otherwise "Only differences" lists rows that run
    identically;
  * staged edits PREVIEW without touching the op, and route to the destination
    the scope rules name (pin vs op field);
  * apply_edits writes exactly those destinations, and a cleared value removes
    the key rather than storing None.
"""
import copy

import pass_compare as pc
from mandrel_analyzer import MandrelManager
from i18n import t

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])
blank_r = float(mgr.props["br"]) * 1.5

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


BASE = {"type": "roughing", "pass_shape": "linear_approach", "r_tool": 25.0,
        "clearance": 1.5, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
        "count": 4, "start_z": min_z + 10, "end_z": min_z + 40,
        "pass_angle": 120.0, "reach": 40.0}


def params_for(ops):
    return {"operations": copy.deepcopy(ops), "blank_radius": blank_r,
            "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "target_clearance": 0.0}


def row_for(rows, key):
    return next((r for r in rows if r["key"] == key and r["kind"] != "header"), None)


def build(p, a, b, **kw):
    return pc.build_rows(p, mgr, a, b, **kw)


# ── 1. Same operation, two passes: only the stepped fields differ ──────────
p = params_for([dict(BASE, name="Rough 1")])
rows = build(p, (0, 0), (0, 2))
check(bool(rows), "comparison built for two passes of one op")
check(row_for(rows, "anchor")["differs"], "anchor Z differs between pass 1 and 3")
check(not row_for(rows, "clr")["differs"], "clearance is identical (same op, no pins)")
check(not row_for(rows, "pass_shape")["differs"], "op-level shape identical for same op")
check(row_for(rows, "op_name")["a"] == "Rough 1", "identity row names the op")

# ── 2. Cross-operation: the op-level difference is what surfaces ───────────
p = params_for([dict(BASE, name="Rough 1"),
                dict(BASE, name="Rough 2", pass_shape="spline", feed=850.0)])
rows = build(p, (0, 0), (1, 0))
shape = row_for(rows, "pass_shape")
check(shape["differs"] and shape["a"] == "linear_approach" and shape["b"] == "spline",
      "cross-op shape difference found")
check(row_for(rows, "feed")["differs"], "cross-op feed difference found")
check(row_for(rows, "anchor")["differs"] is False,
      "identical anchors across ops are NOT flagged")

# ── 3. Forward vs reverse (the case the user asked for by name) ────────────
p = params_for([dict(BASE, name="Fwd", direction="forward"),
                dict(BASE, name="Rev", direction="reverse")])
rows = build(p, (0, 1), (1, 1))
d = row_for(rows, "direction")
check(d["differs"] and d["a"] == "forward" and d["b"] == "reverse",
      "forward vs reverse pass compares and flags the direction")
labels = [x["label"] for x in pc.list_passes(p)]
check(any(t("pc_tag_reverse") in l for l in labels), "reverse passes are tagged in the picker")

# ── 4. A default-valued field does not read as a difference ───────────────
#     op A stores rot=0 explicitly, op B leaves it unset (documented default 0).
p = params_for([dict(BASE, rot=0.0), dict(BASE)])
rows = build(p, (0, 0), (1, 0))
rot = row_for(rows, "rot")
check(not rot["differs"], "explicit 0 vs unset rot (default 0) is NOT a difference")
check(rot["is_default_b"] and not rot["is_default_a"], "the unset side is marked as default")
p = params_for([dict(BASE, rot=7.0), dict(BASE)])
check(row_for(build(p, (0, 0), (1, 0)), "rot")["differs"],
      "an explicit non-default value IS a difference against unset")

# ── 4b. Non-numeric defaults: modes and the two trims that default ON ─────
#      OP_PARAM_DEFAULTS covers neither, so without _IMPLIED_DEFAULTS an op
#      that spells out what it already does would read as different.
p = params_for([dict(BASE, exit_bow_trim=True, direction="forward",
                     feed_mode="mm_min", exit_mid_trim=True),
                dict(BASE)])
rows = build(p, (0, 0), (1, 0))
for key in ("exit_bow_trim", "exit_mid_trim", "direction", "feed_mode"):
    check(not row_for(rows, key)["differs"],
          f"explicit {key} == its engine default, not a difference")
check(row_for(rows, "exit_bow_trim")["b"].startswith(t("pc_yes")),
      "an unset trim reads as ON (engine default True), not as a dash")
check(row_for(rows, "back_pass_enabled")["a"].startswith(t("pc_no")),
      "an unset ordinary boolean reads as OFF")
p2 = params_for([dict(BASE, exit_bow_trim=False), dict(BASE)])
check(row_for(build(p2, (0, 0), (1, 0)), "exit_bow_trim")["differs"],
      "trim turned OFF against the default ON IS a difference")

# ── 4c. Inert dependants (group toggle off) are not reported as differences ─
p = params_for([dict(BASE, progressive_angle_enabled=False, progressive_angle_end=150.0),
                dict(BASE, progressive_angle_enabled=False, progressive_angle_end=90.0)])
rows = build(p, (0, 0), (1, 0))
end = row_for(rows, "progressive_angle_end")
check(not end["differs"], "fan-end angles differ but neither op fans — not a difference")
check(t("pc_inert") in end["a"] and t("pc_inert") in end["b"],
      "both inert sides are marked 'not in use'")
p = params_for([dict(BASE, progressive_angle_enabled=True, progressive_angle_end=150.0),
                dict(BASE, progressive_angle_enabled=False, progressive_angle_end=90.0)])
rows = build(p, (0, 0), (1, 0))
check(row_for(rows, "progressive_angle_enabled")["differs"], "the toggle itself differs")
check(row_for(rows, "progressive_angle_end")["differs"],
      "a live fan end vs an inert one IS a difference")

# ── 5. A key outside an op type's universe shows a dash, not a default ────
p = params_for([dict(BASE), dict(BASE, type="finishing", name="Finish")])
rows = build(p, (0, 0), (1, 0))
check(row_for(rows, "exit_bow")["b"] == "—",
      "roughing-only field is a dash on the finishing side, not its default")

# ── 6. Pins are previewed, not written ────────────────────────────────────
p = params_for([dict(BASE, name="Rough 1")])
before = copy.deepcopy(p["operations"][0])
staged_pins = {(0, 2): {"reach": 12.0}}
rows = build(p, (0, 0), (0, 2), staged_pins=staged_pins)
reach = row_for(rows, "reach")
check(reach["b"] == "12", f"staged pin previews on side B (got {reach['b']})")
check(reach["b_src"] == "staged", "the previewed value is attributed to the staged edit")
check(p["operations"][0] == before, "previewing a staged pin does NOT mutate the op")

# ── 7. Op-level staging previews on BOTH sides of the same operation ──────
rows = build(p, (0, 0), (0, 2), staged_ops={0: {"pass_shape": "spline"}})
sh = row_for(rows, "pass_shape")
check(sh["a"] == "spline" and sh["b"] == "spline" and not sh["differs"],
      "an op-level stage shows on both passes of that op and stays undifferenced")
check(p["operations"][0] == before, "previewing an op-level stage does NOT mutate the op")

# ── 8. Scope rules ────────────────────────────────────────────────────────
rows = build(p, (0, 0), (0, 2))
eff_reach = row_for(rows, "reach")
op_reach = next(r for r in rows if r["key"] == "reach" and r["section"] == "operation")
op_shape = row_for(rows, "pass_shape")
check(pc.edit_scope_options(eff_reach, "roughing") == ["pin"],
      "effective row writes a per-pass pin")
check(pc.edit_scope_options(op_reach, "roughing") == ["pin", "op"],
      "op row for a pin-capable key offers BOTH destinations")
check(pc.edit_scope_options(op_shape, "roughing") == ["op"],
      "op row for a non-pinnable key offers only the op field")
check(pc.edit_scope_options(eff_reach, "finishing") == [],
      "finishing has no per-pass pins — no destination offered")

# ── 9. apply_edits writes the right places, and clears rather than nulls ──
p = params_for([dict(BASE, name="Rough 1", rot=5.0)])
n = pc.apply_edits(p, {0: {"pass_shape": "spline", "rot": None}},
                   {(0, 2): {"reach": 12.0}})
op = p["operations"][0]
check(n == 3, f"3 values written (got {n})")
check(op["pass_shape"] == "spline", "op field written")
check("rot" not in op, "a cleared op field is REMOVED, not set to None")
check(op["pass_edits"]["2"]["reach"] == 12.0, "pin written under the string key")
n = pc.apply_edits(p, {}, {(0, 2): {"reach": None}})
check("pass_edits" not in op, "clearing the last pin removes pass_edits entirely")

# ── 10. Cutting/bending: no per-pass geometry, but the op half still works ─
p = params_for([dict(BASE), {"type": "cutting", "name": "Cut", "plunge_end_x": 90.0,
                             "plunge_end_z": 5.0, "feed": 120.0}])
check(pc.pass_count(p["operations"][1]) == 1, "cutting op contributes exactly one pass")
rows = build(p, (0, 0), (1, 0))
check(bool(rows), "roughing vs cutting comparison still builds")
check(row_for(rows, "anchor")["b"] == "—", "cutting side has no effective anchor")
check(row_for(rows, "plunge_end_x")["b"] == "90", "cutting geometry shows in the op section")
check(not row_for(rows, "anchor")["editable"] or
      pc.edit_scope_options(row_for(rows, "anchor"), "cutting") == [],
      "no pin destination offered on a cutting op")

# ── 11. Value parsing ─────────────────────────────────────────────────────
check(pc.parse_value("12,5", "number") == (True, 12.5), "comma decimal parses")
check(pc.parse_value("", "number") == (True, None), "empty means clear")
check(pc.parse_value("abc", "number")[0] is False, "garbage number rejected")
check(pc.parse_value(t("pc_yes"), "bool") == (True, True), "localised yes parses")
check(pc.parse_value("spline", "enum") == (True, "spline"), "enum passes through")

# ── 12. Report ────────────────────────────────────────────────────────────
p = params_for([dict(BASE, name="A"), dict(BASE, name="B", pass_shape="spline")])
rows = build(p, (0, 0), (1, 0))
rep = pc.format_report(rows, only_diff=True)
check("spline" in rep and "linear_approach" in rep, "report carries both sides")
check(t("pc_sec_operation") in rep, "report keeps the section headings")

print()
print("FAILED" if fails else "ALL PASS", f"({fails} failure(s))")
raise SystemExit(1 if fails else 0)
