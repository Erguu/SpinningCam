# -*- coding: utf-8 -*-
"""TODO #102 — one shared viewpoint for every 2D pass sketch.

THE PROBLEM THIS EXISTS FOR (found 2026-08-28)

The 2D previews disagreed with each other and with the 3D view:

* the pass table drew **Z horizontal, larger X up**, mirrored for a
  negative-X-side machine;
* the waypoint editor drew **X horizontal, larger Z up**, and never mirrored —
  the axes were literally swapped between two windows showing the same pass;
* the 3D view sits wherever the operator last orbited it.

Three orientations for one pass. An operator who has the 3D view set up the way
he thinks about the machine then reads a sketch that disagrees with it, and the
sign of a number he is about to type is exactly what he gets wrong.

WHAT THIS DOES

Reads the live 3D camera and reports which CAM axis is horizontal on screen and
which way each one grows. Both previews then lay their sketch out through the
same `to_plane`, so they match each other and roughly match the 3D view.

SNAPPED, AND FIXED WHILE THE WINDOW IS OPEN (user, 2026-08-28). The result is
one of four orientations, not a free rotation: a sketch is a schematic, and a
freely rotating one is harder to read, not easier. It is resolved once when a
dialog opens — a preview that re-orients under the operator's hands while he is
typing into it would be worse than one that is merely stale.

THE MIRROR IS PART OF THE ORIENTATION. Rows and waypoints are computed in the
canonical +X frame, but the machine (and the 3D scene) mirrors X around the
mandrel centre when the roller is on the negative side. `to_plane` applies that
mirror, so every preview draws what the machine does rather than one drawing
canonical and another machine coordinates.

⚠ WHICH FRAME YOUR POINTS ARE IN IS NOT OPTIONAL — pass `frame=` to `resolve`.
The engine mirrors X at the very END of `calculate_paths`, so anything read out
of `last_calculated_paths` (the SCL inspector) is ALREADY in machine
coordinates, while `compute_pass_rows` and the waypoint editor are canonical.
Mirroring a machine-frame point again lands it on the far side of the axis, and
on a positive-side machine — where the mirror is the identity — the mistake is
completely invisible. That is the failure #100 already paid for once.
"""
from collections import namedtuple

from logger_config import logger

# z_horizontal : True  → CAM Z runs across the sketch, X up the sketch
#                False → CAM X runs across, Z up
# h_sign/v_sign: +1 keeps the axis growing right/up, -1 flips it
Orient = namedtuple("Orient", "z_horizontal h_sign v_sign mirror_x center_x")

# What the pass table has always used. Also the fallback whenever the camera
# cannot be read (headless tests, a dialog opened before the 3D view exists),
# so behaviour without a plotter is exactly what it was before #102.
DEFAULT = Orient(z_horizontal=True, h_sign=1, v_sign=1, mirror_x=False, center_x=0.0)


def _camera_axes(app):
    """(right, up) unit vectors of the 3D view in CAM coordinates, or None."""
    plotter = getattr(app, "plotter", None)
    cam = getattr(plotter, "camera", None) if plotter is not None else None
    if cam is None:
        return None
    try:
        pos = [float(v) for v in cam.position]
        foc = [float(v) for v in cam.focal_point]
        up = [float(v) for v in cam.up]
    except Exception:
        return None

    def _sub(a, b):
        return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]

    def _cross(a, b):
        return [a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0]]

    def _norm(v):
        m = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
        return None if m < 1e-9 else [v[0] / m, v[1] / m, v[2] / m]

    fwd = _norm(_sub(foc, pos))
    if fwd is None:
        return None
    right = _norm(_cross(fwd, up))
    if right is None:                 # looking straight along `up` — degenerate
        return None
    return right, _cross(right, fwd)  # already unit: right ⊥ fwd, both unit


CANONICAL = "canonical"    # +X frame: pass rows, waypoint offsets, op params
MACHINE = "machine"        # what last_calculated_paths holds — mirror ALREADY applied


def resolve(app, frame=CANONICAL):
    """The orientation to draw a pass sketch in, from the live 3D camera.

    `frame` says which X the CALLER will hand to `to_plane`. With `MACHINE` the
    mirror is switched off, because those coordinates already carry it — see the
    warning in the module docstring for why getting this wrong is silent on a
    positive-side machine.

    Never raises and never returns None — a preview that cannot be laid out is
    worse than one laid out the old way, so every failure path returns DEFAULT.
    """
    params = getattr(app, "params", None) or {}
    mirror = (frame != MACHINE) and not params.get("roller_positive_x_side", True)
    try:
        center_x = float(params.get("mandrel_pos_x_offset", 0.0) or 0.0)
    except (TypeError, ValueError):
        center_x = 0.0

    axes = None
    try:
        axes = _camera_axes(app)
    except Exception as e:
        logger.debug(f"#102 preview orientation: camera unreadable ({e})")
    if axes is None:
        return DEFAULT._replace(mirror_x=mirror, center_x=center_x)

    right, up = axes
    # How far each CAM axis travels across the screen and up it. CAM X is world
    # X, CAM Z is world Z — the pass lies in the y=0 plane either way.
    x_h, x_v = right[0], up[0]
    z_h, z_v = right[2], up[2]

    # Whichever axis is more horizontal on screen becomes the sketch's
    # horizontal. Ties (a perfect 45°) fall to Z, which keeps the familiar
    # pass-table layout rather than flipping on a knife edge.
    z_horizontal = abs(z_h) >= abs(x_h)
    if z_horizontal:
        h_sign = 1 if z_h >= 0 else -1
        v_sign = 1 if x_v >= 0 else -1
    else:
        h_sign = 1 if x_h >= 0 else -1
        v_sign = 1 if z_v >= 0 else -1
    return Orient(z_horizontal, h_sign, v_sign, mirror, center_x)


def to_plane(orient, x, z):
    """CAM (x, z) → (horizontal, vertical) in millimetres, ready to be fitted.

    Vertical grows UPWARD; a canvas caller still has to flip it for screen
    coordinates, because that is a property of the canvas, not of the view.
    """
    if orient.mirror_x:
        x = 2.0 * orient.center_x - x
    if orient.z_horizontal:
        return orient.h_sign * z, orient.v_sign * x
    return orient.h_sign * x, orient.v_sign * z


def axis_labels(orient):
    """(horizontal, vertical) axis letters, so a preview can label what it drew.

    Without this the operator has no way to tell a flipped sketch from a
    differently-shaped pass — which is the failure this whole module is about.
    """
    h, v = ("Z", "X") if orient.z_horizontal else ("X", "Z")
    return (h + ("→" if orient.h_sign > 0 else "←"),
            v + ("↑" if orient.v_sign > 0 else "↓"))
