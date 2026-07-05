"""Headless test for 'reach follows blank' (#61 option B): an op flagged
reach_follow_blank must have its reach re-derived from the flange whenever start_z/end_z
change, so the exit keeps kissing the blank edge; unflagged ops are untouched.

Binds the real ProgramTab helper methods to a stub (no Tk needed) so we exercise the
actual code path, not a re-implementation.
"""
from mandrel_analyzer import MandrelManager
import ui.tabs.program_tab as PT

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])
blank_r = float(mgr.props["br"]) * 1.5   # blank larger than the mandrel base


class App:  pass
class Stub: pass

app = App(); app.mandrel_mgr = mgr
app.params = {"blank_radius": blank_r, "operations": []}
tab = Stub(); tab.app = app; tab.refresh_ops_tree = lambda: None
for name in ("_blank_reach_values", "_apply_blank_reach", "_refresh_auto_reach"):
    setattr(tab, name, getattr(PT.ProgramTab, name).__get__(tab))

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


# Flagged op, forming low on the wall.
op = {"type": "roughing", "count": 3, "pass_angle": 100.0, "reach_follow_blank": True,
      "start_z": min_z + 10, "end_z": min_z + 20}
app.params["operations"] = [op]
tab._refresh_auto_reach()
reach_low = op.get("reach")
prend_low = op.get("progressive_reach_end")
check(reach_low and reach_low > 0, f"flagged op got a reach filled ({reach_low})")
check(prend_low is not None, f"progressive_reach_end fanned for multi-pass ({prend_low})")

# Raise end_z (form higher) → less flange remains → the end reach must SHRINK (re-kiss).
op["end_z"] = min_z + 50
tab._refresh_auto_reach()
check(op["progressive_reach_end"] < prend_low,
      f"higher end_z shrinks end reach {prend_low} -> {op['progressive_reach_end']}")

# Lower end_z again → grows back (reach tracks end_z both ways).
op["end_z"] = min_z + 20
tab._refresh_auto_reach()
check(abs(op["progressive_reach_end"] - prend_low) < 1e-6,
      "reach tracks end_z back down (deterministic)")

# Reach factor modifier: scales the computed reach (default 1.0), never below 0.
op["end_z"] = min_z + 20
tab._refresh_auto_reach()
r_base = op["reach"]
op["reach_blank_factor"] = 0.9
tab._refresh_auto_reach()
check(abs(op["reach"] - round(r_base * 0.9, 2)) < 0.02,
      f"factor 0.9 scales reach {r_base} -> {op['reach']}")
op["reach_blank_factor"] = 1.1
tab._refresh_auto_reach()
check(abs(op["reach"] - round(r_base * 1.1, 2)) < 0.02,
      f"factor 1.1 scales reach {r_base} -> {op['reach']}")
op["reach_blank_factor"] = ""   # empty = 1.0
tab._refresh_auto_reach()
check(abs(op["reach"] - r_base) < 1e-6, "empty factor = 1.0 (no change)")

# Unflagged op must be left completely alone.
op_manual = {"type": "roughing", "count": 1, "start_z": min_z + 10, "end_z": min_z + 20,
             "reach": 999.0}
app.params["operations"] = [op_manual]
tab._refresh_auto_reach()
check(op_manual["reach"] == 999.0, "unflagged op reach untouched")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
