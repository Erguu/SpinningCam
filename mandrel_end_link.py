"""No retract at the mandrel end — the "mandrel-end link" (2026-09-16).

Plan: backup/PLAN_2026-09-16_mandrel_end_link.md. User: the lift off the sheet at
the mandrel end "can go".

A reverse pass, and a back pass, end at the MANDREL END of the pass (the straight
arm, the precise-X line). Measured on the shop's real programs, the next forward
pass starts at the same spot: 0.00 mm after a reverse pass, 0.1–10.5 mm after a
back pass. Today the machine stops, retracts 7–14 mm, stops, comes straight
back, and stops again. With this option on, that retract is replaced by a short
slow feed line straight to the next start — ONLY where every rule below allows
it. Everywhere else the retract stays exactly as it is.

THE RULE (all must hold, otherwise today's retract):
  1. pass A is a back pass, or a pass of a REVERSE roughing op, and A's op has
     the tickbox on (``no_retract_mandrel_end``, default OFF);
  2. pass B, the very next toolpath, is a FORWARD ROUGHING pass (not a back pass);
  3. nothing that needs the roller clear happens in between: no other enabled
     operation (e.g. a Point op), no tool change, no spindle speed or feed-mode
     change, no custom command triggered on B's pass (e.g. ``M41 Clamp On``);
  4. the gap A end -> B start is at most the op's ``mandrel_link_max_mm``
     (default 15 mm; the measured linkable cases are 0–10.5 mm);
  5. clearance: the straight link line is never closer to the part than the
     CLOSER of its two ends (0.01 mm tolerance), and all three can be measured.

The program's last pass never has a B, so it always keeps its retract — the
program-end return moves Z first and would otherwise drag along the part.

This module is the rule only: pure, no engine import at module level (the path
generator imports it). ``calculate_paths`` applies it once and records the
result; ``generate_gcode`` follows the record and never re-decides.
"""
import math

OP_FLAG_KEY = "no_retract_mandrel_end"
OP_MAX_KEY = "mandrel_link_max_mm"
DEFAULT_MAX_MM = 15.0
# Below this the link is no line at all: B's first cut leaves from A's end.
# The PLC letter: never emit a segment shorter than 0.05 mm.
MIN_LINE_MM = 0.05
CLEARANCE_TOL_MM = 0.01
# Comment tag of the emitted link line. recipe_to_scl marks lines carrying it
# ``exact`` (an exact stop, CMD=1 even with continuous motion — design option A:
# every move toward the part ends with an exact landing), and motion_stops skips
# them as lines that belong to no toolpath.
LINK_TAG = "(Link Op"

REASONS = {
    "off": "the option is off on this operation",
    "not_mandrel_end": "this pass does not end at the mandrel (only reverse and back passes do)",
    "next_not_forward": "the next pass is not a forward roughing pass",
    "order": "the next toolpath belongs to an earlier operation",
    "operation_between": "another operation runs in between",
    "tool_change": "the next pass uses another tool",
    "spindle_change": "the spindle speed changes before the next pass",
    "feed_mode_change": "the feed mode changes before the next pass",
    "custom_command": "a custom command is triggered on the next pass",
    "too_far": "the next pass starts farther away than the allowed link length",
    "clearance_unmeasurable": "the clearance of the link cannot be measured",
    "clearance": "the link line would come closer to the part than its ends",
    "sequence": "the simulation has something other than rapids in between",
    "emitted_lines": "the G-code has a machine command in between",
}


def enabled(op):
    """The tickbox. Absent = OFF (user, 2026-09-16)."""
    return bool((op or {}).get(OP_FLAG_KEY, False))


def max_link_mm(op):
    """The op's longest allowed link, mm. Unreadable, not finite or <= 0 falls
    back to the default rather than linking with nonsense."""
    raw = (op or {}).get(OP_MAX_KEY, DEFAULT_MAX_MM)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_MM
    if not math.isfinite(v) or v <= 0:
        return DEFAULT_MAX_MM
    return v


def op_can_use(op, builds_back_pass):
    """Whether the tickbox means anything on this op (editor visibility): a
    roughing op whose passes end at the mandrel — reverse, or with a back pass.
    ``builds_back_pass`` is ``path_generator.op_builds_back_pass(op)``, passed in
    so this module stays import-free."""
    op = op or {}
    if op.get("type", "roughing") != "roughing":
        return False
    return op.get("direction", "forward") == "reverse" or bool(builds_back_pass)


def _spindle(op, params):
    # The same pair the emitter compares before writing an M3 between ops.
    try:
        from path_generator import resolve_speed_mode
        mode = resolve_speed_mode(op)
    except Exception:                                   # pragma: no cover
        mode = str((op or {}).get("speed_mode", "RPM") or "RPM").upper()
    try:
        speed = int(float(op.get("speed", params.get("surface_speed_m_min", 200))))
    except (TypeError, ValueError):
        speed = None
    return mode, speed


def blockers(ops, a_op_index, a_is_back_pass, b_op_index, b_is_back_pass,
             b_pass_number, params):
    """Rules 1–3 for the toolpath pair (A, B). [] = allowed; otherwise the
    reason keys (see ``REASONS``). ``b_pass_number`` is the 1-based global pass
    number the emitter uses for "pass" custom-command triggers (B's index + 1).
    """
    ops = ops or []
    params = params or {}
    a = ops[a_op_index] or {}
    b = ops[b_op_index] or {}
    if not enabled(a):
        return ["off"]
    out = []
    a_mandrel_end = bool(a_is_back_pass) or (
        a.get("type", "roughing") == "roughing"
        and a.get("direction", "forward") == "reverse")
    if not a_mandrel_end:
        out.append("not_mandrel_end")
    if (b_is_back_pass or b.get("type", "roughing") != "roughing"
            or b.get("direction", "forward") == "reverse"):
        out.append("next_not_forward")
    if b_op_index < a_op_index:
        out.append("order")
    for k in range(a_op_index + 1, b_op_index):
        if (ops[k] or {}).get("enabled", True):
            out.append("operation_between")
            break
    if str(a.get("tool_id", "T0101")) != str(b.get("tool_id", "T0101")):
        out.append("tool_change")
    if a_op_index != b_op_index:
        if _spindle(a, params) != _spindle(b, params):
            out.append("spindle_change")
        if a.get("feed_mode", "mm_min") != b.get("feed_mode", "mm_min"):
            out.append("feed_mode_change")
    for c in params.get("custom_commands", []) or []:
        if (c or {}).get("trigger") != "pass":
            continue
        try:
            n = int(float(c.get("value")))
        except (TypeError, ValueError):
            continue
        if n == b_pass_number:
            out.append("custom_command")
            break
    return out


def check_geometry(a_end, b_start, op, clearance_of):
    """Rules 4–5. ``clearance_of(points)`` returns the minimum roller-to-part
    clearance along a polyline (the engine's ``_path_min_clearance``; +inf when
    it cannot be measured). Points are [x, y, z].

    Returns (ok, gap_mm, reason_or_None, link_clearance_or_None).
    """
    gap = math.hypot(float(b_start[0]) - float(a_end[0]),
                     float(b_start[2]) - float(a_end[2]))
    if gap > max_link_mm(op):
        return False, gap, "too_far", None
    cl_line = clearance_of([a_end, b_start])
    cl_a = clearance_of([a_end])
    cl_b = clearance_of([b_start])
    if not all(math.isfinite(c) for c in (cl_line, cl_a, cl_b)):
        return False, gap, "clearance_unmeasurable", None
    if cl_line < min(cl_a, cl_b) - CLEARANCE_TOL_MM:
        return False, gap, "clearance", cl_line
    return True, gap, None, cl_line


def is_machine_line(line):
    """True for a G-code line that makes the PLC do something between two
    passes. Comments, blank lines and the G98/G99 feed-mode word do not."""
    s = (line or "").strip()
    if not s or s.startswith("(") or s.startswith(";"):
        return False
    return s.upper() not in ("G98", "G99")
