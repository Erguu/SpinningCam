# -*- coding: utf-8 -*-
"""Headless tests for the SCL Inspector's analysis layer.

The window is a viewer, but its NUMBERS are the whole point — if the flattened-
curve flag is wrong it is worse than no viewer at all. `analyze_plc_output` is
deliberately Tk-free so it can be tested directly."""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.dialogs.scl_inspector import analyze_plc_output, _chord_bulge, _poly_dev

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)

def params(tol=0.5, curl=-60.0, auto=False, budget=350, count=4):
    op = {"type": "roughing", "name": "Rough A", "count": count,
          "start_z": 10.0, "end_z": 50.0, "r_tool": 25.0, "clearance": 0.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": "forward", "p2_radius": 2.0,
          "exit_mid_t": 0.5}
    if curl:
        op["exit_mid_radius"] = curl
    return {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "collision_resolution": 0.5, "gcode_resolution": 2.0,
            "plc_mode": True, "plc_tolerance": tol, "plc_exit_tolerance": tol,
            "plc_auto_tune": auto, "plc_target_lines": budget}

def run(**kw):
    p = params(**kw)
    pg = PathGenerator()
    pg.calculate_paths(p, {}, mgr)
    pg.last_mandrel_mgr = mgr
    return pg, analyze_plc_output(pg, p), p

# ── geometry helpers ────────────────────────────────────────────────────
straight = np.stack([np.linspace(0, 10, 40), np.zeros(40), np.zeros(40)], axis=1)
check(_chord_bulge(straight) < 1e-9, "helper: a straight run has zero bulge")
th = np.linspace(0, 0.6, 60)
arc = np.stack([20 * np.sin(th), np.zeros(60), 20 * (1 - np.cos(th))], axis=1)
check(abs(_chord_bulge(arc) - 20 * (1 - np.cos(0.3))) < 0.05,
      f"helper: arc bulge matches the sagitta formula ({_chord_bulge(arc):.3f} mm)")
check(_poly_dev(arc, np.vstack([arc[0], arc[-1]])) > 0.5,
      "helper: deviation from a chord is measured, not assumed")

# ── no paths ────────────────────────────────────────────────────────────
check(analyze_plc_output(PathGenerator(), params())["ok"] is False,
      "no calculated paths → ok=False instead of raising")

# ── coarse tolerance flattens the curl and SAYS SO ──────────────────────
pg, d, p = run(tol=0.5)
check(d["ok"], "analysis runs on a real program")
check(d["source"] == "manual" and abs(d["tolerance"] - 0.5) < 1e-9,
      "manual tolerance reported when auto-tune is off")
check(d["dec_points"] < d["full_points"],
      f"decimation reduces points ({d['full_points']} → {d['dec_points']})")
bulges = [r["bulge"] for r in d["passes"]]
check(all(0.2 < b < 2.0 for b in bulges),
      f"curl's OWN bulge measured, not the whole exit's "
      f"(R60 → {min(bulges):.2f}–{max(bulges):.2f} mm; sagitta L²/8R for these "
      f"tails ≈ 0.5, whole-exit bulge would read several mm)")
degraded = [r for r in d["passes"] if r["state"] in ("flat", "coarse")]
check(len(degraded) > 0,
      f"R60 curl at 0.5mm tolerance is reported as degraded "
      f"({len(degraded)}/{len(d['passes'])} passes: "
      f"{sorted({r['state'] for r in degraded})})")

# A coarser tolerance than the bulge itself ⇒ the curve can vanish outright.
_pg, d_coarse, _ = run(tol=2.0)
check(any(r["state"] == "flat" for r in d_coarse["passes"]),
      "tolerance above the curl's bulge ⇒ flagged FLAT (curve may vanish)")

# ── fine tolerance keeps it, and the flags clear ────────────────────────
pg2, d2, _ = run(tol=0.02)
check(all(r["state"] == "ok" for r in d2["passes"]),
      "at 0.02mm tolerance every pass reports ok")
check(d2["dec_points"] > d["dec_points"],
      f"finer tolerance keeps more points ({d2['dec_points']} > {d['dec_points']})")
check(max(r["worst_dev"] for r in d2["passes"]) < max(r["worst_dev"] for r in d["passes"]),
      "finer tolerance lowers the worst path error")

# The FLAT flag must mean exactly one thing: the curve bulges less than the
# tolerance, so RDP is free to delete it entirely. Nothing looser.
_bad = None
for dd in (d, d2, d_coarse):
    for r in dd["passes"]:
        expect = (r["bulge"] > 0.02) and (r["bulge"] <= dd["exit_tolerance"])
        if r["flattened"] != expect:
            _bad = (dd["exit_tolerance"], r)
            break
    if _bad:
        break
check(_bad is None,
      "FLAT flag == (curve bulge <= exit tolerance) on every pass"
      + (f" — disagreed at tol={_bad[0]}, bulge={_bad[1]['bulge']:.3f}" if _bad else ""))

# ── worst_dev must respect the RDP guarantee ────────────────────────────
for dd, tol in ((d, 0.5), (d2, 0.02)):
    worst = max(r["worst_dev"] for r in dd["passes"])
    check(worst <= tol + 1e-6,
          f"worst error {worst:.4f} mm never exceeds the tolerance {tol} mm")

# ── a pass with no curl is not falsely flagged ──────────────────────────
pg3, d3, _ = run(tol=0.5, curl=None)
check(all(r["state"] == "ok" for r in d3["passes"]),
      "straight-exit passes are never flagged (nothing to lose)")
check(all(r["bulge"] <= 0.02 for r in d3["passes"]),
      "straight-exit passes report no curve bulge")

# ── auto-tune path: reports the FITTED tolerance, not the manual one ────
pg4, d4, _ = run(tol=0.5, auto=True, budget=60)
check(d4["source"] == "auto", "auto-tune result is used when enabled")
check(abs(d4["tolerance"] - 0.5) > 1e-6,
      f"fitted tolerance differs from the manual 0.5 (got {d4['tolerance']:.4f})")
if d4["lines"] is not None and d4["budget"]:
    check(d4["lines"] <= d4["budget"],
          f"reported line count fits the budget ({d4['lines']} <= {d4['budget']})")

# ── read-only: analysis must not mutate params or stored paths ──────────
p_before = params(tol=0.5, auto=True, budget=60)
pg5 = PathGenerator(); pg5.calculate_paths(p_before, {}, mgr); pg5.last_mandrel_mgr = mgr
snap = {k: (list(v) if isinstance(v, list) else v) for k, v in p_before.items()}
paths_before = [np.array(x, copy=True) for x in pg5.last_calculated_paths]
analyze_plc_output(pg5, p_before)
check(p_before["plc_tolerance"] == snap["plc_tolerance"]
      and p_before["plc_mode"] == snap["plc_mode"],
      "analysis does not mutate params")
check(all(np.array_equal(a, b) for a, b in zip(paths_before, pg5.last_calculated_paths)),
      "analysis does not mutate the calculated paths")

# ── widget smoke: the window must build, populate and redraw ────────────
try:
    import tkinter as tk
    from ui.dialogs.scl_inspector import SclInspectorDialog

    class _AppStub:
        pass

    root = tk.Tk(); root.withdraw()
    stub = _AppStub()
    stub.path_gen, stub.params = pg, p
    dlg = SclInspectorDialog(root, stub)
    # The canvas deliberately refuses to draw before it has a real size, so the
    # window has to be mapped for the drawing path to be exercised at all.
    dlg.deiconify()
    dlg.update()
    n_rows = len(dlg.tree.get_children())
    check(n_rows == len(d["passes"]), f"window lists every pass ({n_rows} rows)")
    check(bool(dlg.lbl_head.cget("text")), "header line is populated")
    dlg.tree.selection_set(dlg.tree.get_children()[0])
    dlg._draw()                                   # selection redraw must not raise
    check(len(dlg.canvas.find_all()) > 0, "canvas draws the overlay")
    dlg.refresh()                                 # re-entrant refresh must not raise
    check(len(dlg.tree.get_children()) == n_rows, "refresh is idempotent")
    dlg.destroy(); root.destroy()
except Exception as exc:                          # noqa: BLE001
    check(False, f"widget smoke raised: {exc!r}")

print()
print("FAILURES:" if fails else "ALL PASS", fails if fails else "")
raise SystemExit(1 if fails else 0)
