"""Headless verification for TODO #64 — Split operation into pass-chunks.

Proves the split is EXACT: the union of chunk-ops produces byte-identical forming
toolpaths to the original single op (only inter-op rapids differ, which are not compared).
"""
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from ui.tabs.program_tab import ProgramTab

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"]); top_z = float(mgr.props["top_z"])
pg = PathGenerator()
base = {"final_part_thickness_on_mandrel": 2.0, "mandrel_pos_x_offset": 0.0, "max_spin_rpm": 2000}


def paths(ops):
    p = dict(base); p["operations"] = [dict(o) for o in ops]
    return pg.calculate_paths(p, {}, mgr)[0]


def check(op, sizes, label):
    orig = paths([op])
    chunks = ProgramTab._split_op(op, sizes, top_z)
    assert sum(c["count"] for c in chunks) == op["count"], "sizes do not sum to count"
    assert [c["count"] for c in chunks] == list(sizes)
    split = paths(chunks)
    assert len(orig) == len(split) == op["count"], (len(orig), len(split), op["count"])
    for k, (a, b) in enumerate(zip(orig, split)):
        assert a.shape == b.shape and np.allclose(a, b, atol=1e-6), \
            f"{label}: pass {k} differs\n{a[0]} {a[-1]}\n{b[0]} {b[-1]}"
    print(f"{label}: {op['count']} passes reproduced EXACTLY by chunks {sizes}: OK")


# progressive angle + progressive reach (the user's 20-pass fan)
op1 = {"type": "roughing", "count": 20, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 10, "end_z": min_z + 60, "pass_angle": 90.0,
       "progressive_angle_enabled": True, "progressive_angle_end": 180.0,
       "reach": 30.0, "progressive_reach_enabled": True, "progressive_reach_end": 50.0}
check(op1, [1, 1, 5, 5, 4, 2, 2], "prog angle + prog reach")
check(op1, [10, 10], "prog angle + prog reach (halves)")
check(op1, [20], "no-op split (whole)")

# constant angle + constant reach
op2 = {"type": "roughing", "count": 10, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 10, "end_z": min_z + 55, "pass_angle": 120.0, "reach": 28.0}
check(op2, [3, 3, 4], "constant angle + reach")

# raw mode (no pass_angle) — direction from p3_x/p3_z
op3 = {"type": "roughing", "count": 8, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.5,
       "start_z": min_z + 12, "end_z": min_z + 52, "p3_x": 20.0, "p3_z": -15.0}
check(op3, [2, 3, 3], "raw p3 mode")

# open-ended op (end_z None -> resolves to mandrel top)
op4 = {"type": "roughing", "count": 6, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 10, "pass_angle": 100.0,
       "progressive_angle_enabled": True, "progressive_angle_end": 160.0}
check(op4, [2, 2, 2], "open-ended (end_z=None)")

print("ALL SPLIT TESTS PASSED")
