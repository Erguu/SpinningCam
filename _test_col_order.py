"""#91 — ops-table column order (display-only) regression tests.

Covers the repair rules in ProgramTab._display_order: Sel pinned first, stale
ids dropped, unknown-to-the-saved-order ids appended.
"""
import types

from ui.tabs.program_tab import ProgramTab

COLS = ("Sel", "Idx", "On", "Type", "Count", "Tool", "RealEndZ",
        "EndReach", "EndAngle", "x_clearance", "x_feed_rate")


def _pt(order=None):
    """A bare ProgramTab shell — _display_order only touches app.params."""
    pt = ProgramTab.__new__(ProgramTab)
    pt.app = types.SimpleNamespace(params={} if order is None
                                   else {"op_view_col_order": list(order)})
    return pt


def check(name, got, want):
    assert tuple(got) == tuple(want), f"{name}:\n  got  {tuple(got)}\n  want {tuple(want)}"
    print(f"  OK  {name}")


print("#91 column order")

# 1. No saved order -> natural order, unchanged from today's behaviour.
check("no saved order = natural", _pt()._display_order(COLS), COLS)

# 2. The headline use case: clearance moved to the front.
saved = ["x_clearance", "Idx", "On", "Type", "Count", "Tool", "RealEndZ",
         "EndReach", "EndAngle", "x_feed_rate"]
check("clearance first", _pt(saved)._display_order(COLS),
      ("Sel", "x_clearance", "Idx", "On", "Type", "Count", "Tool", "RealEndZ",
       "EndReach", "EndAngle", "x_feed_rate"))

# 3. Sel is pinned even if a hand-edited config tries to move it.
check("Sel pinned despite saved order",
      _pt(["x_clearance", "Sel", "Idx"])._display_order(COLS),
      ("Sel", "x_clearance", "Idx", "On", "Type", "Count", "Tool", "RealEndZ",
       "EndReach", "EndAngle", "x_feed_rate"))

# 4. A column the user later unticked is dropped, not left dangling.
check("stale id dropped",
      _pt(["x_gone", "x_clearance"])._display_order(COLS),
      ("Sel", "x_clearance", "Idx", "On", "Type", "Count", "Tool", "RealEndZ",
       "EndReach", "EndAngle", "x_feed_rate"))

# 5. A newly ticked column the saved order never knew about lands at the end.
check("new id appended",
      _pt(["x_feed_rate"])._display_order(COLS),
      ("Sel", "x_feed_rate", "Idx", "On", "Type", "Count", "Tool", "RealEndZ",
       "EndReach", "EndAngle", "x_clearance"))

# 6. Every data column must survive exactly once — a dropped or duplicated id
#    would misalign the values written positionally by refresh_ops_tree.
for label, order in (("empty", []), ("partial", ["x_clearance"]),
                     ("garbage", ["zzz", "Sel", "Sel", "Type"]),
                     ("full reversed", list(reversed(COLS)))):
    got = _pt(order)._display_order(COLS)
    assert sorted(got) == sorted(COLS), f"{label}: column set changed -> {got}"
    assert len(got) == len(set(got)), f"{label}: duplicate column -> {got}"
    assert got[0] == "Sel", f"{label}: Sel not first -> {got}"
    print(f"  OK  set/uniqueness/pin preserved ({label})")

print("\nALL PASS")
