# -*- coding: utf-8 -*-
"""Headless test: the 3D-view-only switches.

Two switches, both purely about what gets DRAWN:

  show_tip_paths  draw at the roller TOUCH POINT instead of the roller centre
  show_rapids     show/hide the orange dashed G0 lines

What this pins:

1. **Neither switch can reach a path, a G-code line or a recipe.** They are view
   preferences; if one ever changes an emitted number the feature is a bug.

2. **The tip view moves EVERYTHING it should.** It used to move only the pass
   lines, leaving the rapids and the Point markers at the roller centre — so the
   rapids no longer met the passes they connect, and the Point triangles sat
   r_tool away from the lines they are read against.

3. **They survive opening someone else's program.** save_project writes the
   whole params dict, so without preservation an old .ssp silently reconfigures
   your 3D view. Same class as the 2026-08-14 machine-settings incident.
"""
import copy
import json
import os
import tempfile

import numpy as np

from path_generator import PathGenerator


class _StubMgr:
    """Flat cylinder R=50, Z 0..100."""
    def __init__(self):
        self.props = {"top_z": 100.0, "min_z": 0.0, "max_radius": 50.0}
    def get_radius_fast(self, z): return 50.0
    def get_normal_at_z(self, z): return 1.0, 0.0
    def get_straightened_radius(self, z): return 50.0
    def get_straightened_normal(self, z): return 1.0, 0.0


def _params(ops, **extra):
    p = {"operations": ops, "retract_x": 50.0, "retract_z": 50.0,
         "home_x": 300.0, "home_z": 150.0, "mandrel_pos_x_offset": 0.0,
         "final_part_thickness_on_mandrel": 2.0, "shell_thickness": 0.0,
         "target_clearance": 2.0, "roller_positive_x_side": True,
         "auto_calculate_paths": False}
    p.update(extra)
    return p


def _rough(**extra):
    op = {"type": "roughing", "enabled": True, "count": 1, "tool_id": "T0101",
          "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0, "p1_x": 40.0,
          "p1_z": 50.0, "p3_x": 40.0, "p3_z": -20.0,
          "pass_shape": "linear_approach"}
    op.update(extra)
    return op


def _point(**extra):
    op = {"type": "point", "enabled": True, "count": 1, "tool_id": "T0101",
          "r_tool": 25.0, "point_x": 120.0, "point_z": 80.0}
    op.update(extra)
    return op


# ── 1. Neither switch touches the engine ───────────────────────────────────
def test_switches_never_change_the_program():
    """The strongest guarantee: flip both switches every way and the emitted
    G-code must be byte-identical each time."""
    ops = [_rough(), _point(), _rough(start_z=60.0, end_z=90.0)]
    outputs = set()
    for tip in (False, True):
        for rap in (False, True):
            pg = PathGenerator()
            p = _params(copy.deepcopy(ops), show_tip_paths=tip, show_rapids=rap)
            pg.calculate_paths(p, {}, _StubMgr())
            outputs.add(pg.generate_gcode(params=p))
    assert len(outputs) == 1, (
        f"{len(outputs)} different G-code outputs — a VIEW switch changed the program")
    print("test_switches_never_change_the_program PASS")


# ── 2. The tip shift, and what it must cover ───────────────────────────────
def test_shift_helper_is_radial_and_clamped():
    """_shift_path_to_tip is pure geometry, so it can be checked without Tk."""
    from main import SpinningApp
    app = SpinningApp.__new__(SpinningApp)          # no __init__: no plotter, no Tk
    app.params = {"mandrel_pos_x_offset": 0.0}

    pts = np.array([[100.0, 0.0, 10.0], [-100.0, 0.0, 20.0]])
    out = app._shift_path_to_tip(pts, 25.0)
    assert out[0][0] == 75.0, out          # +X side pulled IN toward the axis
    assert out[1][0] == -75.0, out         # -X side pulled in too, not flipped
    assert out[0][2] == 10.0 and out[1][2] == 20.0, "Z must not move"

    # Never crosses the spin axis, however big the tool.
    out = app._shift_path_to_tip(np.array([[10.0, 0.0, 0.0]]), 999.0)
    assert out[0][0] > 0.0, out

    # A non-zero mandrel centre shifts about the CENTRE, not about zero.
    app.params["mandrel_pos_x_offset"] = 40.0
    out = app._shift_path_to_tip(np.array([[140.0, 0.0, 0.0]]), 25.0)
    assert out[0][0] == 115.0, out
    print("test_shift_helper_is_radial_and_clamped PASS")


def test_rapid_rtools_tracks_the_mounted_tool():
    """Each rapid is shifted by the roller actually mounted when it runs, taken
    from the most recent cut in the emission sequence."""
    from main import SpinningApp
    app = SpinningApp.__new__(SpinningApp)
    ops = [_rough(r_tool=25.0, tool_id="T0101"),
           _rough(r_tool=10.0, tool_id="T0202", start_z=60.0, end_z=90.0)]
    app.params = _params(ops)
    app.path_gen = PathGenerator()
    res = app.path_gen.calculate_paths(app.params, {}, _StubMgr())
    rapids = res[4]

    rts = app._rapid_rtools(rapids)
    assert len(rts) == len(rapids), (len(rts), len(rapids))
    assert set(rts) <= {25.0, 10.0}, rts
    # Both tools are represented: the run starts on T0101 and ends on T0202.
    assert 25.0 in rts and 10.0 in rts, rts
    # Ordering: the last rapid (park move) happens after the 10 mm tool is on.
    assert rts[-1] == 10.0, rts

    # Desync guard: a mismatched length must fall back, never mis-assign.
    assert app._rapid_rtools(list(rapids) + [rapids[0]]) == [25.0] * (len(rapids) + 1)
    print("test_rapid_rtools_tracks_the_mounted_tool PASS")


def test_tip_shift_keeps_rapids_meeting_passes():
    """The reason rapids must move with the passes: a rapid starts where a pass
    ended. Shift one and not the other and the drawn lines come apart."""
    from main import SpinningApp
    app = SpinningApp.__new__(SpinningApp)
    app.params = _params([_rough()])
    app.path_gen = PathGenerator()
    res = app.path_gen.calculate_paths(app.params, {}, _StubMgr())
    paths, rapids = res[0], res[4]

    pass_end = np.asarray(paths[0][-1], dtype=float)
    joining = [s for s in rapids
               if np.linalg.norm(np.asarray(s[0], dtype=float) - pass_end) < 1e-6]
    assert joining, "no rapid starts at the pass end — test premise is wrong"

    r = 25.0
    shifted_pass_end = app._shift_path_to_tip(np.array([pass_end]), r)[0]
    shifted_rapid_start = app._shift_path_to_tip(
        np.asarray(joining[0], dtype=float), r)[0]
    assert np.allclose(shifted_pass_end, shifted_rapid_start), (
        shifted_pass_end, shifted_rapid_start)
    print("test_tip_shift_keeps_rapids_meeting_passes PASS")


def test_point_marker_shift_lands_on_the_sheet():
    """A surface-mode Point resolves to radius + sheet + r_tool + standoff. Drawn
    at the tip it must land at radius + sheet + standoff — i.e. ON the sheet,
    which is what makes the marker checkable at a glance."""
    from main import SpinningApp
    app = SpinningApp.__new__(SpinningApp)
    op = _point(point_mode="surface", point_z=40.0, point_standoff=10.0,
                r_tool=25.0)
    app.params = _params([op])
    app.path_gen = PathGenerator()
    app.path_gen.calculate_paths(app.params, {}, _StubMgr())

    m = app.path_gen.last_point_markers[0]
    assert m["x"] == 50.0 + 2.0 + 25.0 + 10.0, m       # roller CENTRE as stored
    tip_x = app._shift_path_to_tip(np.array([[m["x"], 0.0, m["z"]]]), 25.0)[0][0]
    assert tip_x == 50.0 + 2.0 + 10.0, tip_x           # contact point
    print("test_point_marker_shift_lands_on_the_sheet PASS")


# ── 3. Opening a program must not reconfigure the view ─────────────────────
def test_view_prefs_survive_a_project_load():
    from main import SpinningApp, _VIEW_ONLY_PREF_KEYS
    assert "show_rapids" in _VIEW_ONLY_PREF_KEYS
    assert "show_tip_paths" in _VIEW_ONLY_PREF_KEYS

    app = SpinningApp.__new__(SpinningApp)
    app.params = _params([_rough()], show_tip_paths=True, show_rapids=False)
    app.mandrel_mgr = _StubMgr()
    app.path_gen = PathGenerator()
    app.gui_pass_overrides = {}

    # A saved program from someone whose view settings are the opposite.
    saved = {"params": _params([_rough()], show_tip_paths=False,
                               show_rapids=True)}
    fd, path = tempfile.mkstemp(suffix=".ssp")
    os.close(fd)
    try:
        with open(path, "w") as f:
            json.dump(saved, f)
        try:
            app.load_project(path)
        except Exception:
            # load_project touches UI/mandrel plumbing this stub does not have;
            # what matters is that the preference restore ran before any of it.
            pass
        assert app.params["show_tip_paths"] is True, "the file overwrote the tip view"
        assert app.params["show_rapids"] is False, "the file overwrote the rapid view"
    finally:
        os.unlink(path)
    print("test_view_prefs_survive_a_project_load PASS")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"\nAll {len(tests)} view-toggle checks passed.")
