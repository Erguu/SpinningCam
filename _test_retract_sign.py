# -*- coding: utf-8 -*-
"""Headless test: the pass retract points AWAY from the part on BOTH roller sides,
and the 3D sim and the emitted G-code agree.

The bug this pins: the sim builds paths in the canonical positive-X frame with
abs(retract_x) and mirrors them at the end, landing the retract at
``end + side*|retract_x|``. The emitter works in the real frame and used the
LITERAL sign, i.e. ``end + retract_x``. On a negative-side machine (which is what
the ID111/ID112 profiles are) a POSITIVE retract_x therefore drove the tool INTO
the part in the .nc while the simulation showed it pulling clear — same recipe,
opposite directions, silently.

Retract is a "get clear" move, so the magnitude is the user's and the direction is
the machine's. The per-op TOOL-CHANGE offsets are deliberately NOT covered by this
rule (they keep their literal sign) — test_tool_change_sign_untouched guards that.
"""
import numpy as np
from path_generator import (PathGenerator, retract_x_offset_real,
                            resolve_tool_change_point)


class _StubMgr:
    """Flat cylinder R=50, Z 0..100."""
    def __init__(self):
        self.props = {"top_z": 100.0, "min_z": 0.0, "max_radius": 50.0}
    def get_radius_fast(self, z): return 50.0
    def get_normal_at_z(self, z): return 1.0, 0.0
    def get_straightened_radius(self, z): return 50.0
    def get_straightened_normal(self, z): return 1.0, 0.0


def _params(ops, positive_side=True):
    return {"operations": ops, "retract_x": 50.0, "retract_z": 50.0,
            "home_x": 300.0, "home_z": 150.0, "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 2.0, "shell_thickness": 0.0,
            "target_clearance": 2.0, "roller_positive_x_side": positive_side,
            "auto_calculate_paths": False}


def _rough(**extra):
    op = {"type": "roughing", "enabled": True, "count": 1, "tool_id": "T0101",
          "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0, "p1_x": 40.0,
          "p1_z": 50.0, "p3_x": 40.0, "p3_z": -20.0,
          "pass_shape": "linear_approach"}
    op.update(extra)
    return op


def _run(op, positive_side):
    """Return (pass end X, sim retract X, gcode retract X) in the REAL frame."""
    pg = PathGenerator()
    p = _params([op], positive_side)
    res = pg.calculate_paths(p, {}, _StubMgr())
    end_x = float(pg.last_calculated_paths[0][-1][0])

    # The sim's retract is the rapid segment that starts at the pass end.
    rapids = res[4] if isinstance(res, tuple) else pg.last_rapids
    sim_x = None
    for seg in rapids:
        if abs(float(seg[0][0]) - end_x) < 1e-6:
            sim_x = float(seg[1][0])
    gc = pg.generate_gcode(params=p)
    gc_x = None
    for l in gc.splitlines():
        if "(Retract Op" in l:
            for tok in l.split():
                if tok.startswith("X"):
                    gc_x = float(tok[1:])
            break
    return end_x, sim_x, gc_x


# ── 1. Pure helper ──────────────────────────────────────────────────────────
def test_helper():
    assert retract_x_offset_real(50.0, 1.0) == 50.0
    assert retract_x_offset_real(-50.0, 1.0) == 50.0    # sign ignored
    assert retract_x_offset_real(50.0, -1.0) == -50.0   # away = -X on that side
    assert retract_x_offset_real(-50.0, -1.0) == -50.0
    assert retract_x_offset_real(0.0, -1.0) == 0.0
    print("test_helper PASS")


# ── 2. Sim and G-code agree, both sides, both signs ─────────────────────────
def test_sim_matches_gcode():
    for positive_side in (True, False):
        for typed in (50.0, -50.0):
            end_x, sim_x, gc_x = _run(_rough(retract_x=typed), positive_side)
            assert sim_x is not None and gc_x is not None, (positive_side, typed)
            assert abs(sim_x - gc_x) < 1e-6, (
                f"side={'+' if positive_side else '-'} retract_x={typed}: "
                f"sim {sim_x} vs gcode {gc_x}")
            # ...and it moved AWAY from the axis (|X - center| grew; center = 0)
            assert abs(gc_x) > abs(end_x), (
                f"side={'+' if positive_side else '-'} retract_x={typed}: "
                f"retract {gc_x} is not clear of end {end_x}")
    print("test_sim_matches_gcode PASS")


# ── 3. The exact field-config regression ───────────────────────────────────
def test_negative_side_positive_value():
    """ID111/ID112 are negative-side. A positive retract_x used to emit a rapid
    toward — and past — the spindle axis."""
    end_x, sim_x, gc_x = _run(_rough(retract_x=50.0), positive_side=False)
    assert end_x < 0.0, end_x                    # roller runs on -X
    assert gc_x < end_x, f"retract {gc_x} must be further out than {end_x}"
    assert abs(gc_x - (end_x - 50.0)) < 1e-6, gc_x
    print(f"test_negative_side_positive_value PASS "
          f"(end {end_x:.1f} -> retract {gc_x:.1f}, was {end_x + 50.0:.1f})")


# ── 4. Existing recipes are untouched ──────────────────────────────────────
def test_existing_recipes_unchanged():
    """Every saved program here uses retract_x = -10 on a negative-side machine —
    the sign that already agreed with the sim. That must not move."""
    _, sim_x, gc_x = _run(_rough(retract_x=-10.0), positive_side=False)
    end_x, _, _ = _run(_rough(retract_x=-10.0), positive_side=False)
    assert abs(gc_x - (end_x - 10.0)) < 1e-6, gc_x
    assert abs(sim_x - gc_x) < 1e-6
    # ...and the ordinary positive-side case is likewise unchanged
    end_p, sim_p, gc_p = _run(_rough(retract_x=50.0), positive_side=True)
    assert abs(gc_p - (end_p + 50.0)) < 1e-6, gc_p
    print("test_existing_recipes_unchanged PASS")


# ── 5. Back-pass retract follows the same rule ─────────────────────────────
def test_back_pass_retract():
    op = _rough(retract_x=50.0, back_pass_enabled=True)
    pg = PathGenerator()
    p = _params([op], positive_side=False)
    pg.calculate_paths(p, {}, _StubMgr())
    gc = pg.generate_gcode(params=p)
    bp = [l for l in gc.splitlines() if "(Retract Op" in l and "BP" in l]
    assert bp, "expected a back-pass retract line"
    x = next(float(tok[1:]) for tok in bp[0].split() if tok.startswith("X"))
    bp_end = float(pg.last_calculated_paths[1][-1][0])
    assert abs(x - (bp_end - 50.0)) < 1e-6, (x, bp_end)
    print("test_back_pass_retract PASS")


# ── 6. Tool-change offsets keep their literal sign ─────────────────────────
def test_tool_change_sign_untouched():
    """Deliberately NOT normalized: a tool-change point is a position the operator
    aims at, not a get-clear move."""
    prev_end = np.array([100.0, 0.0, 20.0])
    home = np.array([300.0, 0.0, 150.0])
    op = {"tool_change_mode": "relative", "tool_change_dx": -30.0,
          "tool_change_dz": 5.0}
    assert resolve_tool_change_point(op, prev_end, home)[0] == 70.0   # sign kept
    op["tool_change_dx"] = 30.0
    assert resolve_tool_change_point(op, prev_end, home)[0] == 130.0
    print("test_tool_change_sign_untouched PASS")


if __name__ == "__main__":
    test_helper()
    test_sim_matches_gcode()
    test_negative_side_positive_value()
    test_existing_recipes_unchanged()
    test_back_pass_retract()
    test_tool_change_sign_untouched()
    print("ALL PASS")
