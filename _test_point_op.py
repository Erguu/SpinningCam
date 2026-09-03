# -*- coding: utf-8 -*-
"""Headless test: the "Point" operation — go to ONE typed X/Z and stop.

What this pins, in order of how badly it would hurt:

1. **A program with no Point op emits byte-identical G-code.** The whole feature
   is opt-in; if this fails, every existing recipe changed.

2. **Path-index accounting stays aligned.** A Point contributes NO toolpath, so
   ``calculate_paths`` and ``generate_gcode`` must BOTH skip it. If one of them
   advances the shared index and the other does not, every later pass is emitted
   against the wrong operation — with the wrong tool and feed. This is the same
   failure the ``emit_count`` guard exists for (cutting/bending once did it).

3. **X survives the canonical/machine mirror.** The sim builds in the canonical
   +X frame and mirrors at the end; the emitter is already in the real frame.
   Getting this wrong is COMPLETELY SILENT on a positive-side machine and wrong
   by 2*(x - center) on a negative-side one — which is what the ID111/ID112
   profiles actually are.
"""
import numpy as np
from path_generator import (PathGenerator, motion_waypoints, point_surface_x,
                            resolve_point_mode, resolve_point_motion,
                            resolve_point_target, resolve_point_feed)


class _StubMgr:
    """Flat cylinder R=50, Z 0..100."""
    def __init__(self):
        self.props = {"top_z": 100.0, "min_z": 0.0, "max_radius": 50.0}
    def get_radius_fast(self, z): return 50.0
    def get_normal_at_z(self, z): return 1.0, 0.0
    def get_straightened_radius(self, z): return 50.0
    def get_straightened_normal(self, z): return 1.0, 0.0


HOME_X = {True: 300.0, False: -300.0}


def _params(ops, positive_side=True):
    # home_x follows the ROLLER SIDE, as the real machine profiles do
    # (ID111-1 stores -419.9 with roller_positive_x_side = 0). A positive home_x
    # on a negative-side machine is not a configuration that exists, and testing
    # it would pin behaviour nobody can hit.
    return {"operations": ops, "retract_x": 50.0, "retract_z": 50.0,
            "home_x": HOME_X[bool(positive_side)],
            "home_z": 150.0, "mandrel_pos_x_offset": 0.0,
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


def _point(**extra):
    op = {"type": "point", "enabled": True, "count": 1, "tool_id": "T0101",
          "r_tool": 25.0, "point_x": 120.0, "point_z": 80.0,
          "point_motion": "synchronized", "point_rapid": True,
          "feed": 300.0, "speed": 300.0, "speed_mode": "RPM"}
    op.update(extra)
    return op


def _gen(ops, positive_side=True):
    """(path_generator, gcode_lines) for a program. The calculate_paths return
    tuple is stashed on the generator as ``_res`` so tests can reach the rapid
    segment list (index 4) without re-running the calculation."""
    pg = PathGenerator()
    p = _params(ops, positive_side)
    pg._res = pg.calculate_paths(p, {}, _StubMgr())
    return pg, pg.generate_gcode(params=p).splitlines()


def _rapids(pg):
    res = pg._res
    return res[4] if isinstance(res, tuple) and len(res) > 4 else []


def _point_lines(lines):
    return [l for l in lines if "(Point Op" in l]


def _axis(line, letter):
    for tok in line.split():
        if tok.startswith(letter) and tok[1:].replace(".", "").replace("-", "").isdigit():
            return float(tok[1:])
    return None


# ── 1. Pure helpers ─────────────────────────────────────────────────────────
def test_motion_waypoints():
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([10.0, 0.0, 20.0])

    sync = motion_waypoints(a, b, "synchronized")
    assert len(sync) == 2, sync

    xf = motion_waypoints(a, b, "x_first")
    assert len(xf) == 3
    assert xf[1][0] == 10.0 and xf[1][2] == 0.0, xf[1]   # X moved, Z held

    zf = motion_waypoints(a, b, "z_first")
    assert len(zf) == 3
    assert zf[1][0] == 0.0 and zf[1][2] == 20.0, zf[1]   # Z moved, X held

    # Unknown mode must fall back to the diagonal, never silently split a move.
    assert len(motion_waypoints(a, b, "sideways")) == 2
    assert resolve_point_motion({"point_motion": "nonsense"}) == "synchronized"
    assert resolve_point_motion({}) == "synchronized"
    print("test_motion_waypoints PASS")


def test_target_frame_conversion():
    """center_x=None is identity (emitter). With center_x/side it must undo the
    end-of-pass mirror, so a round trip returns the typed number."""
    op = {"point_x": 120.0, "point_z": 80.0}
    assert resolve_point_target(op)[0] == 120.0

    center = 0.0
    canon = resolve_point_target(op, center_x=center, side=-1.0)[0]
    assert canon == -120.0, canon                       # pre-mirrored
    assert 2.0 * center - canon == 120.0                # mirror returns the typed X

    # A non-zero mandrel centre must not break the round trip.
    center = 35.0
    canon = resolve_point_target(op, center_x=center, side=-1.0)[0]
    assert abs((2.0 * center - canon) - 120.0) < 1e-9, canon

    # Positive side: no conversion at all.
    assert resolve_point_target(op, center_x=35.0, side=1.0)[0] == 120.0

    # Garbage / missing values fall back to 0 rather than raising mid-calculation.
    assert resolve_point_target({"point_x": "", "point_z": None})[0] == 0.0
    assert resolve_point_target({"point_x": "abc"})[0] == 0.0
    print("test_target_frame_conversion PASS")


def test_feed_resolution():
    assert resolve_point_feed({}, {})[0] is True                # rapid by default
    is_rapid, feed = resolve_point_feed({"point_rapid": False, "feed": 120.0}, {})
    assert is_rapid is False and feed == 120.0
    # Unreadable feed falls back to the global rather than raising.
    _, feed = resolve_point_feed({"point_rapid": False, "feed": "x"},
                                 {"feed_rate_mm_min": 250.0})
    assert feed == 250.0, feed
    print("test_feed_resolution PASS")


# ── 2. THE REGRESSION LOCK: no Point op = byte-identical ────────────────────
def test_no_point_op_is_byte_identical():
    """The one that matters most. Two roughing ops, no Point anywhere: the
    emitted G-code must be exactly what it was before this feature existed."""
    for side in (True, False):
        _, a = _gen([_rough(), _rough(start_z=60.0, end_z=90.0)], side)
        # Same program, regenerated — and nothing Point-shaped may appear in it.
        assert not _point_lines(a), a
        assert not any("POINT" in l for l in a), [l for l in a if "POINT" in l]
    print("test_no_point_op_is_byte_identical PASS")


# ── 3. Path-index accounting: a Point steals nobody's pass ──────────────────
def test_point_contributes_no_toolpath():
    pg_without, _ = _gen([_rough(), _rough(start_z=60.0, end_z=90.0)])
    pg_with, _ = _gen([_rough(), _point(), _rough(start_z=60.0, end_z=90.0)])
    assert len(pg_with.last_calculated_paths) == len(pg_without.last_calculated_paths), (
        f"Point added {len(pg_with.last_calculated_paths) - len(pg_without.last_calculated_paths)} "
        f"toolpath(s); it must add none")
    print("test_point_contributes_no_toolpath PASS")


def test_passes_still_belong_to_their_op():
    """A Point between two roughing ops must not shift the later op's passes.
    Compare the emitted pass geometry with and without the Point in the middle."""
    _, without = _gen([_rough(), _rough(start_z=60.0, end_z=90.0)])
    _, with_pt = _gen([_rough(), _point(), _rough(start_z=60.0, end_z=90.0)])

    def cuts(lines):
        return [l.split("(")[0].strip() for l in lines if l.startswith("G1 X")]

    assert cuts(without) == cuts(with_pt), (
        "the Point op changed the cutting moves of the passes around it")

    # And the second roughing op's passes are still labelled Op3 (not Op2's).
    assert any("(Op3 P1)" in l for l in with_pt), \
        [l for l in with_pt if "Op" in l and "P1" in l][:8]
    print("test_passes_still_belong_to_their_op PASS")


def test_pass_colors_mirror_agrees():
    """pass_colors.path_categories mirrors calculate_paths. It must skip a Point
    op too, or the 3D view colours every later pass as the one before it."""
    import pass_colors
    ops = [_rough(), _point(), _rough(start_z=60.0, end_z=90.0)]
    pg, _ = _gen(ops)
    cats = pass_colors.path_categories(ops)
    assert len(cats) == len(pg.last_calculated_paths), (
        f"{len(cats)} colours for {len(pg.last_calculated_paths)} paths")
    assert "point" not in cats, cats
    print("test_pass_colors_mirror_agrees PASS")


# ── 4. Emitted lines ────────────────────────────────────────────────────────
def test_synchronized_emits_one_line():
    _, lines = _gen([_point(point_motion="synchronized")])
    pts = _point_lines(lines)
    assert len(pts) == 1, pts
    assert _axis(pts[0], "X") == 120.0 and _axis(pts[0], "Z") == 80.0, pts
    assert pts[0].startswith("G0"), pts
    print("test_synchronized_emits_one_line PASS")


def test_split_motion_order_and_line_count():
    _, lines = _gen([_point(point_motion="x_first")])
    pts = _point_lines(lines)
    assert len(pts) == 2, pts
    assert _axis(pts[0], "X") == 120.0 and _axis(pts[0], "Z") is None, pts
    assert _axis(pts[1], "Z") == 80.0 and _axis(pts[1], "X") is None, pts

    _, lines = _gen([_point(point_motion="z_first")])
    pts = _point_lines(lines)
    assert len(pts) == 2, pts
    assert _axis(pts[0], "Z") == 80.0 and _axis(pts[0], "X") is None, pts
    assert _axis(pts[1], "X") == 120.0 and _axis(pts[1], "Z") is None, pts
    print("test_split_motion_order_and_line_count PASS")


def test_feed_move_emits_g1_with_f():
    _, lines = _gen([_point(point_rapid=False, feed=250.0)])
    pts = _point_lines(lines)
    assert len(pts) == 1 and pts[0].startswith("G1"), pts
    assert _axis(pts[0], "F") == 250.0, pts

    # A rapid must carry NO F: the recipe format requires F=0 on every command
    # except LINEAR (CAM_INTERFACE_SPEC section 5).
    _, lines = _gen([_point(point_rapid=True)])
    assert _axis(_point_lines(lines)[0], "F") is None, _point_lines(lines)

    # Feed is clamped into the PLC's 1..3000 window rather than emitted raw.
    _, lines = _gen([_point(point_rapid=False, feed=99999.0)])
    assert _axis(_point_lines(lines)[0], "F") == 3000.0, _point_lines(lines)
    print("test_feed_move_emits_g1_with_f PASS")


# ── 5. The silent one: X on a negative-side machine ─────────────────────────
def test_negative_side_x_matches_sim_and_gcode():
    """The typed X is a real machine X. The emitted line must carry it exactly,
    and the 3D marker must land on the same number after the mirror."""
    for side in (True, False):
        pg, lines = _gen([_point(point_x=120.0, point_z=80.0)], positive_side=side)
        gc_x = _axis(_point_lines(lines)[0], "X")
        assert gc_x == 120.0, (side, gc_x)

        marks = pg.last_point_markers
        assert len(marks) == 1, marks
        assert abs(marks[0]["x"] - gc_x) < 1e-9, (
            f"side={'+' if side else '-'}: 3D marker at X={marks[0]['x']} but "
            f"G-code goes to X={gc_x}")
        assert abs(marks[0]["z"] - 80.0) < 1e-9, marks
    print("test_negative_side_x_matches_sim_and_gcode PASS")


def test_sim_rapids_reach_the_point():
    """The sim must actually travel to the setpoint, with the right number of
    legs for the motion mode — the picture and the machine agree on shape."""
    for motion, legs in (("synchronized", 1), ("x_first", 2), ("z_first", 2)):
        pg, lines = _gen([_point(point_motion=motion)], positive_side=False)
        assert len(_point_lines(lines)) == legs, (motion, _point_lines(lines))
        # Some rapid segment ends exactly on the setpoint (real frame after mirror).
        ends = [(float(s[-1][0]), float(s[-1][2])) for s in _rapids(pg)]
        assert any(abs(x - 120.0) < 1e-6 and abs(z - 80.0) < 1e-6
                   for x, z in ends), (motion, ends[-4:])
    print("test_sim_rapids_reach_the_point PASS")


# ── 6. count is ignored, disabled is skipped ───────────────────────────────
def test_count_ignored_and_disabled_skipped():
    """A stray count>1 (hand-edited .ssp, imported preset) must not repeat the
    move — the same trap cutting/bending's emit_count guard was built for."""
    _, one = _gen([_point(count=1)])
    _, five = _gen([_point(count=5)])
    assert len(_point_lines(one)) == len(_point_lines(five)) == 1, (
        len(_point_lines(one)), len(_point_lines(five)))

    pg, lines = _gen([_point(enabled=False)])
    assert not _point_lines(lines), lines
    assert not pg.last_point_markers, pg.last_point_markers
    print("test_count_ignored_and_disabled_skipped PASS")


# ── 7. Tool change at a chosen place ───────────────────────────────────────
def test_point_op_can_carry_a_tool_change():
    """A Point op with a new tool_id is how an operator says "change the tool
    HERE". The M6 must be emitted, and before the Point's own move."""
    _, lines = _gen([_rough(tool_id="T0101"),
                     _point(tool_id="T0303"),
                     _rough(tool_id="T0303", start_z=60.0, end_z=90.0)])
    idx_m6 = next(i for i, l in enumerate(lines) if l.startswith("M6 T0303"))
    idx_pt = next(i for i, l in enumerate(lines) if "(Point Op" in l)
    assert idx_m6 < idx_pt, (idx_m6, idx_pt)
    assert sum(1 for l in lines if l.startswith("M6 T0303")) == 1, \
        "the following op re-commanded a tool change it already had"
    print("test_point_op_can_carry_a_tool_change PASS")


# ── 8. No retract, by design ───────────────────────────────────────────────
def test_point_emits_no_retract():
    """A retract would immediately undo the position the op exists to reach."""
    _, lines = _gen([_point()])
    assert not [l for l in lines if "(Retract Op1" in l], lines
    print("test_point_emits_no_retract PASS")


# ── 9. Reference modes (2026-09-03b) ───────────────────────────────────────
# A pass takes its Z and derives its X from the mandrel; an absolute Point does
# not follow the part at all. These modes close that gap.
def test_mode_normalisation():
    assert resolve_point_mode({}) == "absolute"
    assert resolve_point_mode({"point_mode": "SURFACE"}) == "surface"
    # Unknown must fall back to absolute — the only mode that needs no context
    # and so cannot resolve against the wrong mandrel or the wrong pass.
    assert resolve_point_mode({"point_mode": "sideways"}) == "absolute"
    assert resolve_point_mode({"point_mode": None}) == "absolute"
    print("test_mode_normalisation PASS")


def test_absolute_mode_unchanged():
    """The default must reproduce exactly what the Point op did before modes
    existed — an op with no point_mode key at all."""
    for side in (True, False):
        _, no_key = _gen([_point()], side)
        _, explicit = _gen([_point(point_mode="absolute")], side)
        _, junk = _gen([_point(point_mode="nonsense")], side)
        assert no_key == explicit == junk, "absolute mode is not the stable default"
        assert _axis(_point_lines(no_key)[0], "X") == 120.0
    print("test_absolute_mode_unchanged PASS")


def test_surface_mode_follows_the_mandrel():
    """X = mandrel radius at that Z + sheet + tool + standoff — the same stack a
    forming pass uses, so standoff 0 lands where a zero-clearance pass would."""
    # _StubMgr is a flat R=50 cylinder; params carry sheet=2.0, shell=0.
    op = _point(point_mode="surface", point_z=40.0, point_standoff=10.0,
                r_tool=25.0)
    want = 50.0 + 2.0 + 25.0 + 10.0                 # radius + sheet + tool + standoff
    assert point_surface_x(op, _params([op]), _StubMgr(), 40.0, 0.0) == want

    for side in (True, False):
        pg, lines = _gen([op], side)
        gx = _axis(_point_lines(lines)[0], "X")
        assert abs(gx - (want if side else -want)) < 1e-6, (side, gx)
        # The 3D marker must land on the same number after the mirror.
        assert abs(pg.last_point_markers[0]["x"] - gx) < 1e-9, pg.last_point_markers

    # The whole reason this mode exists: change the part, the Point moves with it.
    thick = dict(_params([op]))
    thick["final_part_thickness_on_mandrel"] = 5.0
    pg2 = PathGenerator()
    pg2.calculate_paths(thick, {}, _StubMgr())
    moved = _axis(_point_lines(pg2.generate_gcode(params=thick).splitlines())[0], "X")
    assert abs(moved - (want + 3.0)) < 1e-6, moved
    print("test_surface_mode_follows_the_mandrel PASS")


def test_surface_mode_warns_off_the_mandrel():
    """A Z past the end of the profile reads a clamped radius, so the resolved X
    is not what the operator meant. Warn — never silently drive there."""
    pg, lines = _gen([_point(point_mode="surface", point_z=500.0)])
    assert len(pg.last_point_warnings) == 1, pg.last_point_warnings
    assert pg.last_point_warnings[0]["op_index"] == 0
    assert _point_lines(lines), "warning must not suppress the move"

    pg, _ = _gen([_point(point_mode="surface", point_z=40.0)])
    assert not pg.last_point_warnings, pg.last_point_warnings
    # Absolute mode is never checked against the mandrel — it has no business
    # being on it.
    pg, _ = _gen([_point(point_mode="absolute", point_z=500.0)])
    assert not pg.last_point_warnings, pg.last_point_warnings
    print("test_surface_mode_warns_off_the_mandrel PASS")


def test_relative_and_home_modes():
    """Both are an offset from an anchor; only the anchor differs. The anchor
    arrives in the caller's frame, so ONLY the X offset needs the side flip."""
    # ΔX carries its LITERAL SIGN in the real machine frame — a positive ΔX
    # raises X on BOTH roller sides. Same rule as the tool-change offsets, and
    # deliberately unlike the retract, where the sign is ignored and the
    # direction comes from the machine (that one means "get clear"; this one is
    # a position the operator aimed at).
    for side in (True, False):
        # relative: anchor = previous pass's FORMING end (not the retract end).
        pg, lines = _gen([_rough(), _point(point_mode="relative",
                                           point_dx=20.0, point_dz=5.0)], side)
        prev_end = pg.last_calculated_paths[-1][-1]
        gx, gz = _axis(_point_lines(lines)[0], "X"), _axis(_point_lines(lines)[0], "Z")
        assert abs(gx - (prev_end[0] + 20.0)) < 1e-6, (side, gx, prev_end[0])
        assert abs(gz - (prev_end[2] + 5.0)) < 1e-6, (side, gz, prev_end[2])

        # home: anchor = Program Start. dx is applied in the REAL frame, so a
        # positive dx always moves +X whichever side the roller is on.
        _, lines = _gen([_point(point_mode="home", point_dx=-50.0, point_dz=-30.0)], side)
        gx, gz = _axis(_point_lines(lines)[0], "X"), _axis(_point_lines(lines)[0], "Z")
        assert abs(gx - (HOME_X[side] - 50.0)) < 1e-6, (side, gx)
        assert abs(gz - (150.0 - 30.0)) < 1e-6, (side, gz)
    print("test_relative_and_home_modes PASS")


def test_relative_with_no_previous_pass_falls_back():
    """A relative Point as the FIRST op has nothing to measure from. It must
    fall back to the absolute fields rather than resolving against nothing."""
    _, lines = _gen([_point(point_mode="relative", point_dx=20.0, point_dz=5.0,
                            point_x=120.0, point_z=80.0)])
    gx, gz = _axis(_point_lines(lines)[0], "X"), _axis(_point_lines(lines)[0], "Z")
    assert (gx, gz) == (120.0, 80.0), (gx, gz)
    print("test_relative_with_no_previous_pass_falls_back PASS")


def test_modes_agree_between_sim_and_gcode():
    """Every mode, both roller sides: the 3D marker and the emitted line must
    name the same position. This is the silent one — an absolute-mode-only frame
    conversion would pass every other test here."""
    cases = [
        _point(point_mode="absolute", point_x=120.0, point_z=80.0),
        _point(point_mode="surface", point_z=40.0, point_standoff=10.0),
        _point(point_mode="home", point_dx=-50.0, point_dz=-30.0),
        _point(point_mode="relative", point_dx=20.0, point_dz=5.0),
    ]
    for op in cases:
        for side in (True, False):
            pg, lines = _gen([_rough(), op], side)
            gx = _axis(_point_lines(lines)[0], "X")
            gz = _axis(_point_lines(lines)[0], "Z")
            m = pg.last_point_markers[0]
            assert abs(m["x"] - gx) < 1e-6, (op["point_mode"], side, m["x"], gx)
            assert abs(m["z"] - gz) < 1e-6, (op["point_mode"], side, m["z"], gz)
    print("test_modes_agree_between_sim_and_gcode PASS")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"\nAll {len(tests)} Point-op checks passed.")
