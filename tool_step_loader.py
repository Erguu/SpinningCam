import os
import numpy as np
import pyvista as pv
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.BRep import BRep_Tool
from OCC.Core.TopoDS import topods
from OCC.Core.TopLoc import TopLoc_Location

from logger_config import logger


def _occ_load_step(path: str):
    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        return None
    reader.TransferRoots()
    if reader.NbShapes() < 1:
        return None
    return reader.Shape(1)


def _occ_to_pyvista(shape, deflection: float = 0.2):
    if shape is None:
        return None
    mesh = BRepMesh_IncrementalMesh(shape, deflection)
    mesh.Perform()
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    verts, faces = [], []
    v_offset = 0
    while exp.More():
        face = topods.Face(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation(face, loc)
        if tri:
            trsf = loc.Transformation()
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                verts.append([p.X(), p.Y(), p.Z()])
            tris = tri.Triangles()
            for i in range(1, tri.NbTriangles() + 1):
                n1, n2, n3 = tris.Value(i).Get()
                faces.extend([3, n1 - 1 + v_offset, n2 - 1 + v_offset, n3 - 1 + v_offset])
            v_offset += tri.NbNodes()
        exp.Next()
    if not verts:
        return None
    return pv.PolyData(np.array(verts), faces=np.array(faces))


def _resolve_step_path(tool_entry: dict, base_dir: str = "") -> str:
    """Return absolute path to the tool's STEP file, or empty string if not set/found."""
    step_file = tool_entry.get("step_file", "").strip()
    if not step_file:
        return ""
    if os.path.isabs(step_file):
        return step_file if os.path.isfile(step_file) else ""
    # Try relative to base_dir first, then cwd
    for root in (base_dir, os.getcwd()):
        if not root:
            continue
        candidate = os.path.normpath(os.path.join(root, step_file))
        if os.path.isfile(candidate):
            return candidate
    return ""


def _build_canonical(tool_entry: dict, step_path: str, deflection: float = 0.2):
    """Load STEP, apply orientation transforms, auto-detect closest-to-mandrel tip,
    translate so that tip lands at origin.  Canonical: tip at (0,0,0), shaft along Y,
    roller body extending in +X (for the default roller_positive_x_side=True case)."""
    shape = _occ_load_step(step_path)
    if shape is None:
        logger.warning(f"ToolStepLoader: failed to parse STEP: {step_path}")
        return None
    mesh = _occ_to_pyvista(shape, deflection)
    if mesh is None:
        logger.warning(f"ToolStepLoader: no geometry after triangulation: {step_path}")
        return None

    # 1. Rotate shaft_axis → Y
    shaft = tool_entry.get("shaft_axis", "Z").upper().strip()
    if shaft == "Z":
        mesh.rotate_x(-90.0, inplace=True)   # Rx(-90°) maps Z → Y
    elif shaft == "X":
        mesh.rotate_z(90.0, inplace=True)    # Rz(+90°) maps X → Y
    # shaft == "Y": no rotation needed

    # 2. Fine-tune rotations (degrees, applied X→Y→Z).
    #    Changing these shifts which face is closest to the mandrel — tip auto-updates below.
    rot = tool_entry.get("step_rotation", [0.0, 0.0, 0.0])
    if len(rot) >= 3:
        if rot[0]: mesh.rotate_x(float(rot[0]), inplace=True)
        if rot[1]: mesh.rotate_y(float(rot[1]), inplace=True)
        if rot[2]: mesh.rotate_z(float(rot[2]), inplace=True)

    # 3. Auto-detect the tip as the closest point to the mandrel = minimum X.
    #    For a body of revolution the minimum-X region is a circle; take its centroid
    #    so the anchor point lands at the centre of the contact edge, not an arbitrary vertex.
    min_x = float(mesh.points[:, 0].min())
    tol = max(0.1, abs(min_x) * 1e-3)          # within 0.1 mm (or 0.1 % of extent)
    mask = mesh.points[:, 0] <= min_x + tol
    centroid = mesh.points[mask].mean(axis=0)   # [cx, cy, cz]
    mesh.translate([-centroid[0], 0.0, -centroid[2]], inplace=True)
    # Y is intentionally left un-shifted: the roller sits symmetrically around Y=0.

    # 4. Optional post-rotation fine adjustment (tip_offset now lives in the rotated
    #    canonical frame — +X = away from mandrel, +Z = upward along spindle axis).
    tip_off = np.array(tool_entry.get("tip_offset", [0.0, 0.0, 0.0]), dtype=float)
    if np.any(tip_off != 0.0):
        mesh.translate(tip_off, inplace=True)

    return mesh


def _position_mesh(canonical: pv.PolyData, side: float, rx_tip: float, rz_tip: float,
                   tilt_deg: float = 0.0) -> pv.PolyData:
    """Copy canonical mesh, apply side-flip, optional B tilt, translate tip to position.

    tilt_deg rotates the tool about the Y axis at its tip (canonical tip is at the
    local origin). Positive tilt leans the radial tool axis toward +Z on either
    side, matching the tilt convention in kinematics.py (ID112 tilt-arm machine).
    """
    mesh = canonical.copy()
    if side < 0:
        mesh.points[:, 0] *= -1   # mirror X: body extends in -X for left-side roller
    if abs(tilt_deg) > 1e-9:
        mesh.rotate_y(-side * tilt_deg, point=(0.0, 0.0, 0.0), inplace=True)
    mesh.translate([rx_tip, 0.0, rz_tip], inplace=True)
    return mesh


class ToolStepLoader:
    """Loads and caches STEP meshes for spinning tools, positions them in machine space."""

    def __init__(self, base_dir: str = ""):
        self._cache: dict = {}   # {(abs_path, mtime): pv.PolyData}  canonical mesh
        self.base_dir = base_dir

    def get_roller_mesh(self, tool_entry: dict, side: float,
                        rx_tip: float, rz_tip: float,
                        tilt_deg: float = 0.0) -> "pv.PolyData | None":
        """Return a positioned mesh for the tool, or None (→ caller uses sphere fallback)."""
        step_path = _resolve_step_path(tool_entry, self.base_dir)
        if not step_path:
            return None
        canonical = self._get_canonical(tool_entry, step_path)
        if canonical is None:
            return None
        return _position_mesh(canonical, side, rx_tip, rz_tip, tilt_deg)

    def _get_canonical(self, tool_entry: dict, step_path: str) -> "pv.PolyData | None":
        try:
            mtime = os.path.getmtime(step_path)
        except OSError:
            return None
        # Include transform params in key so rotation/offset changes auto-invalidate.
        shaft = tool_entry.get("shaft_axis", "Z")
        rot   = tuple(tool_entry.get("step_rotation", [0.0, 0.0, 0.0]))
        tip   = tuple(tool_entry.get("tip_offset",    [0.0, 0.0, 0.0]))
        key   = (step_path, mtime, shaft, rot, tip)
        if key not in self._cache:
            logger.info(f"ToolStepLoader: building canonical for {step_path} "
                        f"shaft={shaft} rot={rot} tip={tip}")
            self._cache[key] = _build_canonical(tool_entry, step_path)
        return self._cache[key]

    def get_contact_radius(self, tool_entry: dict) -> "float | None":
        """Disc outer radius from STEP geometry.

        After _build_canonical() the TIP (disc rim closest to mandrel) is at the origin
        and the disc body extends in +X.  The far rim of a disc of radius R sits at X=2R,
        so the raw max-XZ distance from the origin equals the disc DIAMETER.  Dividing by 2
        gives the actual disc radius (= distance from disc centre to contact rim).
        """
        step_path = _resolve_step_path(tool_entry, self.base_dir)
        if not step_path:
            return None
        canonical = self._get_canonical(tool_entry, step_path)
        if canonical is None:
            return None
        pts = canonical.points
        return float(np.sqrt(pts[:, 0] ** 2 + pts[:, 2] ** 2).max()) / 2.0

    def get_contact_radius_axis(self, tool_entry: dict) -> "float | None":
        """CHALLENGER reach — does NOT replace get_contact_radius (kept as default).

        get_contact_radius() uses max|XZ|/2, which assumes the far rim point is the
        clean diametral opposite of the tip.  On these discs the far point sits ~45°
        off (tilted diagonal), so max|XZ|/2 blends disc radius with tilt and differs
        tool-to-tool by ~0.5-1 mm.  That inter-tool inconsistency is the residual gap
        seen when calibrating with one tool and running another.

        This method instead fits the disc's revolution axis (centroid of the XZ
        projection of the body) and returns the maximum rim radius about that axis —
        a tilt-independent, geometry-pure reach.  In the 2026-07-02 research this gave
        ~74.9 mm for both T0101 and T0103 (vs 73.79 / 74.31 from max|XZ|/2), i.e. the
        two discs are physically the same reach.  Exposed as an opt-in challenger for
        physical A/B validation; not wired into path-gen or calibration by default.
        """
        step_path = _resolve_step_path(tool_entry, self.base_dir)
        if not step_path:
            return None
        canonical = self._get_canonical(tool_entry, step_path)
        if canonical is None:
            return None
        pts = canonical.points
        # Fit the revolution axis as the centroid of the XZ projection, then take the
        # farthest rim point about it (same method as _research_tool_geometry.py).
        cx = float(pts[:, 0].mean())
        cz = float(pts[:, 2].mean())
        rr = np.sqrt((pts[:, 0] - cx) ** 2 + (pts[:, 2] - cz) ** 2)
        return float(rr.max())

    def get_canonical_mesh(self, tool_entry: dict, side: float) -> "pv.PolyData | None":
        """Return canonical mesh with tip at (0,0,0) and side-flip applied, ready for
        actor.SetPosition() — no translation to machine coords is applied here."""
        step_path = _resolve_step_path(tool_entry, self.base_dir)
        if not step_path:
            return None
        canonical = self._get_canonical(tool_entry, step_path)
        if canonical is None:
            return None
        mesh = canonical.copy()
        if side < 0:
            mesh.points[:, 0] *= -1
        return mesh

    def get_2d_profile(self, tool_entry: dict, side: float) -> "list | None":
        """XZ convex hull for the 2D calibration side view.

        The canonical mesh has shaft along Y and disc face in the XZ plane.
        step_rotation[1] (Ry) rotates around the shaft axis — for a symmetric
        disc this has zero visual effect in XZ.  We substitute Rx(-alpha) which
        tilts the disc OUT of the XZ plane and makes the physical tilt angle
        visible in the side view.

        Returns CCW-sorted [[x_can, z_can], ...] with tip at (0, 0), or None.
        """
        step_path = _resolve_step_path(tool_entry, self.base_dir)
        if not step_path:
            return None
        shaft = tool_entry.get("shaft_axis", "Z").upper().strip()
        rot   = tuple(tool_entry.get("step_rotation", [0.0, 0.0, 0.0]))
        tip   = tuple(tool_entry.get("tip_offset",    [0.0, 0.0, 0.0]))
        try:
            mtime = os.path.getmtime(step_path)
        except OSError:
            return None
        key = ("2d", step_path, mtime, shaft, rot, tip, round(side))
        if key in self._cache:
            return self._cache[key]

        canonical = self._get_canonical(tool_entry, step_path)
        result = None
        if canonical is not None:
            mesh = canonical.copy()
            # Ry(alpha) in canonical rotates around the shaft axis (Y) and has no
            # visual effect in XZ for a symmetric disc.  Apply Rx(-alpha) instead:
            # this tilts the disc face out of XZ so it appears at the correct angle.
            alpha = float(rot[1]) if len(rot) > 1 else 0.0
            if alpha:
                mesh.rotate_x(-alpha, inplace=True)
            if side < 0:
                mesh.points[:, 0] *= -1
            xz = mesh.points[:, [0, 2]]
            if len(xz) >= 3:
                try:
                    from scipy.spatial import ConvexHull
                    hull = ConvexHull(xz)
                    pts  = xz[hull.vertices]
                    cx, cz = pts.mean(axis=0)
                    ang  = np.arctan2(pts[:, 1] - cz, pts[:, 0] - cx)
                    result = pts[np.argsort(ang)].tolist()
                except Exception:
                    pass

        self._cache[key] = result
        return result

    def get_support_table(self, tool_entry: dict, side: float = 1.0):
        """Roller-body penetration table for tilted surface normals.

        For a surface whose outward normal is tilted `theta` degrees from radial
        (positive = toward +Z, i.e. mandrel radius decreasing with +Z), the roller
        body extends delta(theta) mm beyond the tangent plane through the TIP.
        The scalar r_tool model assumes delta == 0 for every angle; the real disc
        violates that on slopes, so delta is the clearance ERROR of that model.

        Returns (angles_deg, deltas_mm) numpy arrays for theta in [-89, +89],
        baseline-corrected so delta(0) == 0 (mesh tip-band tolerance removed),
        or None if the tool has no usable STEP mesh.
        """
        step_path = _resolve_step_path(tool_entry, self.base_dir)
        if not step_path:
            return None
        shaft = tool_entry.get("shaft_axis", "Z")
        rot   = tuple(tool_entry.get("step_rotation", [0.0, 0.0, 0.0]))
        tip   = tuple(tool_entry.get("tip_offset",    [0.0, 0.0, 0.0]))
        try:
            mtime = os.path.getmtime(step_path)
        except OSError:
            return None
        key = ("support", step_path, mtime, shaft, rot, tip, 1 if side >= 0 else -1)
        if key in self._cache:
            return self._cache[key]

        canonical = self._get_canonical(tool_entry, step_path)
        result = None
        if canonical is not None:
            pts = np.asarray(canonical.points)
            angles = np.linspace(-89.0, 89.0, 179)
            # Left-side roller is the X-mirror of the canonical mesh; in the
            # mirrored frame a +Z normal tilt maps to -Z on the canonical mesh.
            eff = angles if side >= 0 else -angles
            rad = np.radians(eff)
            dirs = np.column_stack([np.cos(rad), np.zeros_like(rad), np.sin(rad)])
            deltas = -(pts @ dirs.T).min(axis=0)
            base = deltas[np.argmin(np.abs(angles))]   # delta(0) ~ mesh tolerance
            deltas = np.maximum(0.0, deltas - base)
            result = (angles, deltas)

        self._cache[key] = result
        return result

    def invalidate(self, tool_id: str = "") -> None:
        """Clear cache — call after a tool's STEP file or offsets are changed."""
        self._cache.clear()
