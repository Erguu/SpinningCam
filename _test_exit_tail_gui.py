# -*- coding: utf-8 -*-
"""Real-widget tests for the TODO #100 exit-tail editor.

Builds an actual ExitTailDialog against a withdrawn root (the house pattern —
Tk works headless in this env) and drives its logic directly:

  1. It seeds itself; the table is never empty.
  2. A legal edit is accepted.
  3. An edit that would gouge is REJECTED and the old value survives (D14).
  4. Add / delete keep every surviving point where it was.
  5. Toggling an anchor does not move the point.
  6. OK writes into pass_edits; Remove tail takes it back out.
  7. Every i18n key the dialog uses exists in EN/TR/ES.
  8. NEGATIVE-SIDE MACHINE: the seed reads a mirrored path but P2 is canonical,
     so it must mirror back. Regression for the 2026-08-27 bug (ΔX seeded at
     −270 and every typed value refused). Everything above runs on the default
     positive side, which is exactly why that bug got through.

    runtest.bat _test_exit_tail_gui.py
"""
import tkinter as tk

import numpy as np

import exit_waypoints as ew
import i18n
from i18n import t
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.dialogs.exit_tail_dialog import ExitTailDialog

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


class FakeApp:
    def __init__(self, op):
        self.mandrel_mgr = MandrelManager()
        self.mandrel_mgr.create_default_cone()
        self.mandrel_mgr.update_geometry(0, 0, 0, 0.0, 0.0)
        self.path_gen = PathGenerator()
        self.params = {
            "operations": [op],
            "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 0.0,
            "shell_thickness": 0.0,
        }


def make_op(**over):
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
          "clearance": 3.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": "forward"}
    op.update(over)
    return op


root = tk.Tk()
root.withdraw()

# P2 well clear of the cone so ordinary edits are legal.
mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
P2 = (mgr.get_radius_fast(30.0) + 25.0 + 8.0, 30.0)

op = make_op()
app = FakeApp(op)
applied = {}
dlg = ExitTailDialog(root, app, 0, 0, P2, lambda pts, shape=None: applied.update(points=pts, shape=shape))

# 1 — seeded, never blank
check(len(dlg.points) > 0, f"dialog seeds itself ({len(dlg.points)} points)")
check(len(dlg.tree.get_children()) == len(dlg.points), "table shows every point")

# 2 — a legal edit is accepted (nudge outward, away from the part)
before = [dict(p) for p in dlg.points]
cand = [dict(p) for p in dlg.points]
cand[0]["dx"] = float(cand[0]["dx"]) + 5.0
ok = dlg._try(cand, "test")
check(ok and dlg.points[0]["dx"] == before[0]["dx"] + 5.0,
      "a legal move outward is accepted")

# 3 — an edit that gouges is refused, and nothing changes (D14)
keep = [dict(p) for p in dlg.points]
bad = [dict(p) for p in dlg.points]
bad[0]["dx"] = -(P2[0] * 2.0)          # straight through the axis
ok = dlg._try(bad, "test")
check(not ok, "an edit into the part is refused")
check(dlg.points == keep, "the refused edit left the points untouched")
check("#ffecea" in str(dlg.lbl_status.cget("bg")), "refusal is shown on the status bar")

viol = dlg._violations(bad)
check(bool(viol) and viol[0]["clearance"] < 3.0,
      f"the violation is measured against the op clearance (got {viol[0]['clearance']:.2f})")

# 4 — add / delete preserve the other points' absolute positions
abs_before = ew.resolve(dlg.p2x, dlg.p2z, dlg.points)
n_before = len(dlg.points)
dlg.tree.selection_set("0")
dlg._add()
check(len(dlg.points) == n_before + 1, f"add inserts one point ({n_before} -> {len(dlg.points)})")
abs_after = ew.resolve(dlg.p2x, dlg.p2z, dlg.points)
kept = [a for a in abs_before
        if min(np.hypot(b[0] - a[0], b[1] - a[1]) for b in abs_after) < 1e-6]
check(len(kept) == len(abs_before), "adding a point moved none of the existing ones")

dlg.tree.selection_set("1")
dlg._delete()
check(len(dlg.points) == n_before, f"delete removes one point (-> {len(dlg.points)})")

# 5 — the anchor toggle re-expresses, it does not move
abs_pre = ew.resolve(dlg.p2x, dlg.p2z, dlg.points)
pts = [dict(p) for p in dlg.points]
k = 1
a = ew.resolve(dlg.p2x, dlg.p2z, dlg.points)[k]
prev_abs = ew.resolve(dlg.p2x, dlg.p2z, dlg.points)[k - 1]
pts[k].update(anchor="prev", dx=round(a[0] - prev_abs[0], 3), dz=round(a[1] - prev_abs[1], 3))
dlg._try(pts, "anchor")
abs_post = ew.resolve(dlg.p2x, dlg.p2z, dlg.points)
moved = max(np.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(abs_pre, abs_post))
check(moved < 1e-6, f"re-anchoring keeps every point in place (max move {moved:.2e} mm)")

# 6 — OK writes into pass_edits, Remove tail takes it back out
dlg._ok()
check("points" in applied and applied["points"], "OK hands the points to the caller")

op2 = make_op()
app2 = FakeApp(op2)
out = {}
d2 = ExitTailDialog(root, app2, 0, 0, P2, lambda pts, shape=None: out.update(points=pts, shape=shape))
d2.points = []
d2._ok()
check(out.get("points") == [], "Remove tail hands back an empty list")

# stored points are re-read rather than re-seeded
op3 = make_op(pass_edits={"0": {"exit_points": [
    {"anchor": "p2", "dx": 11.0, "dz": -3.0, "feed": None}]}})
d3 = ExitTailDialog(root, FakeApp(op3), 0, 0, P2, lambda pts: None)
check(len(d3.points) == 1 and d3.points[0]["dx"] == 11.0,
      "an existing tail is loaded, not overwritten by the seed")

# 7 — i18n completeness for every key the dialog touches
KEYS = ["et_shape", "et_shape_straight", "et_shape_spline", "et_hint_cost",
        "et_what_shape",
        "et_title", "et_help", "et_col_anchor", "et_col_dx", "et_col_dz", "et_col_feed",
        "et_anchor_p2", "et_anchor_prev", "et_hint", "et_btn_add", "et_btn_del",
        "et_btn_seed", "et_btn_clear", "et_btn_ok", "et_btn_cancel", "et_edit_title",
        "et_edit_prompt", "et_bad_number", "et_need_one", "et_refused",
        "et_refused_commit", "et_what_move", "et_what_anchor", "et_what_feed",
        "et_what_add", "et_what_del", "et_what_seed", "et_title_seed",
        "et_confirm_seed", "et_title_clear", "et_confirm_clear", "et_end_marker",
        "pt_btn_tail", "pt_tail_pick", "pt_tail_excluded", "lbl_exit_mode_tail",
        "msg_continue_waypoints"]
missing = [k for k in KEYS if k not in i18n.STRINGS]
check(not missing, f"every dialog i18n key exists (missing: {missing})")
half = [k for k in KEYS if k in i18n.STRINGS
        and not all(lg in i18n.STRINGS[k] for lg in ("EN", "TR", "ES"))]
check(not half, f"every dialog key has EN/TR/ES (incomplete: {half})")

# 8 — negative-side machine: the seed must come back into the canonical frame
#
# The engine mirrors X around the mandrel centre at the END of calculate_paths
# (path_generator.py:1141), so last_calculated_paths is in MACHINE X while P2
# (compute_pass_rows, matching path_generator.py:861) is canonical. Feed the
# dialog a mirrored path and check the seed lands back on the canonical one.
CANON_TAIL = [(P2[0] + 5.0, 31.0), (P2[0] + 11.0, 32.0),
              (P2[0] + 17.0, 33.0), (P2[0] + 23.0, 34.0)]
CANON_PATH = [(P2[0] - 20.0, 26.0), (P2[0] - 6.0, 29.0),
              (P2[0] + 0.5, 30.0)] + CANON_TAIL          # index 2 = T2


def app_with_path(positive_side):
    """A FakeApp whose path_gen carries one pass, stored the way the engine
    stores it: canonical on a positive-side machine, mirrored on a negative one."""
    a = FakeApp(make_op())
    a.params["roller_positive_x_side"] = positive_side
    sign = 1.0 if positive_side else -1.0
    a.path_gen.last_calculated_paths = [
        np.array([[sign * x, 0.0, z] for x, z in CANON_PATH], dtype=float)]
    a.path_gen._path_op_map = [a.params["operations"][0]]
    a.path_gen.last_render_split_idx = {0: (1, 2)}
    return a

neg = app_with_path(False)
d8 = ExitTailDialog(root, neg, 0, 0, P2, lambda pts: None)
seeded = d8.points
check(len(seeded) == 4, f"negative side: seeded from the real path ({len(seeded)} points)")

worst = min(p["dx"] for p in seeded)
check(worst > -100.0,
      f"negative side: no wrong-frame ΔX (min {worst:.1f}, pre-fix was ~{-2 * P2[0]:.0f})")

got = ew.resolve(d8.p2x, d8.p2z, seeded)
err = max(np.hypot(g[0] - c[0], g[1] - c[1]) for g, c in zip(got, CANON_TAIL))
check(err < 1e-6,
      f"negative side: the seed resolves onto the canonical path (max err {err:.2e} mm)")

# The whole point of the bug report: a sane number was refused. It must not be.
cand = [dict(p) for p in seeded]
cand[0]["dx"] = float(cand[0]["dx"]) + 4.0        # nudge 4 mm further out
check(d8._try(cand, "test"), "negative side: an ordinary outward nudge is ACCEPTED")

# ...while a genuine gouge is still caught, on this side too.
gouge = [dict(p) for p in d8.points]
gouge[0]["dx"] = -P2[0] * 2.0
check(not d8._try(gouge, "test"), "negative side: a real gouge is still refused")

# Same canonical geometry, either side → identical stored numbers.
d8p = ExitTailDialog(root, app_with_path(True), 0, 0, P2, lambda pts: None)
same = (len(d8p.points) == len(seeded)
        and all(abs(a["dx"] - b["dx"]) < 1e-9 and abs(a["dz"] - b["dz"]) < 1e-9
                for a, b in zip(d8p.points, seeded)))
check(same, "the stored tail is side-independent (same numbers on either machine)")

# 9 — the tail STARTS at exactly the op clearance, and that must be legal
#
# Field report 2026-08-27: every point of every pass refused with
# "1.70 mm from the part ... needs at least 1.70 mm" — the same number twice,
# reported at P2's own Z. Two causes, both here:
#   (a) the dialog was handed round(p2_x_abs, 2); P2 sits at EXACTLY the
#       clearance, so rounding a few µm inward put the tail's own start inside.
#   (b) an exact comparison makes "exactly on the clearance contour" — which is
#       what P2 is by construction — a knife edge.
CLR = 1.70
z_c = 30.0
p2_exact = mgr.get_radius_fast(z_c) + 25.0 + CLR      # r + r_tool + clearance
tight = make_op(clearance=CLR, start_z=z_c)
app_t = FakeApp(tight)

d9 = ExitTailDialog(root, app_t, 0, 0, (p2_exact, z_c), lambda p: None)
check(abs(d9._clearance() - CLR) < 1e-9,
      f"the dialog reads the op clearance ({d9._clearance():.2f})")

# A tail that hugs the clearance contour: every point exactly at the limit.
hug = [{"anchor": "p2", "feed": None, "dx": 0.0, "dz": dz}
       for dz in (0.45, 0.86, 1.26, 1.66)]
hug = [{**w, "dx": round(mgr.get_radius_fast(z_c + w["dz"]) - mgr.get_radius_fast(z_c), 6)}
       for w in hug]
v = d9._violations(hug)
check(not v, f"a tail lying ON the clearance contour is allowed ({len(v)} flagged)")

# Worst-case 2-decimal rounding is 5 µm INWARD. That is 5x CLEARANCE_EPS, so the
# tolerance alone does NOT cover it — which is exactly why the pass table now
# hands over p2x_exact instead of the rounded display value. Characterise both
# halves so neither fix can be dropped in the belief the other one covers it.
d9r = ExitTailDialog(root, app_t, 0, 0, (p2_exact - 0.005, z_c), lambda p: None)
check(bool(d9r._violations(hug)),
      "a 5 um inward P2 (what rounding did) DOES refuse - so exact P2 is required")
check(0.005 > ew.CLEARANCE_EPS,
      f"...because rounding drift ({5:.0f} um) exceeds CLEARANCE_EPS "
      f"({ew.CLEARANCE_EPS * 1000:.0f} um)")

# And the pass table supplies that exact value.
import ui.dialogs.pass_table as _pt
src = open(_pt.__file__, encoding="utf-8").read()
check('"p2x_exact"' in src and 'row.get("p2x_exact"' in src,
      "compute_pass_rows exports p2x_exact and the tail editor consumes it")

# ...and a genuine gouge is still caught at this tight clearance.
dig = [dict(w) for w in hug]
dig[1]["dx"] = dig[1]["dx"] - 0.5              # 0.5 mm into the part
check(bool(d9._violations(dig)), "0.5 mm into the part is still refused at 1.70 mm clearance")

# clearance falls back to the machine default when the op does not carry one
noc = make_op()
noc.pop("clearance")
app_n = FakeApp(noc)
app_n.params["target_clearance"] = 2.5
d10 = ExitTailDialog(root, app_n, 0, 0, P2, lambda p: None)
check(abs(d10._clearance() - 2.5) < 1e-9,
      f"an op with no clearance inherits the machine default (got {d10._clearance():.2f}, not 0)")

# 10 — the shape selector (user 2026-08-27: straight is what this machine needs)
op_s = make_op()
got = {}
d11 = ExitTailDialog(root, FakeApp(op_s), 0, 0, P2,
                     lambda pts, shape=None: got.update(points=pts, shape=shape))
check(d11.shape_var.get() == ew.SHAPE_STRAIGHT, "the dialog opens on Straight lines")

n_pts = len(d11.points)
n_straight = len(ew.build_curve(d11.p2x, d11.p2z, d11.points, shape=ew.SHAPE_STRAIGHT))
n_spline = len(ew.build_curve(d11.p2x, d11.p2z, d11.points, shape=ew.SHAPE_SPLINE))
check(n_straight == n_pts + 1,
      f"straight emits one point per waypoint ({n_pts} -> {n_straight} incl. P2)")
check(n_spline > 5 * n_straight, f"the curve costs far more ({n_spline} vs {n_straight})")

# the status line tells the operator the price, which is the whole point
hint = d11._ok_hint()
check(str(n_pts) in hint and str(n_straight - 1) in hint,
      f"the status line states the point cost (got: {hint[:60]}...)")

# OK carries the shape; straight (the default) is NOT written to the file
d11._ok()
check(got.get("shape") == ew.SHAPE_STRAIGHT, "OK hands the shape back to the caller")

# switching to the curve is remembered
op_c = make_op()
got_c = {}
d12 = ExitTailDialog(root, FakeApp(op_c), 0, 0, P2,
                     lambda pts, shape=None: got_c.update(points=pts, shape=shape))
d12.shape_var.set(ew.SHAPE_SPLINE)
d12._on_shape()
d12._ok()
check(got_c.get("shape") == ew.SHAPE_SPLINE, "a curve tail reports shape=spline")

# a stored spline reopens as a spline
op_st = make_op(pass_edits={"0": {
    "exit_points": [{"anchor": "p2", "dx": 11.0, "dz": -3.0, "feed": None}],
    "exit_shape": "spline"}})
d13 = ExitTailDialog(root, FakeApp(op_st), 0, 0, P2, lambda p, s=None: None)
check(d13.shape_var.get() == ew.SHAPE_SPLINE, "a stored curve tail reopens as a curve")

# an unknown token in a hand-edited file falls back to straight, not to the old curve
op_bad = make_op(pass_edits={"0": {
    "exit_points": [{"anchor": "p2", "dx": 11.0, "dz": -3.0, "feed": None}],
    "exit_shape": "wobbly"}})
d14 = ExitTailDialog(root, FakeApp(op_bad), 0, 0, P2, lambda p, s=None: None)
check(d14.shape_var.get() == ew.SHAPE_STRAIGHT, "an unknown shape token falls back to straight")

# 11 — the PASS TABLE must describe the pass that actually runs (D19/D20)
#
# Field report 2026-08-27: with a tail active, the pass table still drew a plain
# linear pass and reported the parametric Reach / End Z — i.e. a pass that was
# not the one running. compute_pass_rows now resolves the tail itself.
from ui.dialogs.pass_table import compute_pass_rows

TAIL = [{"anchor": "p2", "dx": 6.0, "dz": 1.0, "feed": None},
        {"anchor": "prev", "dx": 6.0, "dz": 1.0, "feed": None},
        {"anchor": "prev", "dx": 6.0, "dz": 1.0, "feed": None}]

pt_params = {"mandrel_pos_x_offset": 0.0, "final_part_thickness_on_mandrel": 0.0,
             "shell_thickness": 0.0, "target_clearance": 1.0}

op_plain = make_op(reach=40.0, pass_angle=170.0)
op_tail = make_op(reach=40.0, pass_angle=170.0,
                  pass_edits={"0": {"exit_points": TAIL}})

row_p = compute_pass_rows(op_plain, pt_params, mgr)[0]
row_t = compute_pass_rows(op_tail, pt_params, mgr)[0]

check(row_p["reach"] is not None and row_t["reach"] is None,
      "D20: Reach is a number without a tail and a dash with one")
check(row_t["angle"] is None, "D20: Pass Angle is a dash on a tail pass")
check(len(row_t.get("tail") or []) == 3,
      f"the row carries the resolved waypoints ({len(row_t.get('tail') or [])})")

# the endpoint must be the LAST waypoint, not the parametric P3
exp_x = row_t["p2x_exact"] + 18.0        # 3 steps of dx=6 from P2
exp_z = row_t["z_exact"] + 3.0
check(abs(row_t["end_x"] - exp_x) < 1e-6 and abs(row_t["end_z"] - exp_z) < 1e-6,
      f"End is the last waypoint ({row_t['end_x']:.2f},{row_t['end_z']:.2f}) "
      f"not the parametric P3 ({row_p['end_x']:.2f},{row_p['end_z']:.2f})")
check(abs(row_t["end_x"] - row_p["end_x"]) > 1.0,
      "...and that really differs from what the table showed before")
check(t("pt_src_tail").format(n=3) == row_t["source"],
      f"the Source column names it a tail (got '{row_t['source']}')")

# a tail must not inherit warnings computed from the exit it replaced
_guard = t("pt_warn_guard").format(c=1.0)
check(all(_guard not in w for w in row_t["warnings"]),
      f"no stale clearance-guard warning on a tail pass (got {row_t['warnings']})")

# and D10-excluded ops keep the old parametric behaviour entirely
row_rev = compute_pass_rows(make_op(reach=40.0, pass_angle=170.0, direction="reverse",
                                    pass_edits={"0": {"exit_points": TAIL}}),
                            pt_params, mgr)[0]
check(not (row_rev.get("tail") or []) and row_rev["reach"] is not None,
      "D10: a reverse op shows no tail and keeps its Reach")

root.destroy()

print()
if fails:
    raise SystemExit(f"{fails} FAILED")
print("ALL PASS")
