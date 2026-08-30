# -*- coding: utf-8 -*-
"""#102 — the break-point editor's PURE logic, without a display.

Tk cannot be instantiated headless here, so the two decisions worth testing are
lifted out of the dialog and exercised directly:

* the ramp arithmetic (`BreakPointsDialog._ok`'s "all passes" branch), and
* what `pass_table._edit_break_points._apply` writes into the op.

Both are transcribed rather than imported — importing the dialog needs Tk. The
transcription is kept next to the original on purpose; if one changes and the
other does not, this test is what says so.

Run:  python _test_break_points_ui.py
"""
import sys

import exit_breaks as eb

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


# ── the dialog's apply branch ───────────────────────────────────────────────
def build_per_pass(rows, n_passes, scope, ramping):
    """Mirror of BreakPointsDialog._ok. `rows` carry an optional 'ramp' end."""
    clean = [{"t": r["t"], "angle": r["angle"]} for r in rows]
    if scope != "all":
        return {0: clean}
    if ramping and n_passes >= 2:
        out = {}
        for i in range(n_passes):
            f = i / (n_passes - 1)
            out[i] = [{"t": r["t"],
                       "angle": round(r["angle"]
                                      + ((r["ramp"] if r.get("ramp") is not None
                                          else r["angle"]) - r["angle"]) * f, 4)}
                      for r in rows]
        return out
    return {i: [dict(r) for r in clean] for i in range(n_passes)}


def test_ramp():
    print("\n[1] ramp across passes")
    rows = [{"t": 0.4, "angle": 5.0, "ramp": 9.0}]
    got = build_per_pass(rows, 5, "all", True)
    angles = [got[i][0]["angle"] for i in range(5)]
    check("5 passes ramp 5→9 in equal steps", angles == [5.0, 6.0, 7.0, 8.0, 9.0],
          str(angles))
    check("the position is NOT ramped",
          all(got[i][0]["t"] == 0.4 for i in range(5)))

    # A row with no ramp end must stay flat while its neighbour ramps.
    rows = [{"t": 0.3, "angle": 4.0, "ramp": None},
            {"t": 0.7, "angle": 0.0, "ramp": 20.0}]
    got = build_per_pass(rows, 3, "all", True)
    check("a row without a ramp end stays constant",
          [got[i][0]["angle"] for i in range(3)] == [4.0, 4.0, 4.0])
    check("its neighbour still ramps",
          [got[i][1]["angle"] for i in range(3)] == [0.0, 10.0, 20.0])

    # Negative / descending ramps are ordinary.
    rows = [{"t": 0.5, "angle": 10.0, "ramp": -10.0}]
    got = build_per_pass(rows, 3, "all", True)
    check("a descending ramp passes through zero",
          [got[i][0]["angle"] for i in range(3)] == [10.0, 0.0, -10.0])

    # Ramp off → the same list everywhere.
    got = build_per_pass([{"t": 0.5, "angle": 8.0, "ramp": 30.0}], 4, "all", False)
    check("ramp off writes the same angle to every pass",
          all(got[i][0]["angle"] == 8.0 for i in range(4)))
    check("apply-to-all covers every pass", sorted(got) == [0, 1, 2, 3])

    # One pass → nothing to ramp across; must not divide by zero.
    got = build_per_pass([{"t": 0.5, "angle": 8.0, "ramp": 30.0}], 1, "all", True)
    check("a single-pass op does not crash the ramp", got == {0: [{"t": 0.5, "angle": 8.0}]})

    # This-pass scope ignores the ramp entirely.
    got = build_per_pass([{"t": 0.5, "angle": 8.0, "ramp": 30.0}], 5, "this", True)
    check("scope 'this pass' writes one pass only", list(got) == [0])


# ── what the pass table writes ──────────────────────────────────────────────
def apply_to_op(op, per_pass):
    """Mirror of pass_table._edit_break_points._apply (minus Tk/undo/recalc)."""
    _suppressible = bool(eb.legacy_break(op))   # read before the pop below
    edits = op.setdefault("pass_edits", {})
    for i, brk in per_pass.items():
        key = str(i)
        slot = edits.setdefault(key, {})
        if brk:
            slot["exit_breaks"] = brk
        elif _suppressible:
            slot["exit_breaks"] = []           # "none, and I mean it"
        else:
            slot.pop("exit_breaks", None)
        if not slot:
            edits.pop(key, None)
    if any(per_pass.values()):
        op.pop("exit_mid_rotation", None)      # NOT exit_mid_t — the curl owns it too
    return op


def test_apply():
    print("\n[2] what lands in the op")
    op = {"count": 3, "exit_mid_t": 0.5, "exit_mid_rotation": 15.0,
          "pass_shape": "linear_approach"}
    apply_to_op(op, build_per_pass([{"t": 0.4, "angle": 5.0, "ramp": 9.0}],
                                   3, "all", True))
    check("the legacy op-level break is retired once breaks are written",
          "exit_mid_rotation" not in op)
    check("but exit_mid_t survives — the #92 curl reads it too",
          op.get("exit_mid_t") == 0.5)
    check("every pass got its own list",
          all("exit_breaks" in op["pass_edits"][str(i)] for i in range(3)))
    check("the engine reads back the ramped angles",
          [eb.get_breaks(op, i)[0]["angle"] for i in range(3)] == [5.0, 7.0, 9.0])

    # Clearing one pass must fall back to nothing (the legacy key is gone), not
    # resurrect a break.
    apply_to_op(op, {1: []})
    check("clearing a pass removes its list", eb.stored(op, 1) == [])
    check("and it does not fall back to a retired legacy break",
          eb.get_breaks(op, 1) == [])
    check("the other passes are untouched", len(eb.get_breaks(op, 2)) == 1)

    # An op that still has ONLY the legacy break keeps working untouched.
    old = {"count": 2, "exit_mid_t": 0.6, "exit_mid_rotation": -12.0,
           "pass_shape": "linear_approach"}
    check("an untouched old op still resolves its legacy break",
          eb.get_breaks(old, 0) == [{"t": 0.6, "angle": -12.0}]
          and eb.get_breaks(old, 1) == [{"t": 0.6, "angle": -12.0}])

    # Clearing everything on an op that never had breaks leaves no debris.
    clean = {"count": 2, "pass_shape": "linear_approach"}
    apply_to_op(clean, {0: [], 1: []})
    check("clearing an op with no breaks leaves pass_edits empty",
          clean.get("pass_edits") == {})


# ── deleting the LEGACY break (the 2026-08-31 fix) ──────────────────────────
def test_delete_legacy():
    """An op whose only break comes from the old exit_mid_rotation.

    This was the hole: the editor removed the pass's key, the fallback saw an
    empty list, decided the pass had never been edited, and handed the legacy
    break straight back. Deleting the row was a no-op you could repeat forever.
    """
    print("\n[4] deleting a break that came from the legacy exit_mid")

    op = {"count": 3, "exit_mid_t": 0.5, "exit_mid_rotation": 15.0,
          "pass_shape": "linear_approach"}
    check("it starts out showing the legacy break on every pass",
          all(eb.get_breaks(op, i) == [{"t": 0.5, "angle": 15.0}] for i in range(3)))

    apply_to_op(op, {1: []})               # open pass 1, delete the row, OK
    check("pass 1 now really has no breaks", eb.get_breaks(op, 1) == [])
    check("it is stored as an explicit empty list, not a missing key",
          eb.has_own_list(op, 1) and eb.stored(op, 1) == [])
    check("the other passes still get the legacy break",
          eb.get_breaks(op, 0) == [{"t": 0.5, "angle": 15.0}]
          and eb.get_breaks(op, 2) == [{"t": 0.5, "angle": 15.0}])
    check("exit_mid_t is untouched — the #92 curl reads it",
          op.get("exit_mid_t") == 0.5)
    check("the legacy rotation is left alone for the passes still using it",
          op.get("exit_mid_rotation") == 15.0)

    # Clearing every pass: nothing runs anywhere.
    op2 = {"count": 2, "exit_mid_t": 0.4, "exit_mid_rotation": -8.0,
           "pass_shape": "linear_approach"}
    apply_to_op(op2, {0: [], 1: []})
    check("clearing all passes leaves no breaks anywhere",
          eb.get_breaks(op2, 0) == [] and eb.get_breaks(op2, 1) == [])

    # ...and it is reversible: drop the pass's entry and the legacy comes back.
    del op2["pass_edits"]["0"]
    check("removing the pass entry restores the legacy break",
          eb.get_breaks(op2, 0) == [{"t": 0.4, "angle": -8.0}])

    # A pass that was never touched must be unchanged to the last float — this
    # is the "replace without migrating" promise for every pre-#102 program.
    old = {"count": 2, "exit_mid_t": 0.6, "exit_mid_rotation": -12.0,
           "pass_shape": "linear_approach"}
    check("an untouched legacy op is bit-identical",
          eb.get_breaks(old, 0) == [{"t": 0.6, "angle": -12.0}])
    check("has_own_list says no for an untouched pass",
          not eb.has_own_list(old, 0))

    # Hand-edited / odd shapes must not resurrect a break either.
    check("an explicit null counts as 'no breaks', not 'never edited'",
          eb.get_breaks({"exit_mid_rotation": 9.0,
                         "pass_edits": {"0": {"exit_breaks": None}}}, 0) == [])
    check("int pass keys work the same as str",
          eb.has_own_list({"pass_edits": {0: {"exit_breaks": []}}}, 0))
    check("an unrelated pin on the pass does NOT count as a break list",
          not eb.has_own_list({"pass_edits": {"0": {"reach": 40.0}}}, 0))
    check("...so that pass still falls back to the legacy break",
          eb.get_breaks({"exit_mid_rotation": 9.0, "exit_mid_t": 0.5,
                         "pass_edits": {"0": {"reach": 40.0}}}, 0)
          == [{"t": 0.5, "angle": 9.0}])


# ── the dialog seeds from what the pass is really running ───────────────────
def test_seed():
    print("\n[3] seeding")
    op = {"count": 2, "exit_mid_t": 0.35, "exit_mid_rotation": 7.5,
          "pass_shape": "linear_approach"}
    seeded = eb.get_breaks(op, 0)
    check("a pass with no list seeds from the legacy break",
          seeded == [{"t": 0.35, "angle": 7.5}])
    check("and it is flagged as legacy (stored() is empty)", eb.stored(op, 0) == [])
    op2 = {"count": 2, "pass_shape": "linear_approach"}
    check("an op with nothing at all seeds empty", eb.get_breaks(op2, 0) == [])


if __name__ == "__main__":
    test_ramp()
    test_apply()
    test_seed()
    test_delete_legacy()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else 0)
