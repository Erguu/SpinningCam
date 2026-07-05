"""Geometry check for the #63 deformed-blank overlay (toolpath-driven model): the blank is
built by revolving the SELECTED pass's own toolpath (contact P2 -> exit P3), pulled in by
the tool radius. So it follows the pass's ANGLE (slope) and REACH (length) by construction.
This replicates main.update_deformed_blank's mesh build against a synthetic pass path.
"""
import numpy as np
import pyvista as pv

cx = 0.0
r_tool = 30.0

fails = 0
def check(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL"), "-", msg)
    if not cond:
        fails += 1


def build(p2, p3, off=0.0):
    """p2, p3 are roller-center XZ points; build the revolved sheet from the P2->P3 stroke."""
    seg = np.array([[p2[0], 0.0, p2[1]], [p3[0], 0.0, p3[1]]], dtype=float)
    radial = np.maximum(np.abs(seg[:, 0] - cx) - r_tool + off, 0.1)
    prof = np.column_stack([radial, np.zeros(len(seg)), seg[:, 2]])
    surf = pv.lines_from_points(prof).extrude_rotate(angle=360.0, resolution=60,
                                                     capping=False, rotation_axis=(0, 0, 1))
    return surf, radial


# Shallow pass (angle ~radial-out): exit moves OUT a lot, up a little.
p2 = (120.0, 40.0)                 # contact (roller center)
p3 = (170.0, 55.0)                 # exit: +50 out, +15 up  -> shallow
surf, rad = build(p2, p3)
b = surf.bounds
check(surf.n_points > 0 and surf.n_cells > 0, f"surface built ({surf.n_points} pts)")
# sheet radius = roller radius pulled in by r_tool
check(abs(rad[0] - (120.0 - r_tool)) < 1e-6, f"contact sheet radius = |P2|-r_tool ({rad[0]:.1f})")
check(abs(rad[1] - (170.0 - r_tool)) < 1e-6, f"exit sheet radius = |P3|-r_tool ({rad[1]:.1f})")
check(abs(b[5] - 55.0) < 1e-3, f"Z reaches the exit Z ({b[5]:.1f})")
shallow_dr = rad[1] - rad[0]       # radial growth of a shallow pass

# Steep pass (angle ~along wall / ~180): exit moves mostly UP, little out.
p3s = (123.0, 90.0)                # +3 out, +50 up -> steep
surf_s, rad_s = build(p2, p3s)
steep_dr = rad_s[1] - rad_s[0]
check(surf_s.bounds[5] > b[5], f"steeper pass -> higher exit Z ({b[5]:.0f} -> {surf_s.bounds[5]:.0f})")
check(steep_dr < shallow_dr, f"steeper pass -> flange leans more upright (Δr {shallow_dr:.0f} -> {steep_dr:.0f})")

# Offset nudges the sheet radius outward.
_, rad_off = build(p2, p3, off=10.0)
check(abs(rad_off[0] - (rad[0] + 10.0)) < 1e-6, "deformed_blank_offset shifts the sheet outward")

print()
print("ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
raise SystemExit(1 if fails else 0)
