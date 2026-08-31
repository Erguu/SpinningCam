"""Warn when an operation would command the spindle to zero RPM (2026-08-31).

Found in the field: DB_RecipeProgram2.scl shipped four operations at RPM=0.0 —
two cutting passes, a roughing pass and a bend. CMD=20 sets the speed TARGET and
Param = rpm // 10, so Param=0 means "run at zero RPM", not "no speed given": the
spindle is commanded to stop and stays stopped for that whole operation.

A WARNING, not a block (user decision) — the operator is told which operations
and decides.

Run: pyrun.bat _test_zero_spindle_warning.py   (conda env spinning_cam)
"""
import sys

from path_generator import zero_spindle_ops
import recipe_to_scl as R

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        fails.append(name)


def op(speed, **kw):
    d = {"type": "roughing", "enabled": True, "speed": speed}
    d.update(kw)
    return d


print("1) what counts as zero")
check("a healthy program warns about nothing",
      zero_spindle_ops({"operations": [op(800), op(600)]}) == [])
check("speed 0 is caught",
      [b["index"] for b in zero_spindle_ops({"operations": [op(800), op(0)]})] == [1])
check("0.0 float is caught",
      len(zero_spindle_ops({"operations": [op(0.0)]})) == 1)
# rpm // 10 == 0 for anything under 10, so testing == 0 alone would miss these.
for rpm in (1, 5, 9, 9.9):
    check(f"{rpm} RPM also encodes to Param 0 and is caught",
          len(zero_spindle_ops({"operations": [op(rpm)]})) == 1)
check("10 RPM is NOT flagged (encodes to Param 1)",
      zero_spindle_ops({"operations": [op(10)]}) == [])
check("negative is caught too", len(zero_spindle_ops({"operations": [op(-5)]})) == 1)

print("2) that threshold matches what the converter actually encodes")
conv = R.GCodeToSCLConverter()
for rpm in (0, 1, 5, 9):
    check(f"{rpm} RPM -> Param 0 in the converter",
          conv._encode_spindle_speed(int(rpm)) == 0)
check("10 RPM -> Param 1", conv._encode_spindle_speed(10) == 1)

print("3) scope")
check("a DISABLED zero-speed op is not reported",
      zero_spindle_ops({"operations": [op(0, enabled=False)]}) == [])
check("a missing speed key falls back to the global, not zero",
      zero_spindle_ops({"operations": [{"type": "roughing", "enabled": True}],
                        "surface_speed_m_min": 200}) == [])
check("a missing speed with NO global still uses the 200 default",
      zero_spindle_ops({"operations": [{"type": "roughing", "enabled": True}]}) == [])
check("a non-numeric speed is left to another check, not crashed on",
      zero_spindle_ops({"operations": [op("fast")]}) == [])
check("empty / None params safe",
      zero_spindle_ops({}) == [] and zero_spindle_ops(None) == [])

print("4) what the operator is told")
rows = zero_spindle_ops({"operations": [
    op(800),
    op(0, type="cutting"),
    op(0, type="bending", name="Flange bend"),
]})
check("two rows", len(rows) == 2, str(len(rows)))
check("index is the position in the FULL op list (1-based on screen)",
      [r["index"] for r in rows] == [1, 2], str([r["index"] for r in rows]))
check("an unnamed op falls back to its type", rows[0]["name"] == "CUTTING",
      rows[0]["name"])
check("a named op shows its name", rows[1]["name"] == "Flange bend", rows[1]["name"])
check("the speed is carried for the message", rows[0]["rpm"] == 0)

print("5) the check is read-only")
params = {"operations": [op(0), op(800)]}
before = repr(params)
zero_spindle_ops(params)
check("params untouched", repr(params) == before)

print("6) the real recipe2 case reproduces")
# Its header: Op3 CUTTING 0, Op5 CUTTING 0, Op6 ROUGHING 0, Op7 BENDING 0.
recipe2 = {"operations": [
    op(600), op(600), op(0, type="cutting"), op(600),
    op(0, type="cutting"), op(0), op(0, type="bending")]}
found = zero_spindle_ops(recipe2)
check("all four are reported", len(found) == 4, str(len(found)))
check("and they are ops 3, 5, 6, 7 on screen",
      [f["index"] + 1 for f in found] == [3, 5, 6, 7],
      str([f["index"] + 1 for f in found]))

print()
if fails:
    print(f"FAILED: {len(fails)} -> {fails}")
    sys.exit(1)
print("ALL PASS")
