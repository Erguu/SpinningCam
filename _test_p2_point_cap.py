"""
Headless tests for TODO #99 — per-op P2 fillet point cap (`p2_radius_max_points`).

Covers:
  1. _thin_evenly: caps the count, keeps both endpoints, spaces by ARC LENGTH.
  2. Unset cap  == byte-identical to today's decimation (the back-compat proof).
  3. Cap APPLIED when it costs no clearance.
  4. Cap REFUSED when it would cut the corner — uncapped path kept + warning raised.
  5. measure_min_clearance still behaves after being refactored onto
     _path_min_clearance (regression on the auto-tune guard).

Run inside the `spinning_cam` conda env (path_generator pulls pythonocc):
    conda run -n spinning_cam python _test_p2_point_cap.py
"""
import math
import numpy as np

from path_generator import PathGenerator


PARAMS = {"mandrel_pos_x_offset": 0.0,
          "final_part_thickness_on_mandrel": 0.0,
          "shell_thickness": 0.0}


class FlatMgr:
    """Cylinder of radius 100 — clearance is simply x - 100."""
    def get_radius_fast(self, z):
        return 100.0


class BumpMgr:
    """Smooth convex bump peaking at z=5 (R 100 -> 108 -> 100).

    Curved, NOT piecewise linear: a chord across it really does cut in, which is
    what makes the refusal case meaningful.
    """
    def get_radius_fast(self, z):
        if z < 0 or z > 10:
            return 100.0
        return 100.0 + 8.0 * math.sin(math.pi * z / 10.0)


class TriangleMgr:
    """The exact mandrel used by _test_plc_autotune.py: piecewise-LINEAR bump,
    R(0)=100, R(5)=108, R(10)=100. A 3-point path along its faces sits at a
    constant 2 mm, so it isolates 'chord across the corner' from 'chord across
    a curve'. Used for the measure_min_clearance regression.
    """
    def get_radius_fast(self, z):
        if z < 0 or z > 10:
            return 100.0
        return 100.0 + 8.0 * (1.0 - abs(z - 5.0) / 5.0)


def _pg(mgr, op=None):
    pg = PathGenerator()
    pg.last_mandrel_mgr = mgr
    pg._path_op_map = [op or {"r_tool": 0.0, "type": "roughing"}]
    return pg


def _path_with_split(radius_fn, n_fillet=21):
    """[approach] + [dense fillet 0..10] + [exit], plus its (T1, T2) split indices."""
    app = [[102.0, 0.0, -5.0]]
    fil = [[radius_fn(z) + 2.0, 0.0, z] for z in np.linspace(0.0, 10.0, n_fillet)]
    ext = [[102.0, 0.0, 15.0]]
    pts = np.array(app + fil + ext, dtype=float)
    t1 = len(app)                    # first fillet point
    t2 = len(app) + n_fillet - 1     # last fillet point
    return pts, (t1, t2)


# --------------------------------------------------------------------------
def test_thin_evenly():
    pg = PathGenerator()

    pts = np.array([[0.0, 0.0, float(z)] for z in range(21)])
    out = pg._thin_evenly(pts, 5)
    assert len(out) == 5, f"expected 5 points, got {len(out)}"
    assert np.allclose(out[0], pts[0]), "first point must survive"
    assert np.allclose(out[-1], pts[-1]), "last point must survive"
    gaps = np.diff(out[:, 2])
    assert np.allclose(gaps, gaps[0]), f"spacing should be even, got {gaps}"

    # already short enough -> untouched
    short = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 1.0]])
    assert len(pg._thin_evenly(short, 9)) == 2, "short runs must pass through"

    # n_max < 2 is clamped to the two endpoints
    assert len(pg._thin_evenly(pts, 0)) == 2, "n_max<2 must clamp to 2"

    # even by ARC LENGTH, not index: points bunched at one end must not bias it
    bunched = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.1], [0.0, 0.0, 0.2],
                        [0.0, 0.0, 0.3], [0.0, 0.0, 10.0]])
    out = pg._thin_evenly(bunched, 3)
    assert abs(out[1][2] - 5.0) > 4.0, (
        f"middle point should be picked by distance, not index; got z={out[1][2]}")
    print("[OK] _thin_evenly: count, endpoints, even arc-length spacing")


def test_unset_cap_is_identical():
    pts, split = _path_with_split(FlatMgr().get_radius_fast)
    pg = _pg(FlatMgr())
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    old = pg.decimate_all_paths(0.5, 0.5, 0.0)                    # no params at all
    new = pg.decimate_all_paths(0.5, 0.5, 0.0, params=PARAMS)     # params, no cap key

    assert len(old) == len(new) == 1
    assert old[0].shape == new[0].shape, f"{old[0].shape} != {new[0].shape}"
    assert np.array_equal(old[0], new[0]), "unset cap must be byte-identical"
    assert pg.last_point_cap_warnings == [], "no cap set -> no warnings"
    print(f"[OK] unset cap byte-identical ({len(old[0])} pts, unchanged)")


def test_cap_applied_when_safe():
    # Fillet bulges AWAY from the mandrel, so chords across it never approach it:
    # thinning costs no clearance and the cap must be honoured.
    pts, split = _path_with_split(
        lambda z: 100.0 + 8.0 * math.sin(math.pi * z / 10.0), n_fillet=61)
    pg = _pg(FlatMgr(), op={"r_tool": 0.0, "type": "roughing",
                            "p2_radius_max_points": 4})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    # Tight tolerance so RDP keeps a genuinely dense fillet -> the cap has to bite.
    plain = pg.decimate_all_paths(0.02, 0.02, 0.0)
    capped = pg.decimate_all_paths(0.02, 0.02, 0.0, params=PARAMS)

    assert len(plain[0]) > 10, (
        f"test setup: fillet should survive RDP densely, got {len(plain[0])}")
    assert len(capped[0]) < len(plain[0]) - 5, (
        f"cap should cut the count hard: {len(plain[0])} -> {len(capped[0])}")
    assert pg.last_point_cap_warnings == [], (
        f"safe cap must not warn, got {pg.last_point_cap_warnings}")

    floor = pg._path_min_clearance(pts, pg._path_op_map[0], PARAMS)
    got = pg._path_min_clearance(capped[0], pg._path_op_map[0], PARAMS)
    assert got >= floor - 1e-6, f"clearance dropped {floor:.3f} -> {got:.3f}"
    print(f"[OK] cap applied: {len(plain[0])} -> {len(capped[0])} pts, "
          f"clearance {floor:.2f} -> {got:.2f} mm")


def test_cap_refused_when_it_gouges():
    # Path hugs a CURVED bump at 2 mm. Thinning the fillet makes chords cut in.
    pts, split = _path_with_split(BumpMgr().get_radius_fast)
    pg = _pg(BumpMgr(), op={"r_tool": 0.0, "type": "roughing", "name": "ROUGH-1",
                            "p2_radius_max_points": 3})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    plain = pg.decimate_all_paths(0.5, 0.5, 0.0)
    out = pg.decimate_all_paths(0.5, 0.5, 0.0, params=PARAMS)

    assert np.array_equal(out[0], plain[0]), (
        "an unsafe cap must fall back to the uncapped decimation")
    assert len(pg.last_point_cap_warnings) == 1, (
        f"expected one warning, got {pg.last_point_cap_warnings}")
    w = pg.last_point_cap_warnings[0]
    assert w["requested"] == 3 and w["op_name"] == "ROUGH-1"
    assert w["clearance"] < w["floor"], "warning must record the clearance loss"
    print(f"[OK] cap refused: kept {w['kept']} pts, clearance would have gone "
          f"{w['floor']:.2f} -> {w['clearance']:.2f} mm")


def test_measure_min_clearance_regression():
    """The refactor onto _path_min_clearance must not change the auto-tune guard.

    Same geometry and same expectations as _test_plc_autotune.py, so a drift here
    means the shared clearance metric moved.
    """
    pg = _pg(TriangleMgr())
    A, B, C = [102.0, 0.0, 0.0], [110.0, 0.0, 5.0], [102.0, 0.0, 10.0]
    full = np.array([A, B, C])
    chord = np.array([A, C])

    cl_full = pg.measure_min_clearance([full], PARAMS)
    cl_chord = pg.measure_min_clearance([chord], PARAMS)

    assert abs(cl_full - 2.0) < 0.05, f"full path ~2mm, got {cl_full}"
    assert cl_chord < -5.0, f"chord must be caught as gouging, got {cl_chord}"

    # empty / missing mandrel still yields +inf rather than raising
    pg2 = PathGenerator()
    assert pg2.measure_min_clearance([full], PARAMS) == float('inf')
    assert pg.measure_min_clearance([], PARAMS) == float('inf')
    print(f"[OK] measure_min_clearance regression: full={cl_full:.2f} "
          f"chord={cl_chord:.2f} (gouge caught)")


def test_warning_renders_for_the_dialog():
    """The refusal dialog formats i18n strings straight from the warning dicts —
    so every key those strings need must actually be in them, in all 3 languages.
    """
    import i18n

    pts, split = _path_with_split(BumpMgr().get_radius_fast)
    pg = _pg(BumpMgr(), op={"r_tool": 0.0, "type": "roughing", "name": "ROUGH-1",
                            "p2_radius_max_points": 3})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}
    pg.decimate_all_paths(0.5, 0.5, 0.0, params=PARAMS)

    cw = pg.last_point_cap_warnings
    assert cw, "expected a warning to format"

    for key in ("msg_cap_warn_title", "msg_cap_warn_op", "msg_cap_warn_body",
                "scl_cap_warn"):
        assert key in i18n.STRINGS, f"missing i18n key {key}"
        for lang in ("EN", "TR", "ES"):
            assert lang in i18n.STRINGS[key], f"{key} missing {lang}"

    for lang in ("EN", "TR", "ES"):
        line = i18n.STRINGS["msg_cap_warn_op"][lang].format(
            op=cw[0]["op_name"], req=cw[0]["requested"], kept=cw[0]["kept"],
            floor=f"{cw[0]['floor']:.2f}", got=f"{cw[0]['clearance']:.2f}")
        body = i18n.STRINGS["msg_cap_warn_body"][lang].format(n=len(cw), ops=line)
        assert "ROUGH-1" in body and "{" not in body, f"{lang} body malformed: {body}"
        assert "{" not in i18n.STRINGS["scl_cap_warn"][lang].format(n=len(cw))
    print("[OK] warning dicts format cleanly in EN/TR/ES")


if __name__ == "__main__":
    test_thin_evenly()
    test_unset_cap_is_identical()
    test_cap_applied_when_safe()
    test_cap_refused_when_it_gouges()
    test_measure_min_clearance_regression()
    test_warning_renders_for_the_dialog()
    print("\nALL PASS")
