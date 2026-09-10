# -*- coding: utf-8 -*-
"""Headless test: portable tool geometry — path resolution, export/import, sync.

WHY THIS BUILDS ITS OWN LIBRARY (changed 2026-09-10)

It used to read the LIVE `tools.json` from the project folder. That file is
git-ignored and is whatever the person at this desk last saved, so the test
failed for anyone who had added a tool by hand without a matching STEP —
observed on 2026-08-30 with T006/T007. That is a local-data problem being
reported as a code problem, which is the most expensive kind of false alarm:
it trains people to ignore a red suite.

Everything here now runs against a fixture built in a temp folder. The STEP
files are one-line stubs because nothing in this module parses them — it is all
path resolution and file copying.

Whether the SHIPPED seed library agrees with the shipped geometry is a real
question, but a different one, and it is already covered by
`check_seed_step_consistency()` in `check_packaging.py` and by
`_test_seed_consistency.py`.
"""
import json
import os
import shutil
import tempfile

import tool_library_io as tio
from tool_step_loader import _resolve_step_path

STEP_STUB = "ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"

# Two tools, both following the ID-named convention the loader expects.
FIXTURE_TOOLS = [
    {"id": "T0101", "name": "Test roller A", "radius": 60.0, "r_tool": 62.5,
     "step_file": "tool_geometry/T0101.STEP"},
    {"id": "T0103", "name": "Test roller B", "radius": 74.31, "r_tool": 79.5,
     "step_file": "tool_geometry/T0103.STEP"},
]


def _make_library(base):
    """A complete tool library on disk: tools.json + tool_geometry/<id>.STEP."""
    gdir = os.path.join(base, "tool_geometry")
    os.makedirs(gdir, exist_ok=True)
    for tl in FIXTURE_TOOLS:
        with open(os.path.join(gdir, tl["id"] + ".STEP"), "w", encoding="utf-8") as f:
            f.write(STEP_STUB)
    with open(os.path.join(base, "tools.json"), "w", encoding="utf-8") as f:
        json.dump(FIXTURE_TOOLS, f, indent=4)
    return [dict(t) for t in FIXTURE_TOOLS]


def test_convention_resolution():
    """tool_geometry/<id>.STEP is found from the id alone."""
    with tempfile.TemporaryDirectory() as base:
        tools = _make_library(base)
        for tl in tools:
            p = _resolve_step_path(tl, base)
            assert p and os.path.isfile(p), f"resolve failed for {tl['id']}: {p!r}"
            assert os.path.basename(p) == tl["id"] + ".STEP", p
    print("1 convention resolution: OK", [t["id"] for t in FIXTURE_TOOLS])


def test_convention_beats_stale_absolute_path():
    """The recorded step_file is a hint, not an authority.

    This is what makes a library portable between machines: a path saved on
    somebody else's computer must not win over the file actually sitting in this
    folder.
    """
    with tempfile.TemporaryDirectory() as base:
        tools = _make_library(base)
        bogus = dict(tools[0])
        bogus["step_file"] = "Z:/nope/gone.STEP"
        p = _resolve_step_path(bogus, base)
        assert p and os.path.basename(p) == tools[0]["id"] + ".STEP", p
    print("2 convention beats stale absolute path: OK")


def test_export_import_round_trip():
    with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as tmp:
        tools = _make_library(base)
        zpath = os.path.join(tmp, "bundle.zip")
        n, g = tio.export_library(base, tools, zpath)
        assert n == len(tools) and g == len(tools), (n, g)

        imported = tio.import_library(tmp, zpath)
        assert len(imported) == len(tools)
        for tl in imported:
            gp = tio.find_geometry_file(tmp, tl["id"])
            assert gp and os.path.isfile(gp), tl["id"]
            assert tl["step_file"] == f"tool_geometry/{tl['id']}.STEP", tl["step_file"]
        # the calibration must survive the trip — it is the whole reason to
        # move a library between machines
        by_id = {t["id"]: t for t in imported}
        for tl in tools:
            assert by_id[tl["id"]]["r_tool"] == tl["r_tool"], tl["id"]
        print(f"3 export/import round trip: OK ({n} tools, {g} geom)")


def test_export_without_geometry_drops_the_path():
    """A tool whose STEP is missing here must export with an EMPTY step_file,
    not with this machine's dead path — otherwise the bundle carries a promise
    the receiving machine cannot keep."""
    with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as tmp:
        tools = _make_library(base)
        os.remove(os.path.join(base, "tool_geometry", "T0101.STEP"))
        zpath = os.path.join(tmp, "bundle.zip")
        n, g = tio.export_library(base, tools, zpath)
        assert n == 2 and g == 1, (n, g)
        imported = tio.import_library(tmp, zpath)
        by_id = {t["id"]: t for t in imported}
        assert by_id["T0101"]["step_file"] == "", by_id["T0101"]
        assert by_id["T0103"]["step_file"] == "tool_geometry/T0103.STEP"
    print("5 export drops the path for missing geometry: OK")


def test_sync_copy_and_rename():
    with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as tmp:
        tools = _make_library(base)
        src = os.path.join(tmp, "some external tool.STEP")
        shutil.copyfile(_resolve_step_path(tools[0], base), src)

        tool = {"id": "T9001", "step_file": src}
        tio.sync_tool_geometry(tmp, tool)
        assert tool["step_file"] == "tool_geometry/T9001.STEP", tool["step_file"]
        assert tio.find_geometry_file(tmp, "T9001"), "copy missing"

        tool2 = dict(tool)
        tool2["id"] = "T9002"
        tio.sync_tool_geometry(tmp, tool2, old_id="T9001")
        assert tio.find_geometry_file(tmp, "T9002"), "rename missing"
        assert not tio.find_geometry_file(tmp, "T9001"), "old file left behind"
        assert tool2["step_file"] == "tool_geometry/T9002.STEP", tool2["step_file"]
    print("4 sync copy + id-rename: OK")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print("ALL TOOL-IO TESTS PASSED")
