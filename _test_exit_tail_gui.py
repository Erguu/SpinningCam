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

    runtest.bat _test_exit_tail_gui.py
"""
import tkinter as tk

import numpy as np

import exit_waypoints as ew
import i18n
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
dlg = ExitTailDialog(root, app, 0, 0, P2, lambda pts: applied.update(points=pts))

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
d2 = ExitTailDialog(root, app2, 0, 0, P2, lambda pts: out.update(points=pts))
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
KEYS = ["et_title", "et_help", "et_col_anchor", "et_col_dx", "et_col_dz", "et_col_feed",
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

root.destroy()

print()
if fails:
    raise SystemExit(f"{fails} FAILED")
print("ALL PASS")
