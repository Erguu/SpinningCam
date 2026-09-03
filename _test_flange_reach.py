"""Sanity checks for corrected estimate_flange_reach (#61 step 4, closed-bottom, from base)."""
import numpy as np, math
from mandrel_analyzer import MandrelManager
from process_planner import estimate_flange_reach, analyze_profile

mgr = MandrelManager(); mgr.create_default_cone(); mgr.update_geometry(0, 0, 0, 0.0, 0.0)
z = np.asarray(mgr.profile_z, float); r = np.asarray(mgr.profile_r, float)
if z[0] > z[-1]:
    z, r = z[::-1], r[::-1]
z0, z1 = float(z[0]), float(z[-1])
r_base = float(r[0])
# exact blank for a closed-bottom part clamped at the base: R^2 = r_base^2 + 2*sum(r*ds)
dz, dr = np.diff(z), np.diff(r); ds = np.sqrt(dz*dz + dr*dr); r_mid = (r[:-1]+r[1:])/2
R_exact = math.sqrt(r_base**2 + 2.0*float((r_mid*ds).sum()))
print(f"z {z0:.1f}..{z1:.1f}  r_base={r_base:.2f}  R_exact={R_exact:.2f}")

# top, fully formed with the exact blank -> ~0
top = estimate_flange_reach(mgr, R_exact, z1)
assert top < 0.5, top
print(f"top overhang={top:.3f} ~0: OK")

# base -> R_exact - r_base
base = estimate_flange_reach(mgr, R_exact, z0)
assert abs(base - (R_exact - r_base)) < 0.5, (base, R_exact - r_base)
print(f"base overhang={base:.2f} ~ R-r_base={R_exact - r_base:.2f}: OK")

# monotonic decrease
zs = np.linspace(z0, z1, 12); ov = [estimate_flange_reach(mgr, R_exact, zz) for zz in zs]
assert all(ov[i] >= ov[i+1]-1e-6 for i in range(len(ov)-1)), ov
print("monotonic base->top: OK", [round(v,1) for v in ov])

# oversized blank leaves flange even at top
assert estimate_flange_reach(mgr, R_exact+15, z1) > 5
print("oversized blank -> flange remains at top: OK")

# The SUGGESTER's blank must be the same blank this model consumes (2026-09-03).
# They drifted once: analyze_profile used r_min (the smallest radius anywhere) as the
# closed disc while this model uses the radius at the clamped base — program zero,
# where the counter-press holds the closed bottom (user). On the default cone that was
# 89.03 vs 106.89, so the suggester handed out a blank the flange model then declared
# used up halfway up the mandrel: follow-blank died and the predicted sheet-edge rings
# collapsed onto the mandrel. Keep these two in lockstep.
R_sugg = float(analyze_profile(mgr)["blank_radius_suggested"])
assert abs(R_sugg - R_exact) < 0.5, (R_sugg, R_exact)
print(f"suggester blank {R_sugg:.2f} == flange-model blank {R_exact:.2f}: OK")

# ...and the consequence that actually matters: the suggested blank is used up AT THE
# TOP, not halfway. A blank exhausted mid-wall cannot form the rest of the part.
assert estimate_flange_reach(mgr, R_sugg, z1) < 0.5
assert estimate_flange_reach(mgr, R_sugg, z0 + 0.5 * (z1 - z0)) > 5.0
print("suggested blank lasts to the top, not halfway: OK")

print("ALL FLANGE-REACH TESTS PASSED")
