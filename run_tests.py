# -*- coding: utf-8 -*-
"""Run the whole headless test suite and say, in one screen, where we stand.

WHY THIS EXISTS

There are ~90 test files and, until now, no way to run them except one at a
time. In practice that meant nobody ran them all, and the list of which ones
were already broken lived in a maintainer's notes rather than in the repo. That
list drifts, and drift here is expensive: `test_path_generator.py` sat on it for
months as "stale test", and when somebody finally read it, it was a REAL bug —
an empty operations list was inventing a twelve-pass program out of nothing.

So: one command, an exit code, and the known-broken list checked in beside the
code it describes.

    python run_tests.py                 everything
    python run_tests.py -k point        only files matching "point"
    python run_tests.py --list          show what would run
    python run_tests.py --timeout 120   per-test limit, seconds

HOW TO RUN IT (this is the part that has gone wrong three times)

    conda run -n spinning_cam python run_tests.py

NOT `envs\\spinning_cam\\python.exe run_tests.py`. Calling the environment's
interpreter without activating it gives an MKL BLAS delay-load crash — exit 127,
no traceback — in anything that touches `np.linalg.*` or `np.polyfit`. The
engine reaches `np.polyfit` through `mandrel_analyzer._flat_start_params`, so
perfectly healthy code reports as broken and the hunt starts in the wrong place.

That failure mode is why this script REFUSES TO RUN until it has proved numpy
works (see `preflight`). One clear message beats ninety false failures.

EXIT CODE

0 when every test either passed or is on the known-broken list. 1 otherwise.
A known-broken test that starts passing is reported loudly but does not fail the
run — that is good news, and the fix is to delete its line from KNOWN_BROKEN.

WHY SEQUENTIAL

The tests share this folder: they write `spinning_cam.log`, and some construct
the real app. Running them in parallel makes them fight over those files and
produces failures that depend on timing, which is the one thing a test suite must
not have. The whole suite is a few minutes; correctness is worth the wait.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# Both naming conventions in use. `_test_*` is the house style; the five
# `test_*` files predate it.
PATTERNS = ("_test_", "test_")

# Files that are not tests despite the name pattern, or that cannot run
# unattended.
EXCLUDE = {
    "test_headless.py",            # a manual smoke script, not an assert suite
    "_test_scl_layout_manual.py",  # says so in the name: needs a human at the dialog
}

# ── Already failing before your change ──────────────────────────────────────
# The point of this list is to keep a red suite readable, NOT to file bugs away.
# Every entry needs a reason and a date. Read the reason before you add to it —
# "known broken" is not the same as "unimportant", and this list has hidden a
# real bug before (test_path_generator, found 2026-08-30 after months).
#
# EMPTY, and worth keeping that way. All five entries that lived here were
# cleared on 2026-09-10, and not one of them turned out to be a product bug:
#
#   _test_reach_follow.py         already passing — the list was simply stale
#   _test_real_end_z.py           hardcoded values[5]; a column was inserted to
#                                 its left, so it indexed the wrong cell
#   _test_pass_edits.py           its oracle called estimate_flange_reach, which
#                                 stopped being the engine's answer when
#                                 follow-blank moved from flat to slant reach
#   _test_program_tab_toolbar.py  asserted on btn_batch, moved to the right-click
#                                 menu in 2026-07; it died there and took TEN
#                                 later assertions down with it
#   _test_tool_io.py              read the live git-ignored tools.json, so it
#                                 broke for anyone who added a tool by hand
#
# The pattern: a red suite that is normal to ignore stops being read, and the
# checks BELOW the first failure quietly stop running. Before you add an entry,
# try to fix the test instead.
KNOWN_BROKEN = {}

PASS, FAIL, KNOWN, FIXED, TIMEOUT = "PASS", "FAIL", "KNOWN", "FIXED", "TIMEOUT"

_COLS = {PASS: "\033[32m", FAIL: "\033[31m", KNOWN: "\033[33m",
         FIXED: "\033[36m", TIMEOUT: "\033[31m"}
_RESET = "\033[0m"


def _colour(status, text=None):
    text = text if text is not None else status
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return "%s%s%s" % (_COLS.get(status, ""), text, _RESET)


def preflight():
    """Prove the interpreter is usable before blaming ninety test files.

    Returns a list of problem strings; empty means go. Deliberately checks the
    two numpy entry points that the un-activated-environment crash actually
    kills, rather than just importing numpy — the import succeeds either way,
    which is exactly what makes the failure so confusing.
    """
    problems = []
    try:
        import numpy as np
    except Exception as e:
        return ["numpy will not import: %s" % e]

    try:
        np.linalg.inv(np.array([[2.0, 0.0], [0.0, 2.0]]))
    except Exception as e:
        problems.append("np.linalg.inv failed: %s" % e)
    try:
        np.polyfit([0.0, 1.0, 2.0], [0.0, 1.0, 4.0], 2)
    except Exception as e:
        problems.append("np.polyfit failed: %s" % e)
    return problems


def discover(keyword=None):
    names = []
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith(".py") or fn in EXCLUDE:
            continue
        if not any(fn.startswith(p) for p in PATTERNS):
            continue
        if keyword and keyword.lower() not in fn.lower():
            continue
        names.append(fn)
    return names


def run_one(name, timeout):
    """Run one test file in its own process. Returns (status, seconds, output)."""
    started = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, name)],
            cwd=HERE, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", "replace")
        ok = (proc.returncode == 0)
        # exit 127 with no traceback is the un-activated-environment crash. It
        # is not a test failure and must not be read as one.
        if proc.returncode == 127 and "Traceback" not in out:
            out = ("EXIT 127 with no traceback — this is the MKL delay-load "
                   "crash, not a test failure. Activate the conda env.\n\n" + out)
    except subprocess.TimeoutExpired:
        return TIMEOUT, time.time() - started, "timed out after %ss" % timeout
    except Exception as e:                                   # pragma: no cover
        return FAIL, time.time() - started, "could not launch: %s" % e

    elapsed = time.time() - started
    if name in KNOWN_BROKEN:
        return (FIXED if ok else KNOWN), elapsed, out
    return (PASS if ok else FAIL), elapsed, out


def write_status(results, path=None):
    """Write TEST_STATUS.md — the current picture, for people who did not run it.

    Generated, never hand-edited: a checked-in status file that someone updates
    by hand is the same drifting list this script exists to replace.
    """
    path = path or os.path.join(HERE, "TEST_STATUS.md")
    buckets = {}
    for name, status, elapsed, _ in results:
        buckets.setdefault(status, []).append((name, elapsed))

    lines = ["# Test status", "",
             "**Generated by `run_tests.py` — do not edit by hand.**", "",
             "Last run: %s" % time.strftime("%Y-%m-%d %H:%M"), "",
             "| Result | Count |", "|---|---|"]
    for status in (PASS, FAIL, KNOWN, FIXED, TIMEOUT):
        if buckets.get(status):
            lines.append("| %s | %d |" % (status, len(buckets[status])))
    lines.append("")

    if buckets.get(FAIL) or buckets.get(TIMEOUT):
        lines += ["## Failing — needs attention", ""]
        for name, _ in buckets.get(FAIL, []) + buckets.get(TIMEOUT, []):
            lines.append("- `%s`" % name)
        lines.append("")

    if buckets.get(FIXED):
        lines += ["## Known-broken but now PASSING", "",
                  "Remove these from `KNOWN_BROKEN` in `run_tests.py`.", ""]
        for name, _ in buckets[FIXED]:
            lines.append("- `%s`" % name)
        lines.append("")

    if buckets.get(KNOWN):
        lines += ["## Known broken", "",
                  "Already failing before your change. Reason and date live in "
                  "`KNOWN_BROKEN` in `run_tests.py`.", ""]
        for name, _ in buckets[KNOWN]:
            lines.append("- `%s` — %s" % (name, KNOWN_BROKEN.get(name, "?")))
        lines.append("")

    slow = sorted(((e, n) for n, s, e, _ in results), reverse=True)[:10]
    lines += ["## Slowest", "", "| Test | Seconds |", "|---|---|"]
    lines += ["| `%s` | %.1f |" % (n, e) for e, n in slow]
    lines.append("")

    lines += ["## Passing", ""]
    lines += ["- `%s`" % n for n, _ in sorted(buckets.get(PASS, []))]
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-k", "--keyword", help="only files whose name contains this")
    ap.add_argument("--timeout", type=int, default=300, help="per test, seconds")
    ap.add_argument("--list", action="store_true", help="list and exit")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="do not print failure output")
    ap.add_argument("--no-status", action="store_true",
                    help="do not write TEST_STATUS.md")
    args = ap.parse_args(argv)

    problems = preflight()
    if problems:
        print("ENVIRONMENT IS NOT USABLE — not running anything.\n")
        for p in problems:
            print("  " + p)
        print("\nAlmost always this: the conda environment was not activated.")
        print("Run it as:  conda run -n spinning_cam python run_tests.py")
        return 2

    names = discover(args.keyword)
    if not names:
        print("No tests matched.")
        return 1
    if args.list:
        for n in names:
            print(n)
        return 0

    print("Running %d test files with %s\n" % (len(names), sys.executable))
    results = []
    width = max(len(n) for n in names) + 2
    started = time.time()

    for i, name in enumerate(names, 1):
        sys.stdout.write("[%3d/%d] %-*s " % (i, len(names), width, name))
        sys.stdout.flush()
        status, elapsed, out = run_one(name, args.timeout)
        print("%s %5.1fs" % (_colour(status, "%-7s" % status), elapsed))
        results.append((name, status, elapsed, out))

    counts = {}
    for _, status, _, _ in results:
        counts[status] = counts.get(status, 0) + 1

    bad = [(n, o) for n, s, _, o in results if s in (FAIL, TIMEOUT)]
    if bad and not args.quiet:
        for name, out in bad:
            print("\n" + "=" * 72)
            print("FAILED: %s" % name)
            print("=" * 72)
            tail = out.strip().splitlines()[-25:]
            print("\n".join(tail) if tail else "(no output)")

    print("\n" + "-" * 72)
    print("%d files in %.1fs   " % (len(results), time.time() - started)
          + "   ".join("%s %d" % (_colour(s, s), counts[s])
                       for s in (PASS, FAIL, KNOWN, FIXED, TIMEOUT)
                       if counts.get(s)))

    fixed = [n for n, s, _, _ in results if s == FIXED]
    if fixed:
        print("\nNow passing but still listed in KNOWN_BROKEN — remove them:")
        for n in fixed:
            print("  " + n)

    if not args.no_status:
        print("\nWrote %s" % write_status(results))

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
