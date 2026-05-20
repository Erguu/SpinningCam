from typing import Optional
import numpy as np
import math
import pyvista as pv
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Ax2, gp_Trsf, gp_Vec
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCone
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.BRep import BRep_Tool
from OCC.Core.TopoDS import topods
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib

from logger_config import logger

class MandrelManager:
    def __init__(self):
        self.raw_shape = None
        self.oriented_shape = None
        self.mesh_cache = None 
        self.pv_mesh = None 
        
        self.props = {"h": 100.0, "br": 60.0, "tr": 10.0, "top_z": 100.0, "min_z": 0.0}
        self.profile_z = np.array([0.0, 100.0])
        self.profile_r = np.array([60.0, 10.0])
        
        # Ayarlar
        self.mesh_deflection = 0.1    
        self.scan_resolution = 0.5    

    def set_quality_params(self, mesh_quality: float, scan_res: float) -> None:
        self.mesh_deflection = mesh_quality
        self.scan_resolution = scan_res

    def load_step(self, filename: str) -> bool:
        logger.info(f"Loading STEP file: {filename}")
        step_reader = STEPControl_Reader()
        status = step_reader.ReadFile(filename)
        if status == IFSelect_RetDone:
            step_reader.TransferRoots()
            if step_reader.NbShapes() > 0:
                self.raw_shape = step_reader.Shape(1)
                logger.info("STEP loaded successfully.")
                return True
        logger.error(f"Failed to load STEP file: {filename}")
        return False

    def create_default_cone(self) -> None:
        self.raw_shape = BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0,0,0), gp_Dir(0,0,1)), 60, 10, 100).Shape()

    def get_shape_bounds(self, shape) -> Optional[tuple]:
        if shape is None or shape.IsNull(): return None
        bbox = Bnd_Box()
        brepbndlib.Add(shape, bbox, True)
        if bbox.IsVoid(): return None
        return bbox.Get() 

    def update_geometry(self, rot_x: float, rot_y: float, rot_z: float, offset_x: float, offset_z: float) -> None:
        if not self.raw_shape: return
        
        # 1. Merkezle
        bbox = self.get_shape_bounds(self.raw_shape)
        if not bbox: return
        x_min, y_min, z_min, x_max, y_max, z_max = bbox
        center_x, center_y, center_z = (x_min + x_max)/2, (y_min + y_max)/2, (z_min + z_max)/2
        
        trsf_center = gp_Trsf()
        trsf_center.SetTranslation(gp_Vec(-center_x, -center_y, -center_z))
        temp_shape = BRepBuilderAPI_Transform(self.raw_shape, trsf_center, True).Shape()
        
        # 2. Rotasyonlar
        if abs(rot_x) > 0.001:
            trsf = gp_Trsf(); trsf.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(1,0,0)), math.radians(rot_x))
            temp_shape = BRepBuilderAPI_Transform(temp_shape, trsf, True).Shape()
        if abs(rot_y) > 0.001:
            trsf = gp_Trsf(); trsf.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(0,1,0)), math.radians(rot_y))
            temp_shape = BRepBuilderAPI_Transform(temp_shape, trsf, True).Shape()
        if abs(rot_z) > 0.001:
            trsf = gp_Trsf(); trsf.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(0,0,1)), math.radians(rot_z))
            temp_shape = BRepBuilderAPI_Transform(temp_shape, trsf, True).Shape()
            
        # 3. Hedefe Taşı
        bbox_new = self.get_shape_bounds(temp_shape)
        if bbox_new:
            _, _, nz_min, _, _, _ = bbox_new
            trsf_final = gp_Trsf()
            move_vec = gp_Vec(offset_x, 0, offset_z - nz_min)
            trsf_final.SetTranslation(move_vec)
            self.oriented_shape = BRepBuilderAPI_Transform(temp_shape, trsf_final, True).Shape()
        else:
            self.oriented_shape = temp_shape

        # 4. Mesh ve Ray Tracing
        self.mesh_cache = self._occ_to_pyvista(self.oriented_shape)
        if self.mesh_cache:
            self.pv_mesh = self.mesh_cache.triangulate()
        
        # 5. Profil Analizi
        f_bbox = self.mesh_cache.bounds 
        if f_bbox:
            fz_min, fz_max = f_bbox[4], f_bbox[5]
            self.props["h"] = fz_max - fz_min
            self.props["top_z"] = fz_max
            self.props["min_z"] = fz_min
            
            self._cache_mandrel_profile(fz_min, fz_max, offset_x)
            self.props["br"] = self.get_radius_fast(fz_min + 0.1)
            self.props["tr"] = self.get_radius_fast(fz_max - 0.1)

    def _cache_mandrel_profile(self, z_min, z_max, center_x):
        resolution = self.scan_resolution
        steps = int((z_max - z_min) / resolution) + 2
        z_values = np.linspace(z_min, z_max, steps)
        
        r_values = []
        if self.pv_mesh:
            for z in z_values:
                p1 = [center_x, 0, z]
                p2 = [center_x + 10000.0, 0, z] 
                points, ind = self.pv_mesh.ray_trace(p1, p2)
                if len(points) > 0:
                    dists = np.linalg.norm(points - np.array(p1), axis=1)
                    r_values.append(np.max(dists))
                else:
                    r_values.append(0.0)
        else:
             r_values = [60.0] * len(z_values) 

        self.profile_z = z_values
        self.profile_r = np.array(r_values)

    def generate_shell_mesh(self, thickness: float, center_x: float) -> Optional[pv.StructuredGrid]:
        if self.profile_z is None or len(self.profile_z) < 2: return None
        radial_resolution = 120; theta = np.linspace(0, 2*np.pi, radial_resolution)
        z_grid, theta_grid = np.meshgrid(self.profile_z, theta)
        r_base = self.profile_r
        r_grid = np.tile(r_base, (radial_resolution, 1)) + thickness
        x = r_grid * np.cos(theta_grid) + center_x; y = r_grid * np.sin(theta_grid); z = z_grid
        grid = pv.StructuredGrid(x, y, z)
        return grid

    def get_radius_fast(self, z_level: float) -> float:
        """
        Calculates the mandrel radius at a specific Z level.
        If the Z level is outside the mandrel bounds, it extrapolates using the slope 
        of the nearest valid segment.
        
        Args:
            z_level (float): The Z coordinate to query.

        Returns:
            float: The radius at that Z level.
        """
        if len(self.profile_z) < 2: return 0.0
        
        # 1. KALIP ALTINDAN DEVAM (Başlangıç öncesi)
        if z_level < self.profile_z[0]:
            dz = self.profile_z[1] - self.profile_z[0]
            dr = self.profile_r[1] - self.profile_r[0]
            if dz == 0: return self.profile_r[0]
            # Eğimle geriye git
            return self.profile_r[0] + (dr/dz) * (z_level - self.profile_z[0])
            
        # 2. KALIP ÜSTÜNDEN DEVAM (Bitiş sonrası - Hayali Çizgi)
        elif z_level > self.profile_z[-1]:
            # Son iki tarama noktası arasındaki eğimi bul
            # Gürültüyü azaltmak için biraz daha geriden örnek alıyoruz (-1 ve -5 arası)
            idx_last = -1
            # Fix: Ensure we go back at least to the start if length is small
            target_prev = -5
            if len(self.profile_z) < 5:
                target_prev = -len(self.profile_z)
            
            idx_prev = target_prev
            
            dz = self.profile_z[idx_last] - self.profile_z[idx_prev]
            dr = self.profile_r[idx_last] - self.profile_r[idx_prev]
            
            if dz == 0: return self.profile_r[-1]
            # Eğimle ileriye git
            return self.profile_r[-1] + (dr/dz) * (z_level - self.profile_z[-1])
            
        # 3. KALIP ÜZERİNDE (Normal)
        else:
            return float(np.interp(z_level, self.profile_z, self.profile_r))

    def get_normal_at_z(self, z_level: float) -> tuple[float, float]:
        """
        Calculates the surface normal vector (nx, nz) at a given Z level in the XZ plane.
        
        Args:
            z_level (float): The Z coordinate.

        Returns:
            tuple[float, float]: The normal vector (nx, nz).
        """
        delta = self.scan_resolution
        r1 = max(0.0, self.get_radius_fast(z_level - delta))  # clamp: ekstrapolasyon negatif dönebilir
        r2 = max(0.0, self.get_radius_fast(z_level + delta))  # clamp: mandrel sınırı dışında negatif radius
        dr = r2 - r1; dz = 2 * delta
        nx = dz; nz = -dr
        length = math.sqrt(nx*nx + nz*nz)
        if length < 1e-6: return (1.0, 0.0)
        return (nx / length, nz / length)

    def _calculate_exact_radius_at_z(self, z_level: float, center_xy: tuple[float, float]) -> float:
        return self.get_radius_fast(z_level)

    def _occ_to_pyvista(self, shape):
        if shape is None: return None
        mesh = BRepMesh_IncrementalMesh(shape, self.mesh_deflection)
        mesh.Perform()
        exp = TopExp_Explorer(shape, TopAbs_FACE); verts, faces = [], []; v_offset = 0
        while exp.More():
            face = topods.Face(exp.Current()); loc = TopLoc_Location(); tri = BRep_Tool.Triangulation(face, loc)
            if tri:
                trsf = loc.Transformation()
                for i in range(1, tri.NbNodes()+1):
                    p = tri.Node(i).Transformed(trsf); verts.append([p.X(), p.Y(), p.Z()])
                tris = tri.Triangles()
                for i in range(1, tri.NbTriangles()+1):
                    n1, n2, n3 = tris.Value(i).Get(); faces.extend([3, n1-1+v_offset, n2-1+v_offset, n3-1+v_offset])
                v_offset += tri.NbNodes()
            exp.Next()
        if not verts: return None
        return pv.PolyData(np.array(verts), faces=np.array(faces))