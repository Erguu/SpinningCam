# -*- coding: utf-8 -*-
"""Compare two passes side by side — "why does THIS one behave differently?"

The pass table answers "what does each pass of ONE operation do". It cannot
answer the question operators actually ask, which is comparative and usually
crosses an operation boundary: *pass 3 of Roughing 1 and pass 2 of Roughing 3
look like they should do the same thing, so why don't they?* The answer is
almost never in one place — it is a per-pass pin on one side, a different
``pass_shape`` on the other, and an exit bow nobody remembers setting.

So a comparison has to show BOTH layers at once:

  * **effective** — what ``compute_pass_rows`` resolves for that one pass
    (anchor, extend, contact Z, clearance, angle, reach, endpoint), each with
    the priority-chain stage that produced it (op field / fan / follow / pin).
  * **operation** — the op-level settings the pass inherits. This is where the
    difference usually is, and it is invisible in any per-pass view.

Editing model (user decision 2026-09-02): the table is editable, staged behind
[Apply] exactly like the pass table. Two staging dicts, because an edit has two
possible destinations and they must not be confused:

  ``staged_pins``  {(op_index, pass_index): {pin_key: value}}  → op["pass_edits"]
  ``staged_ops``   {op_index: {key: value}}                    → the op itself

Keeping them separate (rather than one dict keyed by display row) is what makes
comparing two passes OF THE SAME OPERATION work: both sides then resolve
through the same staged op dict instead of fighting over it. A staged value of
``None`` means "remove this key/pin".

Pure: no Tk. Never mutates params except through :func:`apply_edits`, which the
dialog calls once, after its own undo snapshot.
"""

from i18n import t
from ui.tabs.program_tab import (
    GROUP_DEPS, OP_PARAM_DEFAULTS, OP_PARAM_LABELS, OP_PARAM_UNIVERSE,
    _TILT_KEYS,
)
from ui.dialogs.pass_table import compute_pass_rows

# Per-pass pins the ENGINE reads (path_generator.py ~849). Anything outside this
# set can only be written op-wide — offering "this pass only" for it would be a
# lie, because nothing would read the pin back.
PIN_KEYS = ("target_z", "p2_z_extend", "clearance", "pass_angle", "reach")

# Ops whose per-pass pins the engine ignores entirely.
_PIN_OP_TYPES = ("roughing",)

# Ops with no per-pass geometry at all — one feed line, no pass table.
_NO_PASS_TYPES = ("cutting", "bending")

# Section ids, in display order.
SECTIONS = ("pass", "effective", "operation")

# ── effective rows: (row key, i18n label key, pin key or None) ──────────────
# The pin key is what makes the row editable: it names the field the engine
# reads back out of pass_edits. A row without one is derived (contact Z is
# anchor+extend; the endpoint is the result of everything above it) and editing
# it would have nowhere to go.
EFFECTIVE_ROWS = (
    ("anchor",    "pt_col_anchor", "target_z"),
    ("extend",    "pt_col_extend", "p2_z_extend"),
    ("z",         "pt_col_z",      None),
    ("clr",       "pt_col_clr",    "clearance"),
    ("angle",     "pt_col_angle",  "pass_angle"),
    ("reach",     "pt_col_reach",  "reach"),
    ("end_x",     "pt_col_endx",   None),
    ("end_z",     "pt_col_endz",   None),
    ("source",    "pt_col_src",    None),
    ("n_tail",    "pc_row_tail",   None),
    ("n_breaks",  "pc_row_breaks", None),
    ("warn",      "pt_col_warn",   None),
)

# Effective row key → provenance field name (recipe_explain.explain_field).
# Only the resolved numbers have a chain; the rest are derived or descriptive.
PROV_FIELD = {"anchor": "anchor", "extend": "extend", "clr": "clr",
              "angle": "angle", "reach": "reach"}

# ── op-parameter value kinds, for the cell editor ──────────────────────────
_ENUMS = {
    "pass_shape":       ["spline", "linear_approach", "linear_full"],
    "direction":        ["forward", "reverse"],
    "feed_mode":        ["mm_min", "mm_rev"],
    "tilt_mode":        ["normal", "interp"],
    "tool_change_mode": ["global", "absolute", "relative"],
}

_BOOLS = frozenset((
    "progressive_angle_enabled", "progressive_reach_enabled",
    "reach_follow_blank", "back_pass_enabled", "back_pass_swapped",
    "conformal_clearance_operation_specific", "approach_follow_surface",
    "exit_bow_trim", "exit_mid_trim", "straight_line_mode",
    "tool_change_simultaneous",
))

_TEXTS = frozenset(("name",))

# What the ENGINE uses when a non-numeric field is absent. OP_PARAM_DEFAULTS
# deliberately covers only numbers and relative hints (it drives the faded hint
# in the op editor), so booleans and mode combos need their own table or an
# unset field compares as "nothing" against an explicit value that behaves
# identically — the exact false difference this window exists to avoid.
#
# The two True entries are NOT a typo: exit_bow_trim / exit_mid_trim default to
# TRIM (path_generator.py:2341, :2455). Reading them as False would report a
# difference between two ops that both trim.
_IMPLIED_DEFAULTS = {
    "direction":        "forward",
    "pass_shape":       "spline",
    "feed_mode":        "mm_min",
    "tilt_mode":        "normal",
    "tool_change_mode": "global",
    "exit_bow_trim":    True,
    "exit_mid_trim":    True,
}

# Every other boolean in _BOOLS is off when absent. conformal_clearance_
# operation_specific is the exception handled in _implied_default(): it falls
# back to the GLOBAL conformal setting, not to False.
_BOOL_DEFAULT = False

# Dependent key → the toggle that switches it on (inverted GROUP_DEPS). A
# dependent whose toggle is off is INERT: its number is stored but nothing
# reads it, so comparing two inert values as if they mattered is noise.
_DEP_OF = {}
for _tog, _deps in GROUP_DEPS.items():
    for _d in _deps:
        _DEP_OF[_d] = _tog


def value_kind(key, tools=None):
    """('number'|'bool'|'enum'|'text', choices) for an op parameter.

    ``tools`` (the live tool library list) supplies the tool_id choices; without
    it the field falls back to free text rather than offering an empty combo.
    """
    if key in _BOOLS:
        return "bool", None
    if key in _TEXTS:
        return "text", None
    if key == "speed_mode":
        try:
            from path_generator import speed_mode_choices
            return "enum", list(speed_mode_choices())
        except Exception:
            return "enum", ["RPM"]
    if key == "tool_id":
        ids = [str(x.get("id")) for x in (tools or []) if x.get("id") is not None]
        return ("enum", ids) if ids else ("text", None)
    if key in _ENUMS:
        return "enum", list(_ENUMS[key])
    return "number", None


# ──────────────────────────────────────────────────────────────────────────
# Pass enumeration
# ──────────────────────────────────────────────────────────────────────────

def pass_count(op):
    """Forward passes this op contributes (cutting/bending are always one)."""
    if (op or {}).get("type", "roughing") in _NO_PASS_TYPES:
        return 1
    try:
        return max(1, int(op.get("count", 1) or 1))
    except (TypeError, ValueError):
        return 1


def base_fwd_index(params, op_index):
    """Global forward-pass index of an op's first pass.

    Mirrors PassTableDialog._base_fwd_idx — the key into the legacy top-level
    ``gui_pass_overrides`` map, which is numbered over ENABLED ops only.
    """
    base = 0
    for j, o in enumerate((params or {}).get("operations", [])):
        if j == op_index:
            break
        if o.get("enabled", True):
            base += pass_count(o)
    return base


def op_label(op, op_index, n=None):
    """Picker label for one operation: index, name, pass count, and the two
    tags that change what its passes do (reverse / switched off)."""
    n = pass_count(op) if n is None else n
    bits = [f"{op_index + 1}. {op.get('name') or op.get('type', 'roughing')}",
            t("pc_op_passes").format(n=n)]
    if op.get("direction") == "reverse":
        bits.append(t("pc_tag_reverse"))
    if not op.get("enabled", True):
        bits.append(t("pc_tag_off"))
    return "  ·  ".join(bits)


def list_operations(params):
    """Every operation, in program order: {op_index, n, label}.

    Two-step picking (user 2026-09-02): one flat list of every pass in the
    program is fine with three operations and unusable with twenty, so the
    dialog picks the OPERATION first and then the pass within it. Disabled ops
    are INCLUDED and marked — "why is this pass different" gets asked about ops
    people have just switched off as often as about live ones.
    """
    return [{"op_index": i, "n": pass_count(o), "label": op_label(o, i)}
            for i, o in enumerate((params or {}).get("operations", []))]


def pass_choices(n):
    """Labels for the pass picker of an n-pass operation: "2 / 5"."""
    n = max(1, int(n or 1))
    return [f"{i + 1} / {n}" for i in range(n)]


def list_passes(params):
    """Every selectable pass in the program, flat, in program order.

    Returns dicts {op_index, pass_index, n, label}. The dialog now picks in two
    steps (see list_operations), but this stays: it is the natural enumeration
    for anything that wants every pass at once.
    """
    out = []
    for oi, op in enumerate((params or {}).get("operations", [])):
        n = pass_count(op)
        for i in range(n):
            out.append({"op_index": oi, "pass_index": i, "n": n,
                        "label": f"{op_label(op, oi, n)}  ·  "
                                 f"{t('pc_pass_word')} {i + 1}/{n}"})
    return out


# ──────────────────────────────────────────────────────────────────────────
# Value handling
# ──────────────────────────────────────────────────────────────────────────

_ABSENT = object()


def _as_float(v):
    try:
        if v is None or v == "" or isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm(v, kind):
    """Comparable form of a value. Booleans BEFORE numbers (float(True) == 1.0)."""
    if kind == "bool":
        return bool(v) if v is not _ABSENT else False
    if v is _ABSENT or v is None or v == "":
        return None
    if isinstance(v, bool):
        return bool(v)
    f = _as_float(v)
    return round(f, 6) if f is not None else str(v)


def _fmt(v):
    """Compact display form. Trailing-zero noise makes a diff table unreadable."""
    if v is _ABSENT or v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return t("pc_yes") if v else t("pc_no")
    f = _as_float(v)
    if f is None:
        return str(v)
    return str(int(round(f))) if abs(f - round(f)) < 1e-9 else f"{f:.3f}".rstrip("0").rstrip(".")


def _implied_default(key, kind, op, params):
    """What the engine uses when this field is absent, or _ABSENT if unknown.

    Three sources, in this order:
      * ``_IMPLIED_DEFAULTS`` for modes and the two trims that default ON;
      * ``_BOOL_DEFAULT`` (off) for every other boolean;
      * ``OP_PARAM_DEFAULTS`` for numbers and the RELATIVE hints ("= Feed").
        The hint string is useful here exactly as it is: two unset fields
        compare equal to each other while still differing from a number.
    """
    if key == "speed_mode":
        # Single source of truth (CSS is off machine-wide) — a stale "CSS" on
        # an old op is not what runs, so it must not be what is compared.
        try:
            from path_generator import resolve_speed_mode
            return resolve_speed_mode(op)
        except Exception:
            return "RPM"
    if key == "conformal_clearance_operation_specific":
        # Falls back to the GLOBAL setting, not to False.
        return bool((params or {}).get("conformal_clearance_all_operations", False))
    if key in _IMPLIED_DEFAULTS:
        return _IMPLIED_DEFAULTS[key]
    if kind == "bool":
        return _BOOL_DEFAULT
    return OP_PARAM_DEFAULTS.get(key, _ABSENT)


def _op_value(op, key, kind, params):
    """(value, is_default) for an op field, resolving an unset field to what
    the engine would actually use."""
    v = op.get(key, _ABSENT)
    if v is _ABSENT or v is None or v == "":
        return _implied_default(key, kind, op, params), True
    return v, False


def _is_inert(op, key):
    """True when this field's group toggle is OFF on this op — the value is
    stored but nothing reads it, so it must not be reported as a difference."""
    tog = _DEP_OF.get(key)
    return bool(tog) and not bool(op.get(tog, False))


# ──────────────────────────────────────────────────────────────────────────
# Staged-edit plumbing
# ──────────────────────────────────────────────────────────────────────────

def staged_op(op, edits):
    """Shallow copy of ``op`` with staged op-level edits applied.

    ``None`` removes the key (back to its default). Returns the ORIGINAL object
    when there is nothing staged, so the common path allocates nothing.
    """
    if not edits:
        return op
    out = dict(op)
    for k, v in edits.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def pins_for(staged_pins, op_index):
    """The {pass_index: {key: value}} slice compute_pass_rows() wants."""
    return {i: dict(d) for (oi, i), d in (staged_pins or {}).items()
            if oi == op_index and d}


def pass_row(params, mgr, op_index, pass_index, gui_overrides=None,
             staged_ops=None, staged_pins=None):
    """The effective row for one pass, with staged edits previewed.

    Returns (row, op) where ``row`` is None when this op has no per-pass
    geometry (cutting/bending) or the index is out of range. ``op`` is the
    staged view of the operation — never write through it.
    """
    ops = (params or {}).get("operations", [])
    if not (0 <= op_index < len(ops)):
        return None, None
    op = staged_op(ops[op_index], (staged_ops or {}).get(op_index))
    if op.get("type") in _NO_PASS_TYPES:
        return None, op
    try:
        rows = compute_pass_rows(
            op, params, mgr,
            gui_overrides=gui_overrides or {},
            base_fwd_idx=base_fwd_index(params, op_index),
            staged=pins_for(staged_pins, op_index))
    except Exception:
        # A comparison window must open even on an op the engine mirror chokes
        # on — the op-settings half is exactly what would explain the choke.
        return None, op
    for r in rows:
        if r["i"] == pass_index:
            return r, op
    return None, op


# ──────────────────────────────────────────────────────────────────────────
# Row building
# ──────────────────────────────────────────────────────────────────────────

def _eff_value(row, key):
    if row is None:
        return _ABSENT
    if key == "n_tail":
        return len(row.get("tail") or ())
    if key == "n_breaks":
        return row.get("n_breaks", 0)
    if key == "warn":
        return "  |  ".join(row.get("warnings") or ()) or _ABSENT
    v = row.get(key, _ABSENT)
    return _ABSENT if v is None else v


def _prov_source(row, key):
    """Priority-chain stage that produced an effective number, or ''."""
    field = PROV_FIELD.get(key)
    if row is None or not field:
        return ""
    rec = (row.get("prov") or {}).get(field)
    return rec.get("source", "") if rec else ""


def _universe(op_type, tilt_arm):
    uni = OP_PARAM_UNIVERSE.get(op_type, [])
    return list(uni) if tilt_arm else [k for k in uni if k not in _TILT_KEYS]


def build_rows(params, mgr, sel_a, sel_b, gui_overrides=None,
               staged_ops=None, staged_pins=None, tools=None,
               tilt_arm=False):
    """Full comparison table for two passes.

    ``sel_a`` / ``sel_b`` are (op_index, pass_index). Returns a list of row
    dicts; section headers are rows too (``kind == "header"``) so the display
    layer does not have to re-derive the grouping.

    Row keys: section, key, label, a, b (display strings), a_src, b_src
    (provenance stage label or ""), differs, delta (display string), editable,
    kind, choices, pin_key, is_default_a / is_default_b.
    """
    ops = (params or {}).get("operations", [])
    ia, pa = sel_a
    ib, pb = sel_b
    row_a, op_a = pass_row(params, mgr, ia, pa, gui_overrides, staged_ops, staged_pins)
    row_b, op_b = pass_row(params, mgr, ib, pb, gui_overrides, staged_ops, staged_pins)
    if op_a is None or op_b is None:
        return []
    type_a = op_a.get("type", "roughing")
    type_b = op_b.get("type", "roughing")

    out = []

    def _add(section, key, label, va, vb, kind="number", choices=None,
             editable=False, pin_key=None, a_src="", b_src="",
             def_a=False, def_b=False, inert_a=False, inert_b=False):
        # An inert value (its group toggle is off) compares as ABSENT: two ops
        # that both have Progressive off must not be reported as differing over
        # the fan-end angles neither of them uses.
        na = None if inert_a else _norm(va, kind)
        nb = None if inert_b else _norm(vb, kind)
        differs = na != nb
        delta = ""
        if differs:
            fa, fb = _as_float(va if va is not _ABSENT else None), \
                     _as_float(vb if vb is not _ABSENT else None)
            if fa is not None and fb is not None and not (inert_a or inert_b):
                delta = _fmt(fb - fa)
                if fb > fa:
                    delta = "+" + delta
            else:
                delta = "●"
        out.append({"section": section, "key": key, "label": label,
                    "a": _fmt(va) + (f"  ({t('pc_inert')})" if inert_a else ""),
                    "b": _fmt(vb) + (f"  ({t('pc_inert')})" if inert_b else ""),
                    "a_raw": None if va is _ABSENT else va,
                    "b_raw": None if vb is _ABSENT else vb,
                    "a_src": a_src, "b_src": b_src,
                    "is_default_a": def_a, "is_default_b": def_b,
                    "inert_a": inert_a, "inert_b": inert_b,
                    "differs": differs, "delta": delta,
                    "editable": editable, "kind": kind,
                    "choices": choices, "pin_key": pin_key})

    def _header(section, label):
        out.append({"section": section, "key": f"__hdr_{section}", "label": label,
                    "a": "", "b": "", "a_raw": None, "b_raw": None,
                    "a_src": "", "b_src": "", "is_default_a": False,
                    "is_default_b": False, "inert_a": False, "inert_b": False,
                    "differs": False, "delta": "",
                    "editable": False, "kind": "header", "choices": None,
                    "pin_key": None})

    # ── identity ──────────────────────────────────────────────────────────
    _header("pass", t("pc_sec_pass"))
    _add("pass", "op_name", t("lbl_op_name"),
         op_a.get("name") or f"#{ia + 1}", op_b.get("name") or f"#{ib + 1}", kind="text")
    _add("pass", "op_type", t("pc_row_optype"), type_a, type_b, kind="text")
    _add("pass", "pass_no", t("pc_row_passno"),
         f"{pa + 1}/{pass_count(op_a)}", f"{pb + 1}/{pass_count(op_b)}", kind="text")
    _add("pass", "enabled", t("pc_row_enabled"),
         bool(op_a.get("enabled", True)), bool(op_b.get("enabled", True)), kind="bool")

    # ── effective per-pass values ─────────────────────────────────────────
    _header("effective", t("pc_sec_effective"))
    for key, lbl_key, pin_key in EFFECTIVE_ROWS:
        va, vb = _eff_value(row_a, key), _eff_value(row_b, key)
        # Pins are roughing-only in the engine, and only where the pass exists.
        ed = bool(pin_key) and (
            (type_a in _PIN_OP_TYPES and row_a is not None) or
            (type_b in _PIN_OP_TYPES and row_b is not None))
        _add("effective", key, t(lbl_key), va, vb,
             kind="text" if key in ("source", "warn") else "number",
             editable=ed, pin_key=pin_key,
             a_src=_prov_source(row_a, key), b_src=_prov_source(row_b, key))

    # ── operation settings (union of the two types' universes) ────────────
    _header("operation", t("pc_sec_operation"))
    keys = _universe(type_a, tilt_arm)
    keys += [k for k in _universe(type_b, tilt_arm) if k not in keys]
    for key in keys:
        kind, choices = value_kind(key, tools)
        # A key outside an op type's universe does not exist for that op — show
        # a dash rather than that type's default, which it would never use.
        in_a = key in OP_PARAM_UNIVERSE.get(type_a, ())
        in_b = key in OP_PARAM_UNIVERSE.get(type_b, ())
        va, def_a = _op_value(op_a, key, kind, params) if in_a else (_ABSENT, False)
        vb, def_b = _op_value(op_b, key, kind, params) if in_b else (_ABSENT, False)
        _add("operation", key, t(OP_PARAM_LABELS.get(key, key)), va, vb,
             kind=kind, choices=choices, editable=(in_a or in_b),
             pin_key=key if key in PIN_KEYS else None,
             def_a=def_a and in_a, def_b=def_b and in_b,
             inert_a=in_a and _is_inert(op_a, key),
             inert_b=in_b and _is_inert(op_b, key))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Edit routing
# ──────────────────────────────────────────────────────────────────────────

def edit_scope_options(row, op_type):
    """Which destinations an edit to this row may have, best first.

    "pin" writes op["pass_edits"][i][key] — this pass only. "op" writes the op
    field — every pass of that operation. An operation-section row for a
    pin-capable key on a roughing op offers BOTH and the caller asks (user
    decision 2026-09-02); everything else has exactly one honest destination.
    """
    if not row.get("editable"):
        return []
    if row["section"] == "effective":
        return ["pin"] if (row.get("pin_key") and op_type in _PIN_OP_TYPES) else []
    if row["section"] == "operation":
        if row.get("pin_key") and op_type in _PIN_OP_TYPES:
            return ["pin", "op"]
        return ["op"]
    return []


def parse_value(text, kind):
    """User text → stored value. Returns (ok, value). Empty = None = 'clear'."""
    if text is None:
        return False, None
    s = str(text).strip()
    if s == "":
        return True, None
    if kind == "bool":
        low = s.lower()
        if low in ("1", "true", "yes", "on", "evet", "sí", "si", t("pc_yes").lower()):
            return True, True
        if low in ("0", "false", "no", "off", "hayır", "hayir", t("pc_no").lower()):
            return True, False
        return False, None
    if kind in ("enum", "text"):
        return True, s
    try:
        return True, float(s.replace(",", "."))
    except ValueError:
        return False, None


def stage_edit(staged_ops, staged_pins, scope, op_index, pass_index, key, value):
    """Record one staged edit in place. ``value`` None = clear the key/pin."""
    if scope == "pin":
        staged_pins.setdefault((op_index, pass_index), {})[key] = value
    else:
        staged_ops.setdefault(op_index, {})[key] = value


def staged_count(staged_ops, staged_pins):
    return (sum(len(d) for d in (staged_ops or {}).values()) +
            sum(len(d) for d in (staged_pins or {}).values()))


def apply_edits(params, staged_ops, staged_pins):
    """Write staged edits into ``params["operations"]``. Mutates.

    The caller MUST push its undo snapshot BEFORE calling this — the snapshot
    has to capture the ops list as it was, and pushing afterwards records the
    already-changed state (the bug the exit-tail editor had, pass_table.py:965).

    Returns the number of values written.
    """
    ops = (params or {}).get("operations", [])
    n = 0
    for oi, edits in (staged_ops or {}).items():
        if not (0 <= oi < len(ops)):
            continue
        for k, v in edits.items():
            if v is None:
                ops[oi].pop(k, None)
            else:
                ops[oi][k] = v
            n += 1
    for (oi, i), edits in (staged_pins or {}).items():
        if not (0 <= oi < len(ops)):
            continue
        pe = dict(ops[oi].get("pass_edits") or {})
        slot = dict(pe.get(str(i)) or pe.get(i) or {})
        for k, v in edits.items():
            if v is None:
                slot.pop(k, None)
            else:
                slot[k] = v
            n += 1
        pe.pop(i, None)
        if slot:
            pe[str(i)] = slot
        else:
            pe.pop(str(i), None)
        if pe:
            ops[oi]["pass_edits"] = pe
        else:
            ops[oi].pop("pass_edits", None)
    return n


def format_report(rows, only_diff=True):
    """Plain-text dump of the comparison, for the Copy button and the CLI."""
    lines = []
    for r in rows:
        if r["kind"] == "header":
            lines.append("")
            lines.append(f"── {r['label']} " + "─" * max(0, 44 - len(r["label"])))
            continue
        if only_diff and not r["differs"]:
            continue
        a = r["a"] + (f" ({r['a_src']})" if r["a_src"] else "")
        b = r["b"] + (f" ({r['b_src']})" if r["b_src"] else "")
        mark = "*" if r["differs"] else " "
        lines.append(f"{mark} {r['label']:<28} {a:>18}  |  {b:>18}  {r['delta']}")
    return "\n".join(lines).strip()


__all__ = [
    "PIN_KEYS", "SECTIONS", "EFFECTIVE_ROWS", "PROV_FIELD",
    "value_kind", "pass_count", "base_fwd_index", "list_passes",
    "list_operations", "pass_choices", "op_label",
    "staged_op", "pins_for", "pass_row", "build_rows",
    "edit_scope_options", "parse_value", "stage_edit", "staged_count",
    "apply_edits", "format_report",
]
