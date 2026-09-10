# -*- coding: utf-8 -*-
"""Headless test: the exe builder still matches the app.

`check_packaging.py` has existed for a while and does the right checks — every
shipped data file present, every critical module importable, a source scan for
data files nobody remembered to ship. What it did not have was anything making
it RUN. It was a command to remember before a release, and a step you have to
remember is a step that gets skipped exactly when the release is rushed.

Wrapping it as a test means packaging drift fails the ordinary suite, seconds
after it is introduced, rather than at build time weeks later — and the symptom
of that drift is an exe that starts and then cannot find a file, which is the
worst place to discover it.

STATIC ONLY. The post-build layer needs a built dist/ folder and belongs to
`build_exe.py`, which already calls it (build_exe.py:97).

Warnings are printed, not failed on: the source scan is deliberately eager and
its false positives (currently `.default.json`) are noise, not drift.
"""
import sys

import check_packaging


def test_static_packaging_has_no_problems():
    problems, warnings = check_packaging.check_static()
    for w in warnings:
        print("  warning: %s" % w)
    assert not problems, (
        "packaging drift — the builder no longer matches the app:\n  "
        + "\n  ".join(problems))
    print("1 static packaging: OK (%d warning(s))" % len(warnings))


def test_seed_and_step_files_agree():
    """The shipped seed tool library must reference geometry that is actually
    shipped. A seed naming a STEP that is not in the build gives a first-run
    library whose tools have no shape — and r_tool falls back to a radius the
    machine was never calibrated with."""
    problems, warnings = check_packaging.check_seed_step_consistency()
    for w in warnings:
        print("  warning: %s" % w)
    assert not problems, "seed/STEP mismatch:\n  " + "\n  ".join(problems)
    print("2 seed <-> STEP consistency: OK")


def test_the_new_report_modules_are_shipped():
    """`report_bundle` and the send-report dialog are imported lazily, from
    inside a menu callback. Lazy imports are invisible to PyInstaller's
    dependency walk, so they have to be named in CRITICAL_MODULES or the menu
    entry raises ImportError in the frozen build only — never at this desk."""
    from packaging_manifest import CRITICAL_MODULES
    for mod in ("report_bundle", "ui.dialogs.send_report"):
        assert mod in CRITICAL_MODULES, \
            f"{mod} is lazily imported but missing from CRITICAL_MODULES"
    print("3 report modules listed for the build: OK")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print("FAIL - %s\n%s" % (fn.__name__, e))
    print()
    print("ALL PACKAGING CHECKS PASSED" if not failed
          else "%d PACKAGING CHECK(S) FAILED" % failed)
    sys.exit(1 if failed else 0)
