# -*- coding: utf-8 -*-
"""Headless tests for #92 Phase 1 — exit curl (`exit_mid_radius`).

Straight T2→M then a constant-radius arc tangent at M, running the leftover
|M→P3| length. See PROPOSAL_exit_mid_spline.md.

Test 1 is a TRUE regression: it loads path_generator.py from git HEAD (the
pre-feature version) and asserts byte-identical output for programs that do not
set the new keys — including programs that use exit_bow / exit_arc_angle /
exit_mid_rotation."""
import math
import numpy as np
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

CENTER_X = 0.0

def make_params(gen=None, **op_over):
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
          "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": "forward", "p2_radius": 0.0}
    op.update(op_over)
    return {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
            "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0,
            "collision_resolution": 0.1, "gcode_resolution": 0.05}

def build(gen=None, **op_over):
    g = gen if gen is not None else pg
    return g.calculate_paths(make_params(**op_over), {}, mgr)[0][0]

def exit_of(path):
    """With p2_radius=0 the approach arm is reduced to 2 pts, so path[1] is
    T2 (== P2) and everything from there on is the exit leg."""
    return np.asarray(path)[1:]

def seg_dirs(pts):
    d = np.diff(np.asarray(pts, dtype=float), axis=0)
    n = np.linalg.norm(d, axis=1)
    keep = n > 1e-9
    return d[keep] / n[keep][:, None]

def max_turn_deg(pts):
    """Largest direction change between consecutive segments (a corner)."""
    d = seg_dirs(pts)
    if len(d) < 2:
        return 0.0
    dots = np.clip(np.einsum("ij,ij->i", d[:-1], d[1:]), -1.0, 1.0)
    return float(np.degrees(np.arccos(dots)).max())

def total_turn_deg(pts):
    d = seg_dirs(pts)
    if len(d) < 2:
        return 0.0
    dots = np.clip(np.einsum("ij,ij->i", d[:-1], d[1:]), -1.0, 1.0)
    return float(np.degrees(np.arccos(dots)).sum())

def polyline_len(pts):
    return float(np.linalg.norm(np.diff(np.asarray(pts), axis=0), axis=1).sum())

def fit_radius(pts):
    """Algebraic circle fit in XZ. Returns radius (mm)."""
    p = np.asarray(pts, dtype=float)
    x, z = p[:, 0], p[:, 2]
    A = np.stack([x, z, np.ones_like(x)], axis=1)
    b = x ** 2 + z ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cz = sol[0] / 2.0, sol[1] / 2.0
    return float(math.sqrt(max(sol[2] + cx ** 2 + cz ** 2, 0.0)))

def self_intersects(pts):
    """Any non-adjacent segment pair crossing = the fold we must never produce."""
    p = np.asarray(pts, dtype=float)[:, [0, 2]]
    p = p[::5]                                    # subsample: O(n^2) guard
    n = len(p)
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    for i in range(n - 1):
        for j in range(i + 2, n - 1):
            a, b, c, d = p[i], p[i + 1], p[j], p[j + 1]
            if ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d):
                return True
    return False

# ─────────────────────────────────────────────────────────────────────────
# 1. REGRESSION vs git HEAD — the new keys absent/empty/0 change nothing.
# ─────────────────────────────────────────────────────────────────────────
def load_head_generator():
    import subprocess, tempfile, os, importlib.util
    src = subprocess.check_output(["git", "show", "HEAD:path_generator.py"],
                                  encoding="utf-8", errors="replace")
    fd, tmp = tempfile.mkstemp(suffix="_pg_head.py"); os.close(fd)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(src)
    spec = importlib.util.spec_from_file_location("path_generator_head", tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PathGenerator()

try:
    pg_old = load_head_generator()
except Exception as exc:                                    # noqa: BLE001
    pg_old = None
    print(f"SKIP - could not load git HEAD baseline ({exc})")

if pg_old is not None:
    BASELINES = [
        ("plain linear pass",            {}),
        ("exit_bow set",                 {"exit_bow": 12.0, "exit_bow_bias": 0.4}),
        ("exit_arc_angle set",           {"exit_arc_angle": 25.0}),
        ("exit_mid_rotation set",        {"exit_mid_rotation": 20.0, "exit_mid_t": 0.6}),
        ("bow + rotation (Q3 overlap)",  {"exit_bow": 12.0, "exit_mid_rotation": 20.0,
                                          "exit_mid_t": 0.6}),
        ("linear_full + bow",            {"pass_shape": "linear_full", "exit_bow": 12.0}),
    ]
    for label, over in BASELINES:
        a = build(gen=pg_old, **over)
        b = build(**over)
        check(np.allclose(a, b, atol=1e-12), f"HEAD-identical: {label}")

    # "reverse pass + bow" WAS on that list and is deliberately off it now
    # (2026-08-30). The #82 leg swap used to force a reverse pass's exit leg
    # straight and move the bow onto the arm, where `:2514` then deleted it —
    # so a bow on a reverse pass did nothing at all. The swap is gone: a reverse
    # pass is the forward pass driven backwards and the bow cuts.
    #
    # NOT asserted as "differs from HEAD": this baseline is read from git HEAD,
    # which advances every time the change is committed, so such a check passes
    # once and then fails forever. The durable statement of the same fact is
    # below — the shape a reverse pass cuts is the forward one reversed — and it
    # holds whatever HEAD happens to be.
    check(np.allclose(build(direction="reverse", exit_bow=12.0),
                      build(exit_bow=12.0)[::-1], atol=1e-12),
          "reverse + bow == the forward pass with the same bow, reversed")
    check(np.allclose(build(gen=pg_old, direction="reverse"),
                      build(direction="reverse"), atol=1e-12),
          "a reverse pass with NO exit shape is still HEAD-identical")

    for label, val in (("absent", None), ("empty string", ""), ("zero", 0)):
        over = {} if val is None else {"exit_mid_radius": val}
        check(np.allclose(build(gen=pg_old), build(**over), atol=1e-12),
              f"HEAD-identical: exit_mid_radius {label} → feature inert")
    for label, val in (("empty string", ""), ("zero", 0)):
        check(np.allclose(build(gen=pg_old), build(exit_mid_radius_end=val), atol=1e-12),
              f"HEAD-identical: exit_mid_radius_end {label} → feature inert")

# ─────────────────────────────────────────────────────────────────────────
# 2. Tangency — no corner where the straight leg meets the arc.
# ─────────────────────────────────────────────────────────────────────────
straight = exit_of(build())
curl60   = exit_of(build(exit_mid_radius=60.0, exit_mid_t=0.5))
check(max_turn_deg(curl60) < 0.5,
      f"no corner at M (max per-segment turn {max_turn_deg(curl60):.3f}°)")
# The rigid rotation it replaces DOES leave a corner — proves the test can see one.
rot20 = exit_of(build(exit_mid_rotation=20.0, exit_mid_t=0.5))
check(max_turn_deg(rot20) > 5.0,
      f"control: exit_mid_rotation still kinks (max turn {max_turn_deg(rot20):.1f}°)")

# ─────────────────────────────────────────────────────────────────────────
# 3. Radius accuracy + straight part really is straight.
# ─────────────────────────────────────────────────────────────────────────
chord_len = float(np.linalg.norm(straight[-1] - straight[0]))
for R in (40.0, 60.0, 120.0):
    ex = exit_of(build(exit_mid_radius=R, exit_mid_t=0.5))
    n_half = len(ex) // 2
    arc_part, str_part = ex[n_half + 2:], ex[:n_half - 2]
    r_fit = fit_radius(arc_part)
    check(abs(r_fit - R) / R < 0.01, f"R={R:.0f} → fitted {r_fit:.2f}mm (<1% err)")
    check(max_turn_deg(str_part) < 0.05, f"R={R:.0f}: pre-M leg dead straight")

# t controls where the straight part ends, measured along the CHORD (Q3).
for t_frac in (0.3, 0.5, 0.8):
    ex = exit_of(build(exit_mid_radius=60.0, exit_mid_t=t_frac))
    d0 = seg_dirs(ex)[0]
    dev = np.linalg.norm(np.cross(ex - ex[0], d0), axis=1)
    m_idx = int(np.argmax(dev > 0.02))
    straight_len = polyline_len(ex[:m_idx + 1])
    check(abs(straight_len - t_frac * chord_len) < 0.05 * chord_len,
          f"t={t_frac}: straight run {straight_len:.1f}mm ≈ chord fraction "
          f"{t_frac * chord_len:.1f}mm")

# ─────────────────────────────────────────────────────────────────────────
# 3b. USER-REPORTED REGRESSION (2026-07-26): "magnitude doesn't make any
# changes, sign is changing the curve direction. -1 and -10 looks same."
# Cause: the first cut resolved the 90° cap by OVERRIDING the radius with
# arc_len·2/π, so every |R| below that threshold produced one identical path.
# The original tests only used R=40/60/120 (above the threshold) plus R=2 to
# check the cap fired — they never compared two SMALL radii against each other.
# ─────────────────────────────────────────────────────────────────────────
mag_ends = {}
for R in (1.0, 2.0, 5.0, 10.0, 12.0, 15.0, 30.0, 60.0):
    mag_ends[R] = exit_of(build(exit_mid_radius=R, exit_mid_t=0.5))[-1]
uniq = {(round(float(e[0]), 3), round(float(e[2]), 3)) for e in mag_ends.values()}
check(len(uniq) == len(mag_ends),
      f"every radius gives a DISTINCT shape ({len(uniq)}/{len(mag_ends)} unique ends)")
for a, b in ((1.0, 10.0), (-1.0, -10.0), (2.0, 5.0)):
    pa, pb = build(exit_mid_radius=a), build(exit_mid_radius=b)
    check(not (pa.shape == pb.shape and np.allclose(pa, pb, atol=1e-6)),
          f"R={a:+.0f} differs from R={b:+.0f} (the reported symptom)")
devs = [float(np.linalg.norm(mag_ends[R] - straight[-1])) for R in sorted(mag_ends)]
check(all(x > y - 1e-6 for x, y in zip(devs, devs[1:])),
      "tighter radius bends further from the straight end (monotonic in R)")

# The radius must stay EXACT even when the turn is capped — the cap now stops the
# arc and runs the leftover length on as a straight tangent instead.
Rq = 5.0
tail, sweep_q, run_q = pg._curl_tail(np.array([80.0, 0.0, 30.0]),
                                     np.array([0.0, 0.0, 1.0]), Rq, 40.0, 0.05)
used_q = Rq * sweep_q
n_arc  = max(10, int(used_q / 0.05))
check(abs(math.degrees(sweep_q) - 90.0) < 0.01,
      f"turn capped at exactly 90° (got {math.degrees(sweep_q):.3f}°)")
check(abs(fit_radius(tail[:n_arc]) - Rq) / Rq < 0.01,
      f"radius stays EXACT under the cap (fitted {fit_radius(tail[:n_arc]):.3f} vs {Rq})")
check(abs(run_q - (40.0 - used_q)) < 1e-6, "run-out spends exactly the leftover length")
check(abs(polyline_len(tail) - 40.0) < 0.05,
      f"total tail length still preserved ({polyline_len(tail):.2f} vs 40.00mm)")
check(max_turn_deg(tail) < 1.0, "arc → run-out junction is tangent (no corner)")

# ─────────────────────────────────────────────────────────────────────────
# 3c. MID PHASE — exit_mid_radius_end: curvature varies along the tail
# (clothoid). Removes the curvature JUMP a constant-radius arc has at M.
# ─────────────────────────────────────────────────────────────────────────
def local_radius(pts, i, half=12):
    """Circle fit on a small window around index i → local radius there."""
    a, b = max(0, i - half), min(len(pts), i + half + 1)
    return fit_radius(np.asarray(pts)[a:b])

# Empty end radius ⇒ constant arc ⇒ untouched.
check(np.allclose(build(exit_mid_radius=60.0),
                  build(exit_mid_radius=60.0, exit_mid_radius_end=""), atol=1e-12),
      "empty end radius ⇒ byte-identical to the constant arc")
check(np.allclose(build(exit_mid_radius=60.0),
                  build(exit_mid_radius=60.0, exit_mid_radius_end=60.0), atol=1e-9),
      "equal end radius ⇒ same shape as the constant arc")

# Curvature really does vary: tight→wide and wide→tight are mirror behaviours.
sp = exit_of(build(exit_mid_radius=100.0, exit_mid_radius_end=20.0, exit_mid_t=0.35))
n0 = int(np.argmax(np.linalg.norm(np.cross(sp - sp[0], seg_dirs(sp)[0]), axis=1) > 0.02))
r_near, r_far = local_radius(sp, n0 + 25), local_radius(sp, len(sp) - 20)
check(r_near > r_far * 1.5,
      f"R100→R20 tightens along the tail (local R {r_near:.0f} → {r_far:.0f}mm)")
sp2 = exit_of(build(exit_mid_radius=20.0, exit_mid_radius_end=100.0, exit_mid_t=0.35))
n2 = int(np.argmax(np.linalg.norm(np.cross(sp2 - sp2[0], seg_dirs(sp2)[0]), axis=1) > 0.02))
check(local_radius(sp2, n2 + 25) < local_radius(sp2, len(sp2) - 20) * 0.67,
      "R20→R100 eases out along the tail (reverse direction works too)")

# The point of the feature: end radius ALONE ⇒ leaves M perfectly straight
# (curvature 0) and eases in — no curvature jump at the junction.
ease = exit_of(build(exit_mid_radius_end=-30.0, exit_mid_t=0.4))
check(not (ease.shape == straight.shape and np.allclose(ease, straight, atol=1e-6)),
      "end radius alone switches the curl on")
n_e = int(np.argmax(np.linalg.norm(np.cross(ease - ease[0], seg_dirs(ease)[0]), axis=1) > 0.02))
check(local_radius(ease, n_e + 20) > local_radius(ease, len(ease) - 20) * 2.0,
      "end-radius-only starts near-straight and tightens (no curvature jump at M)")
check(max_turn_deg(ease) < 0.5, "spiral tail has no corner anywhere")

# Mixed signs cannot fold the tail into an S: direction comes from the start
# radius, the end radius contributes magnitude only.
check(np.allclose(build(exit_mid_radius=-60.0, exit_mid_radius_end=20.0),
                  build(exit_mid_radius=-60.0, exit_mid_radius_end=-20.0), atol=1e-12),
      "end radius sign ignored (no accidental S-curve)")
check(not self_intersects(exit_of(build(exit_mid_radius=-8.0, exit_mid_radius_end=-2.0))),
      "aggressive spiral still cannot self-intersect")

# (spiral clearance is checked in §6, once exit_min_clear is defined)

# ─────────────────────────────────────────────────────────────────────────
# 4. Sign = FIXED handedness (same rule as _bezier_bow, no fan flip).
# ─────────────────────────────────────────────────────────────────────────
d_exit = (straight[-1] - straight[0]); d_exit /= np.linalg.norm(d_exit)
perp   = np.array([-d_exit[2], 0.0, d_exit[0]])
pos = exit_of(build(exit_mid_radius=60.0))
neg = exit_of(build(exit_mid_radius=-60.0))
check(float(np.dot(pos[-1] - straight[-1], perp)) > 1.0, "+R deviates along +perp")
check(float(np.dot(neg[-1] - straight[-1], perp)) < -1.0, "−R deviates along −perp")
check(perp[2] > 0 and pos[-1][2] > neg[-1][2],
      "documented convention holds: +R leans toward the mandrel top (+Z)")

# ─────────────────────────────────────────────────────────────────────────
# 5. Fold guard — small R on a long tail cannot loop; LENGTH is preserved.
# ─────────────────────────────────────────────────────────────────────────
tiny = exit_of(build(exit_mid_radius=2.0, exit_mid_t=0.3))
n_m  = int(len(tiny) * 0.3)
arc_tiny = tiny[n_m + 3:]
turn = total_turn_deg(arc_tiny)
check(turn <= 92.0, f"total turn capped at 90° (measured {turn:.1f}°)")
check(not self_intersects(tiny), "capped curl does not self-intersect")
expect_arc = 0.7 * chord_len
check(abs(polyline_len(arc_tiny) - expect_arc) < 0.06 * expect_arc,
      f"tail length preserved under the cap ({polyline_len(arc_tiny):.1f} ≈ {expect_arc:.1f}mm)")
# ...and it is the ARC that stops, not the radius that changes: a tight R must
# still read as that radius, with the rest spent running straight.
check(fit_radius(tiny[n_m + 3:n_m + 3 + 40]) < 4.0,
      f"tight R=2 stays tight under the cap (fitted "
      f"{fit_radius(tiny[n_m + 3:n_m + 3 + 40]):.2f}mm)")

# ─────────────────────────────────────────────────────────────────────────
# 6. Clearance — both trim modes, with a deliberately gouging inward curl.
# ─────────────────────────────────────────────────────────────────────────
# Tested at the guard's own contract level. Using the whole path here would be
# misleading: measure_min_clearance also samples the APPROACH ARM, which on this
# cone runs down toward the fat base and dominates the minimum (the engine's own
# uniform-shift correction handles that separately, and skips out-of-range Z).
# The curl's contract is narrower and exact: no ARC point may sit inside the
# clearance surface, with M pinned.
GUARD = dict(center_x=CENTER_X, r_tool=25.0, blank_thick=0.0, shell_offset=0.0)
CLR = 1.0
# Chord laid PARALLEL to the clearance surface (this cone is r(z)=60−0.5z, so the
# 1 mm clearance surface runs along (−0.447, 0, +0.894) and A sits exactly on it).
# That isolates the guard: the straight leg is clear by construction, so any
# violation is caused by the CURL alone — which is what FLATTEN can actually undo.
A_g   = np.array([71.0, 0.0, 30.0])
d_srf = np.array([-0.4472, 0.0, 0.8944])
B_g   = A_g + 30.0 * d_srf
CURL_R = 18.0        # +R bends −X/−Z here: straight into the part

def arc_part_of(leg, A, B, t_frac, check_res=0.1):
    """Arc portion by construction index (not by deviation): _make_curl_leg emits
    max(2, int(t·L / check_res)) straight points and drops the last before the
    arc, so the arc starts at n_str−1. Robust even when FLATTEN makes the curl
    almost straight."""
    L = float(np.linalg.norm(np.asarray(B) - np.asarray(A)))
    n_str = max(2, int((t_frac * L) / check_res))
    return np.asarray(leg)[n_str - 1:]

def pen_of(pts):
    return pg._curl_penetration(np.asarray(pts, dtype=float), mgr,
                                GUARD["center_x"], GUARD["r_tool"],
                                GUARD["blank_thick"], GUARD["shell_offset"], CLR)

# Control: the UNGUARDED arc really does violate, so the guards below mean something.
raw_arc, _sw, _run = pg._curl_tail(A_g + 0.3 * (B_g - A_g), d_srf,
                                   CURL_R, 0.7 * float(np.linalg.norm(B_g - A_g)), 0.1)
check(pen_of(raw_arc) > 0.5,
      f"control: unguarded arc violates by {pen_of(raw_arc):.2f}mm")
# ...while the straight leg it grows out of is clear, so FLATTEN has a way out.
check(pen_of(np.linspace(A_g, B_g, 200)) <= 0.05,
      "control: the straight chord itself is clear (violation is the curl's)")

leg_trim = pg._make_curl_leg(A_g, B_g, 0.3, CURL_R, 0.1, mgr,
                             GUARD["center_x"], GUARD["r_tool"], GUARD["blank_thick"],
                             GUARD["shell_offset"], CLR, True, "test-trim")
leg_flat = pg._make_curl_leg(A_g, B_g, 0.3, CURL_R, 0.1, mgr,
                             GUARD["center_x"], GUARD["r_tool"], GUARD["blank_thick"],
                             GUARD["shell_offset"], CLR, False, "test-flatten")
arc_trim = arc_part_of(leg_trim, A_g, B_g, 0.3)
arc_flat = arc_part_of(leg_flat, A_g, B_g, 0.3)
p_trim, p_flat = pen_of(arc_trim), pen_of(arc_flat)
check(p_trim <= 0.05, f"TRIM respects clearance (worst penetration {p_trim:.3f}mm)")
check(p_flat <= 0.05, f"FLATTEN respects clearance (worst penetration {p_flat:.3f}mm)")
check(max_turn_deg(leg_flat) < 1.0, "FLATTEN stays smooth (no contour-riding kink)")
check(np.allclose(leg_trim[0], A_g) and np.allclose(leg_flat[0], A_g),
      "both modes keep the straight leg's start pinned")
# FLATTEN yields a gentler curl than TRIM's full-amplitude arc.
check(total_turn_deg(arc_flat) < total_turn_deg(arc_trim) - 1.0,
      "FLATTEN curls less than TRIM (radius grown, not points moved)")

# BACKSTOP: when the leg's own direction runs inside the clearance surface,
# curvature alone cannot save it — FLATTEN must still come out clear (this is
# deliberately stronger than exit_bow's CLAMP, which would pass the gouge on).
d_in = np.array([-0.85, 0.0, 0.527]); d_in /= np.linalg.norm(d_in)
A_b, B_b = A_g.copy(), A_g + 25.0 * d_in
check(pen_of(np.linspace(A_b, B_b, 200)) > 0.5,
      "control: backstop setup — the straight chord itself violates")
leg_bs = pg._make_curl_leg(A_b, B_b, 0.3, 40.0, 0.1, mgr,
                           GUARD["center_x"], GUARD["r_tool"], GUARD["blank_thick"],
                           GUARD["shell_offset"], CLR, False, "test-backstop")
p_bs = pen_of(arc_part_of(leg_bs, A_b, B_b, 0.3))
check(p_bs <= 0.05, f"FLATTEN backstop still clears an unfixable leg ({p_bs:.3f}mm)")

# Integration: on a normal pass the curl is self-guarded — its exit portion never
# breaks the op clearance (z clamped into the mandrel range, as the guard does).
_mz, _tz = mgr.props.get("min_z", -1e9), mgr.props.get("top_z", 1e9)
def exit_min_clear(path, r_tool=25.0, clr_base=0.0):
    worst = float("inf")
    ex = exit_of(path)
    for k in range(len(ex) - 1):
        a, b = ex[k], ex[k + 1]
        n = max(1, int(math.hypot(b[0] - a[0], b[2] - a[2]) / 0.25))
        for s in range(n + 1):
            u = s / n
            x = a[0] + u * (b[0] - a[0]); z = a[2] + u * (b[2] - a[2])
            m_r = mgr.get_radius_fast(min(max(z, _mz), _tz))
            worst = min(worst, abs(x - CENTER_X) - (m_r + r_tool + clr_base))
    return worst
for R_i in (60.0, -60.0, 25.0, -25.0):
    c = exit_min_clear(build(exit_mid_radius=R_i, exit_mid_t=0.4, clearance=1.0))
    check(c >= -0.01, f"curled exit R={R_i:+.0f} keeps clearance (min {c:.2f}mm)")
# ...and the same for the variable-radius (spiral) tail.
for ra, rb in ((60.0, 15.0), (-60.0, -15.0), (15.0, 60.0), (None, -30.0)):
    kw = dict(exit_mid_radius_end=rb, exit_mid_t=0.4, clearance=1.0)
    if ra is not None:
        kw["exit_mid_radius"] = ra
    c = exit_min_clear(build(**kw))
    check(c >= -0.01,
          f"spiral exit R={ra}→{rb:+.0f} keeps clearance (min {c:.2f}mm)")

# Outward curl: guard inert, shape untouched by the trim flag.
out_a = build(exit_mid_radius=60.0, exit_mid_trim=True)
out_b = build(exit_mid_radius=60.0, exit_mid_trim=False)
check(np.allclose(out_a, out_b, atol=1e-9), "outward curl identical in both modes (guard inert)")

# ─────────────────────────────────────────────────────────────────────────
# 7. PLC decimation — the straight run collapses; curl beats a full-leg bow.
# ─────────────────────────────────────────────────────────────────────────
def plc_points(**over):
    pg.calculate_paths(make_params(**over), {}, mgr)
    return len(pg.decimate_all_paths(0.05, 0.05, CENTER_X)[0])

n_curl = plc_points(exit_mid_radius=60.0, exit_mid_t=0.6)
n_bow  = plc_points(exit_bow=12.0)
n_str  = plc_points()
check(n_str <= 4, f"straight leg decimates to ≤4 pts (got {n_str})")
check(n_curl < n_bow, f"curl cheaper than full-leg bow ({n_curl} < {n_bow} pts)")

# ─────────────────────────────────────────────────────────────────────────
# 8. Scope — linear_full is untouched (Q7). Reverse NO LONGER IS (2026-08-30).
# ─────────────────────────────────────────────────────────────────────────
# Q6 originally scoped the curl out of reverse passes, because the #82 leg swap
# forced that leg straight and would have thrown the curl away. The swap is
# deleted: a reverse pass is the forward pass driven backwards, so the curl
# applies there like every other exit shape.
def _same(a, b, atol=1e-12):
    """allclose RAISES on mismatched shapes — and a curl changes the point
    count, which is precisely one of the differences under test."""
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and np.allclose(a, b, atol=atol)


check(not _same(build(direction="reverse"),
                build(direction="reverse", exit_mid_radius=60.0), atol=1e-6),
      "reverse pass now HONOURS the curl (was Q6: ignored)")
check(_same(build(direction="reverse", exit_mid_radius=60.0),
            build(exit_mid_radius=60.0)[::-1]),
      "...as exactly the forward curl reversed")
check(np.allclose(build(pass_shape="linear_full"),
                  build(pass_shape="linear_full", exit_mid_radius=60.0), atol=1e-12),
      "linear_full ignores the curl (Q7)")

# ─────────────────────────────────────────────────────────────────────────
# 9. Q2 — radius wins over exit_mid_rotation, provably.
# ─────────────────────────────────────────────────────────────────────────
check(np.allclose(build(exit_mid_radius=60.0),
                  build(exit_mid_radius=60.0, exit_mid_rotation=35.0), atol=1e-12),
      "rotation provably ignored when a radius is set (Q2)")
check(not np.allclose(build(exit_mid_rotation=35.0), build(), atol=1e-6),
      "control: rotation alone still does something")
check(np.allclose(build(exit_mid_radius_end=-30.0),
                  build(exit_mid_radius_end=-30.0, exit_mid_rotation=35.0), atol=1e-12),
      "end radius alone also supersedes rotation (Q2)")

# 10. Q2 — the curl also supersedes exit_bow / exit_arc_angle on the exit leg.
check(np.allclose(build(exit_mid_radius=60.0),
                  build(exit_mid_radius=60.0, exit_bow=12.0, exit_arc_angle=25.0),
                  atol=1e-12),
      "curl supersedes exit_bow / exit_arc_angle on the exit leg")

# ─────────────────────────────────────────────────────────────────────────
# 11. Q3 — the two readings of exit_mid_t coexist without drifting.
# ─────────────────────────────────────────────────────────────────────────
# Rotation keeps POINT-ARRAY semantics: with a bow also set, the pivot sits at
# the array index, so the path matches the un-rotated bow up to that index.
bow_only = exit_of(build(exit_bow=12.0, exit_bow_bias=0.5))
bow_rot  = exit_of(build(exit_bow=12.0, exit_bow_bias=0.5,
                         exit_mid_rotation=20.0, exit_mid_t=0.6))
if len(bow_only) == len(bow_rot):
    same = np.all(np.isclose(bow_only, bow_rot, atol=1e-9), axis=1)
    k = int(np.argmin(same))                      # first differing index
    frac = k / (len(bow_only) - 1)
    check(0.5 < frac < 0.72,
          f"rotation pivot at ARRAY fraction {frac:.2f} (t=0.6, legacy meaning kept)")
else:
    check(False, "bow vs bow+rot point counts differ — cannot locate pivot")

print()
print("FAILURES:" if fails else "ALL PASS", fails if fails else "")
raise SystemExit(1 if fails else 0)
