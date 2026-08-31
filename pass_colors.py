"""Pass colours by operation category — the single source of truth.

Two consumers must agree or the feature is worse than useless: the 3D view
(``main.update_scene``) and the operation list (``ProgramTab.refresh_ops_tree``).
If they ever disagree, the list says one thing and the picture says another, and
the operator trusts whichever they looked at last.

The palette is a VIEWING preference, not machine data and not part geometry.
Nothing here is allowed to influence a toolpath, a feed, or an exported file.

Categories (2026-08-31, user decision — category colours only, no per-op
override):

    roughing · finishing · reverse · back · cutting · bending

``reverse`` exists because it is the case that prompted the feature: a reverse
pass is still type "roughing"/"finishing" and used to draw in exactly the same
colour as a forward pass, so the one thing an operator most needs to spot in the
3D view was invisible. It therefore OUTRANKS the op type — see ``op_category``.

The active-editing pass keeps its own magenta highlight in the 3D view. That is
a selection indicator, not an operation kind, so it is deliberately not in this
palette and always wins.
"""

from path_generator import op_builds_back_pass

# Order matters: it is the order the palette editor lists them in.
CATEGORIES = ("roughing", "finishing", "reverse", "back", "cutting", "bending")

# Chosen to stay distinguishable from each other AND from the fixed magenta of
# the active pass. `back` keeps the teal it has always had, `roughing` the blue
# and `finishing` the orange, so an existing program looks familiar; only
# reverse, cutting and bending are new (cutting/bending previously fell through
# to the roughing blue and were indistinguishable from it).
DEFAULT_COLORS = {
    "roughing":  "#1f6fd0",   # blue
    "finishing": "#e08000",   # orange
    "reverse":   "#7b52d3",   # violet
    "back":      "#00968f",   # teal
    "cutting":   "#2e9e4f",   # green
    "bending":   "#b03060",   # maroon
}

# The active-editing pass. Not user-editable, not a category. Held as hex, not
# as the name "magenta", because recolor_paths has to hand VTK three floats.
ACTIVE_COLOR = "#ff00ff"


def is_valid_hex(value):
    """True for '#rgb' / '#rrggbb'. Anything else is rejected rather than passed
    to Tk or PyVista, both of which raise on a bad colour string — and a raise
    inside the render loop would blank the 3D view over a typo in settings."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s.startswith("#") or len(s) not in (4, 7):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in s[1:])


def resolve_palette(params):
    """Category -> colour, defaults overlaid with the operator's choices.

    Unknown categories and malformed colours are dropped silently: this runs on
    every redraw, and a bad value in settings.json must degrade to the default
    colour, never break the view.
    """
    palette = dict(DEFAULT_COLORS)
    stored = (params or {}).get("pass_colors") or {}
    if isinstance(stored, dict):
        for key, value in stored.items():
            if key in DEFAULT_COLORS and is_valid_hex(value):
                palette[key] = value.strip()
    return palette


def op_category(op):
    """The colour category of ONE operation (never a back pass — see
    ``path_categories`` for those).

    Precedence, and the reason for it:
      1. cutting / bending — a distinct kind of move, not a spinning pass;
      2. reverse — outranks the op type, because "is this pass reversed?" is the
         question the colour is there to answer;
      3. the op type itself.
    """
    op = op or {}
    op_type = str(op.get("type", "roughing") or "roughing").lower()
    if op_type in ("cutting", "bending"):
        return op_type
    if str(op.get("direction", "forward") or "forward").lower() == "reverse":
        return "reverse"
    return op_type if op_type in DEFAULT_COLORS else "roughing"


def path_categories(ops):
    """One category per TOOLPATH, in render order.

    This mirrors ``calculate_paths``: disabled ops contribute nothing,
    cutting/bending emit exactly one path regardless of ``count``, and a back
    entry follows each forward pass only when the engine actually builds one.
    ``op_builds_back_pass`` is that last rule and is imported rather than
    restated — it already burned this project once, when six copies of an
    inlined version fell out of step with the engine and slid every consumer's
    indices by one path per pass.
    """
    out = []
    for op in (ops or []):
        if not op.get("enabled", True):
            continue
        category = op_category(op)
        count = 1 if category in ("cutting", "bending") else int(op.get("count", 1) or 1)
        has_back = op_builds_back_pass(op)
        for _ in range(max(count, 0)):
            out.append(category)
            if has_back:
                out.append("back")
    return out


def rgb_floats(hex_color):
    """Colour as three 0..1 floats, for VTK's ``prop.SetColor``.

    ``main.recolor_paths`` repaints existing actors in place instead of
    rebuilding them (that is what makes clicking through the operation list
    instant), and VTK properties take floats, not colour strings. Without this
    that function needed its own copy of the palette — which is exactly how it
    came to be painting reverse passes blue after this feature shipped.
    """
    if not is_valid_hex(hex_color):
        return (0.0, 0.0, 0.0)
    s = hex_color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def tint(hex_color, amount=0.82):
    """Blend a colour toward white, for use as a table row background.

    The operation list keeps BLACK text (user decision): the saturated path
    colours are unreadable behind text, and colouring the text instead makes a
    whole row of orange or teal hard to scan. ``amount`` is how far toward white
    — 0.82 keeps the hue recognisable next to the 3D view while leaving black
    text at full contrast.
    """
    if not is_valid_hex(hex_color):
        return "#ffffff"
    s = hex_color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: int(round(c + (255 - c) * amount))
    return "#{:02x}{:02x}{:02x}".format(mix(r), mix(g), mix(b))
