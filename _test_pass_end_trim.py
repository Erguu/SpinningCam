"""Stop short (mm) - end the INWARD stroke early (stop_short.py, 2026-09-20).

THE RULE, from the user: the number only affects movement TOWARDS the mandrel.
So the forward pass is never touched, its back pass is, and a reverse pass is.

What must hold, most important first:

1. DIRECTION, not order. With "swap" ticked the two strokes change places; the
   trim must still land on the one running INWARD. Getting this wrong cuts the
   outward stroke instead, which would silently shorten the flange.
2. OFF = nothing changes. Absent, empty, 0, negative or unreadable all mean
   off, and the toolpath is point-for-point what it was.
3. The forward pass NEVER moves, whatever the trim.
4. The trim is measured ALONG the path, and a trim longer than the stroke is
   REFUSED and REPORTED, not applied as a stub.
5. Parallel arrays (projections, deviations) stay the same length as the path,
   or the 3D deviation colouring indexes into the wrong points.
6. The mandrel-end link refuses while a trim is on: a trimmed pass no longer
   ends at the mandrel, which is the one thing that option rests on.

Run:  python _test_pass_end_trim.py
"""
import copy
import sys

import numpy as np

import stop_short as ss
import mandrel_end_link as mel
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILED.append(name)


def polyline_length(p):
    p = np.asarray(p, dtype=float)
    if len(p) < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


# == A. the pure geometry ===================================================
print("A. plan / apply")

# A straight 100 mm line sampled every 10 mm.
LINE = np.array([[0.0, 0.0, float(z)] for z in range(0, 101, 10)])

check("off: no trim at 0", ss.plan(LINE, 0.0) is None)
check("off: no trim at negative", ss.plan(LINE, -5.0) is None)

cut = ss.plan(LINE, 25.0)
trimmed_line = ss.apply(LINE, cut)
check("25 mm off a 100 mm line leaves 75 mm",
      abs(polyline_length(trimmed_line) - 75.0) < 1e-6,
      polyline_length(trimmed_line))
check("the start is untouched", np.allclose(trimmed_line[0], LINE[0]))

# Landing exactly on a sample point must not invent a duplicate.
t30 = ss.apply(LINE, ss.plan(LINE, 30.0))
check("a trim landing on a point leaves no duplicate",
      len(t30) == 8 and abs(polyline_length(t30) - 70.0) < 1e-6,
      f"{len(t30)} pts, {polyline_length(t30)}")

check("a trim longer than the line is refused", ss.plan(LINE, 100.0) is None)
check("a trim leaving less than the floor is refused",
      ss.plan(LINE, 100.0 - ss.MIN_REMAIN_MM / 2.0) is None)
check("a two-point line still works", ss.plan(LINE[:2], 5.0) is not None)
check("a one-point line is refused", ss.plan(LINE[:1], 5.0) is None)

# Parallel arrays: same length as the path, interpolated at the cut.
devs = np.arange(len(LINE), dtype=float)
t_devs = ss.apply(devs, cut)
check("a 1-D parallel array trims to the same length",
      len(t_devs) == len(trimmed_line), f"{len(t_devs)} vs {len(trimmed_line)}")
check("the interpolated deviation is between its neighbours",
      devs[cut[0]] <= t_devs[-1] <= devs[cut[0] + 1], t_devs[-1])

# Measured ALONG the path, not straight-line: an L keeps the corner honest.
L = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 50.0], [50.0, 0.0, 50.0]])
tl = ss.apply(L, ss.plan(L, 20.0))
check("length is measured along the path, not end to end",
      abs(polyline_length(tl) - 80.0) < 1e-6, polyline_length(tl))

# -- the reader --
check("absent = off", ss.distance_mm({}) == 0.0)
check("empty = off", ss.distance_mm({ss.OP_KEY: ""}) == 0.0)
check("text = off", ss.distance_mm({ss.OP_KEY: "abc"}) == 0.0)
check("negative = off", ss.distance_mm({ss.OP_KEY: -3}) == 0.0)
check("a number is read", ss.distance_mm({ss.OP_KEY: "7.5"}) == 7.5)

# -- who may use it --
check("a reverse roughing op may",
      ss.op_can_use({"type": "roughing", "direction": "reverse"}, False))
check("a back-pass op may",
      ss.op_can_use({"type": "roughing", "back_pass_enabled": True}, True))
check("a plain forward op may NOT",
      not ss.op_can_use({"type": "roughing"}, False))
check("a reverse FINISHING op may (it travels inward too)",
      ss.op_can_use({"type": "finishing", "direction": "reverse"}, False))
check("cutting / bending / point may NOT",
      not any(ss.op_can_use({"type": k, "direction": "reverse"}, True)
              for k in ("cutting", "bending", "point")))


# == B. the engine ==========================================================
print()
print("B. the engine")

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
MIN_Z = float(mgr.props["min_z"])

PARAMS = {
    "auto_calc_angle": False, "min_safety_gap": 0.0,
    "final_part_thickness_on_mandrel": 2.0, "shell_thickness": 0.0,
    "blank_radius": float(mgr.props["br"]) * 1.5,
    "collision_resolution": 0.5, "gcode_resolution": 2.0,
    "home_x": 300.0, "home_z": 150.0, "retract_x": 50.0, "retract_z": 50.0,
    "surface_speed_m_min": 100.0, "feed_rate_mm_min": 300.0, "max_spin_rpm": 2550.0,
}

BASE = {
    "type": "roughing", "enabled": True, "name": "probe", "count": 2,
    "tool_id": "T0101", "r_tool": 25.0, "direction": "forward",
    "speed_mode": "RPM", "speed": 200, "feed_mode": "mm_min", "feed": 300,
    "start_z": MIN_Z + 10, "end_z": MIN_Z + 40,
    "retract_x": 50.0, "retract_z": 50.0,
    "pass_shape": "linear_approach", "p2_radius": 3.0,
    "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0, "reach": 40.0,
    "pass_angle": 120.0, "clearance": 5.0,
}

TRIM = 8.0


def run(op_over):
    p = copy.deepcopy(PARAMS)
    op = copy.deepcopy(BASE)
    op.update(op_over)
    p["operations"] = [op]
    pg = PathGenerator()
    # calculate_paths RETURNS the parallel arrays; only the paths are stored on
    # the generator. B5 needs both, so keep them together.
    out = pg.calculate_paths(p, {}, mgr)
    pg.tp, pg.projections, _cp, pg.deviations = out[0], out[1], out[2], out[3]
    return pg


def paths_equal(a, b):
    if len(a) != len(b):
        return False
    return all(len(x) == len(y) and np.allclose(x, y) for x, y in zip(a, b))


# -- B1. off changes nothing --
BACK = {"back_pass_enabled": True}
base = run(BACK)
for label, val in (("absent", None), ("empty", ""), ("zero", 0), ("negative", -4)):
    over = dict(BACK)
    if val is not None:
        over[ss.OP_KEY] = val
    check(f"off ({label}) = the same toolpaths",
          paths_equal(base.last_calculated_paths, run(over).last_calculated_paths))

# -- B2. back pass: the RETURN shortens, the forward does not --
trimmed = run({**BACK, ss.OP_KEY: TRIM})
b_paths, t_paths = base.last_calculated_paths, trimmed.last_calculated_paths
check("the same number of toolpaths (no pass lost)",
      len(b_paths) == len(t_paths), f"{len(b_paths)} vs {len(t_paths)}")

# Layout with a back pass: forward, back, forward, back.
check("the FORWARD passes are point-for-point unchanged",
      all(np.allclose(b_paths[i], t_paths[i]) for i in (0, 2)))

for i in (1, 3):
    d = polyline_length(b_paths[i]) - polyline_length(t_paths[i])
    check(f"back pass {i} is {TRIM} mm shorter", abs(d - TRIM) < 1e-3, f"{d:.4f}")

check("the back pass still STARTS where it did",
      all(np.allclose(b_paths[i][0], t_paths[i][0]) for i in (1, 3)))
check("the back pass END moved",
      all(not np.allclose(b_paths[i][-1], t_paths[i][-1]) for i in (1, 3)))

# -- B3. THE ONE THAT MATTERS: swap trims the INWARD stroke, not the second --
SWAP = {**BACK, "back_pass_swapped": True}
sb = run(SWAP).last_calculated_paths
st = run({**SWAP, ss.OP_KEY: TRIM}).last_calculated_paths
# Swapped, entry 0 is the OUTWARD stroke (T1 -> P3) and entry 1 the INWARD one.
check("swapped: the OUTWARD stroke is untouched",
      all(np.allclose(sb[i], st[i]) for i in (0, 2)))
for i in (1, 3):
    d = polyline_length(sb[i]) - polyline_length(st[i])
    check(f"swapped: the INWARD stroke {i} is {TRIM} mm shorter",
          abs(d - TRIM) < 1e-3, f"{d:.4f}")

# -- B4. reverse pass --
REV = {"direction": "reverse"}
rb = run(REV).last_calculated_paths
r_trim = run({**REV, ss.OP_KEY: TRIM})
rt = r_trim.last_calculated_paths
check("reverse: the same number of toolpaths", len(rb) == len(rt))
for i in range(len(rb)):
    d = polyline_length(rb[i]) - polyline_length(rt[i])
    check(f"reverse pass {i} is {TRIM} mm shorter", abs(d - TRIM) < 1e-3, f"{d:.4f}")
check("reverse: the pass still STARTS where it did",
      all(np.allclose(rb[i][0], rt[i][0]) for i in range(len(rb))))

# -- B5. parallel arrays stay parallel --
for name, pg in (("back pass", trimmed), ("reverse", r_trim)):
    ok = True
    for i, path in enumerate(pg.last_calculated_paths):
        pr = pg.projections[i] if i < len(pg.projections) else []
        dv = pg.deviations[i] if i < len(pg.deviations) else []
        # The engine already stores ONE FEWER projection than path points on a
        # linear_approach pass, with this feature off - measured 2026-09-20 and
        # not caused by it. So the bar is: equal, or one short. NEVER longer
        # than the path, which is what an untrimmed parallel array would become.
        if len(pr) and len(pr) not in (len(path), len(path) - 1):
            ok = False
        if len(dv) and len(dv) not in (len(path), len(path) - 1):
            ok = False
    check(f"{name}: projections / deviations match the path length", ok)

# -- B6. too long is refused AND reported --
huge = run({**BACK, ss.OP_KEY: 100000.0})
check("a trim longer than the stroke leaves the paths alone",
      paths_equal(base.last_calculated_paths, huge.last_calculated_paths))
check("...and is reported, not swallowed",
      len(huge.last_stop_short_ignored) > 0 and
      all(r["reason"] == "too_long" for r in huge.last_stop_short_ignored),
      huge.last_stop_short_ignored)
check("a trim that fits reports nothing", trimmed.last_stop_short_ignored == [])

# -- B7. the mandrel-end link refuses while a trim is on --
ops_ok = [{"type": "roughing", "direction": "reverse", mel.OP_FLAG_KEY: True,
           "tool_id": "T0101"},
          {"type": "roughing", "direction": "forward", "tool_id": "T0101"}]
check("without a trim the link is allowed",
      mel.blockers(ops_ok, 0, False, 1, False, 2, {}) == [])
ops_trim = copy.deepcopy(ops_ok)
ops_trim[0][ss.OP_KEY] = TRIM
check("with a trim the link is refused, with its own reason",
      mel.blockers(ops_trim, 0, False, 1, False, 2, {}) == ["stop_short"])
check("the reason has operator-facing text", "stop_short" in mel.REASONS)


# == C. the two-operation chain (user scenario, 2026-09-20) =================
# "one forward, one back short stop, forward where it left at previous short
#  ended back pass, one full back or a reverse where forward ended"
#
# Op1 forward -> Op1 back pass TRIMMED -> Op2 forward -> Op2 full back (or a
# reverse). Measured on the default cone, and the headline answer is written
# into the checks below so it cannot drift unnoticed:
#
#   the next FORWARD does NOT pick up where the trim stopped. Its start comes
#   from its own Start Z / P1 Z, out of reach of anything the previous stroke
#   did - 44.4 mm away in this setup. Trimming a back pass shortens THAT
#   stroke; it never moves the next operation.
print()
print("C. the two-operation chain")

CHAIN_OP = dict(BASE, count=1)


def chain(trim_op1, op2_reverse):
    p = copy.deepcopy(PARAMS)
    o1 = dict(CHAIN_OP, name="Op1", start_z=MIN_Z + 10, end_z=MIN_Z + 10,
              back_pass_enabled=True)
    o1[mel.OP_FLAG_KEY] = True
    o1[mel.OP_MAX_KEY] = 200.0
    if trim_op1:
        o1[ss.OP_KEY] = TRIM
    o2 = dict(CHAIN_OP, name="Op2", start_z=MIN_Z + 25, end_z=MIN_Z + 25)
    if op2_reverse:
        o2["direction"] = "reverse"
    else:
        o2["back_pass_enabled"] = True
    p["operations"] = [o1, o2]
    pg = PathGenerator()
    tp = pg.calculate_paths(p, {}, mgr)[0]
    return pg, tp


def gap(a_end, b_start):
    return float(np.hypot(b_start[0] - a_end[0], b_start[2] - a_end[2]))


for op2_reverse in (False, True):
    tag = "Op2 reverse" if op2_reverse else "Op2 forward+full back"
    pg_off, tp_off = chain(False, op2_reverse)
    pg_on, tp_on = chain(True, op2_reverse)

    check(f"{tag}: the same strokes with and without the trim",
          len(tp_off) == len(tp_on), f"{len(tp_off)} vs {len(tp_on)}")

    # [0] Op1 forward, [1] Op1 back (trimmed), [2] Op2 ...
    check(f"{tag}: Op1's FORWARD is unchanged",
          np.allclose(tp_off[0], tp_on[0]))
    d = polyline_length(tp_off[1]) - polyline_length(tp_on[1])
    check(f"{tag}: Op1's back pass is {TRIM} mm shorter", abs(d - TRIM) < 1e-3, f"{d:.4f}")

    # THE ANSWER: Op2 is untouched, and starts nowhere near the trimmed end.
    for i in range(2, len(tp_off)):
        check(f"{tag}: Op2 stroke {i} is point-for-point unchanged",
              np.allclose(tp_off[i], tp_on[i]))
    moved = gap(np.asarray(tp_on[1][-1], float), np.asarray(tp_on[2][0], float))
    check(f"{tag}: Op2's start does NOT follow the trimmed end (it repositions)",
          moved > 10.0, f"gap {moved:.3f} mm")

    # ...while the last INWARD stroke still meets the forward it belongs to.
    if not op2_reverse:
        g = gap(np.asarray(tp_on[2][-1], float), np.asarray(tp_on[3][0], float))
        check("Op2's FULL back pass starts exactly where its forward ended",
              g < 1e-6, f"gap {g:.6f} mm")

    # The link must refuse off the back of a trimmed stroke.
    refused = [r for r in pg_on.last_mandrel_link_refused
               if "stop_short" in (r.get("reasons") or [])]
    check(f"{tag}: the mandrel-end link refuses, naming the trim",
          len(refused) > 0 and pg_on.last_mandrel_links == {},
          f"refused={pg_on.last_mandrel_link_refused} links={pg_on.last_mandrel_links}")


print()
if FAILED:
    print(f"{len(FAILED)} check(s) FAILED: {FAILED}")
    sys.exit(1)
print("All stop-short checks passed.")
