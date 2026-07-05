# Research: true roller-to-blank gap for the two offset models in path_generator,
# evaluated over the ACTUAL mandrel profile with the ACTUAL roller STEP shapes.
#
# Model A (radial): roughing P2 / straight finishing / all clearance-correction loops.
#   ref = P_mandrel(z) + x_hat * (r_tool + blank + clr)
# Model B (normal): conformal P2 / adaptive / sweeping.
#   ref = P_mandrel(z) + n(z) * (r_tool + blank + clr)
# Machine only TRANSLATES the tool (fixed orientation), tip = ref - r_tool*x_hat.
# True gap to the blank outer surface (blank lies on mandrel, thickness along n):
#   gap = n . (tip - P_mandrel) - blank - delta(n)
# where delta(n) = -min_p(p . n) over canonical roller mesh = penetration of the
# roller body beyond the tip's tangent plane for surface-normal direction n.
import sys, os, json, math
import numpy as np

REPO = r"C:\Users\PC\Documents\Python_Projects\SpinningCam"
sys.path.insert(0, REPO)
os.chdir(REPO)

OUT = open("_research_clearance_models.out", "w", encoding="utf-8")
def say(*a):
    s = " ".join(str(x) for x in a)
    print(s); OUT.write(s + "\n"); OUT.flush()

from config_schema import migrate_clearance
from mandrel_analyzer import MandrelManager
from tool_step_loader import ToolStepLoader

p = json.load(open("settings.json", encoding="utf-8"))
migrate_clearance(p)
mm = MandrelManager()
mm.load_step(p["last_step_path"])
mm.update_geometry(p.get("mandrel_rot_x", 90), 0, 0, 0, 0)

blank = float(p.get("final_part_thickness_on_mandrel", 0.0))
say(f"mandrel: {p['last_step_path']}")
say(f"blank thickness = {blank}")

zmin = mm.props.get("min_z"); ztop = mm.props.get("top_z")
say(f"mandrel z range: [{zmin:.2f}, {ztop:.2f}]")

# --- surface angle distribution ---
zs = np.linspace(zmin + 0.5, ztop - 0.5, 400)
angs = []
for z in zs:
    nx, nz = mm.get_normal_at_z(z)
    angs.append(math.degrees(math.atan2(nz, nx)))
angs = np.array(angs)
say(f"surface normal tilt from radial: min {angs.min():.1f} deg, max {angs.max():.1f} deg")
say("  histogram (deg : fraction of z-range):")
for lo in range(-90, 90, 15):
    frac = float(np.mean((angs >= lo) & (angs < lo + 15)))
    if frac > 0.001:
        say(f"    [{lo:+3d},{lo+15:+3d}) : {frac*100:5.1f}%")

# --- ops ---
ops = p.get("operations", [])
say("\noperations:")
for op in ops:
    say(f"  {op.get('name','?')}: type={op.get('type')} tool={op.get('tool_id')} "
        f"r_tool={op.get('r_tool')} clearance={op.get('clearance')} enabled={op.get('enabled', True)}")

tools = {t["id"]: t for t in json.load(open("tools.json", encoding="utf-8"))}
loader = ToolStepLoader(REPO)

def canonical_pts(tid):
    tl = tools[tid]
    c = loader._get_canonical(tl, tl["step_file"])
    return np.asarray(c.points)

def true_gap(tool_pts, r_tool, clr, model):
    """min over z of the true tip-plane gap; returns (min_gap, z_at_min, per-z arrays)."""
    gaps = np.empty(len(zs))
    for i, z in enumerate(zs):
        nx, nz = mm.get_normal_at_z(z)
        n = np.array([nx, 0.0, nz])
        delta = -float((tool_pts @ n).min())          # body penetration beyond tip plane
        if model == "radial":
            tip_minus_P = np.array([blank + clr, 0.0, 0.0])
        else:  # normal
            tip_minus_P = n * (r_tool + blank + clr) - np.array([r_tool, 0.0, 0.0])
        gaps[i] = float(n @ tip_minus_P) - blank - delta
    return gaps

say("\n=== TRUE GAP (negative = roller digs into blank envelope) ===")
for tid, clr_key in (("T0101", "roughing"), ("T0103", "finishing")):
    tpts = canonical_pts(tid)
    # find the op that uses this tool for its clearance value
    clr = 0.0; r_tool = tools[tid].get("r_tool") or tools[tid]["radius"]
    for op in ops:
        if op.get("tool_id") == tid:
            clr = float(op.get("clearance", 0.0))
            r_tool = float(op.get("r_tool", r_tool))
            break
    say(f"\nTOOL {tid}  r_tool={r_tool}  clearance={clr}  blank={blank}")
    for model in ("radial", "normal"):
        gaps = true_gap(tpts, r_tool, clr, model)
        i_min = int(gaps.argmin()); i_max = int(gaps.argmax())
        say(f"  model={model:7s}: gap min {gaps.min():+8.3f} mm at z={zs[i_min]:7.2f} "
            f"(tilt {angs[i_min]:+5.1f} deg) | gap max {gaps.max():+8.3f} mm at z={zs[i_max]:7.2f} "
            f"(tilt {angs[i_max]:+5.1f} deg)")
        # a few sample z's across the range
        for frac in (0.05, 0.25, 0.5, 0.75, 0.95):
            i = int(frac * (len(zs) - 1))
            say(f"      z={zs[i]:7.2f} tilt={angs[i]:+5.1f} deg -> gap {gaps[i]:+8.3f} mm")

say("\ndone")
OUT.close()
