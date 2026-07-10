import os, json, tempfile, shutil
from tool_step_loader import ToolStepLoader, _resolve_step_path
import tool_library_io as tio

BASE = os.path.dirname(os.path.abspath(__file__))
tools = json.load(open(os.path.join(BASE, "tools.json"), encoding="utf-8"))

# 1) convention resolution finds tool_geometry/<id>.STEP for each migrated tool
for tl in tools:
    p = _resolve_step_path(tl, BASE)
    assert p and os.path.isfile(p), f"resolve failed for {tl['id']}: {p!r}"
    assert os.path.basename(p) == tl["id"] + ".STEP", p
print("1 convention resolution: OK", [tl["id"] for tl in tools])

# 2) convention wins even if step_file is a bogus absolute path
bogus = dict(tools[0]); bogus["step_file"] = "Z:/nope/gone.STEP"
p = _resolve_step_path(bogus, BASE)
assert p and os.path.basename(p) == tools[0]["id"] + ".STEP", p
print("2 convention beats stale absolute path: OK")

# 3) export -> import round trip in a temp base
with tempfile.TemporaryDirectory() as tmp:
    zpath = os.path.join(tmp, "bundle.zip")
    n, g = tio.export_library(BASE, tools, zpath)
    assert n == len(tools) and g >= 1, (n, g)
    imported = tio.import_library(tmp, zpath)
    assert len(imported) == len(tools)
    for tl in imported:
        gp = tio.find_geometry_file(tmp, tl["id"])
        assert gp and os.path.isfile(gp), tl["id"]
        assert tl["step_file"] == f"tool_geometry/{tl['id']}.STEP", tl["step_file"]
    print(f"3 export/import round trip: OK ({n} tools, {g} geom)")

# 4) sync: external browse copy + id rename
with tempfile.TemporaryDirectory() as tmp:
    src = os.path.join(tmp, "some external tool.STEP")
    shutil.copyfile(_resolve_step_path(tools[0], BASE), src)
    tool = {"id": "T9001", "step_file": src}
    note = tio.sync_tool_geometry(tmp, tool)
    assert tool["step_file"] == "tool_geometry/T9001.STEP", tool["step_file"]
    assert tio.find_geometry_file(tmp, "T9001"), "copy missing"
    # rename id -> T9002
    tool2 = dict(tool); tool2["id"] = "T9002"
    tio.sync_tool_geometry(tmp, tool2, old_id="T9001")
    assert tio.find_geometry_file(tmp, "T9002"), "rename missing"
    assert not tio.find_geometry_file(tmp, "T9001"), "old file left behind"
    assert tool2["step_file"] == "tool_geometry/T9002.STEP", tool2["step_file"]
    print("4 sync copy + id-rename: OK")

print("ALL TOOL-IO TESTS PASSED")
