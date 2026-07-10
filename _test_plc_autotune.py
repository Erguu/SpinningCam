"""
Headless tests for the PLC auto-tune feature (opt-in adaptive tolerance).

Covers:
  1. PathGenerator.measure_min_clearance samples the STRAIGHT chords (not just the
     retained vertices), so a decimated corner-cut toward the mandrel is detected.
  2. PathGenerator.decimate_all_paths reduces point counts.
  3. ExportManager.auto_fit_plc_tolerance bisection: no_reduction_needed / ok /
     clearance_limited / infeasible_budget.

Run inside the `spinning_cam` conda env (path_generator pulls pythonocc):
    conda run -n spinning_cam python _test_plc_autotune.py
"""
import numpy as np


# --------------------------------------------------------------------------
# 1 & 2 — real PathGenerator (needs OCC via import)
# --------------------------------------------------------------------------
def test_clearance_and_decimation():
    from path_generator import PathGenerator

    class FakeMgr:
        # Triangular convex 'bump' peaking at z=5: R(0)=100, R(5)=108, R(10)=100.
        def get_radius_fast(self, z):
            if z < 0 or z > 10:
                return 100.0
            return 100.0 + 8.0 * (1.0 - abs(z - 5.0) / 5.0)

    pg = PathGenerator()
    pg.last_mandrel_mgr = FakeMgr()
    pg._path_op_map = [{"r_tool": 0.0, "type": "roughing"}]
    # base = blank + shell + r_tool = 0 → clearance = x - R(z)
    params = {"mandrel_pos_x_offset": 0.0,
              "final_part_thickness_on_mandrel": 0.0,
              "shell_thickness": 0.0}

    # Path hugging the bump at constant clearance 2 mm.
    A, B, C = [102.0, 0.0, 0.0], [110.0, 0.0, 5.0], [102.0, 0.0, 10.0]

    full = np.array([A, B, C])
    chord = np.array([A, C])   # what remains if the middle vertex is decimated away

    cl_full = pg.measure_min_clearance([full], params)
    cl_chord = pg.measure_min_clearance([chord], params)

    assert abs(cl_full - 2.0) < 0.05, f"full-path clearance should be ~2mm, got {cl_full}"
    assert cl_chord < -5.0, (
        f"chord across the bump must be detected as gouging (~-6mm), got {cl_chord}")
    print(f"[OK] chord-sampling: full={cl_full:.2f}mm  chord={cl_chord:.2f}mm (gouge caught)")

    # decimate_all_paths thins a dense, nearly-straight path.
    dense = np.array([[100.0, 0.0, z] for z in np.linspace(0, 50, 60)])
    pg.last_calculated_paths = [dense]
    pg.last_render_split_idx = {}
    dec = pg.decimate_all_paths(0.5, 0.5, 0.0)
    assert len(dec) == 1
    assert len(dec[0]) < len(dense), "decimation should drop collinear points"
    assert len(dec[0]) >= 2, "endpoints must survive"
    print(f"[OK] decimate_all_paths: {len(dense)} → {len(dec[0])} pts")


# --------------------------------------------------------------------------
# 3 — auto_fit bisection, isolated from the engine via a fake path_gen
# --------------------------------------------------------------------------
def _fake_pg():
    """A stand-in path_gen whose line count and clearance are deterministic
    functions of plc_tolerance:  lines shrink and clearance drops as tol grows."""
    class FakePG:
        def __init__(self):
            self.last_plc_paths = [np.zeros((1, 3))]
            self._last_cl = 0.0

        def generate_gcode(self, params=None):
            tol = float(params["plc_tolerance"])
            n = max(2, int(round(200.0 / (1.0 + tol * 20.0))))   # monotonic ↓ in tol
            self._last_cl = 1.0 - tol * 0.5                       # monotonic ↓ in tol
            body = "\n".join(f"G1 X{10+i:.1f} Z{i:.1f} F300" for i in range(n))
            return "%\nO1001\nM3 S1000\nG0 X10 Z10\n" + body + "\nM5\nM30\n"

        def measure_min_clearance(self, paths, params, sample_step=0.5):
            return self._last_cl
    return FakePG()


def test_autofit():
    from export_manager import ExportManager
    af = ExportManager.auto_fit_plc_tolerance

    # lines(tol_min=0.05) = round(200/2) = 100 → SCL lines ≈ 103 (M3+G0+100+M5)
    # no_reduction_needed: generous budget
    r = af(_fake_pg(), {}, target_lines=500, floor_clearance=0.0)
    assert r["status"] == "no_reduction_needed", r
    print(f"[OK] no_reduction_needed: {r['lines']} lines ≤ 500")

    # ok: budget forces coarsening, clearance stays above a low floor
    r = af(_fake_pg(), {}, target_lines=50, floor_clearance=0.5)
    assert r["status"] == "ok", r
    assert r["lines"] <= 50, r
    assert r["min_clearance"] >= 0.5 - 1e-6, r
    print(f"[OK] ok: tol={r['tolerance']:.3f} lines={r['lines']} clr={r['min_clearance']:.3f}")

    # clearance_limited: same budget but a demanding floor the fit can't hold
    r = af(_fake_pg(), {}, target_lines=50, floor_clearance=0.97)
    assert r["status"] == "clearance_limited", r
    assert r["lines"] <= 50, r
    assert r["min_clearance"] < 0.97, r
    print(f"[OK] clearance_limited: lines={r['lines']} clr={r['min_clearance']:.3f} < floor 0.97")

    # infeasible_budget: even coarsest tol can't reach a tiny budget
    r = af(_fake_pg(), {}, target_lines=3, floor_clearance=0.0)
    assert r["status"] == "infeasible_budget", r
    print(f"[OK] infeasible_budget: coarsest still {r['lines']} lines > 3")

    # Monotonic fit: smaller budget ⇒ coarser tolerance
    r_big = af(_fake_pg(), {}, target_lines=80, floor_clearance=0.0)
    r_small = af(_fake_pg(), {}, target_lines=30, floor_clearance=0.0)
    assert r_small["tolerance"] >= r_big["tolerance"], (r_small, r_big)
    print(f"[OK] monotonic: tol(30)={r_small['tolerance']:.3f} ≥ tol(80)={r_big['tolerance']:.3f}")


if __name__ == "__main__":
    test_clearance_and_decimation()
    test_autofit()
    print("\nALL PLC AUTO-TUNE TESTS PASSED")
