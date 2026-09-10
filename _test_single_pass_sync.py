# -*- coding: utf-8 -*-
"""#105 — one number when an operation has only one pass.

An operator who runs a SINGLE pass per operation ends up describing that one
pass twice: the operation says Clearance 1.0, the pass table says 0.5. The
engine runs 0.5, the operation editor keeps showing 1.0, and the operator does
not know which number is real.

The fix lifts the pass's value UP into the operation and deletes the pin, so
both places read the same number. The whole feature rests on ONE claim:

    THE LIFT DOES NOT MOVE THE MACHINE.

That claim is not argued here, it is measured — the toolpath is generated
before and after the lift and compared point for point. If a future change to
the resolution chain in path_generator breaks the equivalence for any field,
section [2] fails.

What must hold:
  1. The rule fires on exactly the right operations (1 pass, roughing) and no
     others.
  2. Every liftable field is toolpath-neutral, field by field and all together.
  3. The two REFUSALS are real, not superstition: lifting them would change the
     path, which is proved by lifting them by hand and measuring the difference.
  4. Hand-drawn exit tails, break points, blocked pins and residual slots are
     preserved — the lift touches only what it claims to.
  5. Nothing at all happens with the flag off / on a multi-pass op.

Run:  runtest.bat _test_single_pass_sync.py
"""
import copy

import numpy as np

import single_pass_sync as sps
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()


def base_op(**extra):
    """A one-pass roughing op in POLAR exit mode (so pass_angle is live)."""
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "end_z": 60.0,
          "r_tool": 25.0, "clearance": 1.0, "pass_angle": 20.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "p2_z_extend": 0.0, "reach": 40.0, "pass_shape": "linear_approach"}
    op.update(extra)
    return op


def paths(op, **pextra):
    """Every toolpath this single op produces, as one flat array list."""
    p = {"operations": [copy.deepcopy(op)], "auto_calc_angle": False,
         "min_safety_gap": -999.0, "final_part_thickness_on_mandrel": 0.0,
         "shell_thickness": 0.0}
    p.update(pextra)
    return pg.calculate_paths(p, {}, mgr)[0]


def same_paths(a, b):
    if len(a) != len(b):
        return False
    return all(x.shape == y.shape and np.allclose(x, y, atol=1e-12)
               for x, y in zip(a, b))


def pins(**kw):
    return {"pass_edits": {"0": dict(kw)}}


# ── 1. when the rule fires ──────────────────────────────────────────────────
print("\n[1] applies() — exactly the single-pass roughing case")
check("1 pass roughing", sps.applies(base_op()))
check("2 passes → no", not sps.applies(base_op(count=2)))
check("0 passes → no", not sps.applies(base_op(count=0)))
check("finishing → no (engine ignores pins there; lifting WOULD change the path)",
      not sps.applies({"type": "finishing", "count": 1}))
for _t in ("cutting", "bending", "point"):
    check(f"{_t} → no", not sps.applies({"type": _t, "count": 1}))
check('count "1" as text still counts', sps.applies(base_op(count="1")))
check("count missing → treated as 1", sps.applies({"type": "roughing"}))
check("empty op → no", not sps.applies({}) and not sps.applies(None))


# ── 2. THE CLAIM: lifting does not move the machine ─────────────────────────
print("\n[2] toolpath neutrality — measured, not argued")

NEUTRAL_CASES = [
    # (label, pin dict, op overrides so the pin actually differs)
    ("clearance",           {"clearance": 0.35},    {}),
    ("clearance (op unset)", {"clearance": 0.35},   {"clearance": None}),
    ("extend",              {"p2_z_extend": 7.5},   {}),
    ("anchor Z",            {"target_z": 44.0},     {}),
    ("pass angle",          {"pass_angle": 55.0},   {}),
    ("reach",               {"reach": 61.0},        {}),
    ("all five together",   {"clearance": 0.35, "p2_z_extend": 7.5, "target_z": 44.0,
                             "pass_angle": 55.0, "reach": 61.0}, {}),
]
for label, pin, over in NEUTRAL_CASES:
    op = base_op(**over)
    op.update(pins(**pin))
    before = paths(op)
    lifted = copy.deepcopy(op)
    merged = sps.merge_op(lifted)
    check(f"{label}: lifted", len(merged) == len(pin),
          f"{len(merged)}/{len(pin)} field(s)")
    check(f"{label}: toolpath identical after the lift",
          same_paths(before, paths(lifted)))
    check(f"{label}: pin is gone", not sps.pass_slot(lifted))

# The op fields really hold the pass's numbers now (not just "a path that matches").
op = base_op()
op.update(pins(clearance=0.35, p2_z_extend=7.5, target_z=44.0,
               pass_angle=55.0, reach=61.0))
sps.merge_op(op)
check("anchor Z landed in Zone Start Z", op["start_z"] == 44.0, str(op["start_z"]))
check("clearance landed in Clearance", op["clearance"] == 0.35)
check("extend landed in Extend", op["p2_z_extend"] == 7.5)
check("angle landed in Pass Angle", op["pass_angle"] == 55.0)
check("reach landed in Reach", op["reach"] == 61.0)
check("pass_edits removed entirely once empty", "pass_edits" not in op)

# Neutrality must survive a back pass too (a second toolpath from the same op).
op = base_op(back_pass_enabled=True)
op.update(pins(clearance=0.35, target_z=44.0))
before = paths(op)
lifted = copy.deepcopy(op)
sps.merge_op(lifted)
check("back pass: both toolpaths identical after the lift",
      len(before) == 2 and same_paths(before, paths(lifted)),
      f"{len(before)} path(s)")

# And on a reverse op, where the pass runs backwards.
op = base_op(direction="reverse")
op.update(pins(clearance=0.35, reach=61.0, target_z=44.0))
before = paths(op)
lifted = copy.deepcopy(op)
sps.merge_op(lifted)
check("reverse pass: toolpath identical after the lift",
      same_paths(before, paths(lifted)))


# ── 3. the two refusals are real ────────────────────────────────────────────
print("\n[3] the refusals — proved by doing the forbidden lift and measuring")

# 3a. Reach under follow-blank. The pin beats follow-blank; op["reach"] does
#     not. Lifting would hand the pass to follow-blank.
FOLLOW = {"blank_radius": 220.0}
op = base_op(reach_follow_blank=True)
op.update(pins(reach=61.0))
merges, blocks = sps.plan(op)
check("reach + follow-blank is refused",
      [k for k, _ in blocks] == ["reach"] and not merges)
check("refusal names the follow-blank reason",
      blocks and blocks[0][1] == sps.BLOCK_FOLLOW_BLANK)
before = paths(op, **FOLLOW)
forbidden = copy.deepcopy(op)                       # do it anyway, by hand
forbidden["reach"] = 61.0
forbidden.pop("pass_edits")
check("...and doing it anyway DOES change the toolpath (so refusing is right)",
      not same_paths(before, paths(forbidden, **FOLLOW)))
kept = copy.deepcopy(op)
sps.merge_op(kept)
check("refused pin stays on the pass", sps.pass_slot(kept).get("reach") == 61.0)
check("refusing keeps the toolpath identical",
      same_paths(before, paths(kept, **FOLLOW)))

# Same op WITHOUT follow-blank: the very same reach pin is liftable and neutral.
op = base_op()
op.update(pins(reach=61.0))
before = paths(op, **FOLLOW)
lifted = copy.deepcopy(op)
sps.merge_op(lifted)
check("reach IS liftable once follow-blank is off",
      not sps.pass_slot(lifted) and same_paths(before, paths(lifted, **FOLLOW)))

# 3b. Angle pin in RAW exit mode. The engine gates the whole polar block on
#     pass_angle being set, so the pin does nothing — but lifting it would turn
#     the operation polar.
op = base_op(pass_angle=None)
op.update(pins(pass_angle=55.0))
merges, blocks = sps.plan(op)
check("angle in RAW mode is refused",
      [k for k, _ in blocks] == ["pass_angle"] and not merges)
check("refusal names the raw-mode reason", blocks[0][1] == sps.BLOCK_RAW_ANGLE)
before = paths(op)
forbidden = copy.deepcopy(op)
forbidden["pass_angle"] = 55.0
forbidden.pop("pass_edits")
check("...and doing it anyway DOES change the toolpath",
      not same_paths(before, paths(forbidden)))
kept = copy.deepcopy(op)
sps.merge_op(kept)
check("refused angle pin stays put and the path is unchanged",
      sps.pass_slot(kept).get("pass_angle") == 55.0 and same_paths(before, paths(kept)))

# A refusal must not block its neighbours in the same slot.
op = base_op(reach_follow_blank=True)
op.update(pins(reach=61.0, clearance=0.35))
sps.merge_op(op)
check("a refused pin does not block the liftable ones in the same slot",
      op["clearance"] == 0.35 and sps.pass_slot(op) == {"reach": 61.0})


# ── 4. what the lift must NOT touch ─────────────────────────────────────────
print("\n[4] everything else is left alone")

TAIL = [{"anchor": "p3", "dx": 5.0, "dz": -3.0}]
BREAKS = [{"t": 0.4, "angle": -12.0}]
op = base_op()
op["pass_edits"] = {"0": {"clearance": 0.35, "exit_points": TAIL,
                          "exit_breaks": BREAKS}}
sps.merge_op(op)
check("hand-drawn exit tail survives", sps.pass_slot(op).get("exit_points") == TAIL)
check("break points survive", sps.pass_slot(op).get("exit_breaks") == BREAKS)
check("the pin next to them is still lifted",
      op["clearance"] == 0.35 and "clearance" not in sps.pass_slot(op))

# Residual slots from when the op had more passes: the engine never reads them,
# and deleting operator data is not this feature's job.
op = base_op()
op["pass_edits"] = {"0": {"clearance": 0.35}, "3": {"reach": 99.0}}
sps.merge_op(op)
check("residual slot 3 is left untouched",
      op["pass_edits"] == {"3": {"reach": 99.0}}, str(op.get("pass_edits")))

# An unreadable pin is not lifted — the engine ignores it, so must we.
op = base_op()
op.update(pins(clearance="abc", p2_z_extend=""))
before_clr = op["clearance"]
sps.merge_op(op)
check("garbage / blank pins are not lifted",
      op["clearance"] == before_clr and sps.pass_slot(op) == {"clearance": "abc",
                                                             "p2_z_extend": ""})

# Int-keyed slots (older files) are handled, not duplicated.
op = base_op()
op["pass_edits"] = {0: {"clearance": 0.35}}
sps.merge_op(op)
check("int-keyed pass slot is read and cleaned up",
      op["clearance"] == 0.35 and "pass_edits" not in op, str(op.get("pass_edits")))


# ── 5. no-ops ───────────────────────────────────────────────────────────────
print("\n[5] does nothing when it should do nothing")

op = base_op(count=3)
op.update(pins(clearance=0.35))
snapshot = copy.deepcopy(op)
check("multi-pass op untouched", sps.merge_op(op) == [] and op == snapshot)

op = {"type": "finishing", "count": 1, "clearance": 1.0, **pins(clearance=0.35)}
snapshot = copy.deepcopy(op)
check("finishing op untouched", sps.merge_op(op) == [] and op == snapshot)

op = base_op()
snapshot = copy.deepcopy(op)
check("op with no pins untouched", sps.merge_op(op) == [] and op == snapshot)

op = base_op()
op.update(pins(clearance=0.35))
snap = copy.deepcopy(op)
sps.plan(op)
check("plan() really left the op alone", op == snap)

# differs(): a pin that merely repeats the operation's value is noise.
op = base_op(clearance=1.0)
op.update(pins(clearance=1.0))
check("a pin equal to the op value is not a disagreement", sps.differs(op) == [])
check("...but it is still lifted (the duplicate number goes away)",
      len(sps.plan(op)[0]) == 1)
op = base_op(clearance=1.0)
op.update(pins(clearance=0.35))
check("a pin that differs IS reported as a disagreement",
      [d[0] for d in sps.differs(op)] == ["clearance"])


# ── 6. whole-program helpers ────────────────────────────────────────────────
print("\n[6] scan / merge_all across a program")
ops = [
    base_op(),                                          # 0: nothing to do
    dict(base_op(), **pins(clearance=0.35)),            # 1: one lift
    dict(base_op(count=4), **pins(clearance=0.35)),     # 2: multi-pass, skip
    dict(base_op(reach_follow_blank=True), **pins(reach=61.0, clearance=0.35)),  # 3
]
found = sps.scan(ops)
check("scan finds only the ops with something to lift",
      [i for i, _m, _b in found] == [1, 3], str([i for i, _m, _b in found]))
check("scan reports the refusal alongside the lift",
      [k for k, _r in found[1][2]] == ["reach"])
done = sps.merge_all(ops)
check("merge_all lifts exactly those ops", [i for i, _m in done] == [1, 3])
check("merge_all is idempotent", sps.merge_all(ops) == [])
check("scan is clean afterwards (bar the refusal)", sps.scan(ops) == [])


# ── summary ─────────────────────────────────────────────────────────────────
print(f"\n{'='*66}\n  {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for n in FAIL:
        print(f"    FAILED: {n}")
raise SystemExit(1 if FAIL else 0)
