"""Headless verification for the opt-in start edge-fillet straightening feature.

Covers:
  - the geometry helpers get_straightened_radius / get_straightened_normal on a
    cylinder-with-fillet profile (extrapolate the wall below the transition, identical
    to get_radius_fast above it) and on a steep cone (no flat run -> never straightened)
  - integration through calculate_paths for STRAIGHT-LINE finishing and ROUGHING with
    the flag on vs off, and the regression that flag-off output is byte-identical
The mandrel-side is inherently gouge-safe: the straightened line sits OUTSIDE the fillet.
"""
import math
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

pg = PathGenerator()

WALL_R = 75.0
FILLET_R = 10.0          # quarter-circle fillet radius
FLAT_Z = 10.0            # wall begins here; fillet occupies z in [0, 10]


def make_cyl_fillet():
    """Cylinder wall (r=75, z>=10) with a concave quarter-circle fillet down to z=0."""
    m = MandrelManager()
    z = np.linspace(0.0, 100.0, 401)
    r = np.where(
        z >= FLAT_Z,
        WALL_R,
        (WALL_R - FILLET_R) + np.sqrt(np.maximum(0.0, FILLET_R**2 - (z - FLAT_Z)**2)),
    )
    m.profile_z = z
    m.profile_r = r
    m.props = {"h": 100.0, "br": r[0], "tr": WALL_R, "top_z": 100.0, "min_z": 0.0}
    return m


# --- 1. geometry helpers: cylinder-with-fillet -----------------------------
m = make_cyl_fillet()

flat_z = m.get_flat_start_z()
assert flat_z is not None and 8.0 <= flat_z <= 12.0, flat_z
print(f"flat-start detected at z={flat_z:.2f}: OK (~fillet top)")

# raw follows the fillet (radius dips below the wall); straightened extrapolates the wall
raw2 = m.get_radius_fast(2.0)
str2 = m.get_straightened_radius(2.0)
assert raw2 < WALL_R - 1.0, raw2                       # fillet really dips
assert abs(str2 - WALL_R) < 0.5, str2                  # extrapolated back to the wall
assert str2 > raw2 + 2.0, (str2, raw2)                 # straightened sits outside fillet
print(f"z=2  raw={raw2:.2f}  straightened={str2:.2f}: OK (wall extrapolated)")

# at/above the transition the two are identical (no change on the flat wall)
for z in (FLAT_Z + 5.0, 50.0, 90.0):
    assert abs(m.get_straightened_radius(z) - m.get_radius_fast(z)) < 1e-9, z
print("above transition: straightened == raw: OK")

# straightened normal below the transition is the constant wall normal (radial here)
nx, nz = m.get_straightened_normal(2.0)
assert nx > 0.999 and abs(nz) < 0.02, (nx, nz)
print(f"z=2 straightened normal=({nx:.3f},{nz:.3f}): OK (radial wall)")

# --- 2. geometry helpers: steep cone has no flat run -> never straightened --
mc = MandrelManager()
zc = np.linspace(0.0, 100.0, 201)
mc.profile_z = zc
mc.profile_r = 60.0 - 0.5 * zc          # slope 0.5 >> 0.08 -> get_flat_start_z None
mc.props = {"h": 100.0, "br": 60.0, "tr": 10.0, "top_z": 100.0, "min_z": 0.0}
assert mc.get_flat_start_z() is None
for z in (2.0, 25.0, 80.0):
    assert mc.get_straightened_radius(z) == mc.get_radius_fast(z), z
    assert mc.get_straightened_normal(z) == mc.get_normal_at_z(z), z
print("steep cone (no flat run) -> straightened == raw everywhere: OK")

# --- 3. integration through calculate_paths --------------------------------
base = {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0,
        "max_spin_rpm": 2000}
BLANK = 2.0
S_Z, E_Z = 2.0, 60.0          # start Z sits INSIDE the fillet
R_TOOL = 30.0
CLR = 2.0
TOTAL_OFF = R_TOOL + BLANK + CLR   # 34


def _first_forming_path(toolpaths):
    # the straight-line pass is the only 2-point forming path here
    for p in toolpaths:
        if len(p) == 2:
            return np.asarray(p, dtype=float)
    raise AssertionError("no 2-point forming path found")


def sl_finish_op():
    return {"type": "finishing", "count": 1, "tool_id": "T0101", "r_tool": R_TOOL,
            "clearance": CLR, "start_z": S_Z, "end_z": E_Z, "straight_line_mode": True}


# straight-line finishing: flag OFF follows the fillet, flag ON holds the wall
m = make_cyl_fillet()
p_off = dict(base); p_off["operations"] = [sl_finish_op()]
tp_off = pg.calculate_paths(p_off, {}, m)[0]
ps_off = _first_forming_path(tp_off)[0]

m = make_cyl_fillet()
p_on = dict(base); p_on["operations"] = [sl_finish_op()]; p_on["straighten_start_fillet"] = True
tp_on = pg.calculate_paths(p_on, {}, m)[0]
ps_on = _first_forming_path(tp_on)[0]

# ON: start contact anchored to the extrapolated wall (r=75) + radial offset
assert abs(ps_on[0] - (WALL_R + TOTAL_OFF)) < 0.5, ps_on          # ~109
assert abs(ps_on[2] - S_Z) < 0.05, ps_on                         # Z unchanged (radial normal)
# OFF: start pulled inward/tilted by the fillet -> smaller X than ON
assert ps_on[0] > ps_off[0] + 2.0, (ps_on[0], ps_off[0])
print(f"straight-line finish: OFF start X={ps_off[0]:.2f}  ON start X={ps_on[0]:.2f}: OK")


def rough_op():
    return {"type": "roughing", "count": 3, "tool_id": "T0101", "r_tool": R_TOOL,
            "clearance": CLR, "start_z": S_Z, "end_z": E_Z}


# roughing: flag ON lifts the first pass's P2 contact off the fillet toward the wall
m = make_cyl_fillet()
pr_off = dict(base); pr_off["operations"] = [rough_op()]
tp_r_off = pg.calculate_paths(pr_off, {}, m)[0]

m = make_cyl_fillet()
pr_on = dict(base); pr_on["operations"] = [rough_op()]; pr_on["straighten_start_fillet"] = True
tp_r_on = pg.calculate_paths(pr_on, {}, m)[0]

# The first roughing pass targets Z=S_Z (in the fillet). Its deepest point (min X =
# the P2 contact closest to the axis) is what straightening lifts outward toward the
# wall; the approach/exit arms reach far out either way, so compare the contact, not
# the max extent.
xmin_off = min(float(np.asarray(p)[:, 0].min()) for p in tp_r_off if len(p))
xmin_on = min(float(np.asarray(p)[:, 0].min()) for p in tp_r_on if len(p))
assert xmin_on > xmin_off + 1.0, (xmin_on, xmin_off)
print(f"roughing: OFF contact X={xmin_off:.2f}  ON contact X={xmin_on:.2f}: OK (lifted off fillet)")

# roughing PLACEMENT: with auto-align on and P2 in the fillet, straightening the
# rotation/approach normal makes the forming line follow the (vertical) wall instead
# of tilting into the fillet — the approach (lowest-Z) point moves toward the wall.
def rough_align_op():
    return {"type": "roughing", "count": 1, "tool_id": "T0101", "r_tool": R_TOOL,
            "clearance": CLR, "start_z": 5.0, "end_z": 5.0}   # single pass, P2 at Z=5 (fillet)


m = make_cyl_fillet()
pa_off = dict(base); pa_off["operations"] = [rough_align_op()]; pa_off["auto_calc_angle"] = True
tp_a_off = pg.calculate_paths(pa_off, {}, m)[0]

m = make_cyl_fillet()
pa_on = dict(base); pa_on["operations"] = [rough_align_op()]; pa_on["auto_calc_angle"] = True
pa_on["straighten_start_fillet"] = True
tp_a_on = pg.calculate_paths(pa_on, {}, m)[0]

form_off = np.asarray(max((p for p in tp_a_off if len(p) > 2), key=len), dtype=float)
form_on = np.asarray(max((p for p in tp_a_on if len(p) > 2), key=len), dtype=float)
# the paths must differ (proves the placement normal — not just P2 — changed)
assert not (form_off.shape == form_on.shape and np.allclose(form_off, form_on))
# approach tip (lowest-Z point) sits farther out (toward the wall) with straightening
tip_off = form_off[np.argmin(form_off[:, 2])][0]
tip_on = form_on[np.argmin(form_on[:, 2])][0]
assert tip_on >= tip_off - 1e-6, (tip_on, tip_off)
print(f"roughing auto-align: approach tip X off={tip_off:.2f} on={tip_on:.2f}: OK (wall-aligned)")

# --- 3b. clamp-zone advisory softening -------------------------------------
CLAMP = {"clamp_zone_length": 8.0}   # counter-press up to Z=8 (start_z=2 sits inside)


def _clamp_flags(ops, straighten):
    m2 = make_cyl_fillet()
    p = dict(base); p.update(CLAMP); p["operations"] = ops
    p["straighten_start_fillet"] = straighten
    pg.calculate_paths(p, {}, m2)
    return {w["op_index"]: w.get("softened", False) for w in pg.last_clamp_warnings}


# roughing starting in the clamp zone: softened only when straightening is on
assert _clamp_flags([rough_op()], straighten=False) == {0: False}
assert _clamp_flags([rough_op()], straighten=True) == {0: True}
# straight-line finishing: softened when straightening on
assert _clamp_flags([sl_finish_op()], straighten=True) == {0: True}
# sweeping/adaptive finishing is NOT straightened -> stays a HARD warning even with flag on
_sweep = dict(sl_finish_op()); _sweep["straight_line_mode"] = False
assert _clamp_flags([_sweep], straighten=True) == {0: False}
print("clamp-zone softening: rough/straight-line soft, sweeping stays hard: OK")

# --- 4. regression: flag off (default) is byte-identical --------------------
m = make_cyl_fillet()
pd = dict(base); pd["operations"] = [sl_finish_op(), rough_op()]
tp_default = pg.calculate_paths(pd, {}, m)[0]

m = make_cyl_fillet()
pf = dict(base); pf["operations"] = [sl_finish_op(), rough_op()]; pf["straighten_start_fillet"] = False
tp_false = pg.calculate_paths(pf, {}, m)[0]

assert len(tp_default) == len(tp_false)
for a, b in zip(tp_default, tp_false):
    assert np.array_equal(np.asarray(a), np.asarray(b))
print("flag off == flag absent: byte-identical: OK")

# --- 5. degenerate-flange first-pass reach guard (2026-07-22) ---------------
# When follow-blank is on and the blank is barely larger than the base radius,
# estimate_flange_reach collapses to ~(blank - r_base) at the very base and to 0
# above. Without the guard ONLY the first pass gets that tiny residual as its reach
# while every pass above falls back to the op reach -> the "short first pass" bug.
# The guard treats a sub-floor residual as exhausted so pass 1 falls back like the rest.
import logging, re

class _ReachCap(logging.Handler):
    def __init__(self):
        super().__init__(); self.reaches = []
    def emit(self, r):
        msg = r.getMessage()
        if "PARAM_DEBUG2" in msg:
            mt = re.search(r"reach=([\d.]+)", msg)
            if mt:
                self.reaches.append(float(mt.group(1)))

def _pass_reaches(start_z, blank, follow_min=None):
    op = {"type": "roughing", "count": 4, "tool_id": "T0101", "r_tool": R_TOOL,
          "clearance": CLR, "start_z": start_z, "end_z": 40.0, "pass_angle": 91.0,
          "reach": 90.0, "reach_follow_blank": True}
    if follow_min is not None:
        op["reach_follow_min"] = follow_min
    cap = _ReachCap()
    lg = logging.getLogger("SpinningCam"); lg.addHandler(cap)
    try:
        m2 = make_cyl_fillet()   # base radius ~65, wall 75, fillet z in [0,10], min_z=0
        p = dict(base); p["blank_radius"] = blank
        p["operations"] = [op]
        pg.calculate_paths(p, {}, m2)
    finally:
        lg.removeHandler(cap)
    return cap.reaches

# (a) FLOOR guard — first pass just ABOVE the base (target_z>min_z) gets a small
# sub-floor residual and must fall back to the op reach like the rest.
fixed = _pass_reaches(0.5, blank=70.0)
assert len(fixed) == 4, fixed
assert abs(fixed[0] - fixed[-1]) < 2.0, fixed          # first pass in line with the rest
assert fixed[0] > 80.0, fixed                          # full reach, not a stub
# floor disabled (reach_follow_min=0) reproduces the OLD bug: pass 1 is a short stub
# (target_z=0.5 is above min_z, so ONLY the floor guard could have caught it)
buggy = _pass_reaches(0.5, blank=70.0, follow_min=0.0)
assert buggy[0] < 30.0, buggy                          # degenerate residual leaks through
assert buggy[1] > 80.0, buggy                          # the rest already fell back
print(f"first-pass reach FLOOR guard: fixed[0]={fixed[0]:.1f} vs no-floor[0]={buggy[0]:.1f}: OK")

# (b) BELOW-BASE guard — a pass BELOW min_z has no flange; the estimate there grows and
# would sneak back over the floor, so it must fall back even with the floor DISABLED.
below = _pass_reaches(-5.0, blank=77.8, follow_min=0.0)
assert len(below) == 4, below
assert below[0] > 80.0, below                          # fell back despite floor off
assert abs(below[0] - below[-1]) < 2.0, below          # in line with the rest
print(f"first-pass reach BELOW-BASE guard (floor off): below[0]={below[0]:.1f} (~rest): OK")

print("ALL STRAIGHTEN-FILLET TESTS PASSED")
