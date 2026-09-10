# -*- coding: utf-8 -*-
"""Headless test: the real shop programs still generate what they generated.

WHAT THIS CATCHES THAT NOTHING ELSE DOES

Every other test in the suite asks "does this feature do what it says". This one
asks "did anything change that nobody meant to change" — across the whole
feature matrix at once, on programs that are actually run on a machine. An
engine change that quietly moves a pass shows up here as a diff on the exact
toolpath that moved, even when no unit test covers that combination of settings.

The fixtures are real programs from the shop folder, frozen into
``golden/fixtures``:

    020926.ssp            78 ops (4 on), straighten_start_fillet, PLC auto-tune
    bundan devam ...ssp   80 ops (12 on), the current working part
    bigsheet.ssp          8 ops, roughing + finishing, 65 toolpaths
    bigsheet2.ssp         1 op
    kalin.ssp             18 ops
    kalin2.ssp            20 ops, 79 toolpaths — the biggest
    v1.ssp                1 op, no machine_id (an old file)

HOW TO READ A FAILURE

The snapshot stores a hash of the whole .nc AND a row per toolpath (point count,
first point, last point, bounding box). The hash makes the test sensitive to
everything; the rows tell you WHICH path moved so you are not staring at
"something changed". To see exact coordinates:

    python golden_snapshot.py --write-full _fullgen

If the change was intended:

    python golden_snapshot.py --accept

and COMMIT THE SNAPSHOT DIFF as part of the change. A snapshot updated in its
own commit, with no explanation, is how a golden test becomes decoration.

THE FIXTURES ARE COPIES ON PURPOSE

The shop folder holds working files — one was edited an hour before this was
written. A baseline that moves whenever somebody edits their own program is not
a baseline, and teaches people to run --accept without reading. The snapshot
records each fixture's sha256, so a fixture that changes is reported rather than
silently becoming the new truth.

IF THE FIXTURES ARE ABSENT this test SKIPS rather than fails: they may be kept
out of the repository, and a missing fixture is not a regression.
"""
import copy
import os
import sys

import golden_snapshot as gs

fails = 0


def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


fx = gs.fixtures()
if not fx:
    print("SKIP - no fixtures in %s" % gs.FIXTURE_DIR)
    print("       (import them with:  python golden_snapshot.py "
          "--import-from <folder> --accept)")
    sys.exit(0)

print("Checking %d real program(s)\n" % len(fx))

# ── 1. every fixture still produces its recorded output ───────────────────
built = {}
for path in fx:
    name = os.path.basename(path)
    try:
        new = gs.snapshot(path)
    except Exception as e:
        check(False, "%s regenerated without raising (%r)" % (name, e))
        continue
    built[path] = new

    old = gs.read_snapshot(path)
    if old is None:
        check(False, "%s has a snapshot on record (run --accept to create one)" % name)
        continue

    diffs = gs.compare(old, new)
    check(not diffs, "%s unchanged (%d paths, %d nc lines, %d recipe lines)"
          % (name, new["paths"], new["nc_lines"], new["recipe_motion_lines"]))
    for d in diffs[:20]:
        print("        " + d)
    if len(diffs) > 20:
        print("        ... and %d more" % (len(diffs) - 20))

# ── 2. the fixture itself has not been edited ─────────────────────────────
# A changed fixture is not a code regression, but it DOES invalidate the
# baseline, and the two must never be confused.
for path, new in built.items():
    old = gs.read_snapshot(path)
    if not old:
        continue
    check(old.get("fixture_sha") == new.get("fixture_sha"),
          "%s is the same file the snapshot was taken from"
          % os.path.basename(path))

# ── 3. the mandrel really loaded ──────────────────────────────────────────
# Falling back to create_default_cone() would still produce a stable snapshot —
# of the WRONG PART. Every check above would pass while measuring nothing.
for path, new in built.items():
    check(new.get("step_loaded") is True,
          "%s loaded its real mandrel (%s)"
          % (os.path.basename(path), new.get("step")))

# ── 4. THE HARNESS CAN ACTUALLY FAIL ──────────────────────────────────────
# A golden test that cannot detect a change is worse than none: it reports
# success forever. So perturb a program and require the comparison to notice.
print()
if built:
    probe_path = sorted(built)[0]
    base = built[probe_path]

    _real_load = gs.load_program

    def _nudged(path, _shift=0.37):
        """The same program with the mandrel shifted 0.37 mm in X.

        A PARAMS-LEVEL geometric shift on purpose. The obvious probe — bump every
        operation's `clearance` — is worthless on a real file: all four enabled
        operations in 020926.ssp carry per-pass pins, and a pinned clearance
        beats the operation's own value, so the toolpath does not move at all.
        That is the documented priority chain behaving correctly (and it cost a
        false failure here before it was understood).

        The mandrel position cannot be overridden by any per-op or per-pass
        value, so every toolpath must move on every fixture.
        """
        params, overrides, step = _real_load(path)
        params = copy.deepcopy(params)
        params["mandrel_pos_x_offset"] = float(
            params.get("mandrel_pos_x_offset", 0.0) or 0.0) + _shift
        return params, overrides, step

    try:
        gs.load_program = _nudged
        moved = gs.snapshot(probe_path)
    finally:
        gs.load_program = _real_load

    diffs = gs.compare(base, moved)
    check(bool(diffs),
          "a 0.37 mm mandrel shift on %s IS detected (%d difference(s))"
          % (os.path.basename(probe_path), len(diffs)))
    check(base["nc_sha"] != moved["nc_sha"],
          "the .nc hash moves when the toolpath moves")
    check(any(d.startswith("path ") for d in diffs),
          "the failure names WHICH toolpath moved, not just 'something changed'")

    # And the harness must be stable in the other direction: regenerating the
    # untouched program twice in one process must agree, or every run would
    # look like a regression.
    again = gs.snapshot(probe_path)
    check(gs.compare(base, again) == [],
          "regenerating the same program twice gives the same digest")

print()
print("FAILURES:" if fails else "ALL GOLDEN-PROGRAM CHECKS PASSED",
      fails if fails else "")
sys.exit(1 if fails else 0)
