"""Sanity checks for corrected estimate_flange_reach (#61 step 4, closed-bottom, from base)."""
import numpy as np, math
from mandrel_analyzer import MandrelManager
from process_planner import estimate_flange_reach

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
print("ALL FLANGE-REACH TESTS PASSED")
