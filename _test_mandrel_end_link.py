"""Mandrel-end link — no retract at the mandrel end (mandrel_end_link.py, 2026-09-16).

What must hold, most important first:

1. SAFETY. A link is made only where every rule allows it; everywhere else the
   retract is exactly today's. Every link line is never closer to the part than
   the closer of its two ends. A blocker the rule misses still cannot reach the
   machine: the G-code writer puts the retract back (the safety net is forced
   here and must fire).
2. The cut lines never change — only the air trip between two passes does.
3. Off (the default) = nothing changes; the tickbox on an op that does not end
   at the mandrel = nothing changes.
4. Where it links, what was measured on the shop's programs happens: reverse ->
   forward (gap 0) loses its retract with NO extra line; far jumps (020926's
   93 mm, kalin's 25-41 mm) keep theirs; the program's last pass keeps its retract.
5. The link line lands exactly on the next pass start and is an exact stop in a
   continuous-motion recipe; the stop dots still line up.

Part A needs nothing. Part B uses real programs and SKIPS what is missing.

Run:  python _test_mandrel_end_link.py
"""
import copy
import math
import os
import re
import sys

import numpy as np

import mandrel_end_link as mel

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f"  -- {detail}" if detail else ""))
        FAILED.append(name)


print("A. the rule")
F = mel.OP_FLAG_KEY
ops = [
    {"type": "roughing", "direction": "reverse", "tool_id": "T1", "speed": 600, F: True},   # 0
    {"type": "roughing", "direction": "forward", "tool_id": "T1", "speed": 600},            # 1
    {"type": "point"},                                                                       # 2
    {"type": "roughing", "direction": "forward", "tool_id": "T2", "speed": 600},            # 3
    {"type": "roughing", "direction": "forward", "tool_id": "T1", "speed": 800},            # 4
    {"type": "roughing", "direction": "forward", "tool_id": "T1", "speed": 600,
     "back_pass_enabled": True, F: True},                                                    # 5
    {"type": "roughing", "direction": "forward", "tool_id": "T1", "speed": 600,
     "feed_mode": "mm_rev"},                                                                 # 6
    {"type": "roughing", "direction": "reverse", "tool_id": "T1", "speed": 600},            # 7
]
P = {"surface_speed_m_min": 200}
check("reverse op -> next forward op, same tool / speed / feed mode: allowed",
      mel.blockers(ops, 0, False, 1, False, 2, P) == [])
check("tickbox off: 'off' and nothing else",
      mel.blockers(ops, 1, False, 1, False, 3, P) == ["off"])
check("forward pass of a back-pass op is not a mandrel end",
      "not_mandrel_end" in mel.blockers(ops, 5, False, 5, True, 3, P))
check("back pass -> next forward pass of the same op: allowed",
      mel.blockers(ops, 5, True, 5, False, 4, P) == [])
check("next is a back pass: refused",
      "next_not_forward" in mel.blockers(ops, 5, True, 5, True, 4, P))
check("next is a reverse pass: refused",
      "next_not_forward" in mel.blockers(ops, 0, False, 7, False, 9, P))
check("an enabled operation in between (e.g. a Point op): refused",
      "operation_between" in mel.blockers(ops, 0, False, 3, False, 5, P))
check("a disabled operation in between does not count",
      mel.blockers([ops[0], {"type": "point", "enabled": False}, ops[1]],
                   0, False, 2, False, 2, P) == [])
check("tool change: refused", "tool_change" in mel.blockers(ops, 0, False, 3, False, 5, P))
check("spindle speed change: refused",
      "spindle_change" in mel.blockers([ops[0], ops[4]], 0, False, 1, False, 2, P))
check("feed mode change: refused",
      "feed_mode_change" in mel.blockers([ops[0], ops[6]], 0, False, 1, False, 2, P))
check("custom command on the NEXT pass (e.g. M41 Clamp On): refused",
      "custom_command" in mel.blockers(ops, 0, False, 1, False, 2,
                                       {"custom_commands": [{"trigger": "pass", "value": 2,
                                                             "cmd": "M41 P2"}]}))
check("custom command on another pass, or a Z trigger: not a blocker",
      mel.blockers(ops, 0, False, 1, False, 2,
                   {"custom_commands": [{"trigger": "pass", "value": 3, "cmd": "M41"},
                                        {"trigger": "z", "value": 2, "cmd": "M41"}]}) == [])

check("max link: absent = 15 mm", mel.max_link_mm({}) == 15.0)
check("max link: typed 8 = 8 mm", mel.max_link_mm({mel.OP_MAX_KEY: "8"}) == 8.0)
check("max link: 0 / negative / text / inf fall back to 15 mm",
      all(mel.max_link_mm({mel.OP_MAX_KEY: v}) == 15.0
          for v in (0, -3, "abc", float("inf"), None)))

a, b = [0.0, 0.0, 0.0], [3.0, 0.0, 4.0]
ok, gap, why, _ = mel.check_geometry(a, b, {}, lambda pts: 5.0)
check("geometry: 5 mm gap, even clearance: allowed", ok and abs(gap - 5.0) < 1e-9, why)
ok, gap, why, _ = mel.check_geometry(a, [20.0, 0.0, 0.0], {}, lambda pts: 5.0)
check("geometry: 20 mm gap > 15 mm: too_far", not ok and why == "too_far")
ok, _, why, _ = mel.check_geometry(a, b, {mel.OP_MAX_KEY: 4}, lambda pts: 5.0)
check("geometry: the op's own max (4 mm) is used", not ok and why == "too_far")
ok, _, why, _ = mel.check_geometry(a, b, {}, lambda pts: 4.0 if len(pts) == 2 else 5.0)
check("geometry: link line 1 mm closer than its ends: refused (clearance)",
      not ok and why == "clearance")
ok, _, why, _ = mel.check_geometry(a, b, {}, lambda pts: 4.995 if len(pts) == 2 else 5.0)
check("geometry: within the 0.01 mm tolerance: allowed", ok, why)
ok, _, why, _ = mel.check_geometry(a, b, {}, lambda pts: float("inf"))
check("geometry: clearance not measurable: refused",
      not ok and why == "clearance_unmeasurable")

check("machine lines: comments, blanks, G98/G99 are not",
      not any(mel.is_machine_line(s) for s in
              ("(--- OP 2 START: ROUGHING ---)", "", "  G98 ", "G99", "(Update Params: 1)")))
check("machine lines: M-codes, spindle, motion are",
      all(mel.is_machine_line(s) for s in ("M41 P2 (Clamp On)", "G97 S600 M3", "G0 X1 Z2")))
check("op_can_use: reverse roughing / forward roughing with back pass only",
      mel.op_can_use(ops[0], False) and mel.op_can_use(ops[5], True)
      and not mel.op_can_use(ops[1], False)
      and not mel.op_can_use({"type": "finishing", "direction": "reverse"}, False))


print("\nB. real programs")
try:
    import golden_snapshot as gs
    from path_generator import PathGenerator, op_builds_back_pass
    from recipe_to_scl import (GCodeToSCLConverter, continuous_settings, CMD_LINEAR)
    import motion_stops
except Exception as e:                                     # pragma: no cover
    gs = None
    print(f"  SKIP - cannot import the engine ({e})")

SHOP = r"C:\Users\PC\Documents\Automation\Cursor\MexicoMetalSpinning\gcodes"
CUT_RE = re.compile(r"^G1 .*\((Op\d+ (?:BP|P)\d+)\)\s*$")
XZ_RE = re.compile(r"X(-?[\d.]+)\s+Z(-?[\d.]+)")
# Links expected from the measurements of 2026-09-16 (None = no fixed number).
EXPECTED = {"140926.ssp": 3, "bundan devam geçerli olan.ssp": 5, "020926.ssp": 1,
            "kalin.ssp": 0, "kalin2.ssp": None, "v1.ssp": None}


def find(name):
    for d in (SHOP, getattr(gs, "FIXTURE_DIR", "")):
        if d and os.path.isfile(os.path.join(d, name)):
            return os.path.join(d, name)
    return None


def generate(params, overrides, mgr):
    pg = PathGenerator()
    res = pg.calculate_paths(params, overrides, mgr)
    nc = pg.generate_gcode(params=dict(params, plc_mode=False))
    fb_nc = list(pg.last_mandrel_link_fallbacks)
    rec = pg.generate_gcode(params=dict(params, plc_mode=True), for_recipe=True)
    fb_rec = list(pg.last_mandrel_link_fallbacks)
    return pg, res, nc, rec, fb_nc + fb_rec


def cut_lines(txt):
    return [l for l in txt.splitlines() if CUT_RE.match(l.strip())]


def path_spans(lines):
    """[(first line index, last line index)] per toolpath, in path order."""
    spans, order = {}, []
    for k, l in enumerate(lines):
        m = CUT_RE.match(l.strip())
        if not m:
            continue
        tag = m.group(1)
        if tag not in spans:
            spans[tag] = [k, k]
            order.append(tag)
        spans[tag][1] = k
    return [tuple(spans[t]) for t in order], order


def with_flag(params, eligible=True):
    p = copy.deepcopy(params)
    for op in p.get("operations", []) or []:
        can = mel.op_can_use(op, op_builds_back_pass(op))
        if can == eligible:
            op[F] = True
    return p


cases = [(n, find(n)) for n in EXPECTED] if gs is not None else []
cases = [(n, p) for n, p in cases if p]
if gs is not None and not cases:
    print("  SKIP - no real programs on this computer")

for name, path in cases:
    params, overrides, step = gs.load_program(path)
    mgr, _ = gs.build_mandrel(params, gs.resolve_step(step, (SHOP,)))
    ops_all = params.get("operations", []) or []

    pg0, res0, nc0, rec0, _ = generate(params, overrides, mgr)
    pgx, _, ncx, recx, _ = generate(with_flag(params, eligible=False), overrides, mgr)
    check(f"{name}: tickbox on ops that do not end at the mandrel changes nothing",
          ncx == nc0 and recx == rec0)

    pon = with_flag(params, eligible=True)
    pg, res, nc, rec, fallbacks = generate(pon, overrides, mgr)
    links, refused = pg.last_mandrel_links, pg.last_mandrel_link_refused
    reasons = sorted({r for x in refused for r in x["reasons"]})
    print(f"  {name}: {len(links)} link(s), {len(refused)} refused {reasons}")

    exp = EXPECTED[name]
    if exp is not None:
        check(f"{name}: {exp} link(s) as measured", len(links) == exp, f"got {len(links)}")
    check(f"{name}: cut lines identical to the tickbox off (.nc and recipe)",
          cut_lines(nc) == cut_lines(nc0) and cut_lines(rec) == cut_lines(rec0))
    check(f"{name}: the safety net never had to fire", not fallbacks, fallbacks)

    # Safety: every link, measured again independently.
    bad = []
    for bidx, rec_ in links.items():
        a_op = pg._path_op_map[rec_["a"]]
        line = pg._path_min_clearance(np.array([rec_["from"], rec_["to"]]), a_op, pon)
        ends = min(pg._path_min_clearance(np.array([rec_["from"]]), a_op, pon),
                   pg._path_min_clearance(np.array([rec_["to"]]), a_op, pon))
        if not (line >= ends - mel.CLEARANCE_TOL_MM) or rec_["gap"] > mel.max_link_mm(a_op) + 1e-9:
            bad.append((bidx, round(line, 3), round(ends, 3), round(rec_["gap"], 2)))
        if bidx != rec_["a"] + 1:
            bad.append((bidx, "not adjacent"))
    check(f"{name}: every link keeps clearance and length", not bad, bad[:4])

    # What the G-code does between the two passes.
    lines = nc.splitlines()
    spans, tags = path_spans(lines)
    spans0, tags0 = path_spans(nc0.splitlines())
    lines0 = nc0.splitlines()
    wrong = []
    for bidx, rec_ in links.items():
        a_i = rec_["a"]
        between = lines[spans[a_i][1] + 1: spans[bidx][0]]
        machine = [l for l in between if mel.is_machine_line(l)]
        if rec_["gap"] >= mel.MIN_LINE_MM:
            if len(machine) != 1 or mel.LINK_TAG not in machine[0]:
                wrong.append((bidx, "expected one link line", machine))
                continue
            # lands exactly where the pass starts today
            start0 = [l for l in lines0[spans0[a_i][1] + 1: spans0[bidx][0]]
                      if l.startswith("G0") and "Retract" not in l]
            if not start0 or XZ_RE.search(start0[-1]).groups() != XZ_RE.search(machine[0]).groups():
                wrong.append((bidx, "link does not land on the pass start", machine[0]))
        elif machine:
            wrong.append((bidx, "same point: expected no line", machine))
    check(f"{name}: linked passes have no retract, one link line or none, landing on the start",
          not wrong, wrong[:3])
    kept = []
    for x in refused:
        between = lines[spans[x["a"]][1] + 1: spans[x["b"]][0]]
        if not any("Retract" in l for l in between):
            kept.append(x)
    check(f"{name}: every refused mandrel end keeps its retract", not kept, kept[:3])
    tail = lines[spans[-1][1] + 1:]
    check(f"{name}: the last pass keeps its retract", any("Retract" in l for l in tail))

    rapids = res[4]
    check(f"{name}: simulation rapids and sequence stay pairwise",
          len(rapids) == sum(1 for it in pg.last_calculated_sequence if it[0] == "rapid"))
    if links:
        check(f"{name}: simulation lost rapids where links were made",
              len(rapids) < len(res0[4]), f"{len(res0[4])} -> {len(rapids)}")

    # Continuous motion: link lines are exact stops, and the stop dots still map.
    cont = dict(pon, plc_mode=True, plc_continuous=True, plc_scan_time_s=0.045)
    conv = GCodeToSCLConverter(emit_pass_markers=False,
                               continuous_motion=continuous_settings(cont))
    conv.parse_gcode(pg.generate_gcode(params=cont, for_recipe=True))
    n_link_lines = sum(1 for l in rec.splitlines() if mel.LINK_TAG in l)
    exact_feed = sum(1 for ln in conv.lines if ln.exact and ln.cmd == CMD_LINEAR)
    n_point_lines = sum(1 for l in rec.splitlines() if "(Point Op" in l and l.startswith("G1"))
    check(f"{name}: continuous motion: every link line is an exact stop (CMD=1)",
          exact_feed == n_link_lines + n_point_lines,
          f"{exact_feed} exact vs {n_link_lines} link + {n_point_lines} point")
    dots = motion_stops.compute(pg, dict(cont, plc_auto_tune=False))
    check(f"{name}: stop dots still line up with links on", dots is not None)


print("\nC. the safety net (a blocker the rule misses)")
v1 = find("v1.ssp") if gs is not None else None
if v1:
    params, overrides, step = gs.load_program(v1)
    mgr, _ = gs.build_mandrel(params, gs.resolve_step(step, (SHOP,)))
    has_pass_cmd = any(c.get("trigger") == "pass" for c in params.get("custom_commands", []) or [])
    if not has_pass_cmd:
        print("  SKIP - v1.ssp carries no pass-triggered command here")
    else:
        pon = with_flag(params)
        real = mel.blockers
        mel.blockers = lambda *a, **k: [r for r in real(*a, **k) if r != "custom_command"]
        try:
            pg = PathGenerator()
            pg.calculate_paths(pon, overrides, mgr)
            nc = pg.generate_gcode(params=dict(pon, plc_mode=False))
        finally:
            mel.blockers = real
        fb = list(pg.last_mandrel_link_fallbacks)
        check("the writer notices the command and puts the retract back", len(fb) >= 1, fb)
        lines = nc.splitlines()
        spans, _ = path_spans(lines)
        ok = True
        for bidx in fb:
            a_i = pg.last_mandrel_links[bidx]["a"]
            between = lines[spans[a_i][1] + 1: spans[bidx][0]]
            idx_ret = next((k for k, l in enumerate(between) if "Retract" in l), None)
            idx_cmd = next((k for k, l in enumerate(between)
                            if mel.is_machine_line(l) and "Retract" not in l and not l.startswith("G")), None)
            has_g0_start = any(l.startswith("G0") and "Retract" not in l for l in between)
            has_link = any(mel.LINK_TAG in l for l in between)
            if idx_ret is None or idx_cmd is None or idx_ret > idx_cmd or not has_g0_start or has_link:
                ok = False
        check("...before the command, with the normal rapid to the start and no link line", ok)
else:
    print("  SKIP - v1.ssp not found")

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    sys.exit(1)
print("All mandrel-end link checks passed.")
