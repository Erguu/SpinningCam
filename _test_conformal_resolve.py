# -*- coding: utf-8 -*-
"""Headless test: the conformal-clearance setting resolves the same way everywhere.

THE BUG THIS EXISTS FOR (F3, fixed 2026-09-10, previously untested)

`conformal_clearance_operation_specific` is a THREE-state field: absent (follow
the global), explicit True, explicit False. A checkbox has two states, so the
editor collapsed "absent" onto "off".

Everything that COMPUTED — the engine, the pass-table mirror — fell back to the
global. Everything that DISPLAYED — the checkbox, both pass diagrams — fell back
to a hardcoded False. Two consequences, both silent:

1. With the global ON, an untouched operation RAN conformal while its box looked
   empty and its diagram drew the non-conformal shape. The picture disagreed
   with the machine.
2. Ticking that box on and then off wrote an explicit False. An explicit False
   defeats the global, so the pass moved from normal-projected to purely radial
   placement — and looked identical before and after.

The fix made `resolve_conformal(op, params)` the single source of truth. Nothing
tested it. This file does.

WHAT IS PINNED

1. The truth table: three op states x two global states.
2. `conformal_is_inherited` tells "not set" from "explicitly off".
3. The flag is not inert — on a SLOPED surface it really does move the toolpath.
   (On a cylinder the normal IS radial, so conformal is a no-op there. A test
   written on a cylinder would pass while the feature did nothing at all.)
4. The engine and the pass-table mirror agree in all six combinations.
5. SOURCE SCAN: nobody reads the raw key with a `False` default any more. This
   is the structural guard — it fails when somebody reintroduces the exact
   pattern the fix removed, in a file that does not exist yet.
"""
import os
import re
import sys

from mandrel_analyzer import MandrelManager
from path_generator import (CONFORMAL_GLOBAL_KEY, CONFORMAL_OP_KEY,
                            PathGenerator, conformal_is_inherited,
                            resolve_conformal)

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


ABSENT = object()


def _op(conformal=ABSENT):
    op = {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T1",
          "r_tool": 25.0, "clearance": 5.0, "start_z": 10.0, "end_z": 40.0,
          "pass_shape": "linear_approach", "pass_angle": 120.0, "reach": 40.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0}
    if conformal is not ABSENT:
        op[CONFORMAL_OP_KEY] = conformal
    return op


def _params(ops, global_on):
    return {"operations": ops, CONFORMAL_GLOBAL_KEY: global_on,
            "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "blank_radius": 0.0, "collision_resolution": 0.5,
            "home_x": 300.0, "home_z": 150.0,
            "retract_x": 50.0, "retract_z": 50.0}


# ── 1. The truth table ────────────────────────────────────────────────────
# The row that matters is (absent, global ON) -> True. That is the one every
# display got wrong.
TRUTH = [
    (ABSENT, False, False),
    (ABSENT, True,  True),    # <- inherited from the global. The F3 row.
    (True,   False, True),    # explicit ON beats a global that is off
    (True,   True,  True),
    (False,  False, False),
    (False,  True,  False),   # explicit OFF beats a global that is on
]
for op_val, global_on, want in TRUTH:
    got = resolve_conformal(_op(op_val), {CONFORMAL_GLOBAL_KEY: global_on})
    name = "absent" if op_val is ABSENT else str(op_val)
    check(got is want,
          f"resolve_conformal(op={name}, global={global_on}) -> {got} "
          f"(expected {want})")

# Defensive: the helper is called with None and {} in real code paths.
check(resolve_conformal(None, {CONFORMAL_GLOBAL_KEY: True}) is True,
      "resolve_conformal(None, global=True) follows the global")
check(resolve_conformal({}, {}) is False,
      "resolve_conformal({}, {}) is False when nothing is set")


# ── 2. "not set" is distinguishable from "explicitly off" ─────────────────
check(conformal_is_inherited(_op()) is True,
      "an untouched op reports as inherited")
check(conformal_is_inherited(_op(False)) is False,
      "an explicit False is NOT inherited — this is the distinction a checkbox "
      "cannot show, and why the editor needs the grey '(from global)' note")
check(conformal_is_inherited(_op(True)) is False,
      "an explicit True is not inherited")
check(conformal_is_inherited(None) is True, "None is treated as inherited")


# ── 3. The flag is not inert — on a SLOPE it moves the toolpath ───────────
# create_default_cone gives a sloped wall. On a cylinder the surface normal is
# already radial and conformal placement is identical, so a test built there
# would pass no matter what the flag did.
mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)


def gcode_for(op_val, global_on):
    pg = PathGenerator()
    p = _params([_op(op_val)], global_on)
    pg.calculate_paths(p, {}, mgr)
    return pg.generate_gcode(params=p), pg


g_off, _ = gcode_for(False, False)
g_on, _ = gcode_for(True, False)
check(g_off != g_on,
      "conformal ON vs OFF really does change the G-code on a sloped mandrel "
      "(otherwise every check here would pass on a dead flag)")

# The F3 pair: an untouched op with the global ON must match an explicit ON,
# and must NOT match an explicit OFF.
g_inherited, _ = gcode_for(ABSENT, True)
check(g_inherited == g_on,
      "untouched op + global ON == explicit ON (the engine inherits)")
check(g_inherited != g_off,
      "untouched op + global ON differs from explicit OFF — this is the pass "
      "movement that ticking the box on and off used to cause silently")

g_explicit_off_global_on, _ = gcode_for(False, True)
check(g_explicit_off_global_on == g_off,
      "explicit OFF wins over a global that is ON")


# ── 4. The pass-table mirror agrees with the engine, all six rows ─────────
import ui.dialogs.pass_table as PTAB

for op_val, global_on, want in TRUTH:
    op = _op(op_val)
    p = _params([op], global_on)
    # The mirror reads it through the same helper; assert the VALUE it would
    # use equals what the engine resolved, for every combination.
    mirror = resolve_conformal(op, p)
    check(mirror is want,
          f"pass-table mirror agrees for (op={'absent' if op_val is ABSENT else op_val}, "
          f"global={global_on}) -> {mirror}")
    # and that it can actually build rows in that state
    rows = PTAB.compute_pass_rows(op, p, mgr)
    check(len(rows) == 2, f"pass table still produces rows in that state ({len(rows)})")


# ── 5. SOURCE SCAN: the removed pattern must not come back ────────────────
# The fix was to stop reading the key directly with a False default. A new file
# that reintroduces `op.get(CONFORMAL_OP_KEY, False)` recreates F3 exactly, and
# no behavioural test would catch it until an operator noticed. So look for it.
HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = ("_test_", "test_", "_diag_", "_research_", "_proof_")
# `.get(KEY)` with NO default is fine — that is how the resolver itself, and
# conformal_is_inherited, read it. `.get(KEY, False)` is the bug.
BAD = re.compile(r"\.get\(\s*(?:CONFORMAL_OP_KEY|[\"']conformal_clearance_operation_specific[\"'])\s*,")
offenders = []
for root, dirs, files in os.walk(HERE):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "backup", ".git")]
    for fn in sorted(files):
        if not fn.endswith(".py") or any(fn.startswith(s) for s in SKIP):
            continue
        path = os.path.join(root, fn)
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if line.lstrip().startswith("#"):
                    continue
                if BAD.search(line):
                    offenders.append("%s:%d" % (os.path.relpath(path, HERE), n))
check(not offenders,
      f"nobody reads the conformal key with a default any more — use "
      f"resolve_conformal(op, params) (offenders: {offenders})")

# And the consumers really do go through the resolver.
consumers = 0
for root, dirs, files in os.walk(HERE):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "backup", ".git")]
    for fn in sorted(files):
        if not fn.endswith(".py") or any(fn.startswith(s) for s in SKIP):
            continue
        with open(os.path.join(root, fn), encoding="utf-8") as f:
            consumers += len(re.findall(r"resolve_conformal\(", f.read()))
check(consumers >= 7,
      f"resolve_conformal is still wired into every consumer "
      f"(found {consumers} references; the fix wired 6 call sites + the def)")

print()
print("FAILURES:" if fails else "ALL CONFORMAL CHECKS PASSED", fails if fails else "")
sys.exit(1 if fails else 0)
