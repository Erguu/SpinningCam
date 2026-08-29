# -*- coding: utf-8 -*-
"""Reverse passes after the #82 leg swap was deleted (2026-08-30).

ONE RULE: a reverse pass is the forward pass driven backwards. Every exit shape
— bow, arc, curl, break points, the legacy `exit_mid` — behaves identically in
both directions, and no flag, mode or checkbox selects between them.

What that replaced: #82 forced the leg over the free blank straight on a reverse
pass and moved the curve onto the outgoing arm. The straightening worked; the
move did not, because `path_generator.py:2514` collapses the arm to its two end
points. So every exit-shape field silently did nothing on a reverse pass, and
break points could not be offered there at all.

What must hold:
  1. reverse == forward reversed, for EVERY exit shape. To the float.
  2. The default is untouched: with no shape set, a reverse pass is byte-for-byte
     what it always was (straight in, straight out).
  3. A shape that used to be ignored on a reverse pass now cuts — the one place
     this release changes metal, so it is pinned here deliberately, not by
     accident, and the recipe audit names the operations affected.
  4. A reverse op builds no back pass (#49) — it already IS the return stroke.
  5. The 3D view draws a reverse pass's straight arm straight.
  6. The break editor can still find the exit leg of a reversed array.

Run:  runtest.bat _test_break_points_reverse.py
"""
import numpy as np

import exit_breaks as eb
import recipe_explain
from mandrel_analyzer import MandrelManager
from path_generator import PathGenerator

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")


mgr = MandrelManager()
mgr.create_default_cone()
mgr.update_geometry(0, 0, 0, 0.0, 0.0)
pg = PathGenerator()

BREAKS = [{"t": 0.35, "angle": -15.0}, {"t": 0.70, "angle": -15.0}]
PASS_EDITS = {"0": {"exit_breaks": BREAKS}}


def build_all(direction, **extra):
    """Every toolpath this op produces (a back pass adds a second)."""
    op = {"type": "roughing", "count": 1, "start_z": 30.0, "r_tool": 25.0,
          "clearance": 0.0, "p1_x": 40.0, "p1_z": 50.0, "p3_x": 30.0, "p3_z": -25.0,
          "pass_shape": "linear_approach", "direction": direction}
    op.update(extra)
    p = {"operations": [op], "auto_calc_angle": False, "min_safety_gap": -999.0,
         "final_part_thickness_on_mandrel": 0.0, "shell_thickness": 0.0}
    return pg.calculate_paths(p, {}, mgr)[0]


def build(direction, **extra):
    return build_all(direction, **extra)[0]


# ── 1. one rule, every shape ────────────────────────────────────────────────
print("\n[1] reverse == forward reversed, for every exit shape")
SHAPES = (
    ("nothing set",     {}),
    ("break points",    {"pass_edits": PASS_EDITS}),
    ("exit_bow",        {"exit_bow": 8.0}),
    ("exit_arc_angle",  {"exit_arc_angle": 25.0}),
    ("legacy exit_mid", {"exit_mid_t": 0.5, "exit_mid_rotation": -12.0}),
    ("curl",            {"exit_mid_radius": 60.0}),
    ("p2 fillet",       {"p2_radius": 10.0}),
)
for label, kw in SHAPES:
    f, r = build("forward", **kw), build("reverse", **kw)
    check(f"{label}: point-for-point equal",
          r.shape == f.shape and np.allclose(r, f[::-1], atol=1e-12))

check("break points move the reverse pass's START point",
      not np.allclose(build("reverse", pass_edits=PASS_EDITS)[0],
                      build("reverse")[0], atol=1e-6))
check("the editor is offered on a reverse op",
      eb.excluded_reason({"pass_shape": "linear_approach",
                          "direction": "reverse"}) is None)


# ── 2. the default did not move ─────────────────────────────────────────────
print("\n[2] a reverse pass with no exit shape is what it always was")
plain = build("reverse")
check("still straight in, straight out (== forward reversed)",
      np.allclose(plain, build("forward")[::-1], atol=1e-12))
# The arm is the positioning leg in BOTH directions now — two points, no bow.
arm = np.array([q for q in plain if q[2] <= 30.0001])
check(f"the arm is a straight two-point leg ({len(arm)} pts)", len(arm) == 2)


# ── 3. what this release DOES change, pinned on purpose ────────────────────
print("\n[3] shapes that used to be ignored on a reverse pass now cut")
for label, kw in (("exit_bow", {"exit_bow": 8.0}),
                  ("exit_arc_angle", {"exit_arc_angle": 25.0}),
                  ("legacy exit_mid", {"exit_mid_t": 0.5, "exit_mid_rotation": -12.0})):
    check(f"reverse + {label} differs from a plain reverse pass",
          not np.allclose(build("reverse", **kw), plain, atol=1e-6))

# ...and the audit names the operations, so it is findable before a part is cut.
_a = recipe_explain.audit_operations({"operations": [
    {"type": "roughing", "count": 1, "direction": "reverse",
     "pass_shape": "linear_approach", "exit_bow": 8.0, "name": "R1"}]})
check("the audit flags a reverse op carrying an exit shape",
      any("exit_bow" in f["msg"] for f in _a))
_a2 = recipe_explain.audit_operations({"operations": [
    {"type": "roughing", "count": 1, "direction": "forward",
     "pass_shape": "linear_approach", "exit_bow": 8.0, "name": "F1"}]})
check("...and says nothing about a forward op",
      not any("exit_bow" in f["msg"] for f in _a2))
_a3 = recipe_explain.audit_operations({"operations": [
    {"type": "roughing", "count": 1, "direction": "reverse",
     "pass_shape": "linear_approach", "name": "R2"}]})
check("...nor about a reverse op with no shape set",
      not any("exit_bow" in f["msg"] for f in _a3))


# ── 4. a reverse op builds no back pass (#49) ──────────────────────────────
print("\n[4] a reverse operation builds no back pass")
fwd_bp = build_all("forward", back_pass_enabled=True)
rev_bp = build_all("reverse", back_pass_enabled=True)
ign = list(getattr(pg, "last_back_pass_ignored", []) or [])   # cleared per run
check(f"forward still gets its back pass ({len(fwd_bp)} paths)", len(fwd_bp) == 2)
check(f"reverse gets ONE path, not two (got {len(rev_bp)})", len(rev_bp) == 1)
check("the reverse pass itself is unchanged by the back-pass tick",
      np.allclose(rev_bp[0], build("reverse"), atol=1e-12))
check(f"and it is REPORTED, not dropped in silence ({len(ign)} entry)",
      len(ign) == 1 and ign[0].get("op_name"))
build_all("forward", back_pass_enabled=True)
check("a forward op reports nothing", not getattr(pg, "last_back_pass_ignored", []))
_a4 = recipe_explain.audit_operations({"operations": [
    {"type": "roughing", "count": 1, "direction": "reverse",
     "back_pass_enabled": True, "name": "R3"}]})
check("the audit reports the dead Back Pass tick",
      any("Back Pass" in f["msg"] or "Geri Pas" in f["msg"] for f in _a4))


# ── 5. the break editor can still find the exit leg ────────────────────────
print("\n[5] last_reverse_split_idx locates the exit leg (editor advisory)")
r_brk = build("reverse", pass_edits=PASS_EDITS)
rev_split = dict(getattr(pg, "last_reverse_split_idx", {}) or {})
check("recorded for the reverse pass", 0 in rev_split, f"got {rev_split}")
check("last_render_split_idx still dropped (decimator untouched)",
      0 not in (getattr(pg, "last_render_split_idx", {}) or {}))
if 0 in rev_split:
    leg = r_brk[:rev_split[0][0] + 1][::-1]        # exactly what the dialog slices
    check("leg is a proper subset of the pass", 3 <= len(leg) < len(r_brk),
          f"{len(leg)} of {len(r_brk)} pts")
    check("leg ends at the pass start point (P3)",
          np.allclose(leg[-1], r_brk[0], atol=1e-12))
    f_brk = build("forward", pass_edits=PASS_EDITS)
    fwd_split = (getattr(pg, "last_render_split_idx", {}) or {}).get(0)
    if fwd_split:
        check("identical to the forward pass's exit leg",
              np.allclose(leg, f_brk[fwd_split[1]:], atol=1e-12))


# ── 6. the 3D view draws the straight arm straight ─────────────────────────
# main.py's segment logic is TRANSCRIBED here, the house pattern for UI code
# that cannot be imported headless. A reverse pass has no split index, so it
# used to fall into corner detection — which only fires above 90°, while a pass
# turns ~50° at P2. Nothing fired, the whole path became one spline, and the
# straight arm was DRAWN with a 5.28 mm bow on data straight to 0.000 mm.
print("\n[6] 3D render: the drawn arm is as straight as the data")
try:
    import pyvista as pv

    def _seg_poly(pts, straight):
        if straight or len(pts) <= 2:
            return pv.lines_from_points(pts)
        return pv.Spline(pts, n_points=max(50, min(200, len(pts) * 10)))

    def render(p_arr, pgen, i=0):
        n_pts = len(p_arr)
        splits = pgen.last_render_split_idx.get(i)
        if splits is None:
            _rev = getattr(pgen, "last_reverse_split_idx", {}).get(i)
            if _rev is not None:
                p_arr = p_arr[::-1]
                splits = (n_pts - 1 - _rev[1], n_pts - 1 - _rev[0])
        if splits is not None:
            le = min(splits[0], n_pts - 1)
            ae = min(max(splits[1], le), n_pts - 1)
            poly = _seg_poly(p_arr[:le + 1], True)
            if ae > le:
                poly = poly.merge(_seg_poly(p_arr[le:ae + 1], True))
            if ae < n_pts - 1:
                poly = poly.merge(_seg_poly(p_arr[ae:], False))
            return poly
        d = np.diff(p_arr, axis=0)
        L = np.linalg.norm(d, axis=1, keepdims=True)
        dn = d / np.where(L < 1e-10, 1e-10, L)
        dots = np.clip(np.einsum('ij,ij->i', dn[:-1], dn[1:]), -1, 1)
        si = int(np.argmin(dots)) + 1 if dots.min() < 0 else None
        if si is not None:
            return _seg_poly(p_arr[:si + 1], False).merge(_seg_poly(p_arr[si:], False))
        return _seg_poly(p_arr, False)

    def arm_bow(poly, z_p2=30.0):
        pts = np.asarray(poly.points, float)
        seg = pts[pts[:, 2] <= z_p2 + 1e-6]
        if len(seg) < 3:
            return 0.0
        a, b = seg[0], seg[-1]
        ab = b - a
        L = np.linalg.norm(ab)
        return 0.0 if L < 1e-9 else float(
            np.max(np.linalg.norm(np.cross(seg - a, ab / L), axis=1)))

    for label, kw in (("no fillet", {}), ("p2_radius=10", {"p2_radius": 10.0}),
                      ("p2_radius=25", {"p2_radius": 25.0})):
        pf = build("forward", **kw)
        bf = arm_bow(render(np.array(pf, float), pg))
        pr = build("reverse", **kw)
        br = arm_bow(render(np.array(pr, float), pg))
        check(f"{label}: reverse draws the arm like forward "
              f"({br:.3f} vs {bf:.3f} mm)", abs(br - bf) < 1e-6)
    check("no fillet: the drawn arm is straight (was 5.284 mm)",
          arm_bow(render(np.array(build("reverse"), float), pg)) < 1e-9)
except ImportError:                                            # pragma: no cover
    print("  SKIP  pyvista unavailable")


print()
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for n in FAIL:
        print("  FAILED:", n)
    raise SystemExit(1)
print("ALL PASS")
