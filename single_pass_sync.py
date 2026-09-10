"""
single_pass_sync.py — ONE number when an operation has only one pass.

The problem this solves (customer report 2026-09-10)
----------------------------------------------------
Some operators run a SINGLE pass per operation, on purpose, to keep full
control of every pass. They then also reach for the pass table and pin a
per-pass value there. Now two numbers describe the same single pass: the
operation says Clearance 1.0 and the pass table says 0.5. The engine uses the
pin (0.5), but the operation editor keeps showing 1.0 — so the operator sees a
number that is not the one being run, and does not know which to trust.

The rule
--------
When an operation has exactly ONE pass, the pass IS the operation. So the
pass's value is lifted UP into the operation field and the pin is deleted.
Both places then read the same number, and — this is the point — the machine
runs EXACTLY what it ran before, because the pin was already the value the
engine used.

Why the lift is toolpath-neutral
--------------------------------
Every pin in ``PIN_TO_OP`` sits at the TOP of its resolution chain in
``path_generator.calculate_paths``, and with ``count == 1`` the stages between
the operation field and the pin are all inactive:

  * ``target_z``    — pass 0 of a 1-pass op is ``start_h`` = ``op["start_z"]``
                      verbatim (path_generator.py, ``if count <= 1``). No
                      interpolation to step over.
  * ``p2_z_extend`` — the pin plainly replaces the op field.
  * ``clearance``   — the pin plainly replaces the op field (or the global
                      fallback when the op field is unset).
  * ``pass_angle``  — the progressive angle fan needs ``count > 1``, so with one
                      pass the op field goes straight through to the pin.
  * ``reach``       — the progressive reach fan needs ``count > 1`` too, BUT
                      follow-blank sits BETWEEN the op field and the pin and
                      beats the op field. See ``blocked_reason``.

TWO pins are therefore NOT liftable, and this module refuses to lift them
rather than quietly changing the path:

  1. ``reach`` while "follow blank sheet" is on for the operation. The pin
     beats follow-blank; ``op["reach"]`` does not. Lifting it would hand the
     pass to follow-blank and change the stroke length.
  2. ``pass_angle`` while the operation is in RAW exit mode (its Pass Angle
     field is empty). The engine ignores an angle pin there entirely
     (``if _pa_deg is not None`` gates the whole polar block), so lifting the
     pin would switch the operation from raw to polar — a large change.

Scope
-----
* ROUGHING only, because the engine reads these pins on roughing only
  (``is_finish`` blanks all five in ``calculate_paths``). A pin sitting on a
  finishing op is dead data; lifting it into the op field WOULD change the
  path, so it is left alone.
* Pass slot ``"0"`` only. Slots ``1..n`` on a 1-pass op are residue from when
  the op had more passes; the engine never reads them. They are left untouched
  (the recipe-audit window already reports residual data) — deleting operator
  data is not this module's job.
* ``exit_points`` (hand-drawn tail, #100) and ``exit_breaks`` (#102) live in
  the same pass slot and have NO operation-level twin. They are preserved
  exactly as they are.

This module is PURE: no Tk, no logging side effects, no params dict. It is the
single source of truth for both the pass-table dialog and the tests.
"""

# Pin key (pass table) → operation field that means the same thing when the
# operation has exactly one pass. Same names except the anchor: a 1-pass op
# takes its contact Z straight from Zone Start Z.
PIN_TO_OP = {
    "target_z":    "start_z",
    "p2_z_extend": "p2_z_extend",
    "clearance":   "clearance",
    "pass_angle":  "pass_angle",
    "reach":       "reach",
}

# Only these op types have per-pass pins the engine actually reads.
# Mirrors pass_compare._PIN_OP_TYPES and the is_finish gate in calculate_paths.
SYNC_OP_TYPES = ("roughing",)

# i18n keys for the two refusals, so the UI can explain itself.
BLOCK_FOLLOW_BLANK = "sps_block_follow"
BLOCK_RAW_ANGLE = "sps_block_raw"


def _count(op):
    """Pass count as an int, tolerating "" / None / "3" / 3.0 like the engine."""
    try:
        return int(float(op.get("count", 1)))
    except (TypeError, ValueError):
        return 1


def _num(v):
    """Stored value → float, or None when it is absent/blank/garbage.

    Same tolerance as ``path_generator._pe_f`` — a pin the engine would ignore
    must not be lifted either, or an unreadable string would land in the
    operation field and change what the operator sees.
    """
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def applies(op):
    """True when ``op`` is the single-pass case this module governs."""
    if not op:
        return False
    return op.get("type") in SYNC_OP_TYPES and _count(op) == 1


def pass_slot(op):
    """The pass-0 pin dict, or {}. Accepts the str and int keying both exist."""
    pe = (op or {}).get("pass_edits") or {}
    return pe.get("0") or pe.get(0) or {}


def blocked_reason(op, pin_key):
    """i18n key naming why this pin may NOT be lifted, or None if it may.

    See the module docstring for why these two are exceptions. Both answers
    depend on OTHER operation fields, so this must be asked per operation, not
    decided once per key.
    """
    if pin_key == "reach" and (op or {}).get("reach_follow_blank", False):
        return BLOCK_FOLLOW_BLANK
    if pin_key == "pass_angle" and (op or {}).get("pass_angle") in (None, ""):
        return BLOCK_RAW_ANGLE
    return None


def plan(op):
    """What lifting this operation would do. Reads only — never mutates.

    Returns ``(merges, blocks)`` where::

        merges = [(pin_key, op_key, value, op_current), ...]
        blocks = [(pin_key, reason_i18n_key), ...]

    ``op_current`` is the operation's value before the lift, so a caller can
    say "1.0 → 0.5" instead of only naming the winner. ``merges`` is empty when
    nothing needs doing, which is the normal case.
    """
    merges, blocks = [], []
    if not applies(op):
        return merges, blocks
    slot = pass_slot(op)
    for pin_key, op_key in PIN_TO_OP.items():
        if pin_key not in slot:
            continue
        value = _num(slot.get(pin_key))
        if value is None:
            continue
        reason = blocked_reason(op, pin_key)
        if reason:
            blocks.append((pin_key, reason))
            continue
        merges.append((pin_key, op_key, value, op.get(op_key)))
    return merges, blocks


def differs(op):
    """The subset of ``plan``'s merges where the two numbers actually disagree.

    A pin that merely repeats the operation's own value is noise, not the
    confusion the customer described. Callers that want to report "these two
    numbers disagree" use this; callers that want to clean up use ``plan``.
    """
    out = []
    for pin_key, op_key, value, cur in plan(op)[0]:
        cur_n = _num(cur)
        if cur_n is None or abs(cur_n - value) > 1e-9:
            out.append((pin_key, op_key, value, cur))
    return out


def merge_op(op):
    """Lift pass-0 pins into the operation fields. MUTATES ``op``.

    Returns the ``merges`` list that was applied (empty = nothing changed, and
    ``op`` was not touched at all). The caller MUST push its undo snapshot
    BEFORE calling — same contract as ``pass_compare.apply_edits``.

    Blocked pins stay exactly where they are, as do ``exit_points`` /
    ``exit_breaks`` and any residual slots 1..n.
    """
    merges, _blocks = plan(op)
    if not merges:
        return []

    slot = dict(pass_slot(op))
    for pin_key, op_key, value, _cur in merges:
        op[op_key] = value
        slot.pop(pin_key, None)

    pe = dict(op.get("pass_edits") or {})
    pe.pop(0, None)          # drop the int-keyed twin if this op had one
    if slot:
        pe["0"] = slot       # waypoints / break points / blocked pins survive
    else:
        pe.pop("0", None)
    if pe:
        op["pass_edits"] = pe
    else:
        op.pop("pass_edits", None)
    return merges


def scan(ops):
    """Every operation in a program that has something to lift.

    Returns ``[(op_index, merges, blocks), ...]``, skipping operations with
    nothing to merge. Lets a caller report the whole program in one line
    instead of making the operator open twenty pass tables.
    """
    out = []
    for i, op in enumerate(ops or []):
        merges, blocks = plan(op)
        if merges:
            out.append((i, merges, blocks))
    return out


def merge_all(ops):
    """``merge_op`` across a program. MUTATES. Returns ``[(op_index, merges)]``."""
    done = []
    for i, op in enumerate(ops or []):
        merges = merge_op(op)
        if merges:
            done.append((i, merges))
    return done


__all__ = [
    "PIN_TO_OP", "SYNC_OP_TYPES", "BLOCK_FOLLOW_BLANK", "BLOCK_RAW_ANGLE",
    "applies", "pass_slot", "blocked_reason", "plan", "differs",
    "merge_op", "scan", "merge_all",
]
