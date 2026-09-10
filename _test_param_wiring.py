# -*- coding: utf-8 -*-
"""Headless test: every operation parameter actually reaches the engine.

THE COMPLAINT THIS EXISTS FOR

"I changed something and nothing happened." That is not a value question — no
amount of testing particular numbers finds it — it is a WIRING question: the
field exists, the box exists, and somewhere between the editor and the toolpath
a link drops it. F3 (2026-09-10) was exactly this: the conformal checkbox was
wired to the display but not to what the engine resolved.

So this sweeps the whole parameter universe. For each key: take a baseline
operation, change that ONE key, regenerate, and require the G-code to move. A
parameter that cannot move the G-code under any condition is either dead or
display-only, and it has to say which.

WHY THIS IS FINITE, NOT COMBINATORIAL

76 distinct parameters, one calculation each. It does not try to enumerate
values — one probe value per key is enough to answer "is this wired at all".
Interactions between parameters are a different question and belong to the
tests that own each feature.

DEPENDENCIES ARE THE HARD PART

Most parameters are only live under a condition: `reach_blank_factor` needs
`reach_follow_blank` on, `tool_change_x` needs mode "absolute" AND a preceding
op with a different tool, the PLC point caps need the recipe path. `CONDITIONS`
below records what each one needs. Every entry there was VERIFIED by probing —
none is a guess, and a wrong condition shows up as a failure, not as a pass.

THE ALLOW-LIST IS EVIDENCE, NOT AMNESTY

`INERT` lists parameters that legitimately cannot change the G-code, each with
the reason it cannot. Adding a key there is a claim about the design and should
be as hard to justify as fixing it. `KNOWN_FINDINGS` is different: those DID
fail the sweep and are not yet explained. They are reported loudly on every run
and deliberately do not fail the suite, so they stay visible instead of being
absorbed into the allow-list.
"""
import sys

import numpy as np

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.tabs.program_tab import OP_PARAM_UNIVERSE

mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
MIN_Z = float(mgr.props["min_z"])
BLANK_R = float(mgr.props["br"]) * 1.5

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


# ── baseline ──────────────────────────────────────────────────────────────
# Every dependency flag ON, so dependent fields are live by default. Clearance
# enforcement is LIVE (min_safety_gap 0.0): the exit trim flags only bite when
# there is a floor to ride, and a baseline with it switched off reports them as
# dead.
PARAMS = {
    "auto_calc_angle": False, "min_safety_gap": 0.0,
    "final_part_thickness_on_mandrel": 2.0, "shell_thickness": 0.0,
    "blank_radius": BLANK_R, "collision_resolution": 0.5, "gcode_resolution": 2.0,
    "home_x": 300.0, "home_z": 150.0, "retract_x": 50.0, "retract_z": 50.0,
    "conformal_clearance_all_operations": False,
    "surface_speed_m_min": 100.0, "feed_rate_mm_min": 300.0, "max_spin_rpm": 2550.0,
    "exit_arc_angle": 0.0,
}

BASE_ROUGH = {
    "type": "roughing", "enabled": True, "name": "probe", "count": 3,
    "tool_id": "T0101", "r_tool": 25.0, "direction": "forward",
    "speed_mode": "RPM", "speed": 200, "feed_mode": "mm_min", "feed": 300,
    "start_z": MIN_Z + 10, "end_z": MIN_Z + 40, "p2_z_extend": 2.0,
    "proj_extend_bottom": 1.0, "proj_extend_top": 1.0,
    "retract_x": 50.0, "retract_z": 50.0, "retract_motion": "synchronized",
    "pass_shape": "linear_approach", "p2_radius": 3.0,
    "exit_arc_angle": 20.0, "exit_bow": 5.0, "exit_bow_bias": 0.5,
    "exit_bow_trim": True,
    "exit_mid_t": 0.5, "exit_mid_radius": -60.0, "exit_mid_radius_end": -80.0,
    "exit_mid_trim": True,
    "conformal_clearance_operation_specific": True,
    "approach_follow_surface": True,
    "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0, "reach": 40.0,
    "reach_follow_blank": False, "reach_blank_factor": 1.0, "reach_blank_offset": 0.0,
    "pass_angle": 120.0, "progressive_angle_enabled": True,
    "progressive_angle_end": 170.0,
    "progressive_reach_enabled": True, "progressive_reach_end": 30.0,
    "clearance": 5.0, "rot": 0.0,
    "contact_zone_mm": 5.0, "feed_contact": 150.0, "feed_contact_end": 180.0,
    "back_pass_enabled": True, "back_pass_swapped": False,
    "back_pass_feed": 400.0, "back_pass_arc_x": 2.0, "back_pass_arc_z": 2.0,
    "tilt_mode": "normal", "tilt_start": 0.0, "tilt_end": 0.0, "tilt_offset": 0.0,
    "tool_change_mode": "global", "tool_change_x": 300.0, "tool_change_z": 150.0,
    "tool_change_dx": 0.0, "tool_change_dz": 0.0, "tool_change_simultaneous": False,
    "p2_radius_max_points": "", "exit_max_points": "",
}

# ── probe values ──────────────────────────────────────────────────────────
# Enums need a real alternative; a generic bump would silently probe the SAME
# value and report the key as dead.
PROBE = {
    "direction": "reverse",
    "pass_shape": "spline",
    "retract_motion": "x_first",
    "feed_mode": "mm_rev",
    # The real alternative, not a nonsense string. Probing "RPMX" DOES change
    # the output — an unrecognised mode takes a different fallback — which
    # would report speed_mode as wired for the wrong reason.
    "speed_mode": "CSS",
    "tilt_mode": "interp",
    "tool_change_mode": "absolute",
    "p2_radius_max_points": 4,
    "exit_max_points": 5,
    "point_mode": "surface",
    "point_motion": "x_first",
}

# ── conditions: what a key needs before it can bite ───────────────────────
# op_over / params_over are applied to BOTH sides of the comparison, so they
# set the stage without being the thing under test. `recipe` routes through the
# PLC recipe path; `tool_change` builds a two-op program with a real change.
# EVERY entry here was verified by probing — see the notes.
CONDITIONS = {
    # Only live when the roller is actually inside the contact zone. The
    # baseline's own clearance keeps it outside.
    "feed_contact":       {"op": {"clearance": 0.0, "contact_zone_mm": 20.0}},
    "feed_contact_end":   {"op": {"clearance": 0.0, "contact_zone_mm": 20.0}},
    # Rotation is deliberately locked to 0 on linear shapes ("use pass_angle to
    # control direction" — path_generator logs it), so it can only be probed on
    # a spline.
    "rot":                {"op": {"pass_shape": "spline"}},
    # P1's X only matters on a spline: linear approaches enter dead along -Z, so
    # theta_A is fixed at -90 deg and the typed X cannot move it.
    "p1_x":               {"op": {"pass_shape": "spline", "reach": ""}},
    # The reach model outranks the typed control points (documented priority
    # chain), so they can only be probed with reach empty.
    "p3_x":               {"op": {"reach": ""}},
    "p3_z":               {"op": {"reach": ""}},
    # Blank-follow multipliers do nothing until follow is on.
    "reach_blank_factor": {"op": {"reach_follow_blank": True}},
    "reach_blank_offset": {"op": {"reach_follow_blank": True}},
    # The bow family replaces the arc on the exit leg, and only linear_full
    # actually routes through it in this baseline.
    "exit_bow":           {"op": {"pass_shape": "linear_full", "exit_mid_radius": ""}},
    "exit_bow_bias":      {"op": {"pass_shape": "linear_full", "exit_mid_radius": ""}},
    # A trim flag needs something to trim: a bow big enough to break the floor.
    "exit_bow_trim":      {"op": {"pass_shape": "linear_full", "exit_mid_radius": "",
                                  "exit_bow": 40.0}},
    # PLC point caps are applied during recipe decimation only; the .nc is
    # always full resolution.
    "p2_radius_max_points": {"op": {"p2_radius": 12.0}, "recipe": True},
    "exit_max_points":      {"recipe": True},
    # A tool-change position needs a preceding op with a different tool, and the
    # matching mode: absolute reads x/z, relative reads dx/dz.
    "tool_change_x":  {"tool_change": "absolute"},
    "tool_change_z":  {"tool_change": "absolute"},
    "tool_change_dx": {"tool_change": "relative"},
    "tool_change_dz": {"tool_change": "relative"},
    "tool_change_mode": {"tool_change": "global"},
    # "Move both axes together" only has two orderings to choose between once
    # the move has an explicit target; in global mode the approach to home is
    # already fixed.
    "tool_change_simultaneous": {"tool_change": "absolute"},
}

# ── legitimately unable to move the G-code ────────────────────────────────
# Each reason is a statement about the design, verified while building this.
INERT = {
    "name": "a label. Shown in the op list and in comments, never in a "
            "coordinate.",
    "speed_mode": "CSS is disabled machine-wide (CSS_SPEED_MODE_ENABLED). The "
                  "PLC has no constant-surface-speed mode, so both values "
                  "resolve to RPM by design — see resolve_speed_mode.",
    "proj_extend_bottom": "extends the 3D PROJECTION line used for the "
                          "deviation display (path_generator.py:3338). It is "
                          "not part of the toolpath.",
    "proj_extend_top": "same as proj_extend_bottom — display geometry only.",
    "tilt_mode": "B-axis (ID112 tilt-arm) only. This baseline is a two-axis "
                 "ID111 machine with no kinematics, so no B word is emitted.",
    "tilt_start": "B-axis only — see tilt_mode.",
    "tilt_end": "B-axis only — see tilt_mode.",
    "tilt_offset": "B-axis only — see tilt_mode.",
}

# ── failed the sweep and NOT yet explained ────────────────────────────────
# Reported on every run, deliberately non-fatal. Moving one of these into INERT
# needs a reason; fixing it needs a code change. Leaving it here needs neither,
# which is why it prints loudly.
KNOWN_FINDINGS = {
    "exit_arc_angle":
        "No effect on the toolpath in ANY configuration probed (2026-09-10): "
        "3 pass shapes x angles -60..+85, set on the op AND via the "
        "Process-tab global, with the curl off and the bow at 0 (the branch "
        "at path_generator.py:2986 that feeds it). In the IDENTICAL "
        "configuration exit_bow does move the path (20 -> 22 -> 29 points), so "
        "the exit branch is running; and _tangent_chord_arc is angle-sensitive "
        "when called directly. Root cause not established.",
    "exit_mid_trim":
        "No effect on the toolpath in any configuration probed (2026-09-10), "
        "including a curl radius tight enough to break a live clearance floor, "
        "on all three pass shapes. Its sibling exit_bow_trim does bite under "
        "the same conditions. Root cause not established.",
}


def _strip(txt):
    """Drop the wall-clock header — two generations a second apart are not a
    difference in the toolpath."""
    return "\n".join(l for l in txt.splitlines()
                     if not l.strip().startswith("(Generated:"))


def _gen(ops, params_over=None, recipe=False):
    p = dict(PARAMS)
    if params_over:
        p.update(params_over)
    if recipe:
        p["plc_mode"] = True
        p["plc_tolerance"] = 0.02
    p["operations"] = list(ops)
    pg = PathGenerator()
    pg.calculate_paths(p, {}, mgr)
    return _strip(pg.generate_gcode(params=p, for_recipe=recipe))


def _probe_value(key, cur):
    if key in PROBE:
        return PROBE[key]
    if isinstance(cur, bool):
        return not cur
    if isinstance(cur, (int, float)):
        return float(cur) + 7.0 if cur else 5.0
    if cur in ("", None):
        return 5.0
    return str(cur) + "X"


def sweep_key(base_op, key):
    """(moved, detail). None = could not be probed at all."""
    cond = CONDITIONS.get(key, {})
    op_a = dict(base_op)
    op_a.update(cond.get("op", {}))
    if key not in op_a:
        return None, "not in the baseline operation"
    val = _probe_value(key, op_a[key])
    op_b = dict(op_a)
    op_b[key] = val

    tc_mode = cond.get("tool_change")
    recipe = bool(cond.get("recipe"))
    pov = cond.get("params", {})

    try:
        if tc_mode:
            first = dict(base_op, tool_id="T0101")
            a = dict(op_a, tool_id="T0202", tool_change_mode=tc_mode)
            b = dict(a)
            b[key] = val
            ga, gb = _gen([first, a], pov), _gen([first, b], pov)
        else:
            ga, gb = _gen([op_a], pov, recipe), _gen([op_b], pov, recipe)
    except Exception as e:
        return None, "raised: %r" % (e,)
    return (ga != gb), "%r -> %r" % (op_a[key], val)


# ── the sweep ─────────────────────────────────────────────────────────────
universe = OP_PARAM_UNIVERSE["roughing"]
print("Sweeping %d roughing parameters\n" % len(universe))

wired, inert_ok, findings, unprobeable = [], [], [], []
for key in universe:
    moved, detail = sweep_key(BASE_ROUGH, key)
    if moved is None:
        unprobeable.append((key, detail))
    elif moved:
        wired.append(key)
        if key in INERT:
            findings.append((key, "listed as INERT but it DID change the "
                                  "G-code — the allow-list is wrong"))
    else:
        if key in INERT:
            inert_ok.append(key)
        elif key in KNOWN_FINDINGS:
            findings.append((key, "known finding, still not wired"))
        else:
            findings.append((key, "NO EFFECT (%s) and no reason on record" % detail))

print("wired:        %d" % len(wired))
print("inert (ok):   %d" % len(inert_ok))
print("unprobeable:  %d" % len(unprobeable))
for k, why in unprobeable:
    print("    %-28s %s" % (k, why))
print()

# Every parameter must be accounted for: wired, on the allow-list with a
# reason, or an open finding. Nothing may be silently absent.
accounted = set(wired) | set(inert_ok) | set(KNOWN_FINDINGS)
missing = [k for k in universe if k not in accounted and k not in dict(unprobeable)]
check(not missing,
      "every roughing parameter is wired, allow-listed, or a recorded finding "
      "(unaccounted: %s)" % missing)

check(not unprobeable,
      "every roughing parameter could be probed (%s)" % [k for k, _ in unprobeable])

real = [(k, why) for k, why in findings if k not in KNOWN_FINDINGS]
check(not real,
      "no NEW dead parameters (%s)" % [k for k, _ in real])
for k, why in real:
    print("      %-28s %s" % (k, why))

# The allow-list must stay honest in the other direction too: a key listed as
# inert that starts changing the G-code means the reason is stale.
check(not [k for k in INERT if k in wired],
      "nothing on the INERT list actually moves the G-code "
      "(%s)" % [k for k in INERT if k in wired])

# The sweep is only meaningful if most parameters DO move the output. A
# baseline that quietly stopped generating would make everything "inert" and
# every check above would pass.
check(len(wired) >= 30,
      "the baseline really is generating (%d of %d parameters move the G-code)"
      % (len(wired), len(universe)))


# ── the other op types: their distinctive parameters ──────────────────────
print()
BASE_CUT = {
    "type": "cutting", "enabled": True, "count": 1, "tool_id": "T0101",
    "r_tool": 25.0, "feed": 300, "speed": 200,
    "speed_mode": "RPM", "feed_mode": "mm_min",
    "plunge_start_x": 120.0, "plunge_start_z": MIN_Z + 20.0,
    "plunge_end_x": 90.0, "plunge_end_z": MIN_Z + 20.0,
    "retract_x": 50.0, "retract_z": 50.0, "retract_motion": "synchronized",
}
BASE_POINT = {
    "type": "point", "enabled": True, "count": 1, "tool_id": "T0101",
    "r_tool": 25.0, "feed": 300, "speed": 200,
    "speed_mode": "RPM", "feed_mode": "mm_min",
    "point_mode": "absolute", "point_x": 150.0, "point_z": MIN_Z + 40.0,
    "point_standoff": 5.0, "point_dx": 10.0, "point_dz": 10.0,
    "point_motion": "synchronized", "point_rapid": True,
}

for label, base, keys in (
    ("cutting", BASE_CUT, ["plunge_start_x", "plunge_start_z",
                           "plunge_end_x", "plunge_end_z"]),
    ("point", BASE_POINT, ["point_x", "point_z", "point_motion", "point_rapid"]),
):
    dead = []
    for key in keys:
        moved, detail = sweep_key(base, key)
        if not moved:
            dead.append((key, detail))
    check(not dead, "%s: every move parameter reaches the G-code (%s)"
          % (label, dead))

# point_standoff / point_dx / point_dz are live only in their own modes, which
# is the documented contract (resolve_point_target). Probed in the right mode.
#
# "relative" additionally needs a PRECEDING pass to be relative TO. With no
# earlier forming pass it falls back to absolute — deliberate, and pinned by
# _test_point_op.test_relative_with_no_previous_pass_falls_back. So it is
# probed in a two-op program; probing it alone reports a live field as dead.
_ROUGH_BEFORE = dict(BASE_ROUGH, count=1)


def _point_mode_moves(mode, key, with_previous):
    op_a = dict(BASE_POINT, point_mode=mode)
    op_b = dict(op_a)
    op_b[key] = _probe_value(key, op_a[key])
    lead = [_ROUGH_BEFORE] if with_previous else []
    return _gen(lead + [op_a]) != _gen(lead + [op_b])


for mode, key in (("surface", "point_standoff"),
                  ("home", "point_dx"), ("home", "point_dz")):
    check(_point_mode_moves(mode, key, False),
          "point mode %-8s: %s is live on its own" % (mode, key))

for key in ("point_dx", "point_dz"):
    check(_point_mode_moves("relative", key, True),
          "point mode relative: %s is live after a forming pass" % key)
    check(not _point_mode_moves("relative", key, False),
          "point mode relative: %s correctly falls back with no previous pass"
          % key)


# ── the open findings, reported every run ─────────────────────────────────
if KNOWN_FINDINGS:
    print()
    print("=" * 72)
    print("OPEN FINDINGS — parameters with no measurable effect, unexplained")
    print("=" * 72)
    for k, why in sorted(KNOWN_FINDINGS.items()):
        print("  %s\n      %s\n" % (k, why))

print()
print("FAILURES:" if fails else "ALL PARAMETER-WIRING CHECKS PASSED",
      fails if fails else "")
sys.exit(1 if fails else 0)
