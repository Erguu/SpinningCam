# -*- coding: utf-8 -*-
"""Headless test for provenance + recipe audit (recipe_explain.py).

Covers the real case that motivated it: op #8 of "13. uzun pasolu.ssp" had a
per-pass reach pin of 118 on pass 1 while the operation panel said 95.26 and
follow-blank drove the other passes — invisible in the UI, and the row-level
Source column said "pin" on all three rows so it could not localise the field.

Also guards the additive-only promise: provenance must not change any number
compute_pass_rows produced before it existed.
"""
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.dialogs.pass_table import compute_pass_rows
from recipe_explain import (audit_operations, explain_field, find_overrides,
                            format_report, group_overrides, outlier_fields,
                            SEV_ORDER)

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

def params_for(ops, **kw):
    p = {"operations": ops if isinstance(ops, list) else [ops],
         "blank_radius": blank_r, "auto_calc_angle": False, "min_safety_gap": -999.0,
         "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
         "target_clearance": 0.0}
    p.update(kw)
    return p

BASE = {"type": "roughing", "pass_shape": "linear_full", "r_tool": 25.0,
        "clearance": 0.1, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0}

# ── 1. The op-8 shape: op reach + follow-blank + a reach pin on pass 1 only ──
# Faithful to the real op #8: anchor / extend / clearance / angle pinned on
# EVERY pass (a hand-built ramp), reach pinned on pass 1 ONLY (the anomaly).
op8 = dict(BASE, count=3, start_z=min_z + 10, end_z=min_z + 30, pass_angle=129.0,
           reach=95.26, reach_follow_blank=True, reach_blank_factor=1.05,
           pass_edits={"0": {"target_z": min_z + 5, "p2_z_extend": 11.0,
                             "clearance": 0.2, "pass_angle": 117.0, "reach": 118.0},
                       "1": {"target_z": min_z + 5, "p2_z_extend": 12.0,
                             "clearance": 0.2, "pass_angle": 118.0},
                       "2": {"target_z": min_z + 5, "p2_z_extend": 13.0,
                             "clearance": 0.2, "pass_angle": 119.0}})
rows = compute_pass_rows(op8, params_for(op8), mgr)
check(abs(rows[0]["reach"] - 118.0) < 0.01, f"pass 1 reach = pinned 118 (got {rows[0]['reach']})")
check(rows[0]["prov"]["reach"]["source"] == "pin", "pass 1 reach provenance = pin")
losers = rows[0]["prov"]["reach"]["losers"]
check([s for s, _ in losers] == ["follow", "op"],
      f"pin beat follow then op, in that order (got {[s for s, _ in losers]})")
check(rows[1]["prov"]["reach"]["source"] == "follow",
      f"pass 2 reach comes from follow-blank (got {rows[1]['prov']['reach']['source']})")

# The whole point: which FIELD is manual, per pass. Row-level 'source' cannot.
check(all(r["source"] == "⭑ pin" or r["pinned"] for r in rows),
      "precondition: row-level Source says 'pin' on ALL three rows (the old blind spot)")
f0 = dict(find_overrides(rows[0]))
check("reach" in f0, f"pass 1 flags reach as a hidden override (got {sorted(f0)})")
check("reach" not in dict(find_overrides(rows[1])), "pass 2 does NOT flag reach")

txt = explain_field(rows[0], "reach")
check("118" in txt and "95.26" in txt.replace(",", "."),
      f"explanation names the value AND what it overrode: {txt!r}")

# ── 2. A pin that merely repeats the automatic value is not a finding ────────
# The automatic value must be read from the SAME op the pin will sit in —
# dropping the other pins moves the anchor, and with it the follow-blank reach.
op_nopin = dict(op8, pass_edits={})
auto = compute_pass_rows(op_nopin, params_for(op_nopin), mgr)[2]["reach"]
op_same = dict(op_nopin, pass_edits={"2": {"reach": round(auto, 3)}})
rows_same = compute_pass_rows(op_same, params_for(op_same), mgr)
check(rows_same[2]["prov"]["reach"]["source"] == "pin", "precondition: still a pin")
check("reach" not in dict(find_overrides(rows_same[2])),
      "pin equal to the automatic value is suppressed as noise")

# ── 3. Fan provenance: progressive angle/reach name themselves ───────────────
op_fan = dict(BASE, count=4, start_z=min_z + 10, end_z=min_z + 30, pass_angle=120.0,
              reach=40.0, progressive_angle_enabled=True, progressive_angle_end=170.0,
              progressive_reach_enabled=True, progressive_reach_end=25.0)
rf = compute_pass_rows(op_fan, params_for(op_fan), mgr)
check(rf[2]["prov"]["angle"]["source"] == "fan" and rf[2]["prov"]["reach"]["source"] == "fan",
      "fanned pass attributes both angle and reach to the fan")
check(not find_overrides(rf[2]), "fan values are not reported as manual overrides")

# ── 4. Additive-only: provenance changed no computed number ─────────────────
#     Cross-check against the ENGINE, same way _test_pass_table.py does.
for op in (op8, op_fan):
    p = params_for(op)
    pg.calculate_paths(p, {}, mgr)
    r = compute_pass_rows(op, p, mgr)
    check(abs(r[-1]["reach"] - pg.last_op_reach[0]) < 0.05,
          f"table last-row reach {r[-1]['reach']} still matches engine {pg.last_op_reach[0]:.2f}")
    check(abs(r[-1]["angle"] - pg.last_op_end_angle[0]) < 0.01,
          f"table last-row angle {r[-1]['angle']} still matches engine {pg.last_op_end_angle[0]:.2f}")

# ── 5. Audit: finds the pin, the legacy override, gouge risk, negative clr ───
tools = [{"id": "T004", "radius": 44.56}]
ops = [dict(op8, name="Rough A", tool_id="T004", r_tool=44.56),
       dict(BASE, name="Rough A", tool_id="T004", r_tool=40.0, count=1,
            start_z=min_z + 5, pass_angle=120.0, reach=50.0, clearance=-0.4),
       dict(BASE, name="Off one", enabled=False, count=1, start_z=min_z + 5,
            pass_overrides={"0": {"reach": 46.23}})]
found = audit_operations(params_for(ops), mgr, gui_overrides={1: {"reach": 46.2}},
                         tools=tools)
msgs = [f["msg"] for f in found]
sevs = [f["sev"] for f in found]
check(any(f["field"] == "reach" and f["pass"] == 1 and f["op"] == 0 for f in found),
      "audit pinpoints op #1 pass 1 reach")
check(any(f["sev"] == "error" and "44.56" in f["msg"] for f in found),
      "audit raises gouge risk (r_tool 40 < radius 44.56) as an error")
check(any("negative" in m.lower() or "-0.4" in m for m in msgs),
      "audit reports the negative clearance")
check(any(f["sev"] == "warn" and f["pass"] == 2 for f in found),
      "audit surfaces the legacy per-pass override on the right pass")
check(sevs == sorted(sevs, key=lambda s: SEV_ORDER[s]),
      "findings sorted most-severe first")
check(any("pass_overrides" in m for m in msgs), "audit names the inert leftover key")

# ── 5b. The odd-one-out gets its own RED tier, ramps stay quiet ─────────────
odd_f = [f for f in found if f["sev"] == "hidden"]
check([f["field"] for f in odd_f] == ["reach"],
      f"only the outlier field is tiered 'hidden' (got {[f['field'] for f in odd_f]})")
check(all(f["sev"] == "info" for f in found
          if f["field"] in ("extend", "angle") and f["op"] == 0),
      "hand-built ramps stay at info — they must not compete with the outlier")
check(SEV_ORDER["hidden"] < SEV_ORDER["warn"],
      "'hidden' outranks the amber advisories so it sorts to the top")
check(found[0]["sev"] in ("error", "hidden"), "most serious finding is first")

# ── 5c. Shared grouping drives BOTH the audit and the table highlight ───────
g = group_overrides(rows)          # rows = op8 from section 1
check(set(g["odd"]) == {"reach"}, f"grouping: reach is the odd one ({sorted(g['odd'])})")
check(set(g["ramp"]) == {"anchor", "extend", "clr", "angle"},
      f"grouping: the rest are ramps ({sorted(g['ramp'])})")
om = outlier_fields(rows)
check(om == {0: {"reach"}}, f"outlier map marks only pass 1's reach (got {om})")
check(outlier_fields([]) == {}, "empty rows → no outliers, no crash")

# ── 6. No mandrel → file-level checks still run, no crash ───────────────────
nogeo = audit_operations(params_for(ops), None, tools=tools)
check(any(f["sev"] == "error" for f in nogeo), "gouge check works without geometry")
check(all(f["pass"] is None for f in nogeo), "no per-pass findings without geometry")

# ── 7. Clean recipe → nothing alarming ──────────────────────────────────────
#     Reach must stay INSIDE the estimated flange, otherwise the resolver's
#     pre-existing "exit beyond blank edge" advisory fires (correctly) and this
#     recipe is not clean.
from process_planner import estimate_flange_reach
inside = max(min(estimate_flange_reach(mgr, blank_r, min_z + 10 + k * 10)
                 for k in range(3)) - 5.0, 5.0)
clean = dict(BASE, name="Plain", count=3, start_z=min_z + 10, end_z=min_z + 30,
             pass_angle=120.0, reach=inside, tool_id="T004", r_tool=44.56)
cf = audit_operations(params_for([clean]), mgr, tools=tools)
check(not [f for f in cf if f["sev"] != "info"],
      f"clean recipe raises nothing above info ({[f['msg'] for f in cf if f['sev'] != 'info']})")
check(isinstance(format_report(cf), str), "report renders")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
