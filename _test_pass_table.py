# -*- coding: utf-8 -*-
"""Headless test for the per-pass table compute half (ui/dialogs/pass_table.py,
#80/#79 P1): rows must mirror the ENGINE (cross-checked via last_op_reach /
last_op_end_angle), sources must name the live value origin, and the three
warnings (guard flip, near-duplicate, reach→0) must fire where the engine's
geometry says they do. Staged edits preview without touching the op."""
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.dialogs.pass_table import compute_pass_rows
from i18n import t

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])
blank_r = float(mgr.props["br"]) * 1.5
pg = PathGenerator()

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

def params_for(op, clearance_global=0.0):
    return {"operations": [op], "blank_radius": blank_r, "auto_calc_angle": False,
            "min_safety_gap": -999.0, "final_part_thickness_on_mandrel": 0.0,
            "shell_thickness": 0.0, "target_clearance": clearance_global}

BASE = {"type": "roughing", "pass_shape": "linear_approach", "r_tool": 25.0,
        "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0}

# 1. Cross-check vs engine: fanned polar op — table's LAST row equals the
#    engine's recorded end reach/angle.
op = dict(BASE, count=5, start_z=min_z + 10, end_z=min_z + 40, pass_angle=120.0,
          reach=40.0, progressive_angle_enabled=True, progressive_angle_end=170.0,
          progressive_reach_enabled=True, progressive_reach_end=25.0)
p = params_for(op)
pg.calculate_paths(p, {}, mgr)
rows = compute_pass_rows(op, p, mgr)
check(len(rows) == 5, f"{len(rows)} rows for 5 passes")
check(abs(rows[-1]["angle"] - pg.last_op_end_angle[0]) < 0.01,
      f"last-row angle {rows[-1]['angle']} == engine {pg.last_op_end_angle[0]:.2f}")
check(abs(rows[-1]["reach"] - pg.last_op_reach[0]) < 0.05,
      f"last-row reach {rows[-1]['reach']} == engine {pg.last_op_reach[0]:.2f}")
check(rows[0]["source"] == t("pt_src_fan"), "fan source tagged")

# 2. Follow op: source 'takip', engine cross-check again.
op = dict(BASE, count=3, start_z=min_z + 10, end_z=min_z + 30, pass_angle=100.0,
          reach_follow_blank=True)
p = params_for(op)
pg.calculate_paths(p, {}, mgr)
rows = compute_pass_rows(op, p, mgr)
check(rows[0]["source"] == t("pt_src_follow"), "follow source tagged")
check(abs(rows[-1]["reach"] - pg.last_op_reach[0]) < 0.05,
      f"follow last-row reach {rows[-1]['reach']} == engine {pg.last_op_reach[0]:.2f}")

# 3. Warnings — near-180 fan with big clearance: guard flip + near-duplicates
#    appear in the tail rows (the user's 30-pass symptom, #80).
op = dict(BASE, count=30, start_z=min_z + 10, end_z=min_z + 15, pass_angle=93.0,
          clearance=4.5, reach=40.0, progressive_angle_enabled=True,
          progressive_angle_end=178.0)
rows = compute_pass_rows(op, params_for(op), mgr)
guard_rows = [r["i"] for r in rows if any(t("pt_warn_guard").split("{")[0][:8] in w for w in r["warnings"])]
dup_rows = [r["i"] for r in rows if t("pt_warn_duplicate") in r["warnings"]]
check(bool(guard_rows) and min(guard_rows) > 15,
      f"guard-flip warning fires in the tail (first at pass {min(guard_rows) + 1 if guard_rows else '—'})")
check(bool(dup_rows), f"near-duplicate warning fires ({len(dup_rows)} rows)")

# 4. reach→0 warning: reach fan ending at 0 → last pass falls back to raw exit.
op = dict(BASE, count=4, start_z=min_z + 10, end_z=min_z + 30, pass_angle=120.0,
          reach=30.0, progressive_reach_enabled=True, progressive_reach_end=0.0)
rows = compute_pass_rows(op, params_for(op), mgr)
check(t("pt_warn_reach_zero") in rows[-1]["warnings"], "reach≈0 fallback warning on last pass")

# 5. Pins: source ⭑, value applied; staged preview overrides without op mutation.
op = dict(BASE, count=3, start_z=min_z + 10, end_z=min_z + 30, pass_angle=120.0,
          reach=40.0, pass_edits={"1": {"reach": 22.0}})
rows = compute_pass_rows(op, params_for(op), mgr)
check(rows[1]["source"] == t("pt_src_pin") and abs(rows[1]["reach"] - 22.0) < 0.01,
      "pin row tagged ⭑ with pinned value")
rows_staged = compute_pass_rows(op, params_for(op), mgr, staged={2: {"reach": 15.0}})
check(rows_staged[2]["source"] == t("pt_src_staged") and abs(rows_staged[2]["reach"] - 15.0) < 0.01,
      "staged row previews the unapplied value")
check(op.get("pass_edits") == {"1": {"reach": 22.0}}, "op untouched by staging (pure)")

# 6. Legacy override flag: gui_pass_overrides at the op's global index.
rows = compute_pass_rows(op, params_for(op), mgr,
                         gui_overrides={7: {"reach": 46.2}}, base_fwd_idx=6)
check(rows[1]["legacy_override"] and t("pt_warn_legacy") in rows[1]["warnings"],
      "legacy hidden override surfaced on the right pass")

# 7. Cutting op: no rows (not applicable).
check(compute_pass_rows({"type": "cutting"}, params_for({}), mgr) == [],
      "cutting op → empty table")

# 8. p2_z_extend mirror (user feedback 2026-07-08): the engine contact is
#    target_z + p2_z_extend — the table's Z and end_z must include it.
op = dict(BASE, count=2, start_z=min_z + 10, end_z=min_z + 20, pass_angle=120.0,
          reach=30.0)
rows_plain = compute_pass_rows(op, params_for(op), mgr)
rows_ext = compute_pass_rows(dict(op, p2_z_extend=2.0), params_for(op), mgr)
check(abs(rows_ext[0]["z"] - rows_plain[0]["z"] - 2.0) < 1e-9 and
      abs(rows_ext[0]["end_z"] - rows_plain[0]["end_z"] - 2.0) < 1e-9,
      "p2_z_extend shifts contact Z and end_z by +2.0")

# 9. Beyond-blank-edge warning (user feedback 2026-07-08: 'first pass far away,
#    no warning'): commanded reach far past the estimated flange → air-move
#    advisory. A reach comfortably inside the flange must NOT warn.
from process_planner import estimate_flange_reach
z0 = min_z + 5
fl = estimate_flange_reach(mgr, blank_r, z0)
check(fl > 1.0, f"precondition: flange estimate {fl:.1f}mm > 1 at test Z")
op = dict(BASE, count=1, start_z=z0, pass_angle=93.0, reach=fl + 25.0)
rows = compute_pass_rows(op, params_for(op), mgr)
_bb_head = t("pt_warn_beyond_blank").split("{")[0]
check(any(_bb_head in w for r in rows for w in r["warnings"]),
      "beyond-blank warning fires when reach overshoots the flange")
op = dict(BASE, count=1, start_z=z0, pass_angle=93.0, reach=max(fl - 5.0, 1.0))
rows = compute_pass_rows(op, params_for(op), mgr)
check(not any(_bb_head in w for r in rows for w in r["warnings"]),
      "no beyond-blank warning when reach stays inside the flange")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
