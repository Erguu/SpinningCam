"""Headless test for estimate_surface_angle (#61 surface-derived fan-end angle).

Verifies the tangent-direction math and the cylinder→180° legacy-default equivalence,
plus a cone slope, using a tiny fake mandrel that returns a chosen (nx, nz) normal.
"""
import math
from process_planner import estimate_surface_angle


class FakeMandrel:
    """Minimal stand-in exposing get_normal_at_z with a fixed outward normal."""
    def __init__(self, nx, nz):
        L = math.hypot(nx, nz)
        self._n = (nx / L, nz / L)

    def get_normal_at_z(self, z):
        return self._n


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def fan_end(nx, nz, theta_a=-90.0, forming_up=True):
    """Full pipeline: surface tangent → pass-angle-frame fan-end (as the button computes)."""
    theta_end = estimate_surface_angle(FakeMandrel(nx, nz), 0.0, forming_up)
    return theta_end - theta_a


fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


# 1) Cylinder: dr=0 → normal (1,0). Tangent up = (0,1) → 90°.
#    With linear approach θ_A=-90 → fan-end = 180 (the legacy hardcoded default).
check(approx(estimate_surface_angle(FakeMandrel(1.0, 0.0), 0.0), 90.0),
      "cylinder tangent = 90 deg from +X")
check(approx(fan_end(1.0, 0.0), 180.0),
      "cylinder fan-end = 180 deg (legacy default reproduced)")

# 2) Widening cone (r grows with Z): dr>0 → nz=-dr<0. Take a 45deg wall:
#    normal (dz, -dr) with dz=dr → (1,-1). Tangent up = (-nz,nx)=(1,1) → 45deg.
#    fan-end = 45 - (-90) = 135 (< 180, less laid-over than a cylinder).
check(approx(estimate_surface_angle(FakeMandrel(1.0, -1.0), 0.0), 45.0),
      "45deg widening cone tangent = 45 deg")
check(approx(fan_end(1.0, -1.0), 135.0),
      "45deg widening cone fan-end = 135 deg")

# 3) Narrowing cone (r shrinks with Z): dr<0 → nz=-dr>0. normal (1, 1).
#    Tangent up = (-nz, nx) = (-1, 1) → 135deg. fan-end = 135+90 = 225 (past vertical).
check(approx(estimate_surface_angle(FakeMandrel(1.0, 1.0), 0.0), 135.0),
      "45deg narrowing cone tangent = 135 deg")
check(approx(fan_end(1.0, 1.0), 225.0),
      "45deg narrowing cone fan-end = 225 deg (exit points up-and-in)")

# 4) Forming direction flip: descending pass reverses the tangent branch (180deg apart).
up = estimate_surface_angle(FakeMandrel(1.0, -1.0), 0.0, forming_up=True)
dn = estimate_surface_angle(FakeMandrel(1.0, -1.0), 0.0, forming_up=False)
check(approx(abs(((up - dn) % 360)), 180.0),
      "forming direction flip reverses tangent by 180 deg")

# 5) Spline approach offset: θ_A follows P1 direction, changing the fan-end accordingly.
#    p1_x=p1_z → θ_A = atan2(-1,1) = -45. Cylinder tangent 90 → fan-end = 90-(-45)=135.
check(approx(fan_end(1.0, 0.0, theta_a=-45.0), 135.0),
      "spline approach (θ_A=-45) shifts cylinder fan-end to 135")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
