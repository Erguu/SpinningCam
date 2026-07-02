"""Roller cross-section preview dialog.

Loads the tool STEP file, slices it at Y=0 (XZ plane), and draws the
2D outline on a dark Tkinter canvas.  Falls back to a parametric schematic
if the STEP file is missing or fails to load.
"""

import tkinter as tk
from tkinter import ttk
import math
import threading


# ─── OCC cross-section extraction ────────────────────────────────────────────

def _extract_xz_section(step_file: str, step_rotation: list) -> list:
    """Return list of edge point-lists [(x,z), ...] in the XZ plane.
    All OCC imports are lazy so a missing OCC install degrades gracefully.
    """
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepBndLib import brepbndlib
    from OCC.Core.gp import (gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir,
                               gp_Vec, gp_Pln)
    from OCC.Core.BRepBuilderAPI import (BRepBuilderAPI_Transform,
                                          BRepBuilderAPI_MakeFace)
    from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
    from OCC.Core.GCPnts import GCPnts_QuasiUniformDeflection
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_EDGE
    from OCC.Core.TopoDS import topods

    # ── Load ─────────────────────────────────────────────────────────────
    reader = STEPControl_Reader()
    if reader.ReadFile(step_file) != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed: {step_file}")
    reader.TransferRoots()
    shape = reader.OneShape()

    # ── Centre the shape ─────────────────────────────────────────────────
    bbox = Bnd_Box()
    brepbndlib.Add(shape, bbox)
    x0, y0, z0, x1, y1, z1 = bbox.Get()
    cx, cy, cz = (x0+x1)/2, (y0+y1)/2, (z0+z1)/2
    tc = gp_Trsf()
    tc.SetTranslation(gp_Vec(-cx, -cy, -cz))
    shape = BRepBuilderAPI_Transform(shape, tc, True).Shape()

    # ── Apply step_rotation (rx, ry, rz in degrees) ──────────────────────
    rx = float(step_rotation[0]) if len(step_rotation) > 0 else 0.0
    ry = float(step_rotation[1]) if len(step_rotation) > 1 else 0.0
    rz = float(step_rotation[2]) if len(step_rotation) > 2 else 0.0
    for angle, axis in [(rx, gp_Dir(1,0,0)),
                        (ry, gp_Dir(0,1,0)),
                        (rz, gp_Dir(0,0,1))]:
        if abs(angle) > 0.001:
            t = gp_Trsf()
            t.SetRotation(gp_Ax1(gp_Pnt(0,0,0), axis), math.radians(angle))
            shape = BRepBuilderAPI_Transform(shape, t, True).Shape()

    # ── Re-centre after rotation ──────────────────────────────────────────
    bbox2 = Bnd_Box()
    brepbndlib.Add(shape, bbox2)
    ax0, ay0, az0, ax1, ay1, az1 = bbox2.Get()
    tc2 = gp_Trsf()
    tc2.SetTranslation(gp_Vec(-(ax0+ax1)/2, -(ay0+ay1)/2, -(az0+az1)/2))
    shape = BRepBuilderAPI_Transform(shape, tc2, True).Shape()

    # ── XZ cross-section (cutting plane: normal = Y, passing through Y=0) ─
    big = max(abs(ax1-ax0), abs(az1-az0), abs(ay1-ay0)) * 2 + 100
    plane = gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0))
    face  = BRepBuilderAPI_MakeFace(plane, -big, big, -big, big).Face()
    sec   = BRepAlgoAPI_Section(shape, face, False)
    sec.ComputePCurveOn1(True)
    sec.Approximation(True)
    sec.Build()
    result = sec.Shape()

    # ── Discretise each edge ──────────────────────────────────────────────
    edges = []
    exp = TopExp_Explorer(result, TopAbs_EDGE)
    while exp.More():
        edge = topods.Edge(exp.Current())
        try:
            ada = BRepAdaptor_Curve(edge)
            disc = GCPnts_QuasiUniformDeflection(ada, 0.3)
            pts = []
            for i in range(1, disc.NbPoints() + 1):
                p = ada.Value(disc.Parameter(i))
                pts.append((p.X(), p.Z()))
            if len(pts) >= 2:
                edges.append(pts)
        except Exception:
            pass
        exp.Next()
    return edges


# ─── Parametric schematic fallback ───────────────────────────────────────────

def _schematic_edges(disc_r: float, edge_r: float, tilt_deg: float) -> list:
    """Return approximate XZ cross-section of a toric spinning roller.
    disc_r  = outer disc radius (the `radius` field from tools.json)
    edge_r  = edge / corner radius (r_tool from operations)
    tilt_deg = disc tilt around Y axis in degrees
    """
    edges = []
    tilt = math.radians(tilt_deg)

    # The disc in its own frame: cross-section is two circles of radius edge_r
    # centred at ±(disc_r - edge_r) along the disc's radial axis.
    # We project that frame onto XZ after applying the Y-axis tilt.
    # Disc radial axis is originally X; after tilt it becomes (cos tilt, 0, sin tilt).
    # Disc axial axis is Z (shaft), unchanged by Y-tilt.

    centre_r = max(disc_r - edge_r, edge_r * 0.1)   # guard against edge_r > disc_r

    def toric_arc(side, n=80):
        # centre of this edge-circle in XZ after tilt
        # 'side' = +1 (outer) or -1 (inner, toward axis)
        cx = side * centre_r * math.cos(tilt)
        cz = side * centre_r * math.sin(tilt)
        pts = []
        for i in range(n + 1):
            a = 2 * math.pi * i / n
            # edge circle is in the disc's local (radial, axial) plane
            # radial direction in XZ:  (cos tilt, sin tilt)
            # axial direction in XZ:   (-sin tilt, cos tilt)  -- but disc Z maps to machine Z
            dx = math.cos(a)   # along disc radial after tilt
            dz = math.sin(a)   # along disc axial (Z, not affected by Y-tilt)
            px = cx + edge_r * (dx * math.cos(tilt) - dz * math.sin(tilt))
            pz = cz + edge_r * (dx * math.sin(tilt) + dz * math.cos(tilt))
            pts.append((px, pz))
        edges.append(pts)

    toric_arc(+1)   # outer toric edge
    toric_arc(-1)   # inner toric edge (if visible)

    # Disc face lines connecting the two circles at their extremes
    # (simplified: four tangent lines)
    for a in (math.pi/2, -math.pi/2):
        line = []
        for side in (+1, -1):
            cx = side * centre_r * math.cos(tilt)
            cz = side * centre_r * math.sin(tilt)
            dx = math.cos(a); dz = math.sin(a)
            px = cx + edge_r * (dx * math.cos(tilt) - dz * math.sin(tilt))
            pz = cz + edge_r * (dx * math.sin(tilt) + dz * math.cos(tilt))
            line.append((px, pz))
        edges.append(line)

    return edges


# ─── Dialog ──────────────────────────────────────────────────────────────────

class RollerPreviewDialog(tk.Toplevel):
    C_BG   = "#1a1a2e"
    C_EDGE = "#6688aa"
    C_ANN  = "#aaccff"
    C_DIM  = "#ffdd44"
    C_CON  = "#44cc77"
    C_AXIS = "#334455"

    def __init__(self, parent, tool: dict, r_tool: float, angle_deg: float):
        super().__init__(parent)
        self.tool      = tool
        self.r_tool    = r_tool
        self.angle_deg = angle_deg
        self._edges    = []          # list of [(x,z), …]
        self._zoom     = [1.0]
        self._pan      = [0.0, 0.0]
        self._drag     = [None, None]
        self._status   = tk.StringVar(value="Loading STEP…")

        name = tool.get("name", tool.get("id", "Roller"))
        self.title(f"Roller Preview — {name}")
        self.geometry("620x520")
        self.resizable(True, True)
        self.configure(bg=self.C_BG)

        # Status bar
        tk.Label(self, textvariable=self._status, bg=self.C_BG, fg="#7799aa",
                 font=("Consolas", 8, "italic")).pack(fill="x", padx=8, pady=(4, 0))

        self.canvas = tk.Canvas(self, bg=self.C_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=4)

        tk.Button(self, text="Close", command=self.destroy,
                  bg="#334455", fg="white", width=10).pack(pady=(0, 6))

        c = self.canvas
        c.bind("<MouseWheel>",      self._scroll)
        c.bind("<Button-4>",        self._scroll)
        c.bind("<Button-5>",        self._scroll)
        c.bind("<ButtonPress-1>",   lambda e: self._drag.__setitem__(0, e.x) or self._drag.__setitem__(1, e.y))
        c.bind("<B1-Motion>",       self._drag_move)
        c.bind("<ButtonRelease-1>", lambda e: (self._drag.__setitem__(0, None)))
        c.bind("<Double-Button-1>", lambda e: (self._zoom.__setitem__(0, 1.0),
                                                self._pan.__setitem__(0, 0.0),
                                                self._pan.__setitem__(1, 0.0),
                                                self._redraw()))
        c.bind("<Configure>",       lambda e: self.after(10, self._redraw))

        # Load STEP in background thread
        step_file = tool.get("step_file", "")
        threading.Thread(target=self._load, args=(step_file,), daemon=True).start()

    # ── Mouse ─────────────────────────────────────────────────────────────

    def _scroll(self, e):
        delta = e.delta if hasattr(e, 'delta') and e.delta != 0 else (120 if e.num == 4 else -120)
        factor = 1.12 if delta > 0 else 1/1.12
        self._zoom[0] = max(0.05, min(30.0, self._zoom[0] * factor))
        self._redraw()

    def _drag_move(self, e):
        if self._drag[0] is not None:
            self._pan[0] += e.x - self._drag[0]
            self._pan[1] += e.y - self._drag[1]
            self._drag[0], self._drag[1] = e.x, e.y
            self._redraw()

    # ── STEP load (background thread) ────────────────────────────────────

    def _load(self, step_file):
        try:
            if not step_file:
                raise FileNotFoundError("No step_file in tool data")
            import os
            if not os.path.exists(step_file):
                raise FileNotFoundError(step_file)
            rot = self.tool.get("step_rotation", [0, 0, 0])
            edges = _extract_xz_section(step_file, rot)
            self._edges = edges
            self.after(0, lambda: self._status.set(
                f"STEP cross-section  ·  {len(edges)} edges  ·  "
                f"scroll=zoom  drag=pan  dbl-click=reset"))
        except Exception as ex:
            # Fall back to schematic
            disc_r = float(self.tool.get("radius", 150.0))
            rot    = self.tool.get("step_rotation", [0, 0, 0])
            tilt   = float(rot[1]) if len(rot) > 1 else 0.0
            self._edges = _schematic_edges(disc_r, self.r_tool, tilt)
            self.after(0, lambda: self._status.set(
                f"Schematic (STEP unavailable: {ex})  ·  scroll=zoom  drag=pan"))
        self.after(0, self._redraw)

    # ── Drawing ───────────────────────────────────────────────────────────

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        W = c.winfo_width()  or 600
        H = c.winfo_height() or 460
        if W < 20 or H < 20:
            return
        if not self._edges:
            c.create_text(W/2, H/2, text="Loading…", fill="#445566",
                         font=("Consolas", 14))
            return
        self._draw(c, W, H)

    def _draw(self, C, W, H):
        zoom = self._zoom[0]
        pan  = self._pan

        # Collect all points to determine bounding box
        all_x = [p[0] for seg in self._edges for p in seg]
        all_z = [p[1] for seg in self._edges for p in seg]
        if not all_x:
            return

        cx = (min(all_x) + max(all_x)) / 2
        cz = (min(all_z) + max(all_z)) / 2
        span = max(max(all_x)-min(all_x), max(all_z)-min(all_z), 1.0)
        scale0 = min(W, H) * 0.75 / span   # base scale to fit

        def to_canvas(x, z):
            sx = (x - cx) * scale0 * zoom + W/2 + pan[0]
            sy = -(z - cz) * scale0 * zoom + H/2 + pan[1]  # Z up on canvas
            return sx, sy

        # ── Axes ─────────────────────────────────────────────────────────
        ox, oy = to_canvas(cx, cz)
        C.create_line(ox - W*0.4, oy, ox + W*0.4, oy,
                     fill=self.C_AXIS, width=1, dash=(4, 6))   # X axis
        C.create_line(ox, oy - H*0.4, ox, oy + H*0.4,
                     fill=self.C_AXIS, width=1, dash=(4, 6))   # Z axis
        C.create_text(ox + W*0.38, oy - 8, text="X", fill=self.C_AXIS,
                     font=("Consolas", 8))
        C.create_text(ox + 8, oy - H*0.38, text="Z", fill=self.C_AXIS,
                     font=("Consolas", 8))

        # ── Cross-section edges ───────────────────────────────────────────
        for seg in self._edges:
            if len(seg) < 2:
                continue
            flat = []
            for x, z in seg:
                sx, sy = to_canvas(x, z)
                flat += [sx, sy]
            C.create_line(*flat, fill=self.C_EDGE, width=max(1, int(1.5*zoom)),
                         smooth=True)

        # ── Contact point & approach angle annotation ─────────────────────
        r_t    = self.r_tool
        a_deg  = self.angle_deg
        a_rad  = math.radians(a_deg)
        r_eff  = r_t * math.cos(a_rad)

        disc_r = float(self.tool.get("radius", max(all_x, default=r_t)))
        rot    = self.tool.get("step_rotation", [0, 0, 0])
        tilt   = float(rot[1]) if len(rot) > 1 else 0.0
        tilt_r = math.radians(tilt)

        # Approximate contact point: outermost edge point in the +X direction
        contact_x = max(all_x)
        contact_z = 0.0  # centred
        cpx, cpy = to_canvas(contact_x, contact_z)

        # Approach direction arrow (from outside, approaching at a_deg from X)
        arr_len = min(W, H) * 0.18
        ax = cpx + arr_len * math.cos(math.pi - a_rad)
        ay = cpy - arr_len * math.sin(math.pi - a_rad)   # canvas Y inverted
        C.create_line(ax, ay, cpx, cpy, fill=self.C_CON, width=2, arrow=tk.LAST)
        if abs(a_deg) > 0.5:
            C.create_text((ax+cpx)/2 - 10, (ay+cpy)/2 - 10,
                         text=f"{a_deg:.1f}°", fill=self.C_CON,
                         font=("Consolas", max(7, int(8*zoom))))

        # Contact dot
        cr = max(3, int(4 * zoom))
        C.create_oval(cpx-cr, cpy-cr, cpx+cr, cpy+cr, fill=self.C_CON, outline="")

        # ── Dimension annotations ─────────────────────────────────────────
        def ann(x1, z1, x2, z2, label, color=self.C_DIM):
            sx1, sy1 = to_canvas(x1, z1)
            sx2, sy2 = to_canvas(x2, z2)
            mid_sx, mid_sy = (sx1+sx2)/2, (sy1+sy2)/2
            C.create_line(sx1, sy1, sx2, sy2, fill=color, width=1, dash=(3, 4))
            C.create_text(mid_sx + 4, mid_sy - 10, text=label, fill=color,
                         font=("Consolas", max(7, int(8*zoom))), anchor="w")

        # Outer radius of disc
        ann(0, 0, contact_x, 0,
            f"R={disc_r:.1f} mm", self.C_DIM)

        # Edge/corner radius indicator
        # Draw a small arc near the contact point to represent r_tool
        r_arc = r_t * scale0 * zoom
        if r_arc > 6:
            C.create_arc(cpx - r_arc, cpy - r_arc, cpx + r_arc, cpy + r_arc,
                        start=90, extent=90, style=tk.ARC,
                        outline=self.C_DIM, width=1)
            C.create_text(cpx + r_arc * 0.4, cpy - r_arc * 0.6,
                         text=f"Rr={r_t:.1f}", fill=self.C_DIM,
                         font=("Consolas", max(7, int(8*zoom))), anchor="w")

        # Effective radial offset
        if abs(a_deg) > 0.5:
            eff_px = r_eff * scale0 * zoom
            ex1, ey1 = to_canvas(contact_x, 0)
            ex2, ey2 = to_canvas(contact_x - r_eff, 0)
            C.create_line(ex1, ey1, ex2, ey2, fill="#ff8833", width=2)
            C.create_text((ex1+ex2)/2, ey1 - 12,
                         text=f"Rr·cos({a_deg:.0f}°) = {r_eff:.1f} mm",
                         fill="#ff8833", font=("Consolas", max(7, int(8*zoom))),
                         anchor="s")

        # Tilt angle annotation
        if abs(tilt) > 0.5:
            C.create_text(8, H - 8,
                         text=f"Disc tilt (Y-rot): {tilt:.1f}°",
                         fill="#7799aa", font=("Consolas", 8), anchor="sw")

        # Tool name + key values
        name = self.tool.get("name", self.tool.get("id", ""))
        C.create_text(8, 8,
                     text=f"{self.tool.get('id','')}  {name}",
                     fill=self.C_ANN, font=("Consolas", 9, "bold"), anchor="nw")
        C.create_text(8, 24,
                     text=f"Rr={r_t:.1f} mm   angle={a_deg:.1f}°   eff={r_eff:.2f} mm",
                     fill=self.C_ANN, font=("Consolas", 8), anchor="nw")
