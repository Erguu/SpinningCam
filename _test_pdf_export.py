# -*- coding: utf-8 -*-
"""Headless smoke test for the self-documenting PDF export (#88):
exports a real PDF (paths + full per-op parameter dump) and checks it is a valid,
non-trivial PDF file. Also unit-tests the value formatter."""
import os
import tempfile
import numpy as np

from export_manager import ExportManager, SpinningCamPDF


def test_fmt_val():
    f = SpinningCamPDF._fmt_val
    assert f(True) == "yes" and f(False) == "no"
    assert f(3.0) == "3" and f(2.5) == "2.5"
    assert f([1, 2, 3]) == "<list:3>"
    assert f({"a": 1}) == "<dict:1>"
    assert f("x" * 40).endswith("~") and len(f("x" * 40)) == 24
    # non-latin1 must not raise
    assert isinstance(f("değer"), str)
    print("test_fmt_val PASS")


class _StubMgr:
    profile_z = None
    profile_r = None

    def __init__(self):
        self.props = {"top_z": 100.0, "min_z": 0.0, "max_radius": 50.0}

    def get_radius_fast(self, z): return 50.0
    def get_normal_at_z(self, z): return 1.0, 0.0
    def get_straightened_radius(self, z): return 50.0
    def get_straightened_normal(self, z): return 1.0, 0.0


def test_export():
    from path_generator import PathGenerator
    mgr = _StubMgr()
    params = {
        "operations": [
            {"type": "roughing", "enabled": True, "count": 2, "tool_id": "T0101",
             "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0, "p1_x": 40.0, "p1_z": 50.0,
             "p3_x": 40.0, "p3_z": -20.0, "pass_shape": "linear_approach",
             "retract_x": 40.0, "retract_z": 50.0, "name": "ROUGH-A"},
            {"type": "finishing", "enabled": True, "count": 1, "tool_id": "T0202",
             "r_tool": 20.0, "start_z": 10.0, "end_z": 60.0, "clearance": 0.5,
             "straight_line_mode": True, "retract_x": 30.0, "retract_z": 50.0},
        ],
        "blank_radius": 120.0, "final_part_thickness_on_mandrel": 2.0,
        "shell_thickness": 0.0, "min_safety_gap": 0.0, "target_clearance": 2.0,
        "home_x": 300.0, "home_z": 150.0, "mandrel_pos_x_offset": 0.0,
        "roller_positive_x_side": True,
    }
    pg = PathGenerator()
    pg.calculate_paths(params, {}, mgr)
    paths = pg.last_calculated_paths

    out = os.path.join(tempfile.gettempdir(), "_spincam_test_export.pdf")
    if os.path.exists(out):
        os.remove(out)
    ok = ExportManager.export_pdf(params, paths, out, tools=None, mandrel_mgr=mgr)
    assert ok, "export_pdf returned False"
    assert os.path.exists(out), "PDF file not created"
    size = os.path.getsize(out)
    assert size > 2000, f"PDF suspiciously small: {size} bytes"
    with open(out, "rb") as fh:
        head = fh.read(5)
    assert head == b"%PDF-", "not a PDF file"
    print(f"test_export PASS  ({size} bytes -> {out})")


def _pdf_text(path):
    """Decompress a fpdf2 PDF's content streams to plain text for assertions."""
    import re, zlib
    d = open(path, "rb").read()
    out = b""
    for s in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", d, re.S):
        try:
            out += zlib.decompress(s)
        except Exception:
            pass
    return out


def test_pdf_selection():
    """op_view_config[type]['pdf'] limits which op params the dump shows (#88)."""
    from path_generator import PathGenerator
    mgr = _StubMgr()
    op = {"type": "roughing", "enabled": True, "count": 1, "tool_id": "T0101",
          "r_tool": 25.0, "start_z": 10.0, "end_z": 60.0, "p1_x": 40.0, "p1_z": 50.0,
          "p3_x": 40.0, "p3_z": -20.0, "pass_shape": "linear_approach",
          "retract_x": 40.0, "retract_z": 50.0}
    params = {"operations": [op], "blank_radius": 120.0,
              "final_part_thickness_on_mandrel": 2.0, "home_x": 300.0, "home_z": 150.0,
              "mandrel_pos_x_offset": 0.0, "roller_positive_x_side": True}
    pg = PathGenerator()
    pg.calculate_paths(params, {}, mgr)
    out = os.path.join(tempfile.gettempdir(), "_spincam_test_export_sel.pdf")
    # Flat export-time selection: only start_z / end_z should appear in the dump.
    assert ExportManager.export_pdf(params, pg.last_calculated_paths, out, mandrel_mgr=mgr,
                                    param_selection=["start_z", "end_z"])
    txt = _pdf_text(out)
    assert b"start_z" in txt, "selected key start_z should appear"
    assert b"p1_x:" not in txt, "unselected key p1_x should be filtered out"
    assert b"pass_shape:" not in txt, "unselected key pass_shape should be filtered out"
    print("test_pdf_selection PASS")


if __name__ == "__main__":
    test_fmt_val()
    test_export()
    test_pdf_selection()
    print("ALL PASS")
