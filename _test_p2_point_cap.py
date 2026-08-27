"""
Headless tests for the two per-op point caps: TODO #99 on the P2 fillet
(`p2_radius_max_points`) and TODO #101 on the exit leg (`exit_max_points`).

Covers:
  1. _thin_evenly: caps the count, keeps both endpoints, spaces by ARC LENGTH.
  2. Unset cap  == byte-identical to today's decimation (the back-compat proof).
  3. Cap APPLIED when it costs no clearance.
  4. Cap REFUSED when it would cut the corner — uncapped path kept + warning raised.
  5. measure_min_clearance still behaves after being refactored onto
     _path_min_clearance (regression on the auto-tune guard).
  6. #101 the same four for the exit leg, plus: the caps are gated INDEPENDENTLY,
     the gate baseline is the UNCAPPED decimation (not full resolution), and a
     hand-drawn #100 tail is never thinned.
  7. #101 END-TO-END through calculate_paths on a real bowed pass — everything
     above builds synthetic paths by hand, which cannot catch the wiring between
     the op key, the split indices and the decimator.

Run inside the `spinning_cam` conda env (path_generator pulls pythonocc):
    conda run -n spinning_cam python _test_p2_point_cap.py
"""
import math
import numpy as np

from mandrel_analyzer import MandrelManager
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

    for key in ("msg_cap_sec_fillet", "msg_cap_sec_exit"):
        assert key in i18n.STRINGS, f"missing i18n key {key}"
        for lang in ("EN", "TR", "ES"):
            assert lang in i18n.STRINGS[key], f"{key} missing {lang}"

    for lang in ("EN", "TR", "ES"):
        line = i18n.STRINGS["msg_cap_warn_op"][lang].format(
            op=cw[0]["op_name"],
            sec=i18n.STRINGS["msg_cap_sec_" + cw[0]["section"]][lang],
            req=cw[0]["requested"], kept=cw[0]["kept"],
            floor=f"{cw[0]['floor']:.2f}", got=f"{cw[0]['clearance']:.2f}")
        body = i18n.STRINGS["msg_cap_warn_body"][lang].format(n=len(cw), ops=line)
        assert "ROUGH-1" in body and "{" not in body, f"{lang} body malformed: {body}"
        assert "{" not in i18n.STRINGS["scl_cap_warn"][lang].format(n=len(cw))
    print("[OK] warning dicts format cleanly in EN/TR/ES")


# --------------------------------------------------------------------------
# #101 — the exit-leg twin of the cap (user 2026-08-27, D21-D23)
# --------------------------------------------------------------------------
def _path_with_exit(radius_fn, n_exit=41):
    """[approach] + [short fillet] + [dense EXIT curve], plus its (T1, T2) split.

    Mirror of _path_with_split with the density moved to the exit leg, which is
    where exit_bow / exit_arc_angle / exit_mid all land.
    """
    app = [[102.0, 0.0, -5.0]]
    fil = [[102.0, 0.0, -2.0], [102.0, 0.0, 0.0]]
    ext = [[radius_fn(z) + 2.0, 0.0, z] for z in np.linspace(0.0, 10.0, n_exit)][1:]
    pts = np.array(app + fil + ext, dtype=float)
    t1 = len(app)
    t2 = len(app) + len(fil) - 1
    return pts, (t1, t2)


def test_exit_cap_unset_is_identical():
    pts, split = _path_with_exit(FlatMgr().get_radius_fast)
    pg = _pg(FlatMgr())
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    old = pg.decimate_all_paths(0.5, 0.5, 0.0)
    new = pg.decimate_all_paths(0.5, 0.5, 0.0, params=PARAMS)
    assert np.array_equal(old[0], new[0]), "unset exit cap must be byte-identical"
    assert pg.last_point_cap_warnings == []
    print(f"[OK] #101 unset exit cap byte-identical ({len(old[0])} pts)")


def test_exit_cap_applied_when_safe():
    # Exit bulges AWAY from the part, so chords across it cost no clearance.
    pts, split = _path_with_exit(
        lambda z: 100.0 + 8.0 * math.sin(math.pi * z / 10.0), n_exit=61)
    pg = _pg(FlatMgr(), op={"r_tool": 0.0, "type": "roughing", "exit_max_points": 4})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    plain = pg.decimate_all_paths(0.02, 0.02, 0.0)
    capped = pg.decimate_all_paths(0.02, 0.02, 0.0, params=PARAMS)

    assert len(plain[0]) > 10, f"setup: exit should survive RDP densely ({len(plain[0])})"
    assert len(capped[0]) < len(plain[0]) - 5, (
        f"exit cap should cut hard: {len(plain[0])} -> {len(capped[0])}")
    assert pg.last_point_cap_warnings == [], "a safe exit cap must not warn"
    print(f"[OK] #101 exit cap applied: {len(plain[0])} -> {len(capped[0])} pts")


def test_exit_cap_refused_when_it_gouges():
    pts, split = _path_with_exit(BumpMgr().get_radius_fast)
    pg = _pg(BumpMgr(), op={"r_tool": 0.0, "type": "roughing", "name": "ROUGH-X",
                            "exit_max_points": 3})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    plain = pg.decimate_all_paths(0.5, 0.5, 0.0)
    out = pg.decimate_all_paths(0.5, 0.5, 0.0, params=PARAMS)

    assert np.array_equal(out[0], plain[0]), "an unsafe exit cap must fall back"
    assert len(pg.last_point_cap_warnings) == 1, pg.last_point_cap_warnings
    w = pg.last_point_cap_warnings[0]
    assert w["section"] == "exit", f"the warning must name the exit leg, got {w}"
    assert w["requested"] == 3 and w["op_name"] == "ROUGH-X"
    print(f"[OK] #101 exit cap refused, reported as '{w['section']}' "
          f"({w['floor']:.2f} -> {w['clearance']:.2f} mm)")


def test_caps_are_gated_independently():
    """A refused fillet cap must not throw away a safe exit cap (D23).

    Dense CURVED fillet hugging the bump (thinning it gouges) + dense exit that
    bulges away from the part (thinning it is free). One must be refused and the
    other applied, in the same pass.
    """
    app = [[102.0, 0.0, -5.0]]
    fil = [[BumpMgr().get_radius_fast(z) + 2.0, 0.0, z]
           for z in np.linspace(0.0, 10.0, 31)]
    ext = [[120.0 + 6.0 * math.sin(math.pi * (z - 10.0) / 10.0), 0.0, z]
           for z in np.linspace(10.0, 20.0, 41)][1:]
    pts = np.array(app + fil + ext, dtype=float)
    split = (len(app), len(app) + len(fil) - 1)

    pg = _pg(BumpMgr(), op={"r_tool": 0.0, "type": "roughing", "name": "BOTH",
                            "p2_radius_max_points": 3, "exit_max_points": 4})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    # Ordinary tolerance on purpose. RDP chords the curved fillet and gives up a
    # little clearance by itself; the gate must charge that to RDP, not to the
    # exit cap. Measuring against the full-resolution path instead of the
    # uncapped decimation used to veto BOTH caps here.
    plain = pg.decimate_all_paths(0.05, 0.05, 0.0)
    out = pg.decimate_all_paths(0.05, 0.05, 0.0, params=PARAMS)

    secs = [w["section"] for w in pg.last_point_cap_warnings]
    assert secs == ["fillet"], f"only the fillet cap should be refused, got {secs}"
    assert len(out[0]) < len(plain[0]), (
        f"the SAFE exit cap must still have been applied: "
        f"{len(plain[0])} -> {len(out[0])}")
    # The invariant: never worse than the program that ships with no cap at all.
    floor = pg._path_min_clearance(plain[0], pg._path_op_map[0], PARAMS)
    got = pg._path_min_clearance(out[0], pg._path_op_map[0], PARAMS)
    assert got >= floor - 1e-6, f"clearance dropped {floor:.3f} -> {got:.3f}"
    print(f"[OK] #101 caps gated independently: fillet refused, exit applied "
          f"({len(plain[0])} -> {len(out[0])} pts, clearance held at {got:.2f} mm)")


def test_gate_baseline_is_the_uncapped_decimation():
    """A cap that costs NOTHING must not be refused for RDP's own loss.

    The metric spans the whole path, so before this was fixed a curved fillet
    that RDP chorded would veto a cap on the EXIT leg that cost zero clearance —
    measured: capped 1.9955 vs uncapped 1.9955, refused because full resolution
    was 2.0000. Pins the baseline so that cannot come back.
    """
    app = [[102.0, 0.0, -5.0]]
    fil = [[BumpMgr().get_radius_fast(z) + 2.0, 0.0, z]      # RDP loses a little here
           for z in np.linspace(0.0, 10.0, 31)]
    ext = [[120.0 + 6.0 * math.sin(math.pi * (z - 10.0) / 10.0), 0.0, z]
           for z in np.linspace(10.0, 20.0, 41)][1:]         # bulges away: cap is free
    pts = np.array(app + fil + ext, dtype=float)
    split = (len(app), len(app) + len(fil) - 1)

    pg = _pg(BumpMgr(), op={"r_tool": 0.0, "type": "roughing", "name": "FREE",
                            "exit_max_points": 4})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}

    plain = pg.decimate_all_paths(0.05, 0.05, 0.0)
    out = pg.decimate_all_paths(0.05, 0.05, 0.0, params=PARAMS)

    full_c = pg._path_min_clearance(pts, pg._path_op_map[0], PARAMS)
    plain_c = pg._path_min_clearance(plain[0], pg._path_op_map[0], PARAMS)
    out_c = pg._path_min_clearance(out[0], pg._path_op_map[0], PARAMS)

    assert plain_c < full_c - 1e-9, (
        f"setup: RDP must lose a little on its own ({full_c:.4f} -> {plain_c:.4f})")
    assert abs(out_c - plain_c) < 1e-9, (
        f"setup: this cap should cost nothing ({plain_c:.4f} -> {out_c:.4f})")
    assert len(out[0]) < len(plain[0]), (
        f"a free cap must be APPLIED: {len(plain[0])} -> {len(out[0])}")
    assert pg.last_point_cap_warnings == [], (
        f"a free cap must not warn, got {pg.last_point_cap_warnings}")
    print(f"[OK] #101 gate baseline: free cap applied "
          f"({len(plain[0])} -> {len(out[0])} pts; RDP alone cost "
          f"{full_c - plain_c:.4f} mm and was NOT charged to the cap)")


def test_exit_cap_never_touches_a_hand_drawn_tail():
    """D22: a #100 tail is the operator's own points — the cap must skip it."""
    pts, split = _path_with_exit(
        lambda z: 100.0 + 8.0 * math.sin(math.pi * z / 10.0), n_exit=61)
    pg = _pg(FlatMgr(), op={"r_tool": 0.0, "type": "roughing", "exit_max_points": 3})
    pg.last_calculated_paths = [pts]
    pg.last_render_split_idx = {0: split}
    pg.last_exit_verbatim = {0}          # this pass carries a hand-drawn tail

    plain = pg.decimate_all_paths(0.02, 0.02, 0.0)
    out = pg.decimate_all_paths(0.02, 0.02, 0.0, params=PARAMS)

    n_exit_kept = len(out[0]) - split[1]
    assert n_exit_kept == len(pts) - split[1], (
        f"a hand-drawn tail must survive whole: kept {n_exit_kept} of "
        f"{len(pts) - split[1]}")
    assert pg.last_point_cap_warnings == [], "skipping a tail is not a refusal"
    print(f"[OK] #101 exit cap skips a hand-drawn tail ({n_exit_kept} points intact)")


def test_exit_cap_end_to_end_on_a_real_bow():
    """The wiring, on a genuinely generated pass rather than a hand-built array.

    Everything above constructs its own arrays and split indices, so none of it
    would notice if the op key never reached the decimator, or if the split
    indices pointed at the wrong section on a real path.
    """
    mgr = MandrelManager(); mgr.create_default_cone()
    mgr.update_geometry(0, 0, 0, 0.0, 0.0)

    def run(cap, bow=14.0):
        op = {"type": "roughing", "count": 3, "start_z": 20.0, "end_z": 60.0,
              "r_tool": 25.0, "clearance": 2.0, "p1_x": 40.0, "p1_z": 12.0,
              "p3_x": 40.0, "p3_z": -30.0, "pass_shape": "linear_approach",
              "direction": "forward", "p2_radius": 6.0, "exit_bow": bow,
              "name": "ROUGH"}
        if cap:
            op["exit_max_points"] = cap
        p = {"operations": [op], "auto_calc_angle": False, "min_safety_gap": 0.0,
             "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
             "collision_resolution": 0.5, "gcode_resolution": 2.0,
             "mandrel_pos_x_offset": 0.0, "plc_mode": True}
        pg = PathGenerator()
        pg.calculate_paths(p, {}, mgr)
        capped = pg.decimate_all_paths(0.5, 0.5, 0.0, params=p)
        plain = pg.decimate_all_paths(0.5, 0.5, 0.0)
        return (sum(len(d) for d in capped), sum(len(d) for d in plain),
                min(pg._path_min_clearance(d, op, p) for d in capped),
                min(pg._path_min_clearance(d, op, p) for d in plain),
                list(pg.last_point_cap_warnings))

    base, base_plain, _, _, w0 = run(0)
    assert base == base_plain and not w0, "unset cap must change nothing end-to-end"

    counts = []
    for cap in (8, 6, 4, 3, 2):
        tot, plain, clr, clr_plain, warns = run(cap)
        assert tot <= plain, f"cap {cap} increased the point count: {plain} -> {tot}"
        assert clr >= clr_plain - 1e-6, (
            f"cap {cap} cost clearance: {clr_plain:.4f} -> {clr:.4f}")
        counts.append(tot)

    assert counts == sorted(counts, reverse=True), (
        f"tightening the cap must not increase points: {counts}")
    assert counts[-1] < base, f"the cap never bit: {base} -> {counts}"

    # a STRAIGHT exit has nothing to thin — the cap must be a no-op there
    s_cap, s_plain, _, _, s_w = run(3, bow=0.0)
    assert s_cap == s_plain and not s_w, (
        f"a straight exit must be untouched by the cap ({s_plain} -> {s_cap})")
    print(f"[OK] #101 end-to-end on a real bow: {base} pts uncapped -> {counts} "
          f"for caps 8/6/4/3/2, clearance never worse, straight exit untouched")


if __name__ == "__main__":
    test_thin_evenly()
    test_unset_cap_is_identical()
    test_cap_applied_when_safe()
    test_cap_refused_when_it_gouges()
    test_measure_min_clearance_regression()
    test_warning_renders_for_the_dialog()
    test_exit_cap_unset_is_identical()
    test_exit_cap_applied_when_safe()
    test_exit_cap_refused_when_it_gouges()
    test_caps_are_gated_independently()
    test_gate_baseline_is_the_uncapped_decimation()
    test_exit_cap_never_touches_a_hand_drawn_tail()
    test_exit_cap_end_to_end_on_a_real_bow()
    print("\nALL PASS")
