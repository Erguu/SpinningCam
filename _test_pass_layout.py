"""Every rule about the toolpath LAYOUT must agree with the engine (2026-09-20).

Four places answer "how many toolpath entries does this operation contribute,
and which of them are back passes":

    path_generator.op_toolpath_entries   documented as THE single source
    ui/tabs/program_tab._op_logical_count x _op_toolpath_stride
    pass_colors.path_categories
    main._rtool_for_pass / _active_fwd_pass_idx

They index the SAME arrays the engine built. A rule that disagrees does not
raise - it hands the 3D renderer, the pass colouring, the per-pass roller
radius and the pass navigator someone else's pass, silently. That already
happened once, when six inlined copies fell out of step with the engine; the
docstrings still carry the scar.

Ground truth here is the ENGINE, never another rule:

  * how many        len(toolpaths) from calculate_paths
  * which are back  last_back_pass_meta - the engine stores each back pass's
                    own toolpath index as it appends it

Run:  python _test_pass_layout.py
"""
import copy
import sys

import numpy as np

import pass_colors
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator, op_toolpath_entries, op_builds_back_pass

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILED.append(name)


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

R = {
    "type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
    "r_tool": 25.0, "direction": "forward",
    "speed_mode": "RPM", "speed": 200, "feed_mode": "mm_min", "feed": 300,
    "retract_x": 50.0, "retract_z": 50.0,
    "pass_shape": "linear_approach", "p2_radius": 3.0,
    "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0, "reach": 40.0,
    "pass_angle": 120.0, "clearance": 5.0,
    "start_z": MIN_Z + 10, "end_z": MIN_Z + 30,
}

POINT = {"type": "point", "enabled": True, "name": "P", "tool_id": "T0101",
         "r_tool": 30.0, "point_mode": "absolute", "point_x": 150.0,
         "point_z": MIN_Z + 40.0, "count": 1}

CUT = {"type": "cutting", "enabled": True, "name": "C", "tool_id": "T0101",
       "count": 3, "r_tool": 35.0, "feed": 50, "speed": 500,
       "plunge_start_x": 120.0, "plunge_start_z": MIN_Z + 20.0,
       "plunge_end_x": 90.0, "plunge_end_z": MIN_Z + 20.0,
       "retract_x": 50.0, "retract_z": 50.0}

# Distinct r_tool per operation, so a shifted index shows up as the wrong roller.
CASES = {
    "roughing only":
        [dict(R, name="A", r_tool=25.0)],
    "roughing + back pass":
        [dict(R, name="A", r_tool=25.0, back_pass_enabled=True)],
    "reverse with the back box ticked (#49 builds none)":
        [dict(R, name="A", r_tool=25.0, direction="reverse",
              back_pass_enabled=True)],
    "back pass, swapped":
        [dict(R, name="A", r_tool=25.0, back_pass_enabled=True,
              back_pass_swapped=True)],
    "POINT between two operations":
        [dict(R, name="A", r_tool=25.0), dict(POINT),
         dict(R, name="B", r_tool=40.0, back_pass_enabled=True)],
    "POINT first":
        [dict(POINT), dict(R, name="A", r_tool=40.0)],
    "CUTTING (count 3) between two operations":
        [dict(R, name="A", r_tool=25.0), dict(CUT),
         dict(R, name="B", r_tool=40.0)],
    "a DISABLED operation between two":
        [dict(R, name="A", r_tool=25.0),
         dict(R, name="off", r_tool=99.0, enabled=False, back_pass_enabled=True),
         dict(R, name="B", r_tool=40.0, back_pass_enabled=True)],
    "count = 0":
        [dict(R, name="A", r_tool=25.0, count=0),
         dict(R, name="B", r_tool=40.0)],
    # NOT tested: count = "". Unreachable - an emptied entry POPS the key
    # (program_tab._add_prop_entry.save) rather than storing "", and the engine
    # itself raises on it (path_generator.py:1090, int("")). So the `or 1`
    # guards in the rules defend a state nothing can reach, while costing the
    # count = 0 case above: `0 or 1` is 1.
    "everything at once":
        [dict(R, name="A", r_tool=25.0, back_pass_enabled=True),
         dict(POINT),
         dict(R, name="B", r_tool=40.0, direction="reverse"),
         dict(CUT),
         dict(R, name="C", r_tool=45.0, count=3, back_pass_enabled=True)],
}


def build(ops):
    p = copy.deepcopy(PARAMS)
    p["operations"] = copy.deepcopy(ops)
    pg = PathGenerator()
    tp = pg.calculate_paths(p, {}, mgr)[0]
    return pg, tp, p["operations"]


# ── the engine's own answer ────────────────────────────────────────────────
def engine_layout(pg, tp):
    """(n_paths, set of indices that ARE back passes) - straight from the engine."""
    return len(tp), set(int(k) for k in (pg.last_back_pass_meta or {}))


# ── main.py's two mappers, reached without starting the UI ─────────────────
import main as main_mod


class _FakeApp:
    def __init__(self, ops, tp_idx=0):
        self.params = {"operations": ops}
        self.active_editing_pass_idx = tp_idx

    _rtool_for_pass = main_mod.SpinningApp._rtool_for_pass
    _active_fwd_pass_idx = main_mod.SpinningApp._active_fwd_pass_idx


print("[1] every rule counts the same toolpaths as the engine")
for name, ops in CASES.items():
    pg, tp, ops = build(ops)
    n_engine, back_idx = engine_layout(pg, tp)

    entries = sum(op_toolpath_entries(o) for o in ops if o.get("enabled", True))
    check(f"{name}: op_toolpath_entries", entries == n_engine,
          f"rule {entries}, engine {n_engine}")

    cols = len(pass_colors.path_categories(ops))
    check(f"{name}: pass_colors", cols == n_engine, f"rule {cols}, engine {n_engine}")

    # pass_colors also has to put "back" in the right SLOTS, not just the right count.
    cats = pass_colors.path_categories(ops)
    got_back = set(i for i, c in enumerate(cats) if c == "back")
    check(f"{name}: pass_colors marks the right entries as back",
          got_back == back_idx or cols != n_engine,   # count already reported above
          f"rule {sorted(got_back)}, engine {sorted(back_idx)}")


print()
print("[2] the per-pass roller radius follows the right operation")
for name, ops in CASES.items():
    pg, tp, ops = build(ops)
    n_engine, back_idx = engine_layout(pg, tp)

    # Truth, built from the ENGINE's layout: walk the toolpaths, and step to the
    # next operation whenever this one has delivered all of its entries. An
    # operation's entries are its forward passes, each optionally followed by a
    # back pass - and which entries ARE back passes comes from the engine.
    truth = []
    it = iter(i for i in range(n_engine))
    # Rebuild ownership by replaying the engine's own back-pass marks against
    # the operation order: every non-back entry opens a new forward pass, and
    # forward passes are handed out operation by operation.
    per_op = []
    for o in ops:
        if not o.get("enabled", True) or o.get("type") == "point":
            continue
        n = 1 if o.get("type") in ("cutting", "bending") else \
            (1 if o.get("count", 1) in (None, "") else int(o["count"]))
        per_op.append((o, max(n, 0)))
    i = 0
    for o, n_fwd in per_op:
        for _ in range(n_fwd):
            truth.append(float(o.get("r_tool", 25.0)))
            i += 1
            if i in back_idx:
                truth.append(float(o.get("r_tool", 25.0)))
                i += 1
    check(f"{name}: the truth table itself covers every path",
          len(truth) == n_engine, f"{len(truth)} vs {n_engine}")

    if len(truth) == n_engine:
        app = _FakeApp(ops)
        got = [app._rtool_for_pass(k) for k in range(n_engine)]
        check(f"{name}: _rtool_for_pass", got == truth, f"{got} vs {truth}")


print()
print("[3] a back-pass entry maps to its parent forward pass")
for name, ops in CASES.items():
    pg, tp, ops = build(ops)
    n_engine, back_idx = engine_layout(pg, tp)
    expect, fwd = [], 0
    for i in range(n_engine):
        if i in back_idx:
            expect.append(fwd - 1)      # the forward it mirrors
        else:
            expect.append(fwd)
            fwd += 1
    got = [_FakeApp(ops, k)._active_fwd_pass_idx() for k in range(n_engine)]
    check(f"{name}: _active_fwd_pass_idx", got == expect, f"{got} vs {expect}")


print()
if FAILED:
    print(f"{len(FAILED)} check(s) FAILED: {FAILED}")
    sys.exit(1)
print("All pass-layout checks passed.")
