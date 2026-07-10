"""Headless verification for #85 — Unite operations (inverse of Split #64).

Proves that:
  * split -> merge is a round-trip: uniting the chunks of a Split reproduces
    byte-identical forming toolpaths to the original single op (only inter-op
    rapids differ, which are not compared), and _merge_is_exact reports True.
  * genuinely different (non-colinear) ops are detected as NOT exact, so the UI
    would warn before merging.
  * a pinned pass (pass_edits) survives split -> merge on the SAME physical pass.
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


def roundtrip(op, sizes, label):
    """Split op into chunks, merge them back, assert exact reproduction."""
    chunks = ProgramTab._split_op(op, sizes, top_z)
    merged = ProgramTab._merge_ops(chunks, top_z)
    assert merged["count"] == op["count"], (merged["count"], op["count"])
    assert ProgramTab._merge_is_exact(chunks, merged, top_z), \
        f"{label}: merge of clean chunks should be EXACT"
    orig = paths([op])
    remerged = paths([merged])
    assert len(orig) == len(remerged) == op["count"], (len(orig), len(remerged), op["count"])
    for k, (a, b) in enumerate(zip(orig, remerged)):
        assert a.shape == b.shape and np.allclose(a, b, atol=1e-6), \
            f"{label}: pass {k} differs\n{a[0]} {a[-1]}\n{b[0]} {b[-1]}"
    print(f"{label}: {op['count']} passes split {sizes} -> united EXACTLY: OK")


# --- 1. round-trip on the split test's own op zoo ------------------------------
op1 = {"type": "roughing", "count": 20, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 10, "end_z": min_z + 60, "pass_angle": 90.0,
       "progressive_angle_enabled": True, "progressive_angle_end": 180.0,
       "reach": 30.0, "progressive_reach_enabled": True, "progressive_reach_end": 50.0}
roundtrip(op1, [1, 1, 5, 5, 4, 2, 2], "prog angle + prog reach")
roundtrip(op1, [10, 10], "prog angle + prog reach (halves)")

op2 = {"type": "roughing", "count": 10, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 10, "end_z": min_z + 55, "pass_angle": 120.0, "reach": 28.0}
roundtrip(op2, [3, 3, 4], "constant angle + reach")

op3 = {"type": "roughing", "count": 8, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.5,
       "start_z": min_z + 12, "end_z": min_z + 52, "p3_x": 20.0, "p3_z": -15.0}
roundtrip(op3, [2, 3, 3], "raw p3 mode")

op4 = {"type": "roughing", "count": 6, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 10, "pass_angle": 100.0,
       "progressive_angle_enabled": True, "progressive_angle_end": 160.0}
roundtrip(op4, [2, 2, 2], "open-ended (end_z=None)")


# --- 2. merging MANY separately-split ops back into one ------------------------
# Split op1 into 3 chunks, unite all 3 at once -> exact.
chunks = ProgramTab._split_op(op1, [7, 7, 6], top_z)
merged_all = ProgramTab._merge_ops(chunks, top_z)
assert ProgramTab._merge_is_exact(chunks, merged_all, top_z)
assert merged_all["count"] == 20
o = paths([op1]); m = paths([merged_all])
for a, b in zip(o, m):
    assert np.allclose(a, b, atol=1e-6)
print("unite 3 chunks at once -> EXACT: OK")


# --- 3. genuinely different ops are NOT exact (UI would warn) ------------------
# Two ops whose angle progression does not lie on one straight line.
d1 = {"type": "roughing", "count": 4, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
      "start_z": min_z + 10, "end_z": min_z + 30, "pass_angle": 90.0}
d2 = {"type": "roughing", "count": 4, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
      "start_z": min_z + 30, "end_z": min_z + 50, "pass_angle": 150.0}
dmerged = ProgramTab._merge_ops([d1, d2], top_z)
assert not ProgramTab._merge_is_exact([d1, d2], dmerged, top_z), \
    "non-colinear angle ops should be flagged approximate"
assert dmerged["count"] == 8 and dmerged["start_z"] == d1["start_z"]
print("different ops flagged APPROXIMATE (warn): OK")

# Different structural field (clearance) also breaks exactness.
s1 = dict(d1); s2 = dict(d1); s2["clearance"] = 3.5; s2["start_z"] = d1["end_z"]
smerged = ProgramTab._merge_ops([s1, s2], top_z)
assert not ProgramTab._merge_is_exact([s1, s2], smerged, top_z), \
    "differing structural field should break exactness"
print("differing structural field -> APPROXIMATE: OK")


# --- 4. pass_edits (pins) survive split -> merge on the same physical pass -----
op_pin = dict(op2)
op_pin["pass_edits"] = {"5": {"reach": 99.0}}   # pin on global pass index 5
chunks_p = ProgramTab._split_op(op_pin, [3, 3, 4], top_z)
# the pin should land in the 2nd chunk (passes 3..5) at chunk-local index 2
assert chunks_p[1].get("pass_edits") == {"2": {"reach": 99.0}}, chunks_p[1].get("pass_edits")
merged_p = ProgramTab._merge_ops(chunks_p, top_z)
assert merged_p.get("pass_edits") == {"5": {"reach": 99.0}}, merged_p.get("pass_edits")
print("pass_edits pin survives split -> merge on same pass (5): OK")


# --- 5. non-adjacent picks: merging chunks with a gap is flagged approximate --
# Split op1 into [7, 7, 6]; uniting only chunk 0 and chunk 2 skips chunk 1's
# passes, so the union cannot reproduce them -> _merge_is_exact must be False
# (the UI additionally warns because ops would be relocated).
c0, c1, c2 = ProgramTab._split_op(op1, [7, 7, 6], top_z)
gap_merge = ProgramTab._merge_ops([c0, c2], top_z)
assert gap_merge["count"] == 13
assert not ProgramTab._merge_is_exact([c0, c2], gap_merge, top_z), \
    "non-adjacent chunk merge (skipping a chunk) should be approximate"
# but two ADJACENT chunks of the same split still merge exactly
adj_merge = ProgramTab._merge_ops([c0, c1], top_z)
assert ProgramTab._merge_is_exact([c0, c1], adj_merge, top_z), \
    "two adjacent chunks should still merge exactly"
print("non-adjacent picks flagged approximate; adjacent stay exact: OK")


# --- 6. conflict resolver: detection + apply ----------------------------------
class _FakeTab:
    """Minimal stand-in exposing the ProgramTab conflict helpers as bound methods
    (they only need _param_label, which we stub)."""
    _param_label = staticmethod(lambda k: k)
    _pass_series = staticmethod(ProgramTab._pass_series)
    _unite_conflicts = ProgramTab._unite_conflicts
    _apply_unite_choices = staticmethod(ProgramTab._apply_unite_choices)


tab = _FakeTab()

# clearance + pass_angle differ, contiguous in Z (start/end line up) -> conflicts
# on clearance and pass_angle, but NOT on Z.
g1 = {"type": "roughing", "count": 4, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
      "start_z": min_z + 10, "end_z": min_z + 30, "pass_angle": 90.0, "reach": 28.0}
g2 = {"type": "roughing", "count": 4, "tool_id": "T0101", "r_tool": 30.0, "clearance": 3.5,
      "start_z": min_z + 30, "end_z": min_z + 50, "pass_angle": 150.0, "reach": 28.0}
gm = ProgramTab._merge_ops([g1, g2], top_z)
conf = tab._unite_conflicts([g1, g2], gm, top_z)
keys = {c["key"] for c in conf}
assert "clearance" in keys, keys
assert "pass_angle" in keys, keys
assert "reach" not in keys, "reach is identical -> should NOT be a conflict"
assert "start_z" not in keys and "end_z" not in keys, "Z is continuous -> no Z conflict"
print("conflict detection (clearance + angle, no reach/Z): OK")

# default choice (index 0) reproduces _merge_ops exactly (a no-op)
default_choices = {c["key"]: 0 for c in conf}
fin_default = tab._apply_unite_choices(gm, conf, default_choices)
assert fin_default["clearance"] == gm["clearance"], (fin_default["clearance"], gm["clearance"])
assert abs(fin_default["pass_angle"] - gm["pass_angle"]) < 1e-9
print("default resolver choice == merge default (no-op): OK")

# pick "Last (3.5)" for clearance -> the clearance option whose patch sets 3.5
cl_conf = next(c for c in conf if c["key"] == "clearance")
last_idx = next(i for i, o in enumerate(cl_conf["options"]) if abs(o["patch"]["clearance"] - 3.5) < 1e-9)
fin = tab._apply_unite_choices(gm, conf, {"clearance": last_idx})
assert abs(fin["clearance"] - 3.5) < 1e-9, fin["clearance"]
print("operator override (clearance -> Last 3.5) applied: OK")

# pick a CONSTANT pass_angle (First) -> progressive disabled, angle == first value
pa_conf = next(c for c in conf if c["key"] == "pass_angle")
const_idx = next(i for i, o in enumerate(pa_conf["options"])
                 if o["patch"].get("progressive_angle_enabled") is False
                 and abs(o["patch"]["pass_angle"] - 90.0) < 1e-9)
fin2 = tab._apply_unite_choices(gm, conf, {"pass_angle": const_idx})
assert fin2["progressive_angle_enabled"] is False and abs(fin2["pass_angle"] - 90.0) < 1e-9
print("operator override (pass_angle -> constant First) applied: OK")

# out-of-order Z picks (list order reversed vs Z) DO surface Z conflicts so the
# operator can pull the true extent back with Min/Max. Here the first pick starts
# HIGHER than the last pick, so the naive first-start -> last-end span is degenerate.
o_a = {"type": "roughing", "count": 3, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 30, "end_z": min_z + 50, "pass_angle": 90.0}
o_b = {"type": "roughing", "count": 3, "tool_id": "T0101", "r_tool": 30.0, "clearance": 2.0,
       "start_z": min_z + 10, "end_z": min_z + 30, "pass_angle": 90.0}
om = ProgramTab._merge_ops([o_a, o_b], top_z)
oconf = tab._unite_conflicts([o_a, o_b], om, top_z)
assert any(c["key"] == "start_z" for c in oconf), "out-of-order Z should surface start_z"
assert any(c["key"] == "end_z" for c in oconf), "out-of-order Z should surface end_z"
sc = next(c for c in oconf if c["key"] == "start_z")
assert any(abs(o["patch"]["start_z"] - (min_z + 10)) < 1e-6 for o in sc["options"]), \
    "start_z options should include the true minimum"
print("out-of-order Z surfaces start_z/end_z with Min/Max: OK")

# forward-adjacent ops (different pass counts, endpoints line up) -> NO Z conflict
# even though the merged op redistributes passes.
assert not any(c["key"] in ("start_z", "end_z") for c in conf), \
    "forward-adjacent picks should not surface a Z endpoint conflict"
print("forward-adjacent picks -> no Z endpoint conflict: OK")

# clean split chunks produce NO conflicts (silent path)
c0b, c1b = ProgramTab._split_op(op2, [5, 5], top_z)
mb = ProgramTab._merge_ops([c0b, c1b], top_z)
assert tab._unite_conflicts([c0b, c1b], mb, top_z) == [], "clean split must have no conflicts"
print("clean split chunks -> zero conflicts (silent): OK")

print("ALL UNITE TESTS PASSED")
