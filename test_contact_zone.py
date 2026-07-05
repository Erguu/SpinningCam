"""
Focused verification for the per-point contact-zone feed feature.

Checks:
  1. Baseline (contact_zone_mm = 0) => no F<contact> feed appears.
  2. Enabled  => forward pass has contact feed on near-mandrel segments.
  3. Enabled  => BACK PASS has contact feed on its near-mandrel (inner) segments.
  4. Enabled  => approach/exit arms still run at the normal feed (not everything slow).
"""
import sys, os, re
sys.path.append(os.getcwd())

from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

NORMAL_FEED  = 800
CONTACT_FEED = 120


def build(contact_zone_mm, back_pass=True):
    mgr = MandrelManager()
    mgr.create_default_cone()
    mgr.update_geometry(0, 0, 0, 0, 0)

    pg = PathGenerator()
    op = {
        "type": "roughing",
        "tool_id": "T0101",
        "passes": 3,
        "feed": NORMAL_FEED,
        "speed": 200,
        "r_tool": 30.0,
        "contact_zone_mm": contact_zone_mm,
        "feed_contact": CONTACT_FEED,
    }
    if back_pass:
        op["back_pass_enabled"] = True
        op["back_pass_feed"] = NORMAL_FEED
    params = {
        "mandrel_pos_x_offset": 0.0,
        "shell_thickness": 2.0,
        "operations": [op],
        "feed": NORMAL_FEED,
        "speed": 200,
    }
    pg.calculate_paths(params, {}, mgr)
    return pg.generate_gcode(params=params)


def feeds_in(gcode, tag):
    """All F values on G1 lines whose comment contains `tag` (e.g. 'P' or 'BP')."""
    out = []
    for line in gcode.splitlines():
        if line.startswith("G1") and f"({tag}" not in line and tag in line:
            pass
    # simpler: match lines that contain the pass tag comment
    for line in gcode.splitlines():
        if not line.startswith("G1"):
            continue
        m = re.search(r"F([\d.]+)", line)
        if not m:
            continue
        if tag == "BP" and "BP" in line:
            out.append(float(m.group(1)))
        elif tag == "FWD" and re.search(r"P\d+\)", line) and "BP" not in line:
            out.append(float(m.group(1)))
    return out


print("=== Baseline: contact_zone_mm = 0 ===")
g0 = build(0.0)
assert f"F{CONTACT_FEED:.3f}" not in g0, "contact feed leaked into baseline!"
print("[PASS] No contact feed when disabled.")

print("\n=== Enabled: contact_zone_mm = 6 ===")
g1 = build(6.0)
fwd = feeds_in(g1, "FWD")
bp  = feeds_in(g1, "BP")

print(f"forward feeds seen: {sorted(set(fwd))}")
print(f"back-pass feeds seen: {sorted(set(bp))}")

assert CONTACT_FEED in fwd, "[FAIL] forward pass never used contact feed"
print("[PASS] Forward pass uses contact feed near mandrel.")

assert NORMAL_FEED in fwd, "[FAIL] forward pass never used normal feed (everything slow)"
print("[PASS] Forward pass keeps normal feed on approach/exit arms.")

assert bp, "[FAIL] no back-pass G1 feed lines found (back pass generated?)"
assert CONTACT_FEED in bp, "[FAIL] BACK PASS never used contact feed near mandrel"
print("[PASS] Back pass uses contact feed near mandrel.")

assert NORMAL_FEED in bp, "[FAIL] back pass never used normal feed (everything slow)"
print("[PASS] Back pass keeps normal feed on outer segment.")

print("\n--- ALL CHECKS PASSED ---")
