# -*- coding: utf-8 -*-
"""Headless test: the screen reports what the machine actually did.

THE COMPLAINT THIS EXISTS FOR

"The table says 118 but the machine ran something else." Every number an
operator reads — the pass table, the operation panel, the pass diagram — is
computed by a MIRROR of the engine, not by the engine. Mirrors drift. This
project has been bitten twice:

  2026-07-22  the engine gained the degenerate-flange guard; the pass-table
              mirror did not. The table showed ~9.8 mm while the machine ran
              ~39 mm.
  2026-09-10  F3: the engine resolved conformal from the global setting; the
              checkbox and both diagrams resolved it from a hardcoded False.
              The picture disagreed with the machine.

Neither was a wrong VALUE. Both were the screen and the engine answering the
same question differently. That is what this file tests.

TWO PARTS

A. NUMERIC. Over a matrix of configurations, the pass table's last row must
   equal the engine's own `last_op_reach` / `last_op_end_angle` /
   `last_op_end_z`. Those three are what the operation list and the pass
   navigator display, so a disagreement is visible to the operator.

B. STRUCTURAL. A `resolve_*` helper exists precisely so one question has one
   answer. The F3 bug was possible because the engine called the resolver and
   the display did not. So: every resolver must be reachable from BOTH a
   computing site and a displaying site, and nothing may re-derive a resolved
   field by reading the raw key with its own default.

   This is the part that protects fields that do not exist yet.
"""
import itertools
import os
import re
import sys

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.dialogs.pass_table import compute_pass_rows

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
MIN_Z = float(mgr.props["min_z"])
BLANK_R = float(mgr.props["br"]) * 2.0

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


# ── A. numeric agreement over a configuration matrix ──────────────────────

def make_op(**over):
    op = {"type": "roughing", "enabled": True, "count": 3, "tool_id": "T1",
          "r_tool": 25.0, "clearance": 2.0,
          "start_z": MIN_Z + 10, "end_z": MIN_Z + 30,
          "pass_shape": "linear_approach",
          "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "reach": 40.0}
    op.update(over)
    return op


def params_for(op, **over):
    p = {"operations": [op], "blank_radius": BLANK_R,
         "auto_calc_angle": False, "min_safety_gap": -999.0,
         "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
         "target_clearance": 0.0, "home_x": 300.0, "home_z": 150.0,
         "retract_x": 50.0, "retract_z": 50.0,
         "conformal_clearance_all_operations": False}
    p.update(over)
    return p


# Each axis is something that feeds one of the three reported numbers.
MATRIX = {
    "pass_angle":        (None, 120.0, 170.0),
    "reach_follow_blank": (False, True),
    "progressive_angle_enabled": (False, True),
    "progressive_reach_enabled": (False, True),
    "p2_z_extend":       (0.0, 3.0),
    "conformal_clearance_operation_specific": (None, True, False),
    "count":             (1, 3),
}

keys = sorted(MATRIX)
cases = list(itertools.product(*(MATRIX[k] for k in keys)))
print("Comparing engine vs pass table over %d configurations\n" % len(cases))

mismatches = []
compared = 0
for combo in cases:
    over = {}
    for k, v in zip(keys, combo):
        if v is not None:
            over[k] = v
    if over.get("progressive_angle_enabled") and "pass_angle" not in over:
        continue                      # an angle fan with no angle is not a state
    over.setdefault("progressive_angle_end", 170.0)
    over.setdefault("progressive_reach_end", 30.0)

    op = make_op(**over)
    p = params_for(op)
    try:
        rows = compute_pass_rows(op, p, mgr)
        pg = PathGenerator()
        pg.calculate_paths(p, {}, mgr)
    except Exception as e:
        mismatches.append((over, "raised: %r" % (e,)))
        continue
    if not rows:
        mismatches.append((over, "pass table produced no rows"))
        continue

    compared += 1
    last = rows[-1]
    # `z_exact` is the row's CONTACT Z — the same quantity as last_op_end_z
    # ("Real End Z"). The row's `end_z` is where the EXIT LEG finishes, which is
    # a different question and is deliberately different.
    #
    # `angle` is compared only in angular mode: compute_pass_rows returns None
    # for it in raw mode on purpose ("no angle was commanded"), while the engine
    # still reports the angle the geometry came out at. Those are two different
    # questions and comparing them reports a disagreement that is not one.
    fields = [("reach", pg.last_op_reach.get(0), last.get("reach"), 0.05),
              ("contact_z", pg.last_op_end_z.get(0), last.get("z_exact"), 0.05)]
    if "pass_angle" in over:
        fields.append(("angle", pg.last_op_end_angle.get(0), last.get("angle"), 0.05))
    for field, engine_val, table_val, tol in fields:
        if engine_val is None or table_val is None:
            # Both must be absent together: one side having an opinion the
            # other does not is itself a disagreement.
            if (engine_val is None) != (table_val is None):
                mismatches.append(
                    (over, "%s: engine=%r table=%r (one side has no value)"
                     % (field, engine_val, table_val)))
            continue
        if abs(float(engine_val) - float(table_val)) > tol:
            mismatches.append(
                (over, "%s: engine=%.3f table=%.3f" % (field, engine_val, table_val)))

check(not mismatches,
      "engine and pass table agree in all %d comparable configurations" % compared)
for over, why in mismatches[:15]:
    print("      %s\n        %s" % (over, why))

check(compared >= 100,
      "the matrix really ran (%d configurations compared)" % compared)


# ── B. structural: one question, one answer ───────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_PREFIX = ("_test_", "test_", "_diag_", "_research_", "_proof_")
SKIP_DIRS = {"__pycache__", "backup", ".git", "machines", "tool_geometry"}

# resolver -> the raw op key it is the single source of truth for. A consumer
# that reads the raw key WITH ITS OWN DEFAULT has re-derived the answer, which
# is exactly how F3 happened.
RESOLVERS = {
    "resolve_conformal": "conformal_clearance_operation_specific",
    "resolve_speed_mode": "speed_mode",
    "resolve_retract_motion": "retract_motion",
    "resolve_point_motion": "point_motion",
    "resolve_point_mode": "point_mode",
}

# Files that COMPUTE (feed the machine) and files that DISPLAY (feed the eye).
# A resolver used by only one side is the F3 shape.
COMPUTE_FILES = {"path_generator.py", "export_manager.py", "recipe_to_scl.py"}
DISPLAY_FILES = {"program_tab.py", "pass_table.py", "pass_compare.py",
                 "main.py", "recipe_explain.py"}


def source_files():
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in sorted(files):
            if fn.endswith(".py") and not any(fn.startswith(s) for s in SKIP_PREFIX):
                yield os.path.join(root, fn)


text = {}
for path in source_files():
    with open(path, encoding="utf-8") as f:
        text[os.path.basename(path)] = f.read()

for fn, raw_key in sorted(RESOLVERS.items()):
    users = {b for b, t in text.items() if re.search(r"\b%s\s*\(" % fn, t)}
    computing = users & COMPUTE_FILES
    displaying = users & DISPLAY_FILES
    check(bool(computing) and bool(displaying),
          "%s is called from BOTH a computing and a displaying file "
          "(compute=%s display=%s)"
          % (fn, sorted(computing) or "NONE", sorted(displaying) or "NONE"))

    # Nobody may read the raw key with their own default.
    #
    # Two readings are legitimate and are skipped:
    #   * inside the resolver's OWN body — that is where the default belongs,
    #     and it is the whole point of the helper;
    #   * inside an ImportError fallback right after importing the resolver.
    #     recipe_to_scl doubles as a standalone CLI and must not drag in OCC, so
    #     it degrades to the raw read when path_generator is unavailable.
    pattern = re.compile(r"\.get\(\s*[\"']%s[\"']\s*," % re.escape(raw_key))
    def_re = re.compile(r"^def\s+%s\s*\(" % re.escape(fn))
    offenders = []
    for b, t in text.items():
        lines = t.splitlines()
        # line range of the resolver's own definition, if this file defines it
        own = range(0)
        for i, line in enumerate(lines):
            if def_re.match(line):
                end = len(lines)
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("def ") or lines[j].startswith("class "):
                        end = j
                        break
                own = range(i, end)
                break
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("#") or not pattern.search(line):
                continue
            if (n - 1) in own:
                continue
            context = "\n".join(lines[max(0, n - 7):n])
            if ("import %s" % fn) in context or "pragma: no cover" in context:
                continue
            offenders.append("%s:%d" % (b, n))
    check(not offenders,
          "nobody re-derives %r with their own default — call %s "
          "(offenders: %s)" % (raw_key, fn, offenders))

print()
print("FAILURES:" if fails else "ALL ENGINE-VS-SCREEN CHECKS PASSED",
      fails if fails else "")
sys.exit(1 if fails else 0)
