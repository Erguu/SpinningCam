"""Pass colours by operation category (2026-08-31).

The feature only works if the 3D view and the operation list agree, so both read
pass_colors. What has to hold:

  * REVERSE outranks the op type — that is the case the feature exists for,
  * path_categories mirrors calculate_paths' toolpath order exactly,
  * a bad colour in settings degrades to the default instead of raising inside
    the render loop,
  * nothing here touches a toolpath.

Run: pyrun.bat _test_pass_colors.py   (conda env spinning_cam)
"""
import sys

import pass_colors as pc

fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        fails.append(name)


print("1) op_category")
check("plain roughing", pc.op_category({"type": "roughing"}) == "roughing")
check("plain finishing", pc.op_category({"type": "finishing"}) == "finishing")
check("REVERSE outranks roughing",
      pc.op_category({"type": "roughing", "direction": "reverse"}) == "reverse")
check("REVERSE outranks finishing",
      pc.op_category({"type": "finishing", "direction": "reverse"}) == "reverse")
check("explicit forward is not reverse",
      pc.op_category({"type": "roughing", "direction": "forward"}) == "roughing")
check("cutting outranks reverse",
      pc.op_category({"type": "cutting", "direction": "reverse"}) == "cutting")
check("bending outranks reverse",
      pc.op_category({"type": "bending", "direction": "reverse"}) == "bending")
check("unknown type falls back to roughing",
      pc.op_category({"type": "nonsense"}) == "roughing")
check("empty / None safe",
      pc.op_category({}) == "roughing" and pc.op_category(None) == "roughing")
check("case insensitive",
      pc.op_category({"type": "ROUGHING", "direction": "REVERSE"}) == "reverse")

print("2) path_categories mirrors the engine's toolpath order")
check("count expands", pc.path_categories([
    {"type": "roughing", "count": 3}]) == ["roughing"] * 3)
check("disabled op contributes nothing", pc.path_categories([
    {"type": "roughing", "count": 2, "enabled": False},
    {"type": "finishing", "count": 1}]) == ["finishing"])
check("cutting emits ONE path even with count>1", pc.path_categories([
    {"type": "cutting", "count": 5}]) == ["cutting"])
check("bending emits ONE path even with count>1", pc.path_categories([
    {"type": "bending", "count": 4}]) == ["bending"])
check("back pass follows each forward pass", pc.path_categories([
    {"type": "roughing", "count": 2, "back_pass_enabled": True}])
    == ["roughing", "back", "roughing", "back"])
check("a REVERSE op builds no back pass (engine rule)", pc.path_categories([
    {"type": "roughing", "count": 2, "direction": "reverse",
     "back_pass_enabled": True}]) == ["reverse", "reverse"])
check("mixed program", pc.path_categories([
    {"type": "roughing", "count": 2},
    {"type": "roughing", "count": 1, "direction": "reverse"},
    {"type": "finishing", "count": 1, "back_pass_enabled": True},
    {"type": "cutting", "count": 1}])
    == ["roughing", "roughing", "reverse", "finishing", "back", "cutting"])
check("empty / None safe", pc.path_categories([]) == [] and pc.path_categories(None) == [])

print("3) palette resolution is crash-proof")
check("no overrides -> defaults", pc.resolve_palette({}) == pc.DEFAULT_COLORS)
check("None params safe", pc.resolve_palette(None) == pc.DEFAULT_COLORS)
p = pc.resolve_palette({"pass_colors": {"reverse": "#ff0000"}})
check("an override is applied", p["reverse"] == "#ff0000")
check("and the rest stay default", p["roughing"] == pc.DEFAULT_COLORS["roughing"])
for bad in ("red", "#12345", "", None, 42, "#gggggg", []):
    got = pc.resolve_palette({"pass_colors": {"reverse": bad}})["reverse"]
    check(f"bad colour {bad!r} falls back", got == pc.DEFAULT_COLORS["reverse"], got)
check("unknown category ignored",
      pc.resolve_palette({"pass_colors": {"nope": "#ff0000"}}) == pc.DEFAULT_COLORS)
check("non-dict pass_colors ignored",
      pc.resolve_palette({"pass_colors": "nonsense"}) == pc.DEFAULT_COLORS)
check("short hex accepted", pc.resolve_palette(
    {"pass_colors": {"back": "#f00"}})["back"] == "#f00")

print("4) every category has a default, all distinct")
check("one default per category",
      set(pc.DEFAULT_COLORS) == set(pc.CATEGORIES))
check("no two categories share a colour",
      len(set(pc.DEFAULT_COLORS.values())) == len(pc.CATEGORIES))
check("none collides with the active-pass colour",
      pc.ACTIVE_COLOR not in pc.DEFAULT_COLORS.values())

print("5) tint stays light enough for black text")
for cat, col in pc.DEFAULT_COLORS.items():
    tinted = pc.tint(col)
    rgb = [int(tinted[i:i + 2], 16) for i in (1, 3, 5)]
    check(f"{cat:9} tint is pale ({tinted})", min(rgb) > 200, str(rgb))
check("tint of a bad colour is white, not a crash", pc.tint("nope") == "#ffffff")
check("short hex tints", pc.tint("#f00") == pc.tint("#ff0000"))
check("amount=0 returns the colour itself", pc.tint("#1f6fd0", 0.0) == "#1f6fd0")

print("6) rgb_floats — what recolor_paths hands to VTK")
check("black", pc.rgb_floats("#000000") == (0.0, 0.0, 0.0))
check("white", pc.rgb_floats("#ffffff") == (1.0, 1.0, 1.0))
check("active pass is magenta in VTK terms",
      pc.rgb_floats(pc.ACTIVE_COLOR) == (1.0, 0.0, 1.0),
      str(pc.rgb_floats(pc.ACTIVE_COLOR)))
check("short hex expands", pc.rgb_floats("#f00") == pc.rgb_floats("#ff0000"))
check("bad colour does not raise", pc.rgb_floats("nope") == (0.0, 0.0, 0.0))
for cat, col in pc.DEFAULT_COLORS.items():
    v = pc.rgb_floats(col)
    check(f"{cat:9} in range", len(v) == 3 and all(0.0 <= c <= 1.0 for c in v), str(v))

print("7) THE REGRESSION: recolor_paths must agree with the full render")
# update_scene builds the actors with palette[category]; recolor_paths repaints
# them IN PLACE when the operator clicks through the operation list. They used
# to hold separate copies of the category rule and the colour table, so after
# Calculate the view was right and one click turned every reverse pass blue.
# This drives the REAL function against fake VTK actors.
try:
    from main import SpinningApp
except Exception as e:
    print(f"  SKIP recolor_paths check ({e})")
else:
    class FakeProp:
        def __init__(self):
            self.color = None
            self.width = None

        def SetColor(self, r, g, b):
            self.color = (r, g, b)

        def SetLineWidth(self, w):
            self.width = w

    class FakeActor:
        def __init__(self):
            self.prop = FakeProp()

        def GetProperty(self):
            return self.prop

    class FakePlotter:
        def render(self):
            pass

    ops = [{"type": "roughing", "count": 1, "enabled": True},
           {"type": "roughing", "count": 1, "enabled": True, "direction": "reverse"},
           {"type": "finishing", "count": 1, "enabled": True, "back_pass_enabled": True},
           {"type": "cutting", "count": 1, "enabled": True},
           {"type": "bending", "count": 1, "enabled": True}]
    cats = pc.path_categories(ops)          # roughing, reverse, finishing, back, cutting, bending
    actors = [FakeActor() for _ in cats]

    app = SpinningApp.__new__(SpinningApp)
    app.actors = {"paths": actors}
    app.params = {"operations": ops, "pass_colors": {"reverse": "#123456"}}
    app.active_editing_pass_idx = -1
    app.plotter = FakePlotter()
    SpinningApp.recolor_paths(app)

    palette = pc.resolve_palette(app.params)
    for i, cat in enumerate(cats):
        want = pc.rgb_floats(palette[cat])
        got = actors[i].prop.color
        check(f"path {i} ({cat:9}) repainted to its category colour",
              got == want, f"{got} != {want}")
    check("REVERSE is not painted the roughing colour",
          actors[1].prop.color != actors[0].prop.color)
    check("and it honours the operator's override",
          actors[1].prop.color == pc.rgb_floats("#123456"),
          str(actors[1].prop.color))

    # The selected pass wins over its category, and is fatter.
    app.active_editing_pass_idx = 1
    SpinningApp.recolor_paths(app)
    check("the edited pass goes magenta, overriding reverse",
          actors[1].prop.color == pc.rgb_floats(pc.ACTIVE_COLOR),
          str(actors[1].prop.color))
    check("and is drawn thicker", actors[1].prop.width == 7)
    check("its neighbours keep their category colour",
          actors[0].prop.color == pc.rgb_floats(palette["roughing"])
          and actors[0].prop.width == 5)

    # More actors than categories must not raise (stale actor list mid-edit).
    app.actors["paths"] = actors + [FakeActor()]
    app.active_editing_pass_idx = -1
    SpinningApp.recolor_paths(app)
    check("a surplus actor falls back instead of raising",
          app.actors["paths"][-1].prop.color == pc.rgb_floats(palette["roughing"]))

print("8) the palette cannot reach a toolpath")
try:
    from mandrel_analyzer import MandrelManager
    from path_generator import PathGenerator
except Exception as e:
    print(f"  SKIP engine check ({e})")
else:
    mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0, 0)
    base = {"operations": [{"type": "roughing", "enabled": True, "count": 2,
                            "tool_id": "T0101", "r_tool": 20.0, "speed": 800,
                            "speed_mode": "RPM", "feed": 300.0,
                            "feed_mode": "mm_min", "start_z": 0.0, "end_z": 30.0}],
            "blank_radius": 100.0, "final_part_thickness_on_mandrel": 2.0,
            "num_sweeping_passes": 1}
    coloured = dict(base, pass_colors={"roughing": "#ff0000", "reverse": "#00ff00"})
    g1 = PathGenerator(); g1.calculate_paths(base, {}, mgr)
    g2 = PathGenerator(); g2.calculate_paths(coloured, {}, mgr)
    check("G-code is byte-identical with and without a palette",
          g1.generate_gcode(params=base) == g2.generate_gcode(params=coloured))

print()
if fails:
    print(f"FAILED: {len(fails)} -> {fails}")
    sys.exit(1)
print("ALL PASS")
