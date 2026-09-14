"""Short recipe lines under continuous motion (CMD=2) — a small advisory warning.

letter_spinningcam_velocity_path.md, item 4: the PLC re-aims a blending line
about once per scan, so a line should last a few scans. Its rule of thumb is

    suggested length = 5 x v x T        (2.5 mm at F300 and T = 0.1 s)

using each line's own programmed feed. This module only MEASURES and SUGGESTS.
It never moves a point: the suggested values go into settings that already
exist — "P2 Max Points" / "Exit Max Points", which refuse any value that would
bring the roller closer to the mandrel. That is
why this warning carries no safety risk of its own. (User, 2026-09-15: "A small
warning with simple suggestion would be nice".)

It reads what the LAST PLC-mode emission left on the path generator:
``last_plc_paths`` (the points that shipped) and ``last_path_point_feeds``
(the feed into each of them), so call it right after the generate_gcode whose
recipe is being exported.

Suggested point count for a section = floor(section length / suggested length)
+ 1, on the SHORTEST pass of the operation (the caps are per operation, one
number for every pass), never below 2. Deliberately simple: no trial run here —
the existing gap check still judges the value once it is typed in.
"""
import math

import numpy as np

LOOKAHEAD_SCANS = 5
APPROACH, FILLET, EXIT, OTHER = "approach", "fillet", "exit", "other"
CAP_KEYS = {FILLET: "p2_radius_max_points", EXIT: "exit_max_points"}


def suggested_length(feed_mm_min, scan_time_s):
    """The letter's minimum useful line length, mm."""
    return LOOKAHEAD_SCANS * (float(feed_mm_min) / 60.0) * float(scan_time_s)


def cap_value(op, key):
    """The operation's point cap as an int, or None for "no cap" (∞)."""
    raw = (op or {}).get(key)
    try:
        v = int(float(raw))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _index_of(pts, target):
    hit = np.where(np.all(np.abs(pts[:, [0, 2]] - np.asarray(target, float)[[0, 2]]) < 1e-6,
                          axis=1))[0]
    return int(hit[0]) if len(hit) else None


def section_bounds(path_gen, i, pts):
    """(index of T1, index of T2, reverse) inside the shipped points of path i,
    or None when the pass has no such structure (a back pass, a spline pass).

    T1 = end of the straight approach arm, T2 = end of the P2 radius. Both are
    always kept by the PLC decimation, so they are found by exact position. A
    reverse pass is stored back to front with its own split record — and the
    direction must come from THAT, not from comparing i1 and i2: with no P2
    radius T1 and T2 are the same point, and the index order says nothing
    (found on a real program, 2026-09-15).
    """
    full_paths = getattr(path_gen, "last_calculated_paths", None) or []
    if i >= len(full_paths):
        return None
    full = np.asarray(full_paths[i], float)
    split = (getattr(path_gen, "last_render_split_idx", {}) or {}).get(i)
    reverse = False
    if split is not None:
        t1, t2 = full[split[0]], full[split[1]]
    else:
        rv = (getattr(path_gen, "last_reverse_split_idx", {}) or {}).get(i)
        if rv is None:
            return None
        t1, t2 = full[rv[1]], full[rv[0]]
        reverse = True
    i1, i2 = _index_of(pts, t1), _index_of(pts, t2)
    if i1 is None or i2 is None:
        return None
    return i1, i2, reverse


def classify(k, bounds):
    """Section of the line from point k-1 to point k.

    Forward pass: approach arm, T1, P2 radius, T2, exit leg.
    Reverse pass: exit leg, T2, P2 radius, T1, approach arm.
    """
    if bounds is None:
        return OTHER
    i1, i2, reverse = bounds
    lo, hi = min(i1, i2), max(i1, i2)
    if lo <= k - 1 and k <= hi:
        return FILLET
    if not reverse:
        return APPROACH if k <= i1 else EXIT
    return APPROACH if k - 1 >= i1 else EXIT


def analyze(path_gen, scan_time_s):
    """One report per operation that has short lines, in operation order.

    Each report: op_no, name, count, shortest, need (the largest suggested length
    among its short lines), sections {section: count}, main (the section with the
    most), suggest {section: points} and too_short {section: True} for the two
    capped sections, current {section: cap or None}, capable (the pass shape has
    a P2 radius / exit leg the caps act on).
    """
    paths = getattr(path_gen, "last_plc_paths", None) or []
    feeds = getattr(path_gen, "last_path_point_feeds", None) or {}
    reports = {}
    for i, raw in enumerate(paths):
        rec = feeds.get(i)
        if not rec:
            continue                       # not emitted as a cut (e.g. a Point op)
        pts = np.asarray(raw, float)
        if pts.ndim != 2 or len(pts) < 2:
            continue
        f = rec["feeds"]
        op = rec["op"]
        bounds = section_bounds(path_gen, i, pts)
        rep = reports.setdefault(rec["op_idx"], {
            "op_no": rec["op_idx"] + 1,
            "name": (op or {}).get("name") or (op or {}).get("type", "?"),
            "count": 0, "shortest": math.inf, "need": 0.0,
            "sections": {}, "suggest": {}, "too_short": {}, "short_points": {},
            "current": {s: cap_value(op, k) for s, k in CAP_KEYS.items()},
            "capable": False,
        })
        if bounds is not None:
            rep["capable"] = True
        sec_len = {FILLET: 0.0, EXIT: 0.0}
        sec_need = {FILLET: 0.0, EXIT: 0.0}
        sec_segs = {FILLET: 0, EXIT: 0}
        sec_short = {FILLET: 0, EXIT: 0}
        for k in range(1, len(pts)):
            fk = f[k] if k < len(f) else None
            if not fk or fk <= 0:
                continue
            length = math.hypot(pts[k, 0] - pts[k - 1, 0], pts[k, 2] - pts[k - 1, 2])
            if length < 1e-6:
                continue                   # zero-length: the PLC skips it
            need = suggested_length(fk, scan_time_s)
            sec = classify(k, bounds)
            if sec in sec_len:
                sec_len[sec] += length
                sec_need[sec] = max(sec_need[sec], need)
                sec_segs[sec] += 1
            if length < need - 1e-9:
                rep["count"] += 1
                rep["shortest"] = min(rep["shortest"], length)
                rep["need"] = max(rep["need"], need)
                rep["sections"][sec] = rep["sections"].get(sec, 0) + 1
                if sec in sec_short:
                    sec_short[sec] += 1
        for sec in (FILLET, EXIT):
            if sec_len[sec] <= 0 or sec_need[sec] <= 0:
                continue
            n = int(math.floor(sec_len[sec] / sec_need[sec] + 1e-9)) + 1
            if sec_short[sec]:
                # Most points this section has on a pass that HAS short lines: a
                # suggestion at or above it cannot change any of them (v1.ssp: a
                # P2 radius already down to one line was offered "→ 2").
                rep["short_points"][sec] = max(rep["short_points"].get(sec, 0),
                                               sec_segs[sec] + 1)
                # A cap only acts when it is BELOW the points the section already
                # has — then the points are re-spaced evenly. A long exit leg of 7
                # unevenly spaced points with one short line would otherwise get
                # "40", which changes nothing (found on bundan devam, 2026-09-15).
                # Points - 1 = segments, and fewer points never makes lines shorter.
                n = min(n, sec_segs[sec])
            if n < 2:
                rep["too_short"][sec] = True
            else:
                rep["suggest"][sec] = min(rep["suggest"].get(sec, n), n)

    out = []
    for idx in sorted(reports):
        rep = reports[idx]
        if rep["count"] == 0:
            continue
        rep["main"] = max(rep["sections"], key=rep["sections"].get)
        out.append(rep)
    return out


def format_report(reports, t, scan_time_s, max_ops=8):
    """The warning text. ``t`` is i18n.t, passed in so this stays testable.

    Only values that were shown to work are suggested. "Lower the auto-tune
    line target" was tried for lines outside the P2 radius / exit leg and
    REMOVED: on v1.ssp a target of 400 -> 150 -> 130 -> 110 left the short
    back-pass line exactly where it was (auto-tune thins elsewhere first).
    Those lines now get a plain note instead of a "Try".
    """
    lines = [t("msg_short_head").format(T=f"{scan_time_s:g}",
                                        ex=f"{suggested_length(300, scan_time_s):.1f}"), ""]
    for rep in reports[:max_ops]:
        lines.append(t("msg_short_op").format(
            n=rep["op_no"], name=rep["name"], count=rep["count"],
            shortest=f"{rep['shortest']:.2f}", need=f"{rep['need']:.1f}",
            where=t("msg_short_where_" + rep["main"])))
        for sec in (FILLET, EXIT):
            if not rep["sections"].get(sec):
                continue
            cur = rep["current"].get(sec)
            sug = rep["suggest"].get(sec)
            if (sug is not None and (cur is None or sug < cur)
                    and sug < rep["short_points"].get(sec, 0)):
                lines.append(t("msg_short_try_cap").format(
                    param=t("lbl_p2_max_pts" if sec == FILLET else "lbl_exit_max_pts"),
                    cur="∞" if cur is None else cur, sug=sug))
            if rep["too_short"].get(sec):
                lines.append(t("msg_short_too_short_" + sec).format(
                    need=f"{rep['need']:.1f}"))
        if rep["sections"].get(APPROACH):
            # The approach arm is ONE straight line by construction (the PLC
            # decimation keeps it verbatim); no setting makes it longer.
            lines.append(t("msg_short_approach_info"))
        if rep["sections"].get(OTHER):
            lines.append(t("msg_short_other_info"))
    if len(reports) > max_ops:
        lines.append(t("msg_short_more").format(n=len(reports) - max_ops))
    lines += ["", t("msg_short_foot")]
    return "\n".join(lines)
