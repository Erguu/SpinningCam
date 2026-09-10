# -*- coding: utf-8 -*-
"""Headless test: everything that counts toolpaths must count them the same way.

THE FAILURE THIS EXISTS FOR

``calculate_paths`` and ``generate_gcode`` walk the toolpath list on a SHARED
index. Several other places re-derive that same list independently — the colour
strip, the pass table, the pass comparison, the operation tree's pass counter.
When one of them disagrees about whether an operation contributes a toolpath,
every later pass is attributed to the wrong operation: wrong tool, wrong feed,
wrong colour, and a pass table describing somebody else's pass.

The operation types that contribute NO forward pass per ``count`` are the sharp
edge here. ``cutting`` and ``bending`` emit exactly one path whatever ``count``
says; ``point`` emits NONE at all. That set is currently spelled out in four
separate places:

    pass_compare._NO_PASS_TYPES          pass_compare.py:52
    program_tab._NO_PASS_OP_TYPES        ui/tabs/program_tab.py:123
    an inline literal                    ui/dialogs/pass_table.py:68
    a category check                     pass_colors.path_categories

Adding a sixth operation type and updating three of the four is silent. On a
machine where the missed consumer is only the colour strip it is cosmetic; where
it is the pass table it hands the operator the wrong numbers to edit.

WHAT IS PINNED

1. The declared sets are identical to each other.
2. Every op type the adapter offers is classified by all of them the same way.
3. The ENGINE agrees: the number of toolpaths it really builds equals what
   ``pass_colors.path_categories`` predicts, for a program containing one of
   every op type.

Point 3 is the one that cannot be faked by keeping four literals in step — it
compares the mirrors against the thing they mirror.
"""
import sys
from unittest.mock import MagicMock

import pass_colors
import pass_compare
from machine_adapter import StandardTwoAxisSpinningAdapter
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


# The one place this test is allowed to state the answer. If a new op type is
# added that contributes no per-count pass, it belongs here AND in the four
# sites above — and test 2 below will fail until it is.
EXPECTED_NO_PASS = {"cutting", "bending", "point"}
# Of those, the ones that still emit exactly ONE path (the others emit zero).
EXPECTED_SINGLE_PATH = {"cutting", "bending"}
EXPECTED_ZERO_PATH = {"point"}


# ── 1. The declared sets agree with each other ────────────────────────────
import ui.tabs.program_tab as PT
import ui.dialogs.pass_table as PTAB

check(set(pass_compare._NO_PASS_TYPES) == EXPECTED_NO_PASS,
      f"pass_compare._NO_PASS_TYPES == {sorted(EXPECTED_NO_PASS)} "
      f"(got {sorted(pass_compare._NO_PASS_TYPES)})")
check(set(PT._NO_PASS_OP_TYPES) == EXPECTED_NO_PASS,
      f"program_tab._NO_PASS_OP_TYPES == {sorted(EXPECTED_NO_PASS)} "
      f"(got {sorted(PT._NO_PASS_OP_TYPES)})")
check(set(pass_compare._NO_PASS_TYPES) == set(PT._NO_PASS_OP_TYPES),
      "the two declared sets are identical to each other")


# ── 2. Every adapter op type is classified consistently ───────────────────
# compute_pass_rows returns no rows for a no-pass type; the tree's counter
# returns 0 only for the zero-path ones. Both are asked about EVERY type the
# machine offers, so a newly added type cannot slip past unclassified.
mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])

adapter = StandardTwoAxisSpinningAdapter()
ALL_TYPES = adapter.get_available_op_types()
check(EXPECTED_NO_PASS.issubset(set(ALL_TYPES)),
      f"the adapter still offers every no-pass type ({ALL_TYPES})")


def make_op(op_type, count=3):
    op = {"type": op_type, "enabled": True, "count": count, "tool_id": "T1",
          "r_tool": 25.0, "clearance": 0.0,
          "start_z": min_z + 10, "end_z": min_z + 30,
          "pass_shape": "linear_approach", "pass_angle": 120.0, "reach": 40.0,
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0}
    if op_type in ("cutting", "bending"):
        op.update({"plunge_start_x": 120.0, "plunge_start_z": min_z + 20.0,
                   "plunge_end_x": 90.0, "plunge_end_z": min_z + 20.0})
    if op_type == "point":
        op.update({"point_mode": "absolute", "point_x": 150.0,
                   "point_z": min_z + 40.0})
    return op


_tab = PT.ProgramTab.__new__(PT.ProgramTab)      # no widgets needed for the rule
for ot in ALL_TYPES:
    op = make_op(ot)
    want_rows = 0 if ot in EXPECTED_NO_PASS else 3
    rows = PTAB.compute_pass_rows(op, {"blank_radius": 0.0}, mgr)
    check(len(rows) == want_rows,
          f"pass_table.compute_pass_rows({ot}) -> {len(rows)} rows "
          f"(expected {want_rows})")

    want_count = 0 if ot in EXPECTED_ZERO_PATH else (1 if ot in EXPECTED_SINGLE_PATH else 3)
    got_count = _tab._op_logical_count(op)
    check(got_count == want_count,
          f"program_tab._op_logical_count({ot}) -> {got_count} "
          f"(expected {want_count})")


# ── 3. The engine agrees with the colour mirror ───────────────────────────
# One of every op type in a single program, counts deliberately unequal so a
# mirror that ignores `count` shows up as a mismatch rather than a coincidence.
ops = [make_op("roughing", count=3),
       make_op("point"),
       make_op("finishing", count=2),
       make_op("cutting"),
       make_op("bending"),
       make_op("point")]
params = {"operations": ops, "blank_radius": 0.0, "auto_calc_angle": False,
          "min_safety_gap": -999.0, "final_part_thickness_on_mandrel": 0.0,
          "shell_thickness": 0.0, "target_clearance": 0.0,
          "home_x": 300.0, "home_z": 150.0, "retract_x": 50.0, "retract_z": 50.0}

pg = PathGenerator()
pg.calculate_paths(params, {}, mgr)
n_engine = len(pg.last_calculated_paths or [])
cats = pass_colors.path_categories(ops)

check(n_engine == len(cats),
      f"engine built {n_engine} toolpaths, path_categories predicted "
      f"{len(cats)} — these index the SAME list")
check("point" not in cats,
      f"no Point op contributes a colour (categories: {sorted(set(cats))})")
check(cats.count("cutting") == 1 and cats.count("bending") == 1,
      f"cutting/bending contribute exactly one path each despite count=3 "
      f"(cutting {cats.count('cutting')}, bending {cats.count('bending')})")

# The Point ops must have produced markers instead of paths — otherwise "no
# toolpath" could be hiding an op that did nothing at all.
check(len(getattr(pg, "last_point_markers", []) or []) == 2,
      f"both Point ops produced a marker "
      f"({len(getattr(pg, 'last_point_markers', []) or [])})")

# A disabled op contributes nothing, in the engine and in the mirror alike.
ops_off = [dict(o) for o in ops]
ops_off[0]["enabled"] = False
pg2 = PathGenerator()
pg2.calculate_paths(dict(params, operations=ops_off), {}, mgr)
check(len(pg2.last_calculated_paths or []) == len(pass_colors.path_categories(ops_off)),
      "a disabled op drops the same number of paths from both")

print()
print("FAILURES:" if fails else "ALL NO-PASS MIRROR CHECKS PASSED", fails if fails else "")
sys.exit(1 if fails else 0)
