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

Pure: no Tk, no file IO, never mutates params. Consumed by the pass-table
explanation bar, ui/dialogs/recipe_audit.py (Tools ▸ Why is my pass weird?)
and explain.py (CLI).
"""
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
