# Research script: verify get_contact_radius() and measure true roller support function.
# Task 1: is the STEP-derived radius (74.31 for T0103) trustworthy?
# Task 2: how far off are the radial / normal clearance models on angled surfaces?
import sys, os, json, math
import numpy as np

REPO = r"C:\Users\PC\Documents\Python_Projects\SpinningCam"
sys.path.insert(0, REPO)
os.chdir(REPO)

OUT = open("_research_tool_geometry.out", "w", encoding="utf-8")
def say(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.write(s + "\n")
    OUT.flush()

from tool_step_loader import ToolStepLoader

tools = json.load(open("tools.json", encoding="utf-8"))
loader = ToolStepLoader(REPO)

for tl in tools:
    tid = tl["id"]
    say("=" * 70)
    say(f"TOOL {tid} ({tl.get('name')})  step={tl.get('step_file')}")
    say(f"  tools.json: radius={tl.get('radius')}  r_tool={tl.get('r_tool')}")
    step_path = tl.get("step_file", "")
    if not os.path.isfile(step_path):
        say("  !! STEP file not found on disk")
        continue

    canonical = loader._get_canonical(tl, step_path)
    if canonical is None:
        say("  !! canonical mesh failed to build")
        continue

    pts = canonical.points  # tip at origin (x,z), shaft along Y, body extends +X
    say(f"  mesh: {len(pts)} verts")
    say(f"  bounds X [{pts[:,0].min():.3f}, {pts[:,0].max():.3f}]"
        f"  Y [{pts[:,1].min():.3f}, {pts[:,1].max():.3f}]"
        f"  Z [{pts[:,2].min():.3f}, {pts[:,2].max():.3f}]")

    # get_contact_radius reproduction: max sqrt(x^2+z^2)/2
    dxz = np.sqrt(pts[:, 0]**2 + pts[:, 2]**2)
    imax = int(dxz.argmax())
    say(f"  get_contact_radius = max|XZ|/2 = {dxz.max()/2.0:.3f}"
        f"   (max point at X={pts[imax,0]:.2f} Z={pts[imax,2]:.2f} Y={pts[imax,1]:.2f})")

    # Sanity: is the far point roughly diametrically opposite the tip (on the X axis, Z~0)?
    say(f"  far-point Z/X ratio = {pts[imax,2]/max(pts[imax,0],1e-9):.4f} "
        f"(should be ~0 if it is the opposite rim of the disc)")

    # Independent estimate: fit the disc rim. Rim = points at max radial distance
    # from the shaft axis. Shaft is along Y; disc axis = line x=cx, z=cz.
    # Estimate disc axis as centroid of ALL points in XZ (revolution body).
    cx, cz = pts[:, 0].mean(), pts[:, 2].mean()
    rr = np.sqrt((pts[:, 0]-cx)**2 + (pts[:, 2]-cz)**2)
    say(f"  centroid-axis estimate: axis at X={cx:.2f} Z={cz:.2f}; "
        f"max radius about axis = {rr.max():.3f}")
    # distance tip(0,0) -> axis:
    say(f"  |tip -> axis| = {math.hypot(cx, cz):.3f}  (independent disc-radius estimate)")

    # Rim rounding radius: look at the profile near the tip.
    # Take points with y in a thin slab through the widest section? Better: revolve
    # everything into (r_axis, y) profile coordinates.
    prof_r = rr
    prof_y = pts[:, 1]
    # tip in profile coords:
    tip_r = math.hypot(cx, cz)
    near = np.abs(prof_r - prof_r.max()) < 3.0   # outer 3mm band of the rim
    say(f"  rim band ({near.sum()} pts): y range [{prof_y[near].min():.2f}, {prof_y[near].max():.2f}]"
        f"  -> rim axial thickness ~{prof_y[near].max()-prof_y[near].min():.2f}")

    # ---- SUPPORT FUNCTION in the XZ working plane ----
    # Canonical: tip at origin = contact point for a purely radial surface normal
    # (mandrel toward -X). For a surface whose outward normal n(theta) is tilted
    # theta degrees from +X toward +Z (or -Z), the roller penetrates the tangent
    # plane through the tip by delta(theta) = -min_p(p . n). To *touch*, the tip
    # must back off delta along n. delta(0) should be ~0 by construction.
    say("  support function (theta = surface-normal tilt from radial, XZ plane):")
    say("    theta   delta+ (toward +Z)   delta- (toward -Z)")
    for th in (0, 5, 10, 15, 20, 30, 45, 60, 75, 89):
        t = math.radians(th)
        npos = np.array([math.cos(t), 0.0, math.sin(t)])
        nneg = np.array([math.cos(t), 0.0, -math.sin(t)])
        dpos = -float((pts @ npos).min())
        dneg = -float((pts @ nneg).min())
        say(f"    {th:5.0f}   {dpos:12.3f}       {dneg:12.3f}")

say("=" * 70)
say("done")
OUT.close()
