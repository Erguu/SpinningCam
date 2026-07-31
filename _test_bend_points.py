# -*- coding: utf-8 -*-
"""Headless test: cutting/bending explicit START -> END feed line.

Before this change these ops carried only ``z_pos`` (Z of the whole move) and
``plunge_x`` (its END X). The START was hidden — derived as
``plunge_x + abs(retract_x)`` — so the retract field silently decided how far the
tool travelled under feed. Both ends are now typed by the user, and retract does
nothing but retract, exactly like a roughing pass.

Covers: the pure resolver, the legacy fallback (must stay bit-identical), the
migration, the emitted G-code, and the count>1 path/op desync guard.
"""
import numpy as np
from path_generator import PathGenerator, resolve_bend_points
from config_schema import migrate_bend_points


class _StubMgr:
    """Flat cylinder R=50, Z 0..100 — enough for calculate_paths to run."""
    def __init__(self):
        self.props = {"top_z": 100.0, "min_z": 0.0, "max_radius": 50.0}
    def get_radius_fast(self, z): return 50.0
    def get_normal_at_z(self, z): return 1.0, 0.0
    def get_straightened_radius(self, z): return 50.0
    def get_straightened_normal(self, z): return 1.0, 0.0


def _params(ops):
    return {"operations": ops, "retract_x": 50.0, "retract_z": 50.0,
            "home_x": 300.0, "home_z": 150.0, "mandrel_pos_x_offset": 0.0,
            "final_part_thickness_on_mandrel": 2.0, "shell_thickness": 0.0,
            "target_clearance": 2.0, "roller_positive_x_side": True,
            "auto_calculate_paths": False}


def _bend(**extra):
    op = {"type": "bending", "enabled": True, "count": 1, "tool_id": "T0303",
          "r_tool": 0.0, "retract_x": 50.0, "retract_z": 50.0,
          "feed": 50.0, "feed_mode": "mm_min", "speed": 300.0, "speed_mode": "RPM"}
    op.update(extra)
    return op


def _emit(op):
    pg = PathGenerator()
    p = _params([op])
    pg.calculate_paths(p, {}, _StubMgr())
    gc = pg.generate_gcode(params=p)
    return pg.last_calculated_paths[0], gc


# ── 1. Pure resolver ────────────────────────────────────────────────────────
def test_resolver():
    full = {"plunge_start_x": 110.0, "plunge_start_z": 10.0,
            "plunge_end_x": 60.0, "plunge_end_z": 45.0}
    assert resolve_bend_points(full, 50.0) == ((110.0, 10.0), (60.0, 45.0))

    # legacy pair -> old derived start, reproduced exactly
    legacy = {"z_pos": 10.0, "plunge_x": 60.0}
    assert resolve_bend_points(legacy, 50.0) == ((110.0, 10.0), (60.0, 10.0))
    assert resolve_bend_points(legacy, -50.0) == ((110.0, 10.0), (60.0, 10.0))  # abs

    # blank / bad entries fall through to the derived values
    partial = {"plunge_end_x": 60.0, "plunge_end_z": 10.0,
               "plunge_start_x": "", "plunge_start_z": None}
    assert resolve_bend_points(partial, 25.0) == ((85.0, 10.0), (60.0, 10.0))

    # nothing at all -> engine default end X, start one retract out
    assert resolve_bend_points({}, 50.0, 70.0) == ((120.0, 0.0), (70.0, 0.0))
    print("test_resolver PASS")


# ── 2. Retract no longer sets the stroke ────────────────────────────────────
def test_retract_is_only_a_retract():
    geom = dict(plunge_start_x=110.0, plunge_start_z=10.0,
                plunge_end_x=60.0, plunge_end_z=10.0)
    p_a, _ = _emit(_bend(retract_x=50.0, **geom))
    p_b, gc = _emit(_bend(retract_x=10.0, **geom))
    assert np.allclose(p_a, p_b), "retract must not change the feed line"
    assert np.allclose(p_a[0], [110, 0, 10]) and np.allclose(p_a[-1], [60, 0, 10])
    # ...but it still retracts, from the END point, like any roughing pass
    ret = [l for l in gc.splitlines() if "(Retract Op" in l]
    assert ret and "X70.000" in ret[0], ret
    print("test_retract_is_only_a_retract PASS")


# ── 3. Diagonal / axial bend + the op's own feed ────────────────────────────
def test_diagonal_and_feed():
    path, gc = _emit(_bend(plunge_start_x=110.0, plunge_start_z=10.0,
                           plunge_end_x=60.0, plunge_end_z=45.0))
    assert np.allclose(path[-1], [60, 0, 45]), "End Z must be honored"
    g1 = [l for l in gc.splitlines() if l.startswith("G1") and "Op1" in l]
    assert len(g1) == 1 and "F50.000" in g1[0], g1
    g0 = [l for l in gc.splitlines() if l.startswith("G0") and "(Op1" in l]
    assert g0 and "X110.000" in g0[0] and "Z10.000" in g0[0], g0
    print("test_diagonal_and_feed PASS")


# ── 4. Legacy op stays bit-identical to the pre-split engine ────────────────
def test_legacy_unchanged():
    path, _ = _emit(_bend(z_pos=10.0, plunge_x=60.0, retract_x=50.0))
    assert np.allclose(path[0], [110, 0, 10]) and np.allclose(path[-1], [60, 0, 10])
    print("test_legacy_unchanged PASS")


# ── 5. Migration ────────────────────────────────────────────────────────────
def test_migration():
    p = {"retract_x": -10.0, "operations": [
        {"type": "bending", "z_pos": 10.0, "plunge_x": 60.0, "retract_x": 50.0},
        {"type": "cutting", "z_pos": 5.0, "plunge_x": 40.0},   # inherits global
        {"type": "roughing", "start_z": 1.0},                  # untouched
    ]}
    migrate_bend_points(p)
    b, c, r = p["operations"]
    assert (b["plunge_start_x"], b["plunge_start_z"]) == (110.0, 10.0)
    assert (b["plunge_end_x"], b["plunge_end_z"]) == (60.0, 10.0)
    assert c["plunge_start_x"] == 50.0, c   # 40 + abs(-10) from the global
    assert "z_pos" not in b and "plunge_x" not in b, "legacy keys must be dropped"
    assert "plunge_end_x" not in r and r["start_z"] == 1.0, "roughing untouched"

    before = dict(b)
    migrate_bend_points(p)
    assert p["operations"][0] == before, "migration must be idempotent"

    # the migrated op emits exactly what the legacy op emitted
    legacy_path, _ = _emit(_bend(z_pos=10.0, plunge_x=60.0, retract_x=50.0))
    mig_path, _ = _emit(_bend(retract_x=50.0,
                              **{k: v for k, v in before.items()
                                 if k.startswith("plunge_")}))
    assert np.allclose(legacy_path, mig_path)
    print("test_migration PASS")


# ── 6. count>1 must not swallow the next op's path ──────────────────────────
def test_count_desync_guard():
    """calculate_paths emits ONE path per cutting/bending op and ignores count;
    the emitter must too, or a stray count>1 runs the NEXT op's path with this
    op's tool and feed."""
    rough = {"type": "roughing", "enabled": True, "count": 1, "tool_id": "T0101",
             "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0, "p1_x": 40.0,
             "p1_z": 50.0, "p3_x": 40.0, "p3_z": -20.0,
             "pass_shape": "linear_approach"}
    bend = _bend(count=2, plunge_start_x=110.0, plunge_start_z=10.0,
                 plunge_end_x=60.0, plunge_end_z=10.0)
    pg = PathGenerator()
    p = _params([bend, rough])
    pg.calculate_paths(p, {}, _StubMgr())
    assert len(pg.last_calculated_paths) == 2, "one bend path + one rough path"
    gc = pg.generate_gcode(params=p)
    hdrs = [l.strip() for l in gc.splitlines() if l.strip().startswith("(--- OP ")]
    assert len(hdrs) == 2, hdrs
    assert "BENDING - PASO 1" in hdrs[0] and "ROUGHING - PASO 1" in hdrs[1], hdrs
    print("test_count_desync_guard PASS")


if __name__ == "__main__":
    test_resolver()
    test_retract_is_only_a_retract()
    test_diagonal_and_feed()
    test_legacy_unchanged()
    test_migration()
    test_count_desync_guard()
    print("ALL PASS")
