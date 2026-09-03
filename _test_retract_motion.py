# -*- coding: utf-8 -*-
"""Headless test: axis order on the PASS RETRACT.

The retract is the move that pulls the roller off the work after a pass. It has
always been a single diagonal G0; this adds "one axis at a time".

What this pins, hardest first:

1. **Default = byte-identical.** `retract_motion` defaults to "synchronized",
   and an op that does not set it must emit EXACTLY the G-code it emitted
   before this feature existed. Every recipe ever written by this program is
   riding on that.

2. **The sim and the emitter describe the same shape.** Both call
   ``retract_segments``. If they diverge, the 3D view shows a path the machine
   does not run — the class of bug that made the retract SIGN wrong for months
   (see _test_retract_sign.py).

3. **Direction still comes from the machine, not the mode.** Splitting the move
   must not disturb the "away from the part" rule: magnitude is the operator's,
   direction is the machine's (``retract_x_offset_real``).

4. **z_first warns.** It drags the roller along the part before lifting. Warn,
   never block — but it must reach the operator even when the setting was
   inherited from an opened .ssp and nobody touched the dropdown.
"""
import numpy as np
from path_generator import (PathGenerator, retract_segments,
                            resolve_retract_motion, retract_motion_is_risky,
                            retract_x_offset_real)


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
          "pass_shape": "linear_approach", "retract_x": 50.0, "retract_z": 50.0}
    op.update(extra)
    return op


def _gen(ops, positive_side=True):
    pg = PathGenerator()
    p = _params(ops, positive_side)
    pg._res = pg.calculate_paths(p, {}, _StubMgr())
    return pg, pg.generate_gcode(params=p).splitlines()


def _rapids(pg):
    res = pg._res
    return res[4] if isinstance(res, tuple) and len(res) > 4 else []


def _ret_lines(lines, tag="(Retract Op"):
    return [l for l in lines if tag in l]


def _sim_retract_legs(pg, end, target):
    """The sim's retract legs: rapid segments chained from the pass end UNTIL the
    retract target is reached.

    Stopping at the target matters — the program-end park move also starts where
    the retract finished, so a chain-follower with no stop condition swallows it
    and reports four legs for a two-leg retract.
    """
    end = np.asarray(end, dtype=float)
    target = np.asarray(target, dtype=float)
    legs, cur = [], end
    for seg in _rapids(pg):
        if np.linalg.norm(np.asarray(seg[0], dtype=float) - cur) > 1e-6:
            continue
        legs.append(seg)
        cur = np.asarray(seg[-1], dtype=float)
        if np.linalg.norm(cur - target) < 1e-6:
            break
    return legs


def _xz(line):
    x = z = None
    for tok in line.split():
        if tok.startswith("X"):
            x = float(tok[1:])
        elif tok.startswith("Z"):
            z = float(tok[1:])
    return x, z


# ── 1. Pure helper ──────────────────────────────────────────────────────────
def test_retract_segments():
    end = np.array([100.0, 0.0, 30.0])

    segs = retract_segments(end, 50.0, 20.0, "synchronized")
    assert len(segs) == 1, segs
    assert tuple(segs[0][-1][[0, 2]]) == (150.0, 50.0), segs[0][-1]

    segs = retract_segments(end, 50.0, 20.0, "x_first")
    assert len(segs) == 2, segs
    assert tuple(segs[0][-1][[0, 2]]) == (150.0, 30.0), segs[0][-1]   # X moved
    assert tuple(segs[1][-1][[0, 2]]) == (150.0, 50.0), segs[1][-1]

    segs = retract_segments(end, 50.0, 20.0, "z_first")
    assert len(segs) == 2, segs
    assert tuple(segs[0][-1][[0, 2]]) == (100.0, 50.0), segs[0][-1]   # Z moved
    assert tuple(segs[1][-1][[0, 2]]) == (150.0, 50.0), segs[1][-1]

    # A zero-length leg is dropped: with no Z offset there is nothing for the
    # second line to do, whatever the mode says.
    assert len(retract_segments(end, 50.0, 0.0, "x_first")) == 1
    assert len(retract_segments(end, 0.0, 20.0, "z_first")) == 1
    # Both zero -> no retract at all rather than a degenerate G0.
    assert retract_segments(end, 0.0, 0.0, "x_first") == []

    # Unknown mode falls back to the diagonal, never silently splits a move.
    assert len(retract_segments(end, 50.0, 20.0, "sideways")) == 1
    assert resolve_retract_motion({"retract_motion": "junk"}) == "synchronized"
    assert resolve_retract_motion({}) == "synchronized"
    print("test_retract_segments PASS")


def test_risk_predicate():
    assert retract_motion_is_risky("z_first") is True
    assert retract_motion_is_risky("x_first") is False
    assert retract_motion_is_risky("synchronized") is False
    assert retract_motion_is_risky("garbage") is False       # normalises first
    print("test_risk_predicate PASS")


# ── 2. THE REGRESSION LOCK ─────────────────────────────────────────────────
def test_default_is_byte_identical():
    """An op that never sets retract_motion must emit exactly one diagonal G0
    per retract, with the same numbers it always had."""
    for side in (True, False):
        _, unset = _gen([_rough()], side)
        _, explicit = _gen([_rough(retract_motion="synchronized")], side)
        assert unset == explicit, "explicit 'synchronized' differs from unset"

        rl = _ret_lines(unset)
        assert len(rl) == 1, rl
        x, z = _xz(rl[0])
        assert x is not None and z is not None, rl[0]
        # Exactly the legacy arithmetic: end + direction-resolved offsets.
        pg, _ = _gen([_rough()], side)
        end = pg.last_calculated_paths[0][-1]
        want_x = end[0] + retract_x_offset_real(50.0, 1.0 if side else -1.0)
        assert abs(x - want_x) < 1e-6, (side, x, want_x)
        assert abs(z - (end[2] + 50.0)) < 1e-6, (side, z, end[2] + 50.0)

        # An unknown value on disk must also reproduce the legacy output.
        _, junk = _gen([_rough(retract_motion="nonsense")], side)
        assert junk == unset, "an unreadable mode changed the output"
    print("test_default_is_byte_identical PASS")


# ── 3. Split modes: line count and order ───────────────────────────────────
def test_split_emits_two_lines_in_order():
    for side in (True, False):
        pg, lines = _gen([_rough(retract_motion="x_first")], side)
        rl = _ret_lines(lines)
        assert len(rl) == 2, rl
        end = pg.last_calculated_paths[0][-1]
        x0, z0 = _xz(rl[0])
        x1, z1 = _xz(rl[1])
        # Leg 1 moves X only (Z still at the pass end), leg 2 completes Z.
        assert abs(z0 - end[2]) < 1e-6, (side, z0, end[2])
        assert abs(x0 - x1) < 1e-6, (side, x0, x1)
        assert abs(z1 - (end[2] + 50.0)) < 1e-6, (side, z1)

        pg, lines = _gen([_rough(retract_motion="z_first")], side)
        rl = _ret_lines(lines)
        assert len(rl) == 2, rl
        end = pg.last_calculated_paths[0][-1]
        x0, z0 = _xz(rl[0])
        x1, z1 = _xz(rl[1])
        # Leg 1 moves Z only (X still at the pass end) — the risky one.
        assert abs(x0 - end[0]) < 1e-6, (side, x0, end[0])
        assert abs(z0 - (end[2] + 50.0)) < 1e-6, (side, z0)
        assert abs(z0 - z1) < 1e-6, (side, z0, z1)
    print("test_split_emits_two_lines_in_order PASS")


def test_both_axis_words_on_every_leg():
    """Each leg names X and Z, so the .nc does not depend on modal state to be
    read correctly — and a recipe line carries both regardless."""
    _, lines = _gen([_rough(retract_motion="x_first")])
    for l in _ret_lines(lines):
        x, z = _xz(l)
        assert x is not None and z is not None, l
    print("test_both_axis_words_on_every_leg PASS")


# ── 4. Direction is still the machine's ────────────────────────────────────
def test_direction_survives_the_split():
    """Splitting must not disturb the sign rule: the retract always ends up
    FURTHER from the axis, on both roller sides, in every mode."""
    for side in (True, False):
        for motion in ("synchronized", "x_first", "z_first"):
            for typed in (50.0, -50.0):          # the typed sign is ignored
                pg, lines = _gen(
                    [_rough(retract_x=typed, retract_motion=motion)], side)
                end = pg.last_calculated_paths[0][-1]
                final_x, _ = _xz(_ret_lines(lines)[-1])
                assert abs(final_x) > abs(end[0]), (
                    f"side={'+' if side else '-'} {motion} retract_x={typed}: "
                    f"final {final_x} is not clear of end {end[0]}")
    print("test_direction_survives_the_split PASS")


# ── 5. Sim and emitter agree on the shape ──────────────────────────────────
def test_sim_matches_gcode():
    for side in (True, False):
        for motion, legs in (("synchronized", 1), ("x_first", 2), ("z_first", 2)):
            pg, lines = _gen([_rough(retract_motion=motion)], side)
            rl = _ret_lines(lines)
            assert len(rl) == legs, (side, motion, rl)

            end = np.asarray(pg.last_calculated_paths[0][-1], dtype=float)
            target = np.array([
                end[0] + retract_x_offset_real(50.0, 1.0 if side else -1.0),
                end[1], end[2] + 50.0])
            chain = _sim_retract_legs(pg, end, target)
            assert len(chain) == legs, (side, motion, len(chain))

            for seg, line in zip(chain, rl):
                gx, gz = _xz(line)
                assert abs(float(seg[-1][0]) - gx) < 1e-6, (side, motion, seg[-1][0], gx)
                assert abs(float(seg[-1][2]) - gz) < 1e-6, (side, motion, seg[-1][2], gz)
    print("test_sim_matches_gcode PASS")


# ── 6. Back pass and cutting/bending follow the same rule ──────────────────
def test_back_pass_retract_splits_too():
    op = _rough(retract_motion="x_first", back_pass_enabled=True)
    _, lines = _gen([op], positive_side=False)
    bp = _ret_lines(lines, "(Retract Op1 BP")
    assert len(bp) == 2, bp
    # The forward retract is skipped when a back pass follows — unchanged rule.
    assert not _ret_lines(lines, "(Retract Op1 P"), _ret_lines(lines, "(Retract Op1 P")
    print("test_back_pass_retract_splits_too PASS")


def test_cut_bend_retract_splits_too():
    cut = {"type": "cutting", "enabled": True, "count": 1, "tool_id": "T0303",
           "r_tool": 0.0, "plunge_start_x": 100.0, "plunge_start_z": 0.0,
           "plunge_end_x": 50.0, "plunge_end_z": 0.0,
           "retract_x": 50.0, "retract_z": 50.0, "feed": 50.0,
           "retract_motion": "x_first"}
    pg, lines = _gen([cut])
    assert len(_ret_lines(lines)) == 2, _ret_lines(lines)

    # ...and the sim splits it as well (the cutting/bending branch is a THIRD
    # call site, easy to forget — it lives apart from the pass loop).
    end = np.asarray(pg.last_calculated_paths[0][-1], dtype=float)
    chain = _sim_retract_legs(pg, end,
                              np.array([end[0] + 50.0, end[1], end[2] + 50.0]))
    assert len(chain) == 2, chain
    print("test_cut_bend_retract_splits_too PASS")


# ── 7. The warning ─────────────────────────────────────────────────────────
def test_z_first_warns_and_others_do_not():
    pg, _ = _gen([_rough(retract_motion="z_first")])
    w = pg.last_retract_motion_warnings
    assert len(w) == 1, w
    assert w[0]["op_index"] == 0 and w[0]["motion"] == "z_first", w[0]

    for motion in ("synchronized", "x_first", None):
        op = _rough() if motion is None else _rough(retract_motion=motion)
        pg, _ = _gen([op])
        assert not pg.last_retract_motion_warnings, (motion, pg.last_retract_motion_warnings)

    # One entry per offending op, and it never blocks: the lines are still there.
    pg, lines = _gen([_rough(retract_motion="z_first"),
                      _rough(start_z=60.0, end_z=90.0, retract_motion="z_first"),
                      _rough(start_z=90.0, end_z=95.0)])
    assert len(pg.last_retract_motion_warnings) == 2, pg.last_retract_motion_warnings
    assert len(_ret_lines(lines)) == 2 + 2 + 1, _ret_lines(lines)
    print("test_z_first_warns_and_others_do_not PASS")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"\nAll {len(tests)} retract-motion checks passed.")
