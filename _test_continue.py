"""Headless verification for TODO #61 step 2 — Continue-from-previous fill logic."""
from ui.tabs.program_tab import ProgramTab
f = ProgramTab._continue_fill_values

# --- pass-angle op with progressive fan: copy fan END angle + computed end Z/reach ---
prev = {"type": "roughing", "count": 5, "pass_angle": 95.0,
        "progressive_angle_enabled": True, "progressive_angle_end": 101.0,
        "clearance": 2.0, "tool_id": "T0101"}
out = f(prev, prev_end_z=88.0, prev_reach=42.0)
assert out["start_z"] == 88.0, out
assert out["pass_angle"] == 101.0, out           # fan END, not the start angle
assert out["reach"] == 42.0, out
assert out["clearance"] == 2.0, out
assert "tool_id" not in out                        # tool deliberately not copied
print("pass-angle + progressive: copies fan-end angle, computed end Z/reach: OK")

# --- pass-angle, no progressive: copy the single pass_angle ---
prev2 = {"type": "roughing", "count": 3, "pass_angle": 120.0, "clearance": 1.5}
out2 = f(prev2, 60.0, 30.0)
assert out2["pass_angle"] == 120.0 and out2["start_z"] == 60.0 and out2["reach"] == 30.0
print("pass-angle no fan: copies pass_angle: OK")

# --- raw mode (no pass_angle): copy p3_x/p3_z direction ---
prev3 = {"type": "roughing", "count": 1, "p3_x": 20.0, "p3_z": -15.0, "clearance": 3.0}
out3 = f(prev3, 50.0, 25.0)
assert "pass_angle" not in out3
assert out3["p3_x"] == 20.0 and out3["p3_z"] == -15.0
assert out3["reach"] == 25.0
print("raw mode: copies p3_x/p3_z direction: OK")

# --- fallback when nothing computed yet: use previous op's params ---
prev4 = {"type": "roughing", "count": 1, "pass_angle": 100.0, "end_z": 70.0,
         "reach": 18.0, "clearance": 2.0}
out4 = f(prev4, prev_end_z=None, prev_reach=None)
assert out4["start_z"] == 70.0 and out4["reach"] == 18.0 and out4["pass_angle"] == 100.0
print("uncalculated fallback: uses previous op's params: OK")

print("ALL CONTINUE TESTS PASSED")
