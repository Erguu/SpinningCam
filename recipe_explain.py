# -*- coding: utf-8 -*-
"""Why does this pass behave like that? — provenance + recipe audit.

An operation's live numbers come out of a PRIORITY CHAIN: the op's own field,
then the progressive fan, then follow-blank, then a per-pass pin. The editor
panel only shows the op's field, and the pass table's Source column is
row-level ("something here is manual") — so a single stray pin on one field of
one pass is effectively invisible. That is the top cause of "this pass acts
weird and I can't find why".

This module turns the machine's own resolution into plain sentences:

  explain_field(row, "reach")
      → "Reach = 118.0 — set by hand on this pass (pin).
         Overrides: follow blank edge 62.3 · operation setting 95.26"

  audit_operations(params, mgr)
      → every hidden override, contradiction and leftover in the whole recipe

It also lists the M-codes the program will carry (list_mcodes) — custom
commands and the cylinder block inject those, and they appear nowhere in the
operation panel.

Pure: no Tk, no file IO, never mutates params. Consumed by the pass-table
explanation bar, ui/dialogs/recipe_audit.py (Help ▸ Preview & Analyze) and
explain.py (CLI).
"""
import re

from i18n import t

# Priority-chain stage → i18n key for its plain-language name. Order here is
# the engine's order (path_generator.calculate_paths ~line 560), lowest first.
SOURCE_KEYS = ("raw", "op", "fan", "follow", "pin", "staged")

_SOURCE_LABEL = {
    "raw":    "rx_src_raw",
    "op":     "rx_src_op",
    "fan":    "rx_src_fan",
    "follow": "rx_src_follow",
    "pin":    "rx_src_pin",
    "staged": "rx_src_staged",
}

# Field key → i18n label (matches the pass-table column headings).
_FIELD_LABEL = {
    "anchor": "pt_col_anchor",
    "extend": "pt_col_extend",
    "clr":    "pt_col_clr",
    "angle":  "pt_col_angle",
    "reach":  "pt_col_reach",
}

# Per-field "materially different" threshold. Below this a pin that merely
# repeats what the automatic value would have been is noise, not a finding.
_TOL = {"anchor": 0.5, "extend": 0.5, "clr": 0.02, "angle": 0.5, "reach": 0.5}

# Stages a human set deliberately for THIS pass. A win by one of these is what
# the operator is usually hunting for.
MANUAL_SOURCES = ("pin", "staged")


def source_label(key):
    """Plain-language name of a priority-chain stage."""
    return t(_SOURCE_LABEL.get(key, "rx_src_op"))


def field_label(field):
    """Plain-language name of a resolved field."""
    return t(_FIELD_LABEL.get(field, field))


def _num(v):
    """Compact number for display (no trailing .0 noise)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(round(f))) if abs(f - round(f)) < 1e-9 else f"{f:.2f}".rstrip("0")


def explain_field(row, field):
    """One-sentence plain-language explanation of one resolved number.

    ``row`` is a dict from pass_table.compute_pass_rows. Returns "" when the
    field has no provenance record (not applicable to this op type).
    """
    rec = (row.get("prov") or {}).get(field)
    if not rec:
        return ""
    head = t("rx_explain_head").format(
        f=field_label(field), v=_num(rec["value"]), src=source_label(rec["source"]))
    losers = rec.get("losers") or []
    if not losers:
        return head
    chain = " · ".join(f"{source_label(s)} {_num(v)}" for s, v in losers)
    return head + "  " + t("rx_explain_beat").format(chain=chain)


def find_overrides(row, manual_only=True):
    """Fields on this pass whose live value came from a manual per-pass edit
    AND materially differs from what the chain would otherwise have produced.

    Returns [(field, rec)]. These are the numbers that surprise people.
    """
    out = []
    for field, rec in (row.get("prov") or {}).items():
        if manual_only and rec["source"] not in MANUAL_SOURCES:
            continue
        losers = rec.get("losers") or []
        if not losers:
            continue
        try:
            if abs(float(rec["value"]) - float(losers[0][1])) < _TOL.get(field, 0.5):
                continue          # pin merely repeats the automatic value
        except (TypeError, ValueError):
            pass
        out.append((field, rec))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Recipe audit
# ──────────────────────────────────────────────────────────────────────────

# Keys some older versions wrote into an op dict but nothing reads today. They
# are skipped by the export/copy paths (export_manager._skip) and the engine
# never looks at them — but they LOOK meaningful, so people chase them.
INERT_OP_KEYS = ("pass_overrides",)

# Severity tiers, most serious first:
#   error  — physically dangerous (roller would dig into the part)
#   hidden — a hand-set value that does NOT fit the operation's pattern. Not
#            dangerous, but it is the answer people are actually hunting for,
#            so it gets its own tier instead of being lost among the advisories.
#   warn   — advisory (air move, negative clearance, legacy override)
#   info   — deliberate and expected (hand-built ramps, disabled ops, leftovers)
SEV_ORDER = {"error": 0, "hidden": 1, "warn": 2, "info": 3}


def group_overrides(rows):
    """Per-FIELD grouping of manual overrides across one operation's passes.

    A recipe built in the pass table legitimately pins the same field on every
    pass (a hand-made ramp). The anomaly is the field pinned on only SOME
    passes — that value does not fit the pattern.

    Returns {"ramp": {field: [values, …]}, "odd": {field: [row, …]}}.
    Single source of truth: used by the audit AND by the pass table's
    outlier highlighting, so the two can never disagree.
    """
    ramp, odd = {}, {}
    if not rows:
        return {"ramp": ramp, "odd": odd}
    for field in ("anchor", "extend", "clr", "angle", "reach"):
        hit = [r for r in rows if field in dict(find_overrides(r))]
        if not hit:
            continue
        if len(hit) == len(rows):
            ramp[field] = [r["prov"][field]["value"] for r in hit]
        else:
            odd[field] = hit
    return {"ramp": ramp, "odd": odd}


def outlier_fields(rows):
    """{pass index: {field, …}} for the values that do not fit the pattern."""
    out = {}
    for field, hit in group_overrides(rows)["odd"].items():
        for r in hit:
            out.setdefault(r["i"], set()).add(field)
    return out


def _short(name, n=44):
    """Operation names in a copied recipe grow '(copy) (copy) …' without bound
    and would push the actual finding off the line."""
    s = str(name)
    return s if len(s) <= n else s[:n - 1] + "…"


def _ranges(nums):
    """[1,2,3,7,8] → '#1–#3, #7–#8' — keeps long index lists readable."""
    if not nums:
        return ""
    nums = sorted(set(nums))
    out, start, prev = [], nums[0], nums[0]
    for x in nums[1:] + [None]:
        if x != prev + 1:
            out.append(f"#{start}" if start == prev else f"#{start}–#{prev}")
            start = x
        prev = x
    return ", ".join(out)


# ── M-codes the generated program will contain ───────────────────────────
# Custom commands and the cylinder block inject M-codes that appear nowhere in
# the operation panel, so a recipe can carry actuator commands its author never
# sees. Listing them is deliberately DUMB: nothing here judges whether a set is
# right or wrong (every machine wires these differently), it only reports what
# the post-processor will emit and in what order. The bug this was written for
# — valve commands firing while the cylinder extend was switched off — is
# obvious the moment the list is in front of you, with no rule needed.
_MCODE_RE = re.compile(r"M\s*(\d+)", re.IGNORECASE)

# Sort keys around the pass numbers: program_start runs before every pass, the
# Z-triggered ones cannot be placed on the pass axis at all so they trail.
_MC_EARLY = -1
_MC_LATE = 10 ** 6


def _mcode_num(cmd):
    """Bare M-code number from a command string ('M41 P2' → '41'), or None."""
    m = _MCODE_RE.search(str(cmd or ""))
    return m.group(1) if m else None


def orphan_pass_commands(params, total_passes):
    """Pass-triggered commands whose pass number does not exist in this program.

    A "pass" trigger is pinned to a global pass NUMBER. Add or remove a pass,
    reorder operations, or disable one, and a command can end up pointing past
    the end of the program — where it simply never fires, with nothing said.
    For an actuator command (a clamp that never releases) that silence is the
    dangerous part.

    Returns ``[{index, cmd, value, note}, ...]`` in table order. Pure.
    """
    out = []
    try:
        total = int(total_passes)
    except (TypeError, ValueError):
        return out
    for i, c in enumerate(params.get("custom_commands") or []):
        if not isinstance(c, dict) or c.get("trigger") != "pass":
            continue
        if not str(c.get("cmd", "") or "").strip():
            continue
        try:
            v = int(float(c.get("value", 0) or 0))
        except (TypeError, ValueError):
            continue
        if v > total or v < 1:
            out.append({"index": i, "cmd": c.get("cmd", ""), "value": v,
                        "note": c.get("note", "")})
    return out


# Resolutions offered when a command points at a pass that does not exist.
ORPHAN_LAST = "last"    # clamp it onto the final pass
ORPHAN_SKIP = "skip"    # leave it out of THIS output only


def apply_orphan_action(params, total_passes, action):
    """Copy of ``params`` with out-of-range pass commands resolved.

    Never mutates the input: the caller exports the copy, so the user's command
    table keeps the original row and the decision applies to this file only.
    """
    orphans = orphan_pass_commands(params, total_passes)
    if not orphans:
        return params
    bad = {o["index"] for o in orphans}
    try:
        last = max(1, int(total_passes))
    except (TypeError, ValueError):
        last = 1

    new_cmds = []
    for i, c in enumerate(params.get("custom_commands") or []):
        if i not in bad:
            new_cmds.append(c)
            continue
        if action == ORPHAN_LAST:
            moved = dict(c)
            moved["value"] = last
            new_cmds.append(moved)
        # ORPHAN_SKIP: dropped from this copy only
    out = dict(params)
    out["custom_commands"] = new_cmds
    return out


def commanded_cylinder_position(params, code="40"):
    """Extension (mm) the recipe actually commands for the cylinder, else 0.0.

    Reads the P value of the first M40 in custom_commands. Since 2026-07-30 the
    cylinder has no dedicated enable/position fields — M40 is an ordinary custom
    command — so the 3D view derives its extension from the command instead of a
    separate setting that could silently disagree with it. No command, no
    extension. Pure.
    """
    want = str(code).lstrip("Mm")
    for c in (params.get("custom_commands") or []):
        cmd = str(c.get("cmd", "") or "")
        if _mcode_num(cmd) != want:
            continue
        m = re.search(r"P\s*(\d*\.?\d+)", cmd, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return 0.0
    return 0.0


def list_mcodes(params):
    """Every M-code this recipe will emit, in emission order.

    Mirrors ``path_generator.generate_gcode``: the cylinder block first (it is
    written before the spindle starts), then the pass-triggered custom
    commands in pass order, then the Z-triggered ones. Returns a list of
    ``(command, when, description)`` triples. Read-only.
    """
    descs = params.get("mcode_descriptions") or {}
    out = []

    # Cylinder block — path_generator.py guards on BOTH the enable flag and a
    # positive position, so mirror both or the list would promise a line the
    # post never writes.
    try:
        cyl_pos = float(params.get("cylinder_position_mm", 0.0) or 0.0)
    except (TypeError, ValueError):
        cyl_pos = 0.0
    if params.get("cylinder_enabled") and cyl_pos > 0:
        out.append((f"M40 P{cyl_pos:.1f}", t("rx_mc_start"), descs.get("40", "")))

    rows = []
    for c in (params.get("custom_commands") or []):
        cmd = str(c.get("cmd", "") or "").strip()
        if not cmd:
            continue
        trig = c.get("trigger")
        note = str(c.get("note", "") or "").strip()
        try:
            val = float(c.get("value", 0) or 0)
        except (TypeError, ValueError):
            val = 0.0
        if trig == "program_start":
            rows.append((_MC_EARLY, cmd, t("rx_mc_start"), note))
        elif trig == "pass":
            rows.append((int(val), cmd, t("rx_mc_pass").format(n=int(val)), note))
        elif trig == "z":
            rows.append((_MC_LATE, cmd, t("rx_mc_z").format(v=_num(val)), note))
        else:
            rows.append((_MC_LATE + 1, cmd, str(trig or "?"), note))

    # The entry's own note wins over the code's shared description: the
    # description covers every parameter value of that code ("1 for relax, 2
    # for retract") and so cannot say which value THIS line is.
    for _, cmd, when, note in sorted(rows, key=lambda r: r[0]):
        num = _mcode_num(cmd)
        out.append((cmd, when, note or (descs.get(num, "") if num else "")))
    return out


def _finding(sev, msg_key, op_i=None, op_name=None, pas=None, field=None, **kw):
    # NB: **kw carries the message's format fields, so no parameter here may
    # share a name with one of them (a 'key' param collided with rx_f_inert).
    return {"sev": sev, "op": op_i, "op_name": op_name, "pass": pas,
            "field": field, "msg": t(msg_key).format(**kw) if kw else t(msg_key)}


def audit_operations(params, mgr=None, gui_overrides=None, tools=None):
    """Everything in this recipe that could make a pass behave unexpectedly.

    ``mgr`` (MandrelManager) unlocks the per-pass checks; without it (e.g. the
    mandrel STEP is missing) the static checks still run. Read-only.

    Returns findings sorted by severity: {sev, op, op_name, pass, field, msg}.
    """
    findings = []
    ops = params.get("operations") or []
    gui_overrides = gui_overrides or {}
    tool_radius = {}
    for tl in (tools or []):
        try:
            tool_radius[tl.get("id")] = float(tl.get("radius"))
        except (TypeError, ValueError):
            pass

    names = {}
    fwd_idx = 0
    inert_ops, disabled_ops = {}, []
    for i, op in enumerate(ops):
        name = _short(op.get("name") or op.get("type") or "?")
        enabled = op.get("enabled", True)
        n_pass = 1 if op.get("type") in ("cutting", "bending") else int(op.get("count", 1) or 1)
        names.setdefault(name, []).append(i + 1)

        # Leftover data that reads like a setting but is ignored by the engine.
        # Collected, not emitted per-op: these repeat across every operation in
        # a copied recipe and would bury the findings that actually matter.
        for k in INERT_OP_KEYS:
            if op.get(k):
                inert_ops.setdefault(k, []).append(i + 1)

        # Legacy hidden per-pass overrides (the pre-pass_edits mechanism).
        if enabled:
            for p in range(n_pass):
                if gui_overrides.get(fwd_idx + p):
                    findings.append(_finding("warn", "rx_f_legacy", i, name, pas=p + 1))

        # Roller reach shorter than the roller itself → the path would drive
        # the disc into the part (tools.json rule: r_tool >= radius).
        rt, rad = op.get("r_tool"), tool_radius.get(op.get("tool_id"))
        try:
            if rt is not None and rad is not None and float(rt) < rad - 0.01:
                findings.append(_finding("error", "rx_f_gouge", i, name,
                                         rt=_num(rt), rad=_num(rad),
                                         tool=op.get("tool_id")))
        except (TypeError, ValueError):
            pass

        # Until 2026-08-30 the #82 leg swap silently discarded every exit shape
        # on a reverse pass — you could type a bow and the machine cut straight.
        # With the swap deleted those values CUT. A program written while they
        # were inert is the one case where this release changes the metal, so
        # name the operations rather than leaving it to be discovered on a part.
        if (enabled and op.get("direction", "forward") == "reverse"
                and op.get("pass_shape", "spline") in ("linear_approach", "linear_full")):
            _shapes = [k for k in ("exit_bow", "exit_arc_angle", "exit_mid_rotation")
                       if op.get(k) not in (None, "", 0, 0.0)]
            if _shapes:
                findings.append(_finding("warn", "rx_f_rev_shape", i, name,
                                         fields=", ".join(_shapes)))

        # A back pass is the return half of a forward pass, run without
        # stopping — so a reverse pass already IS one and the engine does not
        # build a second (#49, user 2026-08-29). The checkbox stays ticked in
        # the file, so without this the operator has a setting that reads as
        # active and produces nothing.
        if (enabled and op.get("back_pass_enabled", False)
                and op.get("direction", "forward") == "reverse"):
            findings.append(_finding("warn", "rx_f_bp_reverse", i, name))

        if not enabled:
            disabled_ops.append(i + 1)
        else:
            fwd_idx += n_pass

        # Per-pass checks need the resolver (and therefore the mandrel).
        if mgr is None or not enabled:
            continue
        try:
            from ui.dialogs.pass_table import compute_pass_rows
            rows = compute_pass_rows(op, params, mgr)
        except Exception:
            continue
        # Group per FIELD across the op's passes, not per pass. A recipe built
        # in the pass table legitimately pins the same field on every pass (a
        # hand-made ramp) — flagging each one buries the finding that matters.
        # The anomaly is the field pinned on only SOME passes: that is the value
        # that does not fit the pattern, and it is what people actually hunt.
        grouped = group_overrides(rows)
        for field, vals in grouped["ramp"].items():
            # Pinned everywhere → a deliberate hand-built ramp, not an anomaly.
            # A single-pass op has no pattern to deviate from.
            findings.append(_finding(
                "info", "rx_f_single" if len(rows) == 1 else "rx_f_ramp",
                i, name, field=field, f=field_label(field), n=len(rows),
                a=_num(vals[0]), b=_num(vals[-1])))
        for field, hit in grouped["odd"].items():
            vals = [r["prov"][field]["value"] for r in hit]
            rest = next((r for r in rows if field not in dict(find_overrides(r))), None)
            auto_rec = (rest or {}).get("prov", {}).get(field) if rest else None
            auto_src, auto_val = ((auto_rec["source"], auto_rec["value"]) if auto_rec
                                  else (hit[0]["prov"][field]["losers"] or [(None, None)])[0])
            findings.append(_finding(
                "hidden", "rx_f_odd", i, name, pas=hit[0]["i"] + 1, field=field,
                f=field_label(field), k=len(hit), n=len(rows),
                list=_ranges([r["i"] + 1 for r in hit]).replace("#", ""),
                v=" / ".join(_num(v) for v in vals),
                auto=source_label(auto_src) if auto_src else "?",
                av=_num(auto_val)))

        neg = [r for r in rows
               if (r.get("prov") or {}).get("clr", {}).get("value", 0) < -0.001]
        if neg:
            findings.append(_finding("warn", "rx_f_negclr", i, name,
                                     pas=neg[0]["i"] + 1, field="clr",
                                     v=_num(neg[0]["prov"]["clr"]["value"]),
                                     list=_ranges([r["i"] + 1 for r in neg]).replace("#", "")))

        # Identical resolver warnings repeat on every pass of a fanned op.
        by_msg = {}
        for row in rows:
            for w in row.get("warnings") or []:
                by_msg.setdefault(w, []).append(row["i"] + 1)
        for w, passes in by_msg.items():
            suffix = "" if len(passes) == 1 else \
                "  (" + t("rx_passes").format(list=_ranges(passes).replace("#", "")) + ")"
            findings.append({"sev": "warn", "op": i, "op_name": name,
                             "pass": passes[0], "field": None, "msg": w + suffix})

    # ── collapsed file-level notes (one line each, not one per operation) ──
    # M-codes first among the notes: they describe the whole program, and they
    # are the one class of content the operation panel cannot show at all.
    for cmd, when, desc in list_mcodes(params):
        findings.append(_finding("info", "rx_mc_line", cmd=cmd, when=when,
                                 desc=desc or t("rx_mc_nodesc")))

    for k, idxs in inert_ops.items():
        findings.append(_finding("info", "rx_f_inert", key=k, n=len(idxs)))
    if disabled_ops:
        findings.append(_finding("info", "rx_f_disabled", n=len(disabled_ops),
                                 total=len(ops), list=_ranges(disabled_ops)))
    dup = {n: ix for n, ix in names.items() if len(ix) > 1}
    if dup:
        findings.append(_finding(
            "info", "rx_f_dupname", n=sum(len(v) for v in dup.values()),
            g=len(dup), list=" / ".join(_ranges(v) for v in dup.values())))

    findings.sort(key=lambda f: (SEV_ORDER.get(f["sev"], 3), f["op"] or 0,
                                 f["pass"] or 0))
    return findings


def format_report(findings, width=100):
    """Findings as plain text — for the CLI and the dialog's Copy button."""
    if not findings:
        return t("rx_none")
    mark = {"error": "!!", "hidden": "=>", "warn": " !", "info": "  "}
    out = []
    for f in findings:
        where = ""
        if f.get("op") is not None:
            where = f"op #{f['op'] + 1} {f.get('op_name') or ''}".strip()
            if f.get("pass"):
                where += f", pass {f['pass']}"
        out.append(f"{mark.get(f['sev'], '  ')} [{f['sev']:<5}] {where}: {f['msg']}"[:width * 3])
    return "\n".join(out)
