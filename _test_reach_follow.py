# -*- coding: utf-8 -*-
"""Headless test for ENGINE-SIDE follow-blank reach (2026-07-07 rework,
PROPOSAL_REACH_ANGLE_PRIORITY R2/R3).

Follow mode now lives inside path_generator.calculate_paths: each pass's reach
is computed from the flange model at THAT pass's Z (robust edge), modified by
the user-owned factor (×) and offset (mm). The op dict must NEVER be
auto-rewritten. Replaces the old UI-side _refresh_auto_reach test (removed)."""
import math

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator
from process_planner import estimate_flange_reach, flange_slant_length

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
min_z = float(mgr.props["min_z"])
blank_r = float(mgr.props["br"]) * 1.5

pg = PathGenerator()

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1

def run(op, blank=blank_r):
    p = {"operations": [op], "blank_radius": blank, "auto_calc_angle": False,
         "min_safety_gap": -999.0, "final_part_thickness_on_mandrel": 0.0,
         "shell_thickness": 0.0, "target_clearance": 0.0}
    pg.calculate_paths(p, {}, mgr)
    return pg.last_op_reach.get(0), pg.last_op_end_angle.get(0)

BASE = {"type": "roughing", "pass_shape": "linear_approach", "r_tool": 25.0,
        "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
        "pass_angle": 100.0}

# 2026-09-03: follow-blank commands the SLANT length along the exit, not the flat
# sideways overhang estimate_flange_reach returns. The stroke travels along the exit,
# where the same material is longer, so the old flat number stopped short of the sheet
# edge — worse the steeper the pass (~41% at 90°). See process_planner.flange_slant_length.
# linear_approach → θ_A = -90°, so pass_angle 100° exits at +10°.
EXIT_POLAR = (math.cos(math.radians(10.0)), math.sin(math.radians(10.0)))
EXIT_RAW = (30.0, 25.0)          # |p3_z| is normalised positive before use

# Degenerate-flange floor (2026-07-22): a follow reach under `reach_follow_min` is
# treated as exhausted and the pass falls back to its own reach/|p3|. The checks below
# have to model it or they "fail" on high passes where the flange is nearly used up —
# which is exactly what they were doing before 2026-09-03.
FB_MIN = 10.0

def want_reach(z, factor=1.0, offset=0.0, exit_dir=EXIT_POLAR):
    """Follow-blank's commanded reach, or None where the floor makes it fall back."""
    fr = estimate_flange_reach(mgr, blank_r, z)
    if fr <= 0:
        return None
    L = flange_slant_length(mgr.get_radius_fast(z), fr, *exit_dir)[0] * factor + offset
    L = max(L, 0.0)
    return None if (L < FB_MIN or z <= min_z) else L

# 1. Per-pass exactness: single-pass follow ops at several Z — engine reach must
#    equal the flange estimate AT THAT Z (not a lerp between two endpoints).
ok = True
tested = 0
for dz in (10, 20, 35, 50):
    z = min_z + dz
    op = dict(BASE, count=1, start_z=z, end_z=z + 1, reach_follow_blank=True)
    r, _ = run(op)
    want = want_reach(z)
    if want is None:            # flange exhausted here — falls back, covered by 1d
        continue
    tested += 1
    if abs(r - want) > 0.05:
        ok = False
        print(f"   z={z}: engine {r} vs flange {want}")
check(ok and tested >= 2,
      f"follow reach == flange estimate at each pass Z ({tested} heights checked)")

# 1b. The correction only ever LENGTHENS, and a flat exit is left bit-for-bit alone —
#     that is what keeps already-proven programs from moving.
ok_long = ok_flat = True
for dz in (10, 20, 35, 50):
    z = min_z + dz
    fr = estimate_flange_reach(mgr, blank_r, z)
    if fr <= 0:
        continue
    if flange_slant_length(mgr.get_radius_fast(z), fr, *EXIT_POLAR)[0] < fr - 1e-9:
        ok_long = False
    if abs(flange_slant_length(mgr.get_radius_fast(z), fr, 1.0, 0.0)[0] - fr) > 1e-9:
        ok_flat = False
check(ok_long, "slant correction never shortens the stroke")
check(ok_flat, "a FLAT exit returns the old flat number exactly (no drift)")

# 1c. Escape hatch for a program already proven on the machine. Checked on a STEEP
#     pass (θ_A=-90° + 160° → 70° exit) where the flat/slant gap is large; at the
#     near-flat 10° exit of BASE the two answers are within a rounding error.
STEEP = dict(BASE, pass_angle=160.0)
EXIT_STEEP = (math.cos(math.radians(70.0)), math.sin(math.radians(70.0)))
z = min_z + 20
r_new, _ = run(dict(STEEP, count=1, start_z=z, end_z=z + 1, reach_follow_blank=True))
r_leg, _ = run(dict(STEEP, count=1, start_z=z, end_z=z + 1, reach_follow_blank=True,
                    reach_blank_flat_legacy=True))
want_leg = estimate_flange_reach(mgr, blank_r, z)
want_new = want_reach(z, exit_dir=EXIT_STEEP)
check(abs(r_leg - want_leg) < 0.05,
      f"reach_blank_flat_legacy restores the old flat stroke ({r_leg:.2f})")
check(want_new is not None and abs(r_new - want_new) < 0.05,
      f"steep pass commands the slant length ({r_new:.2f}, want {want_new})")
check(r_new > r_leg + 1.0,
      f"and the corrected stroke is materially longer ({r_new:.2f} vs {r_leg:.2f})")

# 1d. Below the floor the pass falls back to its own reach — unchanged by this work.
z_hi = min_z + 50
op = dict(BASE, count=1, start_z=z_hi, end_z=z_hi + 1, reach_follow_blank=True,
          reach=42.0)
r_hi, _ = run(op)
check(want_reach(z_hi) is None and abs(r_hi - 42.0) < 0.05,
      f"exhausted flange falls back to the op's own reach ({r_hi:.2f})")

# 2. Multi-pass: LAST pass follows the flange at end_z exactly. end_z stays where the
#    flange is still above the floor, otherwise this only measures the fallback (1d).
op = dict(BASE, count=4, start_z=min_z + 10, end_z=min_z + 20, reach_follow_blank=True)
r_last, _ = run(op)
want_last = want_reach(min_z + 20)
check(want_last is not None and abs(r_last - want_last) < 0.05,
      f"multi-pass last reach {r_last:.2f} == flange(end_z) {want_last}")

# 3. R2 — the op dict is NEVER auto-rewritten by follow mode.
check("reach" not in op, "op['reach'] not written by follow")
check("progressive_reach_end" not in op, "op['progressive_reach_end'] not written")
check(not op.get("progressive_reach_enabled", False),
      "fan flag NOT flipped by follow (user owns it)")

# 4. Modifiers: factor (×) then offset (mm) — reach = flange × factor + offset.
op = dict(BASE, count=1, start_z=min_z + 20, end_z=min_z + 21,
          reach_follow_blank=True, reach_blank_factor=0.9, reach_blank_offset=-5.0)
r_mod, _ = run(op)
want_mod = want_reach(min_z + 20, factor=0.9, offset=-5.0)
check(abs(r_mod - want_mod) < 0.05,
      f"modifiers: flange×0.9−5 → {r_mod:.2f} (want {want_mod:.2f})")

# 5. Follow supersedes the reach fan; a manual reach underneath is ignored but preserved.
op = dict(BASE, count=3, start_z=min_z + 10, end_z=min_z + 20, reach_follow_blank=True,
          reach=999.0, progressive_reach_enabled=True, progressive_reach_end=1.0)
r_f, _ = run(op)
want_f = want_reach(min_z + 20)
check(want_f is not None and abs(r_f - want_f) < 0.05,
      f"follow supersedes fan+manual ({r_f:.2f})")
check(op["reach"] == 999.0 and op["progressive_reach_end"] == 1.0,
      "manual values preserved untouched underneath")

# 6. RAW mode (no pass_angle): follow rescales the p3 vector, ratio preserved.
op = dict(BASE, count=1, start_z=min_z + 20, end_z=min_z + 21, reach_follow_blank=True)
op.pop("pass_angle")
r_raw, ang_raw = run(op)
want_raw = want_reach(min_z + 20, exit_dir=EXIT_RAW)
check(abs(r_raw - want_raw) < 0.05, f"RAW mode follow length {r_raw:.2f}")
want_dir = math.degrees(math.atan2(25.0, 30.0))  # |p3_z|/p3_x ratio preserved
check(abs(ang_raw - want_dir) < 0.5, f"RAW mode direction preserved ({ang_raw:.1f}°)")

# 7. No blank radius → follow silently inert (engine guard), op untouched.
op = dict(BASE, count=1, start_z=min_z + 20, end_z=min_z + 21,
          reach_follow_blank=True, reach=40.0)
r_nb, _ = run(op, blank=0.0)
check(abs(r_nb - 40.0) < 0.05, f"no blank radius → manual reach used ({r_nb:.2f})")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
