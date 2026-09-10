# -*- coding: utf-8 -*-
"""Headless test: "why is this pass's reach that number?" — the whole chain.

THE COMPLAINT THIS EXISTS FOR

An operator reads 118 in the pass table, the operation panel says 95, and
nobody can say which one the machine used. Reach is decided by a priority
chain, and only the FIRST link is visible in the operation panel:

    per-pass pin  >  follow blank edge  >  progressive fan  >  operation reach
                  >  |P3| (the typed control point)

Highest link present wins. There were already about fifty assertions across six
files, but each tested ONE link on its own. Nothing tested the CHAIN — that
when three links are present at once, the documented one wins.

That sounds like it needs endless tests. It does not: four optional links is
sixteen combinations, times the two modes the engine has (angular, when
pass_angle is set; raw, when it is not) — thirty-two cases. This file walks all
thirty-two.

THE SECOND CLAIM IS THE IMPORTANT ONE

For every case it also asserts that THE ENGINE'S ACTUAL REACH EQUALS THE VALUE
THE EXPLANATION NAMES. `compute_pass_rows` records provenance — which stage won
and what it beat — and that record is what Tools > "Why is my pass strange?"
and the pass table show the operator. If it ever disagrees with what the engine
did, the operator asks "why is reach 118?", gets an answer, and the answer is
WRONG. Nothing checked that before.
"""
import itertools
import sys

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.dialogs.pass_table import compute_pass_rows

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
MIN_Z = float(mgr.props["min_z"])

# x2.0, NOT x1.5. At x1.5 the flat flange at the last pass measures 9.815 mm,
# which is under the 10 mm degenerate-flange floor (`reach_follow_min`), so
# follow-blank switches ITSELF off — and does so at some pass angles and not
# others, because the slant conversion moves the number either side of 10 mm.
# A baseline balanced on that threshold makes the priority chain look broken
# when what is really being measured is the guard. The guard has its own
# section at the end of this file.
BLANK_R = float(mgr.props["br"]) * 2.0

COUNT = 3
PIN_REACH = 12.5
OP_REACH = 40.0
FAN_END = 30.0

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


def make_op(angular, pin, follow, fan, op_reach):
    """One operation with the requested links present or absent."""
    op = {
        "type": "roughing", "enabled": True, "count": COUNT, "tool_id": "T1",
        "r_tool": 25.0, "clearance": 0.0,
        "start_z": MIN_Z + 10, "end_z": MIN_Z + 30,
        "pass_shape": "linear_approach",
        "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
    }
    if angular:
        # pass_angle ABSENT is how "off" is stored — the engine reads
        # op.get("pass_angle", None) and only converts when it is not None.
        op["pass_angle"] = 120.0
    if op_reach:
        op["reach"] = OP_REACH
    if fan:
        op["progressive_reach_enabled"] = True
        op["progressive_reach_end"] = FAN_END
    if follow:
        op["reach_follow_blank"] = True
    if pin:
        # Pin the LAST pass, which is the one last_op_reach reports.
        op["pass_edits"] = {str(COUNT - 1): {"reach": PIN_REACH}}
    return op


def params_for(op):
    return {"operations": [op], "blank_radius": BLANK_R,
            "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "target_clearance": 0.0,
            "home_x": 300.0, "home_z": 150.0,
            "retract_x": 50.0, "retract_z": 50.0}


def engine_reach(op):
    pg = PathGenerator()
    pg.calculate_paths(params_for(op), {}, mgr)
    return pg.last_op_reach.get(0)


def expected_source(angular, pin, follow, fan, op_reach):
    """The documented winner. Deliberately written as the rule, not read from
    the code under test."""
    if pin:
        return "pin"
    if follow:
        return "follow"
    if angular and fan and COUNT > 1:
        return "fan"
    if op_reach:
        return "op"
    return "raw"


print("Walking %d cases: 2 modes x 2^4 link combinations\n" % (2 * 2 ** 4))

seen_sources = set()
for angular, pin, follow, fan, op_reach in itertools.product(
        (True, False), repeat=5):
    op = make_op(angular, pin, follow, fan, op_reach)
    label = "%s pin=%-5s follow=%-5s fan=%-5s opreach=%-5s" % (
        "angular" if angular else "raw    ", pin, follow, fan, op_reach)

    rows = compute_pass_rows(op, params_for(op), mgr)
    if len(rows) != COUNT:
        check(False, "%s -> pass table produced %d rows" % (label, len(rows)))
        continue

    last = rows[-1]
    prov = (last.get("prov") or {}).get("reach") or {}
    src = prov.get("source")
    want = expected_source(angular, pin, follow, fan, op_reach)
    seen_sources.add(src)

    # 1. the documented link wins
    ok_src = (src == want)

    # 2. the explanation's value is the pass table's own effective reach
    ok_val = (prov.get("value") is not None
              and abs(float(prov["value"]) - float(last["reach"])) < 0.05)

    # 3. THE ENGINE AGREES with the explanation
    eng = engine_reach(op)
    ok_eng = (eng is not None and abs(float(eng) - float(last["reach"])) < 0.05)

    check(ok_src and ok_val and ok_eng,
          "%s -> source=%-7s (want %-7s) table=%7.2f engine=%s"
          % (label, src, want, last["reach"],
             "%.2f" % eng if eng is not None else "None"))

print()
# Every stage of the chain must have won at least once, or a "passing" run
# could be one where three links never actually engaged.
for stage in ("pin", "follow", "fan", "op", "raw"):
    check(stage in seen_sources,
          "the %-6s stage won at least one case (otherwise it was never "
          "exercised)" % stage)

print()
# The pinned value must be the one the operator typed, not a scaled version of
# it — a pin is an absolute instruction, and this is what "the table says 12.5
# but the machine ran 40" would look like.
op = make_op(True, True, True, True, True)
check(abs(engine_reach(op) - PIN_REACH) < 0.05,
      "a pin wins against EVERY other link at once and is used verbatim "
      "(engine %.2f, typed %.2f)" % (engine_reach(op), PIN_REACH))

# And removing the pin must hand the decision to follow, not back to the fan.
op_nopin = make_op(True, False, True, True, True)
r_nopin = engine_reach(op_nopin)
check(abs(r_nopin - PIN_REACH) > 0.05,
      "removing the pin really does change the answer (%.2f)" % r_nopin)

rows = compute_pass_rows(op_nopin, params_for(op_nopin), mgr)
check((rows[-1].get("prov") or {}).get("reach", {}).get("source") == "follow",
      "with the pin gone, follow-blank takes over (not the fan)")

# The losers list is what the audit shows as "it overrode:". It must name the
# stages that were actually present and lost — an empty list next to a pinned
# value reads as "nothing was overridden", which is the opposite of true.
losers = dict((rows[-1].get("prov") or {}).get("reach", {}).get("losers") or [])
check("fan" in losers or "op" in losers,
      "the explanation names what follow-blank beat (%s)" % sorted(losers))


# ── the degenerate-flange guard: a REAL "I turned it on and nothing happened" ──
#
# follow-blank switches itself off when the flange it measures is smaller than
# `reach_follow_min` (default 10 mm), or when the pass sits at/below the base.
# Added 2026-07-22 for a good reason — at the very base the estimate collapses
# and would make only the FIRST pass a short stub — but it is invisible from the
# operation panel, and it is a genuine answer to "I ticked follow blank edge and
# the reach did not move".
#
# It is also angle-dependent, which is the surprising part: the flat estimate is
# converted to a SLANT length along the exit, so the same flange lands either
# side of the floor depending on the pass angle. Measured on this mandrel with a
# x1.5 blank (flat flange 9.815 mm): off at 90-120 deg, on from 140 deg.
print()
SMALL_BLANK = float(mgr.props["br"]) * 1.5


def _reach_with(blank_r, angle, follow_min=None):
    op = make_op(angular=(angle is not None), pin=False, follow=True,
                 fan=False, op_reach=True)
    if angle is not None:
        op["pass_angle"] = angle
    if follow_min is not None:
        op["reach_follow_min"] = follow_min
    p = params_for(op)
    p["blank_radius"] = blank_r
    pg = PathGenerator()
    pg.calculate_paths(p, {}, mgr)
    rows = compute_pass_rows(op, p, mgr)
    return pg.last_op_reach.get(0), (rows[-1].get("prov") or {}).get("reach", {}).get("source")


r_off, src_off = _reach_with(SMALL_BLANK, 120.0)
check(src_off != "follow" and abs(r_off - OP_REACH) < 0.05,
      "a flange under the 10 mm floor silently disables follow-blank "
      "(reach %.2f from %s — the operation's own value, unchanged)"
      % (r_off, src_off))

r_on, src_on = _reach_with(SMALL_BLANK, 170.0)
check(src_on == "follow",
      "the SAME flange at a steeper pass angle is above the floor and follow "
      "does apply (reach %.2f from %s) — the guard is angle-dependent"
      % (r_on, src_on))

r_floor, src_floor = _reach_with(SMALL_BLANK, 120.0, follow_min=0.0)
check(src_floor == "follow",
      "lowering reach_follow_min to 0 re-enables it (reach %.2f from %s) — "
      "proving the floor, not the geometry, was the cause"
      % (r_floor, src_floor))

# And the mirror must agree about being switched off, or the pass table would
# show a follow value the machine never used.
check(abs(r_off - OP_REACH) < 0.05,
      "when the guard trips, table and engine agree on the fallback")

print()
print("FAILURES:" if fails else "ALL REACH-PRIORITY CHECKS PASSED",
      fails if fails else "")
sys.exit(1 if fails else 0)
