# -*- coding: utf-8 -*-
"""The toolpath-list LAYOUT: how many entries an op contributes, and in what order.

Two silent bugs, both found by a 2026-08-30 check-up, both of the same shape —
something outside `calculate_paths` restated a rule the engine owns, and then the
engine changed.

  #1  `operations: []` was treated as "old file, migrate me". It is not: it is an
      operator who deleted every operation. The migration built a roughing op out
      of `num_sweeping_passes`, a parameter today's UI does not even show, so
      clearing the program and exporting produced a full cutting program. Measured
      on a real recipe before the fix: 12 passes, 1036 lines of motion. `del_op`
      has no last-op guard, so it was one Delete key away.

  #2  A reverse pass stopped building a back pass (#49, 2026-08-29) because it
      already IS the return stroke. Six places still counted one anyway, from
      `back_pass_enabled` alone: the renderer, the pass colouring, the per-pass
      tool radius, the active-pass mapping and the PDF. The engine emitted 4
      paths while the UI indexed 6, so every entry after the first named the
      wrong pass. G-code was never affected — emission runs off
      `last_back_pass_meta` and `_path_op_map`, which are engine truth — which is
      exactly why nothing caught it.

What must hold:
  1. An EMPTY operation list produces no passes and no motion. An ABSENT one
     still migrates, because the legacy/headless callers depend on that.
  2. `op_builds_back_pass` / `op_toolpath_entries` are the one rule, and they
     agree with what `calculate_paths` actually emits.
  3. The UI's own mapping (`ProgramTab._op_toolpath_stride`) lands on the same
     count as the engine for the combination that broke it.

Run:  python _test_toolpath_layout.py
"""
import numpy as np

from mandrel_analyzer import MandrelManager
from path_generator import (PathGenerator, op_builds_back_pass,
                            op_toolpath_entries)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()

BASE = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
        "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
        "pass_shape": "linear_approach"}


def params_for(ops):
    return {"operations": ops, "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0}


def op(**extra):
    o = dict(BASE)
    o.update(extra)
    return o


# ── 1. an empty list is an answer, not a missing one ────────────────────────
print("\n[1] operations: [] means zero passes (#1)")

paths, _, _, _, rapids, _ = pg.calculate_paths(params_for([]), {}, mgr)
check("empty list -> no paths", len(paths) == 0, f"got {len(paths)}")
check("empty list -> no rapids", len(rapids) == 0, f"got {len(rapids)}")

# The migration used to fire here and invent passes from this very key.
p_bait = params_for([])
p_bait["num_sweeping_passes"] = 12
paths_bait = pg.calculate_paths(p_bait, {}, mgr)[0]
check("num_sweeping_passes=12 cannot resurrect a cleared program",
      len(paths_bait) == 0, f"got {len(paths_bait)} paths")

gcode = pg.generate_gcode(params=p_bait)
motion = [l for l in gcode.splitlines() if l.startswith(("G0 ", "G1 ", "G00", "G01"))]
check("a cleared program emits no motion", not motion,
      f"got {len(motion)} motion line(s)")

# ABSENT is still migrated — test_headless.py and test_path_generator.py drive the
# engine this way, and so does every pre-ops .ssp.
p_legacy = {"auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "num_sweeping_passes": 3}
check("an ABSENT operations key still migrates (legacy files keep working)",
      len(pg.calculate_paths(p_legacy, {}, mgr)[0]) == 3)

check("a malformed (non-list) operations value migrates too",
      len(pg._ensure_ops_dict({"operations": "junk", "num_sweeping_passes": 2})) == 1)


# ── 2. one rule for the back pass ───────────────────────────────────────────
print("\n[2] op_builds_back_pass is the only rule (#2)")

TRUTH = (
    ({},                                                       False, 1),
    ({"count": 4},                                             False, 4),
    ({"back_pass_enabled": True, "count": 4},                  True,  8),
    ({"back_pass_enabled": True, "count": 4,
      "direction": "forward"},                                 True,  8),
    ({"back_pass_enabled": True, "count": 4,
      "direction": "reverse"},                                 False, 4),
    ({"back_pass_enabled": True, "count": 3, "type": "cutting"}, False, 1),
    ({"back_pass_enabled": True, "count": 3, "type": "bending"}, False, 1),
    ({"back_pass_enabled": True, "count": None},               True,  2),
    (None,                                                     False, 1),
)
for o, want_bp, want_n in TRUTH:
    got_bp, got_n = op_builds_back_pass(o), op_toolpath_entries(o)
    check(f"{str(o)[:46]:48} -> back={want_bp!s:5} n={want_n}",
          got_bp == want_bp and got_n == want_n,
          f"got back={got_bp} n={got_n}")


# ── 3. the rule matches what the engine emits ───────────────────────────────
print("\n[3] op_toolpath_entries == what calculate_paths actually appends")

CASES = (
    ("forward, no back pass",   op(count=3)),
    ("forward + back pass",     op(count=3, back_pass_enabled=True,
                                   direction="forward")),
    ("reverse, no back pass",   op(count=3, direction="reverse")),
    ("reverse + back pass tick", op(count=3, direction="reverse",
                                    back_pass_enabled=True)),
)
for name, o in CASES:
    n_engine = len(pg.calculate_paths(params_for([o]), {}, mgr)[0])
    check(f"{name}: engine {n_engine} == rule {op_toolpath_entries(o)}",
          n_engine == op_toolpath_entries(o))

# The regression itself: a reverse op with the box ticked, followed by another op.
# Before the fix the second op's passes were attributed to the first.
rev = op(count=2, direction="reverse", back_pass_enabled=True)
fin = op(count=2, type="finishing", direction="forward")
n_engine = len(pg.calculate_paths(params_for([rev, fin]), {}, mgr)[0])
n_rule = op_toolpath_entries(rev) + op_toolpath_entries(fin)
check(f"reverse+back_pass then another op: engine {n_engine} == rule {n_rule}",
      n_engine == n_rule)
check("the engine reported the back pass it refused to build",
      len(pg.last_back_pass_ignored) == 2,
      f"got {len(pg.last_back_pass_ignored)}")
check("_path_op_map really does hand the tail passes to the SECOND op",
      [o is fin for o in pg._path_op_map] == [False, False, True, True],
      str([None if o is None else o.get("type") for o in pg._path_op_map]))

# A disabled op contributes nothing, and the rule never claims otherwise.
n_engine = len(pg.calculate_paths(params_for([dict(rev, enabled=False), fin]),
                                  {}, mgr)[0])
check(f"a disabled op contributes nothing: engine {n_engine} == "
      f"rule {op_toolpath_entries(fin)}",
      n_engine == op_toolpath_entries(fin))


# ── 4. the UI's own mapping agrees ──────────────────────────────────────────
print("\n[4] the Program tab lands on the same count as the engine")
try:
    from ui.tabs.program_tab import ProgramTab
    stride = ProgramTab._op_toolpath_stride.__get__(object())
    logical = ProgramTab._op_logical_count.__get__(object())
    for name, o in CASES:
        n_engine = len(pg.calculate_paths(params_for([o]), {}, mgr)[0])
        n_ui = logical(o) * stride(o)
        check(f"{name}: UI {n_ui} == engine {n_engine}", n_ui == n_engine)
except ImportError as e:                                       # pragma: no cover
    print(f"  SKIP  ProgramTab unavailable ({e})")


print()
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for n in FAIL:
        print("  FAILED:", n)
    raise SystemExit(1)
print("ALL PASS")
