"""Headless verification for per-operation configurable tool-change position.

Covers:
  - resolve_tool_change_point(): global / absolute / relative math, mirror, defaults
  - generate_gcode(): global mode is byte-identical to the legacy home retract;
    absolute/relative modes emit the resolved retract coordinates
  - calculate_paths(): warn-only swing guard fires for a custom point inside the
    envelope and stays silent for a clear point (and always for global)
"""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import (PathGenerator, resolve_tool_change_point,
                            TOOL_CHANGE_SWING_MARGIN_MM)


class _FakeMgr:
    """Radius profile with a bulge around z=50 so a straight (diagonal) traverse
    at constant X can be made to dip into the part mid-path."""
    def get_radius_fast(self, z):
        return 60.0 if 40.0 <= z <= 60.0 else 10.0

# ── 1. resolve_tool_change_point unit tests ───────────────────────────────
home = np.array([300.0, 0.0, 150.0])
prev = np.array([80.0, 0.0, 40.0])

# global (default + explicit) -> home
assert np.allclose(resolve_tool_change_point({}, prev, home), home)
assert np.allclose(resolve_tool_change_point({"tool_change_mode": "global"}, prev, home), home)

# absolute -> explicit X/Z (Y carried from home frame)
r = resolve_tool_change_point(
    {"tool_change_mode": "absolute", "tool_change_x": 250.0, "tool_change_z": 120.0}, prev, home)
assert np.allclose(r, [250.0, 0.0, 120.0]), r

# absolute with missing fields falls back to home X/Z
r = resolve_tool_change_point({"tool_change_mode": "absolute"}, prev, home)
assert np.allclose(r, home), r

# absolute, sim frame on a NEGATIVE-side roller: the real-frame X the user typed
# is converted into the canonical frame (center + side*(x-center)) so it lands
# back on the typed value after the engine mirrors X at pass end.
r = resolve_tool_change_point(
    {"tool_change_mode": "absolute", "tool_change_x": -40.0, "tool_change_z": 10.0},
    prev, home, center_x=0.0, side=-1.0)
assert np.allclose(r, [40.0, 0.0, 10.0]), r          # canonical = 0 + (-1)*(-40-0)
# absolute, positive-side sim frame: identity (no mirror to undo)
r = resolve_tool_change_point(
    {"tool_change_mode": "absolute", "tool_change_x": -40.0, "tool_change_z": 10.0},
    prev, home, center_x=0.0, side=1.0)
assert np.allclose(r, [-40.0, 0.0, 10.0]), r

# relative -> previous pass end + offset (real frame, literal sign)
r = resolve_tool_change_point(
    {"tool_change_mode": "relative", "tool_change_dx": 15.0, "tool_change_dz": -5.0}, prev, home)
assert np.allclose(r, [95.0, 0.0, 35.0]), r
# relative negative sign really subtracts (no abs)
r = resolve_tool_change_point(
    {"tool_change_mode": "relative", "tool_change_dx": -15.0, "tool_change_dz": -5.0}, prev, home)
assert np.allclose(r, [65.0, 0.0, 35.0]), r
# relative in the negative-side sim frame flips the offset (so it matches G-code
# after the X mirror): prev.x + side*dx = 80 + (-1)*15 = 65
r = resolve_tool_change_point(
    {"tool_change_mode": "relative", "tool_change_dx": 15.0, "tool_change_dz": -5.0},
    prev, home, center_x=0.0, side=-1.0)
assert np.allclose(r, [65.0, 0.0, 35.0]), r

# relative with no offsets -> previous pass end unchanged
r = resolve_tool_change_point({"tool_change_mode": "relative"}, prev, home)
assert np.allclose(r, prev), r
print("resolve_tool_change_point: OK")

# ── 1b. collision check: destination gap + traverse (path) min gap ────────
_pg = PathGenerator()
_fp = {"blank_radius": 0.0, "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0}
# single-point radial gap: X=30 vs radius 10 at z=0 -> gap 20
assert abs(_pg._tc_radial_gap([30.0, 0.0, 0.0], 0.0, _FakeMgr(), _fp, 0.0) - 20.0) < 1e-6
# straight traverse at X=30 from z=0 to z=100 passes the z=50 bulge (radius 60)
dest_gap, path_min = _pg._tool_change_swing_check(
    [[30.0, 0.0, 0.0], [30.0, 0.0, 100.0]], 0.0, _FakeMgr(), _fp, 0.0)
assert dest_gap > 0.0, dest_gap                 # both ends are clear (radius 10)
assert path_min < 0.0, path_min                 # but the diagonal dips into the bulge
print("swing check: dest clear yet traverse penetrates -> path_min<0: OK", round(path_min, 1))

# ── mandrel + two-op fixture (op2 uses a different tool -> tool change) ────
mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"]); top_z = float(mgr.props["top_z"])
span = top_z - min_z

HOME_X, HOME_Z = 300.0, 150.0
base = {
    "final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0,
    "max_spin_rpm": 2000, "home_x": HOME_X, "home_z": HOME_Z,
    # identity post-processor so machine coords == global coords
    "machine_origin_x": 0.0, "machine_origin_z": 0.0,
    "machine_gcode_offset_x": 0.0, "machine_gcode_offset_z": 0.0,
    "machine_invert_x": False, "machine_invert_z": False,
    "machine_output_diameter_mode": False,
}


def op(tool, **extra):
    d = {"type": "roughing", "count": 1, "tool_id": tool, "r_tool": 30.0,
         "clearance": 2.0, "start_z": min_z + span * 0.1, "end_z": min_z + span * 0.8}
    d.update(extra); return d


def gcode_for(op2):
    pg = PathGenerator()
    p = dict(base); p["operations"] = [op("T0101"), op2]
    pg.calculate_paths(p, {}, mgr)
    return pg, pg.generate_gcode(params=p)


def retract_lines(gc):
    lines = gc.splitlines()
    i = lines.index("(--- TOOL CHANGE SAFETY ---)")
    return lines[i + 1], lines[i + 2]  # G0 Z..., G0 X...


# ── 2. global mode: byte-identical to the legacy home retract ─────────────
pg_g, gc_g = gcode_for(op("T0202"))                       # default mode = global
z_line, x_line = retract_lines(gc_g)
assert z_line == f"G0 Z{HOME_Z:.3f} (Home Z)", z_line
assert x_line == f"G0 X{HOME_X:.3f} (Retract X)", x_line
assert len(pg_g.last_tool_change_warnings) == 0, "global must never warn"
print("global mode retract byte-identical + no warn: OK")

# ── 3. absolute mode: retract carries the entered X/Z ─────────────────────
pg_a, gc_a = gcode_for(op("T0202", tool_change_mode="absolute",
                          tool_change_x=250.0, tool_change_z=120.0))
z_line, x_line = retract_lines(gc_a)
assert z_line == "G0 Z120.000 (Tool Change Z, absolute)", z_line
assert x_line == "G0 X250.000 (Tool Change X, absolute)", x_line
print("absolute mode retract coordinates: OK")

# ── 4. relative mode: retract = previous pass end + offset ────────────────
pg_r, gc_r = gcode_for(op("T0202", tool_change_mode="relative",
                          tool_change_dx=20.0, tool_change_dz=-10.0))
prev_end = np.asarray(pg_r.last_calculated_paths[0][-1], dtype=float)  # op1 last pass end
z_line, x_line = retract_lines(gc_r)
assert z_line == f"G0 Z{prev_end[2] - 10.0:.3f} (Tool Change Z, relative)", (z_line, prev_end)
assert x_line == f"G0 X{prev_end[0] + 20.0:.3f} (Tool Change X, relative)", (x_line, prev_end)
print("relative mode retract = prev pass end + offset: OK")

# ── 4a. sim and G-code agree on the RELATIVE point (regression) ───────────
# Relative must reference the previous pass's FORMING end (path[-1]), not the
# post-per-pass-retract position. The sim retracts current_pt past the forming
# end, so if the two used different references they would disagree. Use a
# 2-pass op1 with a non-trivial retract so forming-end != retract-point.
_pg = PathGenerator()
_p = dict(base); _p["retract_x"] = 25.0; _p["retract_z"] = 15.0
_p["operations"] = [op("T0101", count=2), op("T0202", tool_change_mode="relative",
                                              tool_change_dx=30.0, tool_change_dz=-30.0)]
_pg.calculate_paths(_p, {}, mgr)
_forming_end = np.asarray(_pg.last_calculated_paths[1][-1], dtype=float)  # op1 pass 2 end
_expect = np.array([_forming_end[0] + 30.0, _forming_end[2] - 30.0])      # (x, z) target
# (a) G-code lands on forming_end + offset
_gc = _pg.generate_gcode(params=_p)
_zl, _xl = retract_lines(_gc)
assert _zl == f"G0 Z{_expect[1]:.3f} (Tool Change Z, relative)", (_zl, _expect)
assert _xl == f"G0 X{_expect[0]:.3f} (Tool Change X, relative)", (_xl, _expect)
# (b) the 3D-sim sequence contains a rapid ENDING exactly on that same target
_hits = [seg for (kind, seg, *rest) in _pg.last_calculated_sequence
         if kind == "rapid" and abs(seg[-1][0] - _expect[0]) < 1e-6
         and abs(seg[-1][2] - _expect[1]) < 1e-6]
assert _hits, "sim has no rapid ending on the relative tool-change target {}".format(_expect)
print("sim and G-code agree on relative tool-change point: OK", tuple(_expect.round(2)))

# ── 4a-cue. sequence carries a 'toolchange' marker (from→to) at the point ──
_marks = [it for it in _pg.last_calculated_sequence if it[0] == "toolchange"]
assert len(_marks) == 1, "expected exactly one toolchange marker, got {}".format(len(_marks))
_mk = _marks[0]
assert str(_mk[2]) == "T0101" and str(_mk[3]) == "T0202", _mk        # outgoing → incoming
assert abs(_mk[1][0] - _expect[0]) < 1e-6 and abs(_mk[1][2] - _expect[1]) < 1e-6, _mk
print("sim sequence carries a toolchange marker (from→to + point): OK")

# ── 4a-neg. sign is LITERAL (no abs) and sim==gcode on BOTH roller sides ───
# The engine mirrors X for a negative-side roller; the offset must survive that
# so +ΔX/−ΔX move opposite ways and the 3D sim matches the G-code either side.
def _rel_run(dx, dz, positive_side):
    pg = PathGenerator()
    p = dict(base); p["retract_x"] = 25.0; p["retract_z"] = 15.0
    p["roller_positive_x_side"] = positive_side
    p["operations"] = [op("T0101", count=2),
                       op("T0202", tool_change_mode="relative",
                          tool_change_dx=dx, tool_change_dz=dz)]
    pg.calculate_paths(p, {}, mgr)
    forming = np.asarray(pg.last_calculated_paths[1][-1], dtype=float)  # real frame
    zl, xl = retract_lines(pg.generate_gcode(params=p))
    gx = float(xl.split()[1][1:])   # "X173.000" -> 173.0
    gz = float(zl.split()[1][1:])
    # G-code coords are rounded to 3 decimals; compare with that tolerance.
    sim_hit = any(kind == "rapid"
                  and abs(seg[-1][0] - gx) < 2e-3 and abs(seg[-1][2] - gz) < 2e-3
                  for (kind, seg, *rest) in pg.last_calculated_sequence)
    return forming, gx, gz, sim_hit

for _pos in (True, False):
    f, gx_p, gz, hit = _rel_run(30.0, -30.0, _pos)
    assert abs(gx_p - (f[0] + 30.0)) < 2e-3, (_pos, gx_p, f[0])   # +ΔX => +X literally
    assert abs(gz - (f[2] - 30.0)) < 2e-3, (_pos, gz, f[2])       # ΔZ sign literal
    assert hit, "sim disagrees with G-code, side positive={}".format(_pos)
    f2, gx_n, _, hit2 = _rel_run(-30.0, -30.0, _pos)              # opposite ΔX
    assert abs(gx_n - (f2[0] - 30.0)) < 2e-3, (_pos, gx_n, f2[0])  # −ΔX => −X (no abs)
    assert hit2, "sim disagrees on −ΔX, side positive={}".format(_pos)
    assert abs((gx_p - f[0]) + (gx_n - f2[0])) < 2e-3, "±ΔX not symmetric (abs?)"
print("relative ΔX/ΔZ sign honored (no abs) + sim==G-code on BOTH roller sides: OK")

# ── 4b. simultaneous XZ: one combined diagonal G0 (not a Z-then-X split) ──
pg_s, gc_s = gcode_for(op("T0202", tool_change_mode="absolute",
                          tool_change_x=250.0, tool_change_z=120.0,
                          tool_change_simultaneous=True))
_lines = gc_s.splitlines()
_i = _lines.index("(--- TOOL CHANGE SAFETY ---)")
assert _lines[_i + 1] == "G0 X250.000 Z120.000 (Tool Change XZ, absolute)", _lines[_i + 1]
assert _lines[_i + 2] == "M5", _lines[_i + 2]   # only ONE move line, then M5
print("simultaneous XZ emits one combined diagonal G0: OK")

# ── 5. warn-only swing guard ──────────────────────────────────────────────
# Absolute point pulled in close to the part (small X) -> warn.
pg_near, _ = gcode_for(op("T0202", tool_change_mode="absolute",
                          tool_change_x=5.0, tool_change_z=min_z + span * 0.5))
assert len(pg_near.last_tool_change_warnings) == 1, pg_near.last_tool_change_warnings
w = pg_near.last_tool_change_warnings[0]
assert w["op_index"] == 1 and w["mode"] == "absolute", w
assert w["gap"] < TOOL_CHANGE_SWING_MARGIN_MM, w
print("swing guard warns for a point inside the envelope: OK", round(w["gap"], 2))

# Absolute point well clear (large X) -> no warn.
pg_far, _ = gcode_for(op("T0202", tool_change_mode="absolute",
                         tool_change_x=500.0, tool_change_z=200.0))
assert len(pg_far.last_tool_change_warnings) == 0, pg_far.last_tool_change_warnings
print("swing guard silent for a clear point: OK")

print("ALL TOOL-CHANGE POSITION TESTS PASSED")
