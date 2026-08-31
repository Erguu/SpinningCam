"""Real-Tk check: the operation list tints rows, and the palette editor builds.

The pure rules are covered by _test_pass_colors.py. What this adds is that the
two things the operator actually looks at are wired to them: a reverse row must
not share a tag with a forward row, and the tag's background must be the tint of
the SAME palette entry the 3D view reads.
"""
import sys
import types
import tkinter as tk

import pass_colors as pc
from ui.tabs.program_tab import ProgramTab

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        fails.append(name)


class Stub:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, name):
        return lambda *a, **k: None


class Helper:
    def __getattr__(self, name):
        return lambda *a, **k: None


def op(kind, **kw):
    d = {"type": kind, "enabled": True, "count": 1, "tool_id": "T0101",
         "speed": 800, "speed_mode": "RPM", "feed": 300.0,
         "feed_mode": "mm_min"}
    d.update(kw)
    return d


root = tk.Tk()
root.withdraw()

OPS = [op("roughing"),                          # 0
       op("roughing", direction="reverse"),     # 1
       op("finishing"),                         # 2
       op("cutting"),                           # 3
       op("roughing", enabled=False)]           # 4 — disabled

params = {"operations": OPS, "pass_colors": {}}
app = Stub(params=params, tools={}, path_gen=None, machine_adapter=None,
           active_machine_profile=None, gui_pass_overrides={},
           active_adapter=None, sim_controller=Stub())

tab = ProgramTab(tk.Frame(root), app, Stub(), Helper())
tab.refresh_ops_tree()

rows = tab.tree_ops.get_children()
check("a row per operation", len(rows) == len(OPS), f"{len(rows)}")
tags = [tab.tree_ops.item(r, "tags") for r in rows]
tags = [tuple(x) if isinstance(x, (list, tuple)) else (x,) for x in tags]

print("1) each category gets its own tag")
check("forward roughing", tags[0] == ("opcol_roughing",), str(tags[0]))
check("REVERSE differs from forward", tags[1] == ("opcol_reverse",), str(tags[1]))
check("the two are not the same tag", tags[0] != tags[1])
check("finishing", tags[2] == ("opcol_finishing",), str(tags[2]))
check("cutting", tags[3] == ("opcol_cutting",), str(tags[3]))
check("a DISABLED op stays grey, untinted", tags[4] == ("op_disabled",), str(tags[4]))

print("2) the tag background is the tint of the palette the 3D view uses")
palette = pc.resolve_palette(params)
for idx, cat in ((0, "roughing"), (1, "reverse"), (2, "finishing"), (3, "cutting")):
    got = str(tab.tree_ops.tag_configure(f"opcol_{cat}", "background"))
    check(f"{cat:9} background", got == pc.tint(palette[cat]),
          f"{got} != {pc.tint(palette[cat])}")

print("3) an operator override reaches the list")
params["pass_colors"] = {"reverse": "#ff0000"}
tab.refresh_ops_tree()
check("reverse row repainted to the chosen colour",
      str(tab.tree_ops.tag_configure("opcol_reverse", "background"))
      == pc.tint("#ff0000"),
      str(tab.tree_ops.tag_configure("opcol_reverse", "background")))
check("forward roughing untouched",
      str(tab.tree_ops.tag_configure("opcol_roughing", "background"))
      == pc.tint(pc.DEFAULT_COLORS["roughing"]))

print("4) toggling an op off drops its tint")
OPS[0]["enabled"] = False
tab.refresh_ops_tree()
_t = tab.tree_ops.item(tab.tree_ops.get_children()[0], "tags")
_t = tuple(_t) if isinstance(_t, (list, tuple)) else (_t,)
check("row 0 is now grey", _t == ("op_disabled",), str(_t))

root.destroy()

print()
if fails:
    print(f"FAILED: {len(fails)} -> {fails}")
    sys.exit(1)
print("ALL PASS")
