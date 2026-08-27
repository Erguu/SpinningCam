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
    edits = op.setdefault("pass_edits", {})
    for i, brk in per_pass.items():
        key = str(i)
        slot = edits.setdefault(key, {})
        if brk:
            slot["exit_breaks"] = brk
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
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    sys.exit(1 if FAIL else 0)
