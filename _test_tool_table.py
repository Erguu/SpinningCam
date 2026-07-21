"""Headless tests for the recipe-carried tool table (CAM_TOOL_TABLE_HANDOVER.md).

Proves generate_scl emits the 5 header fields correctly and that validation
blocks the setups the PLC would reject. Run: python _test_tool_table.py
"""
from recipe_to_scl import (GCodeToSCLConverter, normalize_turret,
                           tool_code_from_id)

GCODE = """
G21 G90 G18
M6 T0103 (ROUGHING)
G96 S1000 M3
G0 X100 Z0
G1 X120 Z50 F300
M5
M30
"""


def _gen(turret_slots, auto=True):
    conv = GCodeToSCLConverter()
    conv.parse_gcode(GCODE)
    params = {"turret_slots": turret_slots, "turret_auto_angles": auto}
    return conv.generate_scl(db_name="DB_RecipeProgram1",
                             program_title="SpinningCam Program", params=params)


def test_tool_code_from_id():
    assert tool_code_from_id("T0103") == 103
    assert tool_code_from_id("T0101") == 101
    assert tool_code_from_id("T0202") == 202
    assert tool_code_from_id("") == 0
    print("OK  tool_code_from_id")


def test_normalize_auto_angles():
    slots = [{"code": 101}, {"code": 102}, {"code": 103}, {"code": 0}]
    codes, angles, auto, count = normalize_turret(
        {"turret_slots": slots, "turret_auto_angles": True})
    assert codes == [101, 102, 103, 0], codes
    assert count == 3, count
    assert angles == [0.0, 120.0, 240.0, 0.0], angles
    print("OK  normalize auto angles (3 slots -> 0/120/240)")


def test_worked_example_matches_handover():
    slots = [{"code": 101}, {"code": 102}, {"code": 103}, {"code": 0}]
    scl = _gen(slots, auto=True)
    expected = [
        "Header.ProvidesToolConfig := TRUE;",
        "Header.ToolCount := 3;",
        "Header.AutoCalcAngles := TRUE;",
        "Header.ToolCode_List[1] := 101;",
        "Header.ToolCode_List[2] := 102;",
        "Header.ToolCode_List[3] := 103;",
        "Header.ToolCode_List[4] := 0;",
        "Header.ToolAngle_List[1] := 0.0;",
        "Header.ToolAngle_List[2] := 120.0;",
        "Header.ToolAngle_List[3] := 240.0;",
        "Header.ToolAngle_List[4] := 0.0;",
    ]
    for line in expected:
        assert line in scl, f"missing header line: {line}"
    # Table must sit AFTER MaxZ and BEFORE the recipe lines.
    assert scl.index("Header.MaxZ") < scl.index("ProvidesToolConfig")
    assert scl.index("ProvidesToolConfig") < scl.index("Lines[0]")
    print("OK  worked example matches handover §3")


def test_manual_angles():
    slots = [{"code": 101, "angle": 5.0}, {"code": 102, "angle": 95.0},
             {"code": 103, "angle": 185.0}, {"code": 0, "angle": 0.0}]
    scl = _gen(slots, auto=False)
    assert "Header.AutoCalcAngles := FALSE;" in scl
    assert "Header.ToolAngle_List[1] := 5.0;" in scl
    assert "Header.ToolAngle_List[2] := 95.0;" in scl
    print("OK  manual angles (AutoCalcAngles FALSE uses entered values)")


def test_unmapped_tool_blocks():
    # Program uses 103, but the turret only has 101/102 → must raise.
    slots = [{"code": 101}, {"code": 102}, {"code": 0}, {"code": 0}]
    try:
        _gen(slots, auto=True)
    except ValueError as e:
        assert str(e).startswith("TOOL_TABLE:"), e
        assert "103" in str(e)
        print("OK  unmapped tool code blocks export (TOOL_TABLE error)")
        return
    raise AssertionError("expected ValueError for unmapped tool 103")


def test_empty_turret_blocks():
    slots = [{"code": 0}, {"code": 0}, {"code": 0}, {"code": 0}]
    try:
        _gen(slots, auto=True)
    except ValueError as e:
        assert str(e).startswith("TOOL_TABLE:"), e
        print("OK  empty turret blocks export")
        return
    raise AssertionError("expected ValueError for empty turret")


def test_byte_range_blocks():
    slots = [{"code": 300}, {"code": 0}, {"code": 0}, {"code": 0}]
    try:
        _gen(slots, auto=True)
    except ValueError as e:
        assert "0-255" in str(e), e
        print("OK  out-of-byte-range code blocks export")
        return
    raise AssertionError("expected ValueError for code 300")


if __name__ == "__main__":
    test_tool_code_from_id()
    test_normalize_auto_angles()
    test_worked_example_matches_handover()
    test_manual_angles()
    test_unmapped_tool_blocks()
    test_empty_turret_blocks()
    test_byte_range_blocks()
    print("\nAll tool-table tests passed.")
