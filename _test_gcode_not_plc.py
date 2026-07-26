# -*- coding: utf-8 -*-
"""The .nc export must be FULL RESOLUTION regardless of PLC mode (2026-07-26).

PLC mode / auto-tune exist to fit the PLC recipe, and the PLC is fed by the SCL
export — not by the .nc file. The Machine-tab tooltip has always said "CNC çıktısı
(normal G-code kaydetme) bundan etkilenmez", but `SpinningApp.save_gcode` passed
`self.params` straight through, so a 0.5 mm tolerance silently rewrote the .nc
(1971 lines -> 128, exit curls flattened to 3 points in NCViewer).

Also pins the other half: the SCL path must STILL decimate."""
import os
import tempfile
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)

def make_params(plc, tol=0.5):
    op = {"type": "roughing", "count": 4, "start_z": 10.0, "end_z": 50.0,
          "r_tool": 25.0, "clearance": 0.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": "forward", "p2_radius": 2.0,
          "exit_mid_t": 0.5, "exit_mid_radius": -60.0}
    return {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "collision_resolution": 0.5, "gcode_resolution": 2.0,
            "plc_mode": plc, "plc_tolerance": tol, "plc_exit_tolerance": tol}

def g_lines(s):
    return len([l for l in s.splitlines() if l.strip().startswith("G")])

# ── 1. The engine still honours plc_mode when it is asked to (unchanged) ──
pg = PathGenerator()
p_off, p_on = make_params(False), make_params(True)
pg.calculate_paths(p_off, {}, mgr); g_off = pg.generate_gcode(params=p_off)
pg.calculate_paths(p_on, {}, mgr);  g_on  = pg.generate_gcode(params=p_on)
check(g_lines(g_on) < g_lines(g_off),
      f"engine: plc_mode still decimates when asked ({g_lines(g_off)} → {g_lines(g_on)} lines)")

# ── 2. THE FIX: SpinningApp.save_gcode ignores plc_mode entirely ──────────
os.environ.setdefault("SPINCAM_HEADLESS", "1")
from main import SpinningApp

app = SpinningApp(headless=True)
app.mandrel_mgr = mgr
app.path_gen.last_mandrel_mgr = mgr

def export_nc(plc, tol=0.5):
    app.params.update(make_params(plc, tol))
    app.path_gen.calculate_paths(app.params, {}, mgr)
    fd, tmp = tempfile.mkstemp(suffix=".nc"); os.close(fd)
    app.save_gcode(True, filepath=tmp)
    with open(tmp, "r") as fh:
        txt = fh.read()
    os.unlink(tmp)
    return txt

nc_off = export_nc(False)
nc_on  = export_nc(True)
nc_on_coarse = export_nc(True, tol=2.0)
check(nc_off == nc_on,
      f"save_gcode: PLC mode ON == OFF, byte-identical ({g_lines(nc_off)} lines)")
check(nc_off == nc_on_coarse,
      "save_gcode: even a very coarse 2.0 mm tolerance cannot touch the .nc")
check(g_lines(nc_off) > g_lines(g_on),
      f"save_gcode: .nc keeps full resolution ({g_lines(nc_off)} vs decimated {g_lines(g_on)})")

# ── 3. The curl actually survives in the exported .nc ─────────────────────
def exit_pts(txt):
    """Count distinct G1 moves — a flattened curl collapses to almost none."""
    return len([l for l in txt.splitlines() if l.strip().startswith("G1")])
check(exit_pts(nc_on) == exit_pts(nc_off) and exit_pts(nc_on) > 40,
      f"curl survives in the .nc with PLC mode on ({exit_pts(nc_on)} G1 moves)")

# ── 4. The SCL side must STILL decimate (that is what PLC mode is for) ────
from export_manager import ExportManager
app.params.update(make_params(True))
app.path_gen.calculate_paths(app.params, {}, mgr)
floor = app.path_gen.measure_min_clearance(app.path_gen.last_calculated_paths, app.params)
res = ExportManager.auto_fit_plc_tolerance(app.path_gen, app.params, 60, floor)
check(res.get("lines", 0) <= 60 or res.get("status") == "infeasible_budget",
      f"SCL auto-tune still fits the budget (status={res.get('status')}, "
      f"lines={res.get('lines')}, tol={res.get('tolerance')})")
check(res.get("tolerance") is not None, "SCL auto-tune still returns a tolerance")

print()
print("FAILURES:" if fails else "ALL PASS", fails if fails else "")
raise SystemExit(1 if fails else 0)
