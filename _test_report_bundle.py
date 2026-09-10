# -*- coding: utf-8 -*-
"""Headless test: the "Send Report to Devs" troubleshooting bundle.

What this pins, in order of how badly it would hurt:

1. **A broken machine can still produce a report.** This feature exists to be
   used when something is already wrong. Every collector must swallow its own
   failure and mark the row, never raise — a missing STEP file, an unreadable
   settings.json or an engine that cannot generate G-code must each cost one
   row, not the whole bundle.

2. **Only what was ticked goes in the zip.** Nothing else in the program hands
   a customer's files to a third party, so the selection has to be exact. A
   selection naming a row that failed to collect must produce no member for it
   rather than an empty one.

3. **The license file never travels.** It is the customer's key. The report
   carries the fingerprint instead, which identifies them without being usable.

4. **The zip is whole or it is absent.** It is written to a .part file and
   renamed, so a failure halfway cannot leave something that unzips to a
   partial bundle and sends a maintainer down the wrong path.
"""
import json
import os
import shutil
import tempfile
import zipfile

import report_bundle as rb


# --- stubs -----------------------------------------------------------------

class _StubPathGen:
    def __init__(self, paths=True, gcode="G0 X0 Z0\nG1 X10 Z-5 F200\n"):
        self.last_calculated_paths = [object()] if paths else []
        self._gcode = gcode

    def generate_gcode(self, params=None):
        if self._gcode is None:
            raise RuntimeError("engine exploded")
        return self._gcode


class _StubApp:
    """Enough of SpinningApp for the collectors, over a throwaway base folder."""

    def __init__(self, base, paths=True, gcode="G0 X0 Z0\n", step=""):
        self._base = base
        self.params = {
            "machine_id": "ID111-1",
            "machine_name": "Test Lathe",
            "language": "EN",
            "operations": [
                {"type": "roughing", "enabled": True},
                {"type": "finishing", "enabled": True},
                {"type": "point", "enabled": False},
            ],
        }
        self.gui_pass_overrides = {}
        self.step_file_path_global = step
        self.path_gen = _StubPathGen(paths, gcode)

    def get_base_path(self):
        return self._base

    def save_project(self, filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"params": self.params, "overrides": {},
                       "step": self.step_file_path_global}, f)
        return True


def _make_base(with_files=True):
    base = tempfile.mkdtemp(prefix="rbtest_")
    if with_files:
        for name, body in (("spinning_cam.log", "line one\nline two\n"),
                           ("spinning_cam.prev.log", "older session\n"),
                           ("settings.json", '{"a": 1}'),
                           ("tools.json", '[{"id": "T0103"}]')):
            with open(os.path.join(base, name), "w", encoding="utf-8") as f:
                f.write(body)
        mdir = os.path.join(base, "machines")
        os.makedirs(mdir)
        for name in ("ID111-1.json", "ID111-1.default.json"):
            with open(os.path.join(mdir, name), "w", encoding="utf-8") as f:
                f.write('{"machine_id": "ID111-1"}')
        gdir = os.path.join(base, "tool_geometry")
        os.makedirs(gdir)
        with open(os.path.join(gdir, "T0103.STEP"), "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\n")
    return base


def _keyed(items):
    return {it.key: it for it in items}


# --- tests -----------------------------------------------------------------

def test_full_collection_finds_everything():
    base = _make_base()
    try:
        step = os.path.join(base, "part.STEP")
        with open(step, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\n")
        items = _keyed(rb.collect_items(_StubApp(base, step=step)))
        for key in rb.ITEM_ORDER:
            assert key in items, key
            assert items[key].available, (key, items[key].error)
        # the log item must carry BOTH generations
        assert len(items[rb.LOG].members) == 2, items[rb.LOG].members
        names = [a for a, _ in items[rb.LOG].members]
        assert "spinning_cam.prev.log" in names, names
        # the machine item must carry the live profile AND the factory template
        assert len(items[rb.MACHINE].members) == 2, items[rb.MACHINE].members
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_full_collection_finds_everything PASS")


def test_nothing_on_disk_still_collects():
    """The whole point: a machine where everything is missing still gets a
    report, with every row marked instead of an exception."""
    base = _make_base(with_files=False)
    try:
        app = _StubApp(base, paths=False)
        items = _keyed(rb.collect_items(app))
        assert len(items) == len(rb.ITEM_ORDER)
        for key in (rb.LOG, rb.SETTINGS, rb.TOOLS, rb.MACHINE,
                    rb.STEP, rb.TOOL_GEOMETRY, rb.GCODE):
            assert not items[key].available, key
            assert items[key].error, key
        # the program is built from memory, so it survives an empty disk
        assert items[rb.PROGRAM].available, items[rb.PROGRAM].error
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_nothing_on_disk_still_collects PASS")


def test_engine_failure_is_one_row_not_a_crash():
    base = _make_base()
    try:
        app = _StubApp(base)
        app.path_gen = _StubPathGen(paths=True, gcode=None)   # raises
        items = _keyed(rb.collect_items(app))
        assert items[rb.GCODE].error == "generate_failed", items[rb.GCODE]
        assert items[rb.SETTINGS].available, "one bad row must not poison the rest"
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_engine_failure_is_one_row_not_a_crash PASS")


def test_uncalculated_program_says_so():
    base = _make_base()
    try:
        items = _keyed(rb.collect_items(_StubApp(base, paths=False)))
        assert items[rb.GCODE].error == "no_paths", items[rb.GCODE]
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_uncalculated_program_says_so PASS")


def test_only_ticked_items_are_written():
    base = _make_base()
    try:
        app = _StubApp(base)
        items = rb.collect_items(app)
        sel = rb.selected_items(items, [rb.PROGRAM, rb.TOOLS])
        assert {i.key for i in sel} == {rb.PROGRAM, rb.TOOLS}

        out = os.path.join(base, "r.zip")
        n, _ = rb.write_bundle(out, sel, rb.summary_text(app, "note", sel))
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
        assert names == {rb.SUMMARY_NAME, "program.ssp", "tools.json"}, names
        assert n == 3, n
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_only_ticked_items_are_written PASS")


def test_unavailable_selection_is_dropped():
    """A ticked row whose collector failed must not become an empty zip entry
    that looks like a file the developers can open."""
    base = _make_base(with_files=False)
    try:
        app = _StubApp(base, paths=False)
        items = rb.collect_items(app)
        sel = rb.selected_items(items, [rb.PROGRAM, rb.LOG, rb.GCODE, rb.STEP])
        assert {i.key for i in sel} == {rb.PROGRAM}, [i.key for i in sel]
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_unavailable_selection_is_dropped PASS")


def test_license_never_travels():
    """Guards the one hard rule. If somebody adds a collector that sweeps the
    folder, this is what stops the customer's key going with it."""
    base = _make_base()
    try:
        for name in ("admin.lic", "license.lic", "license_private_key.pem"):
            with open(os.path.join(base, name), "w", encoding="utf-8") as f:
                f.write("SECRET-KEY-MATERIAL")
        app = _StubApp(base)
        items = rb.collect_items(app)
        sel = rb.selected_items(items, rb.ITEM_ORDER)
        out = os.path.join(base, "r.zip")
        rb.write_bundle(out, sel, rb.summary_text(app, "note", sel))
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            blob = b"".join(zf.read(n) for n in names)
        for n in names:
            assert not n.endswith((".lic", ".pem")), n
        assert b"SECRET-KEY-MATERIAL" not in blob, "key material leaked into the zip"
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_license_never_travels PASS")


def test_summary_carries_note_version_and_fingerprint():
    base = _make_base()
    try:
        app = _StubApp(base)
        items = rb.collect_items(app)
        txt = rb.summary_text(app, note="it dives on pass 3", items=items)
        from version import APP_VERSION
        assert "it dives on pass 3" in txt
        assert APP_VERSION in txt
        assert "ID111-1" in txt
        assert "Fingerprint" in txt
        # the note is what nothing else can reconstruct — it goes ABOVE the
        # machine details, where it will actually be read
        assert txt.index("it dives on pass 3") < txt.index("App version")
        # 3 operations, 2 of them enabled
        assert "3 (2 enabled)" in txt, txt
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_summary_carries_note_version_and_fingerprint PASS")


def test_empty_note_is_recorded_not_faked():
    base = _make_base()
    try:
        txt = rb.summary_text(_StubApp(base), note="   ")
        assert "(no description given)" in txt
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_empty_note_is_recorded_not_faked PASS")


def test_failed_write_leaves_no_zip():
    base = _make_base()
    try:
        app = _StubApp(base)

        class _Exploding:
            key = "boom"
            available = True
            size = 0
            @property
            def members(self):
                raise RuntimeError("disk went away")

        out = os.path.join(base, "r.zip")
        try:
            rb.write_bundle(out, [_Exploding()], "summary")
            raise AssertionError("write_bundle should have propagated")
        except RuntimeError:
            pass
        assert not os.path.exists(out), "a half-written zip was left behind"
        assert not os.path.exists(out + ".part"), "the .part file was not cleaned up"
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_failed_write_leaves_no_zip PASS")


def test_write_replaces_an_existing_file():
    base = _make_base()
    try:
        app = _StubApp(base)
        out = os.path.join(base, "r.zip")
        with open(out, "w", encoding="utf-8") as f:
            f.write("stale")
        sel = rb.selected_items(rb.collect_items(app), [rb.TOOLS])
        rb.write_bundle(out, sel, "summary")
        with zipfile.ZipFile(out) as zf:
            assert "tools.json" in zf.namelist()
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_write_replaces_an_existing_file PASS")


def test_default_filename_is_sortable_and_safe():
    base = _make_base()
    try:
        app = _StubApp(base)
        app.params["machine_id"] = "ID111-1/../etc"
        name = rb.default_filename(app)
        assert name.endswith(".zip")
        assert "/" not in name and "\\" not in name and ".." not in name, name
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_default_filename_is_sortable_and_safe PASS")


def test_preview_marks_binary_instead_of_dumping_it():
    base = _make_base()
    try:
        item = rb.Item("x", [("a.bin", b"\xff\xfe\x00\x01binary")])
        assert "binary file" in rb.preview_text(item)
        item = rb.Item("y", [("a.txt", b"hello")])
        assert rb.preview_text(item) == "hello"
        # a long member is truncated, and says so
        item = rb.Item("z", [("big.txt", b"x" * 5000)])
        out = rb.preview_text(item, limit=100)
        assert len(out) < 5000 and "showing the first" in out
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("test_preview_marks_binary_instead_of_dumping_it PASS")


def test_human_size_reads_like_a_size():
    assert rb.human_size(0) == "0 B"
    assert rb.human_size(999) == "999 B"
    assert rb.human_size(17 * 1024) == "17 KB"
    assert rb.human_size(3 * 1024 * 1024) == "3.0 MB"
    assert rb.human_size(None) == "?"
    print("test_human_size_reads_like_a_size PASS")


def test_defaults_leave_the_heavy_items_off():
    """The two items that can be megabytes, and that carry a customer's own part
    geometry, must not be pre-ticked."""
    assert rb.STEP not in rb.DEFAULT_ON
    assert rb.TOOL_GEOMETRY not in rb.DEFAULT_ON
    assert rb.PROGRAM in rb.DEFAULT_ON, "the program is the whole point"
    assert rb.LOG in rb.DEFAULT_ON
    print("test_defaults_leave_the_heavy_items_off PASS")


def test_every_item_has_labels_in_all_languages():
    """A row with no label renders as its raw key. Checked here rather than in
    the i18n sweep because these keys are BUILT from ITEM_ORDER, so a new item
    silently ships three missing strings."""
    from i18n import LANGUAGES, STRINGS
    missing = []
    keys = (["rep_item_" + k for k in rb.ITEM_ORDER]
            + ["rep_hint_" + k for k in rb.ITEM_ORDER])
    for key in keys:
        entry = STRINGS.get(key)
        if entry is None:
            missing.append(key)
            continue
        for lang in LANGUAGES:
            if not entry.get(lang):
                missing.append("%s[%s]" % (key, lang))
    assert not missing, missing
    print("test_every_item_has_labels_in_all_languages PASS")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
    print(f"\nAll {len(tests)} report-bundle checks passed.")
