# -*- coding: utf-8 -*-
"""Headless ENGINE tests for TODO #100 — hand-drawn exit tails in real toolpaths.

The pure geometry lives in _test_exit_waypoints.py; this checks the wiring:

  1. No waypoints  -> output BYTE-IDENTICAL, including for programs that use the
     existing exit shapes (exit_bow / exit_arc_angle / exit_mid_rotation).
  2. Waypoints     -> the pass ENDS at the last waypoint (there is no P3) and
     passes through every one of them.
  3. Waypoints supersede exit_bow / exit_arc_angle on that leg.
  4. Per-pass: only the pass that carries points is reshaped; its neighbours are
     untouched (the list lives in pass_edits, keyed by pass index).
  5. D10: a reverse op and a back-pass op ignore waypoints entirely.

    runtest.bat _test_exit_waypoints_engine.py
"""
import numpy as np

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
import exit_waypoints as ew

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


def make_params(**op_over):
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
          "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": "forward", "p2_radius": 0.0}
    op.update(op_over)
    return {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "collision_resolution": 0.1, "gcode_resolution": 0.05}


def build_all(**op_over):
    return pg.calculate_paths(make_params(**op_over), {}, mgr)[0]


def build(**op_over):
    return build_all(**op_over)[0]


def wp(dx, dz, anchor="p2", feed=None):
    return {"anchor": anchor, "dx": dx, "dz": dz, "feed": feed}


# ── 1. absent == unchanged ──────────────────────────────────────────────────
base_variants = {
    "plain":            {},
    "exit_bow":         {"exit_bow": 4.0},
    "exit_arc_angle":   {"exit_arc_angle": 25.0},
    "exit_mid_rotation": {"exit_mid_rotation": 15.0, "exit_mid_t": 0.5},
    "p2_radius":        {"p2_radius": 8.0},
}
baseline = {k: np.array(build(**v)) for k, v in base_variants.items()}

for name, over in base_variants.items():
    again = np.array(build(**over))
    same = (again.shape == baseline[name].shape and np.array_equal(again, baseline[name]))
    check(same, f"no waypoints: '{name}' output is byte-identical")

# an EMPTY list must also be a no-op, not a degenerate tail
empty = np.array(build(pass_edits={"0": {"exit_points": []}}))
check(np.array_equal(empty, baseline["plain"]),
      "no waypoints: empty exit_points list changes nothing")

# junk that normalize() throws away must also be a no-op
junk = np.array(build(pass_edits={"0": {"exit_points": [{"dx": "x", "dz": 1}]}}))
check(np.array_equal(junk, baseline["plain"]),
      "no waypoints: unparseable points fall back to the normal exit")


# ── 2. the pass ends at the last waypoint ───────────────────────────────────
PTS = [wp(12.0, -6.0), wp(10.0, -8.0, anchor="prev"), wp(8.0, -14.0, anchor="prev")]
path = np.array(build(pass_edits={"0": {"exit_points": PTS}}))

p2 = np.array(baseline["plain"])[1]          # p2_radius=0 -> path[1] is P2
abs_pts = ew.resolve(p2[0], p2[2], ew.normalize(PTS))

end = path[-1]
check(abs(end[0] - abs_pts[-1][0]) < 1e-6 and abs(end[2] - abs_pts[-1][1]) < 1e-6,
      f"pass ENDS at the last waypoint {abs_pts[-1]} (got {end[0]:.3f},{end[2]:.3f})")

miss = max(float(np.min(np.hypot(path[:, 0] - x, path[:, 2] - z))) for x, z in abs_pts)
check(miss < 1e-5, f"path passes THROUGH every waypoint (worst miss {miss:.2e} mm)")

check(not np.array_equal(path, baseline["plain"]), "waypoints actually change the path")


# ── 3. waypoints beat the parametric exit shapes ────────────────────────────
with_bow = np.array(build(exit_bow=6.0, pass_edits={"0": {"exit_points": PTS}}))
check(np.array_equal(with_bow, path), "waypoints supersede exit_bow on the exit leg")

with_arc = np.array(build(exit_arc_angle=30.0, pass_edits={"0": {"exit_points": PTS}}))
check(np.array_equal(with_arc, path), "waypoints supersede exit_arc_angle")


# ── 4. per-pass, keyed by pass index ────────────────────────────────────────
multi_plain = [np.array(p) for p in build_all(count=3, end_z=60.0)]
multi_wp = [np.array(p) for p in build_all(
    count=3, end_z=60.0, pass_edits={"1": {"exit_points": PTS}})]

check(len(multi_plain) == len(multi_wp) == 3, "3 passes built in both cases")
check(np.array_equal(multi_wp[0], multi_plain[0]), "pass 0 (no points) untouched")
check(not np.array_equal(multi_wp[1], multi_plain[1]), "pass 1 (has points) reshaped")
check(np.array_equal(multi_wp[2], multi_plain[2]), "pass 2 (no points) untouched")


# ── 5. D10 exclusions ───────────────────────────────────────────────────────
rev_plain = np.array(build(direction="reverse"))
rev_wp = np.array(build(direction="reverse", pass_edits={"0": {"exit_points": PTS}}))
check(np.array_equal(rev_wp, rev_plain), "D10: reverse op ignores waypoints")

bp_plain = [np.array(p) for p in build_all(back_pass_enabled=True)]
bp_wp = [np.array(p) for p in build_all(
    back_pass_enabled=True, pass_edits={"0": {"exit_points": PTS}})]
check(len(bp_plain) == len(bp_wp)
      and all(np.array_equal(a, b) for a, b in zip(bp_plain, bp_wp)),
      "D10: back-pass op ignores waypoints")


# ── 6. a tail closer than the op clearance is REPORTED (#100 D11) ───────────
# A clear tail says nothing...
build(clearance=5.0, pass_edits={"0": {"exit_points": PTS}})
check(pg.last_waypoint_warnings == [],
      f"clear tail raises no warning (got {pg.last_waypoint_warnings})")

# ...but one aimed back INTO the mandrel does. Moving toward the spindle axis
# (negative dx) always reduces clearance, whatever the profile does in Z.
# min_safety_gap is -999 here, so nothing shifts the pass clear first — the tail
# stays exactly where it was drawn, which is the case the warning exists for.
INTO = [wp(-10.0, 2.0), wp(-12.0, 4.0, anchor="prev")]
build(clearance=5.0, pass_edits={"0": {"exit_points": INTO}})
w = pg.last_waypoint_warnings
check(len(w) == 1, f"tail inside the clearance raises exactly one warning (got {len(w)})")
if w:
    check(w[0]["n_violating"] > 0 and w[0]["worst"]["clearance"] < 5.0,
          f"warning records the worst point ({w[0]['worst']['clearance']:.2f}mm "
          f"vs clearance {w[0]['clearance']:.2f}mm)")
    check(w[0]["n_points"] == 2, "warning records how many points the tail had")

# the list is per-calculation, not cumulative
build(clearance=5.0, pass_edits={"0": {"exit_points": PTS}})
check(pg.last_waypoint_warnings == [], "warning list resets on each calculation")


# ── 7. per-point feed, STEP semantics (#100, user 2026-08-27) ───────────────
# A waypoint's feed governs the span ARRIVING at it; a blank inherits the
# previous span. Emission is checked through real G-code, not internals.
def gcode_feeds(**op_over):
    p = make_params(**op_over)
    pg.calculate_paths(p, {}, mgr)
    g = pg.generate_gcode(params=p, feed=400, speed=200)
    out = []
    for ln in g.splitlines():
        if ln.startswith("G1") and " F" in ln:
            out.append(float(ln.split(" F")[1].split()[0]))
    return out

# Values deliberately unlike any default (300 IS the default pass feed here, so
# using it would prove nothing).
FED = [wp(12.0, -6.0, feed=321.0),
       wp(10.0, -8.0, anchor="prev"),            # blank -> inherits 321
       wp(8.0, -14.0, anchor="prev", feed=123.0)]
feeds = gcode_feeds(pass_edits={"0": {"exit_points": FED}})
check(321.0 in feeds, f"the first waypoint's feed reaches the G-code (got {set(feeds)})")
check(123.0 in feeds, f"the last waypoint's feed reaches the G-code (got {set(feeds)})")
check(feeds.index(321.0) < feeds.index(123.0),
      "321 is commanded before 123 — the slow span is the one arriving at the last point")

# the blank middle point must NOT restore the pass feed between them
_between = feeds[feeds.index(321.0):feeds.index(123.0)]
check(all(f == 321.0 for f in _between),
      f"a blank feed inherits the previous span, no reversion in between (got {_between})")

# no feeds anywhere -> nothing beyond the ordinary pass feed
plain_feeds = set(gcode_feeds(pass_edits={"0": {"exit_points": PTS}}))
check(321.0 not in plain_feeds and 123.0 not in plain_feeds,
      f"waypoints without feeds add no feed changes (got {plain_feeds})")


# ── 8. STRAIGHT mode: the waypoints ARE the emitted points ──────────────────
# User 2026-08-27: "if I have 4-5 waypoints, the pass should only have those
# after P2." The PLC stops at every point and has 1000 lines total, so the
# spline's ~24 samples per span was the thing making this unusable.
STR4 = [wp(12.0, -6.0), wp(10.0, -8.0, anchor="prev"),
        wp(9.0, -10.0, anchor="prev"), wp(8.0, -14.0, anchor="prev")]

straight_path = np.array(build(p2_radius=0.0, pass_edits={"0": {"exit_points": STR4}}))
spline_path = np.array(build(p2_radius=0.0, pass_edits={
    "0": {"exit_points": STR4, "exit_shape": "spline"}}))

check(len(straight_path) < len(spline_path),
      f"straight emits fewer points than the curve ({len(straight_path)} vs {len(spline_path)})")

# Everything from P2 onward must be EXACTLY the 4 waypoints — nothing between.
p2_s = straight_path[1]
abs4 = ew.resolve(p2_s[0], p2_s[2], ew.normalize(STR4))
tail = straight_path[2:]
check(len(tail) == len(abs4),
      f"the tail is exactly the {len(abs4)} waypoints, no interpolation (got {len(tail)})")
if len(tail) == len(abs4):
    worst = max(abs(t[0] - a[0]) + abs(t[2] - a[1]) for t, a in zip(tail, abs4))
    check(worst < 1e-6, f"each emitted point IS a waypoint (worst {worst:.2e} mm)")

# ...and it survives gcode_resolution, which would otherwise drop close pairs.
TIGHT = [wp(2.0, -0.4), wp(0.6, -0.3, anchor="prev"),
         wp(0.6, -0.3, anchor="prev"), wp(0.6, -0.3, anchor="prev")]
tight_path = np.array(build(p2_radius=0.0, gcode_resolution=5.0,
                            pass_edits={"0": {"exit_points": TIGHT}}))
p2_t = tight_path[1]
abs_t = ew.resolve(p2_t[0], p2_t[2], ew.normalize(TIGHT))
kept = sum(1 for a in abs_t
           if float(np.min(np.hypot(tight_path[:, 0] - a[0],
                                    tight_path[:, 2] - a[1]))) < 1e-6)
check(kept == len(abs_t),
      f"points closer than gcode_resolution are NOT dropped ({kept}/{len(abs_t)} kept)")

# The PLC decimator must leave the tail alone too — RDP would happily drop a
# collinear waypoint, taking its per-point feed with it.
COLL = [wp(6.0, 0.0), wp(6.0, 0.0, anchor="prev"), wp(6.0, 0.0, anchor="prev")]
p_coll = make_params(p2_radius=0.0, pass_edits={"0": {"exit_points": COLL}})
pg.calculate_paths(p_coll, {}, mgr)
dec = pg.decimate_all_paths(0.5, 0.5, 0.0, params=p_coll)[0]
p2_c = np.array(pg.last_calculated_paths[0])[1]
abs_c = ew.resolve(p2_c[0], p2_c[2], ew.normalize(COLL))
kept_c = sum(1 for a in abs_c
             if float(np.min(np.hypot(np.asarray(dec)[:, 0] - a[0],
                                      np.asarray(dec)[:, 2] - a[1]))) < 1e-6)
check(kept_c == len(abs_c),
      f"PLC decimation keeps every collinear waypoint ({kept_c}/{len(abs_c)})")
check(0 in getattr(pg, "last_exit_verbatim", set()),
      "the path is flagged verbatim so the decimator knows to leave it")

# A spline tail is NOT flagged — it may be decimated like any other curve.
p_sp = make_params(p2_radius=0.0, pass_edits={
    "0": {"exit_points": COLL, "exit_shape": "spline"}})
pg.calculate_paths(p_sp, {}, mgr)
check(0 not in getattr(pg, "last_exit_verbatim", set()),
      "a spline tail is not flagged verbatim")


# ── 9. tails an op CANNOT use are excluded at the source, and reported ──────
# Research 2026-08-27: a "spline" pass_shape ignores the tail geometry entirely,
# but the tail was still stored and its per-point FEEDS were still emitted,
# matched to whatever path point happened to be nearest (measured 6-14 mm away).
FED2 = [wp(12.0, -6.0, feed=321.0), wp(10.0, -8.0, anchor="prev", feed=123.0)]

lin_feeds = set(gcode_feeds(pass_shape="linear_approach",
                            pass_edits={"0": {"exit_points": FED2}}))
check(321.0 in lin_feeds and 123.0 in lin_feeds,
      f"precondition: a linear pass DOES emit the per-point feeds ({sorted(lin_feeds)})")

sp_feeds = set(gcode_feeds(pass_shape="spline", pass_edits={"0": {"exit_points": FED2}}))
check(321.0 not in sp_feeds and 123.0 not in sp_feeds,
      f"a spline op no longer emits feeds for a tail it ignores (got {sorted(sp_feeds)})")

# the geometry is untouched either way — excluding must not change the path
sp_plain = np.array(build(pass_shape="spline"))
sp_tail = np.array(build(pass_shape="spline", pass_edits={"0": {"exit_points": FED2}}))
check(np.array_equal(sp_plain, sp_tail),
      "a spline op's path is byte-identical with and without a stored tail")

# no clearance report about a tail that is not running
build(clearance=5.0, pass_shape="spline", pass_edits={"0": {"exit_points": INTO}})
check(pg.last_waypoint_warnings == [],
      f"no clearance warning for a tail the op ignores (got {pg.last_waypoint_warnings})")

# ...but the operator IS told the points are not running
check(len(pg.last_waypoint_ignored) == 1,
      f"an ignored tail is reported exactly once (got {len(pg.last_waypoint_ignored)})")
if pg.last_waypoint_ignored:
    _ig = pg.last_waypoint_ignored[0]
    check(_ig["reason"] == "pass_shape" and _ig["n_points"] == 2,
          f"the report names the reason and the point count ({_ig})")

for _d, _why in (({"direction": "reverse"}, "reverse"),
                 ({"back_pass_enabled": True}, "back_pass")):
    build(pass_edits={"0": {"exit_points": FED2}}, **_d)
    _got = [w["reason"] for w in pg.last_waypoint_ignored]
    check(_got == [_why], f"D10 {_why} tail is reported as ignored (got {_got})")

# a tail that IS running reports nothing
build(pass_edits={"0": {"exit_points": FED2}})
check(pg.last_waypoint_ignored == [],
      f"a working tail is not reported as ignored (got {pg.last_waypoint_ignored})")


# ── 10. the safety floor moving a tail pass is reported ─────────────────────
# The floor pushes P2 out until the WHOLE pass clears, and the tail is part of
# the pass — so a stale tail can shove the pass off the work without colliding.
def shifted(**over):
    p = make_params(**over)
    p["min_safety_gap"] = over.pop("_gap", p["min_safety_gap"])
    pg.calculate_paths(p, {}, mgr)
    return pg.last_waypoint_shifted


p_gap = make_params(clearance=0.0, pass_edits={"0": {"exit_points": INTO}})
p_gap["min_safety_gap"] = 12.0          # forces the floor to push the pass out
pg.calculate_paths(p_gap, {}, mgr)
_mv = pg.last_waypoint_shifted
check(len(_mv) == 1, f"a tail pass moved by the safety floor is reported (got {len(_mv)})")
if _mv:
    check(_mv[0]["shift"] > 1.0 and _mv[0]["n_points"] == 2,
          f"the report carries the distance and the point count ({_mv[0]})")

p_nogap = make_params(clearance=0.0, pass_edits={"0": {"exit_points": INTO}})
pg.calculate_paths(p_nogap, {}, mgr)   # min_safety_gap = -999 -> no shift
check(pg.last_waypoint_shifted == [],
      f"an unshifted tail pass reports nothing (got {pg.last_waypoint_shifted})")

# and a pass with no tail never reports, however far the floor moves it
p_notail = make_params(clearance=0.0)
p_notail["min_safety_gap"] = 12.0
pg.calculate_paths(p_notail, {}, mgr)
check(pg.last_waypoint_shifted == [],
      "a pass without a tail is never reported as shifted")


print()
if fails:
    raise SystemExit(f"{fails} FAILED")
print("ALL PASS")
