import pyvista as pv
import numpy as np
import math

# --- pythonOCC Gerekli Modüller ---
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax1, gp_Ax2, gp_Trsf, gp_Vec
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh # Mesh oluşturmak için
from OCC.Core.TopExp import TopExp_Explorer # Şekil üzerinde gezinmek için
from OCC.Core.TopAbs import TopAbs_FACE # Yüzeyleri seçmek için
from OCC.Core.BRep import BRep_Tool # Triangulation (üçgenleme) gibi araçlar için
from OCC.Core.TopoDS import topods # Şekil tiplerini dönüştürmek için
from OCC.Core.TopLoc import TopLoc_Location # Geometrik konumlar için
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform # Dönüşüm uygulamak için
from OCC.Core.TColgp import TColgp_Array1OfPnt # Nokta dizisi
from OCC.Core.GeomAPI import GeomAPI_PointsToBSpline # Noktalardan B-Spline oluşturma
from OCC.Core.STEPControl import STEPControl_Reader # STEP okumak için
from OCC.Core.IFSelect import IFSelect_RetDone # STEP okuma durumu için
from OCC.Core.Bnd import Bnd_Box # Sınırlayıcı kutu için
from OCC.Core.BRepBndLib import brepbndlib_Add # Sınırlayıcı kutuya şekil eklemek için
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Section # OCC importlarına ekleyin (en başa)
from OCC.Core.gp import gp_Pln # gp_Pnt, gp_Dir yanına eklenebilir (en başa)

# --- Global Sabitler ve Başlangıç Değerleri ---
# Bu değerler, STEP yüklenemezse veya ilk açılışta varsayılan mandrel için kullanılır.
# STEP yüklendiğinde, bu değerler calculate_and_draw_all içinde GÜNCELLENMEZ,
# bunun yerine reorient_shape_and_get_properties'den dönen ANLIK değerler kullanılır.
INITIAL_MANDREL_BASE_RADIUS = 60.0
INITIAL_MANDREL_TOP_RADIUS = 10.0
INITIAL_MANDREL_HEIGHT = 100.0

blank_radius = 120.0 # Bu, mandrelin maksimum yarıçapından büyük olmalı
blank_thickness = 2.0
MACHINE_MAX_EXPECTED_RADIUS = 150.0 
MACHINE_MAX_EXPECTED_HEIGHT = 150.0 

# --- Global Parametreler (GUI ile Değiştirilecek) ---
params = {
    "num_sweeping_passes": 3,
    "p1_p3_x_offset_from_p2": 40.0, 
    "p1_z_offset_from_p2": 50.0,    
    "p3_z_offset_from_p2": -20.0,   
    "y_rotation_degrees": 10.0,     
    "roughing_step_radial": 1.0,
    "safety_clearance_roller_to_part": 0.5,
    "first_pass_p2_contact_z_abs": INITIAL_MANDREL_HEIGHT * 0.98, # Başlangıçta INITIAL_MANDREL_HEIGHT kullan
    "roller_nose_radius_param": 10.0,
    "final_part_thickness_on_mandrel": blank_thickness,
    "camera_focal_x_offset": 0.0, 
    "camera_focal_z_offset": 0.0, 
    "camera_y_distance": 600.0,
    "show_advanced_sliders": False,
    "flip_z_axis": False 
}

# --- Slider Yerleşim Parametreleri ---
slider_config = { # Slider yerleşimini biraz daha sıkıştıralım
    "start_x": 0.03, "end_x": 0.25, "start_y": 0.945, "vertical_gap": 0.14
}

# --- Global Değişkenler (Fonksiyonlar ve Ana Blok Tarafından Kullanılacak) ---
slider_widgets = {} 
plotter = None 
initial_camera_params = {} 
raw_mandrel_shape = None # STEP'ten okunan ham şekil
mandrel_actor = None     # PyVista mandrel actor'ü
blank_actor = None       # PyVista blank actor'ü
# roller_visual_actor, if __name__ == '__main__' içinde lokal olacak ve bir kere eklenecek.

toolpath_actors = [] 
control_point_actors = [] 
control_point_label_actors = [] 
text_actors = {} # add_text ile eklenen actor'leri (veya isimlerini) tutar
approach_transition_actors = [] # YAKLAŞMA VE GEÇİŞ HAREKETLERİ İÇİN

# --- Yardımcı Fonksiyonlar ---
def get_shape_bounds_and_center(shape):
    if shape is None or shape.IsNull(): return None, None
    bbox = Bnd_Box()
    brepbndlib_Add(shape, bbox, True) 
    if bbox.IsVoid(): return None, None
    x_min, y_min, z_min, x_max, y_max, z_max = bbox.Get()
    center_pnt = gp_Pnt((x_min + x_max) / 2.0, (y_min + y_max) / 2.0, (z_min + z_max) / 2.0)
    return bbox, center_pnt
def get_radius_at_z(shape_to_section, z_level, center_xy=gp_Pnt(0,0,0)):
    """
    Bir şeklin belirtilen Z seviyesindeki kesitinin yaklaşık maksimum radyal genişliğini döndürür.
    Şeklin bu Z seviyesinde XY merkezinin center_xy olduğu varsayılır.
    """
    if shape_to_section is None or shape_to_section.IsNull(): return 0.0

    section_plane = gp_Pln(gp_Pnt(center_xy.X(), center_xy.Y(), z_level), gp_Dir(0,0,1))
    
    try:
        section_maker = BRepAlgoAPI_Section(shape_to_section, section_plane, True)
        # section_maker.SetRunParallel(True) # Büyük modeller için performansı artırabilir
        section_maker.Build()
        section_shape = section_maker.Shape()

        if section_shape is None or section_shape.IsNull() or not section_maker.IsDone():
            return 0.0

        section_bbox = Bnd_Box()
        brepbndlib_Add(section_shape, section_bbox, True) 
        if section_bbox.IsVoid(): return 0.0

        x_min_s, y_min_s, _, x_max_s, y_max_s, _ = section_bbox.Get()
        # XY merkezine göre en uzak mesafeyi alalım (yaklaşık yarıçap)
        radius = max(abs(x_min_s - center_xy.X()), abs(x_max_s - center_xy.X()), 
                     abs(y_min_s - center_xy.Y()), abs(y_max_s - center_xy.Y()))
        return radius
    except Exception as e:
        print(f"  HATA: get_radius_at_z (Z={z_level:.2f}) içinde: {e}")
        return 0.0
def reorient_shape_and_get_properties(shape, flip_z=False):
    if shape is None or shape.IsNull():
        print("UYARI: Yeniden yönlendirmek için geçerli bir şekil yok.")
        return None, 0, 0, 0, 0 

    bbox_initial, center_initial = get_shape_bounds_and_center(shape)
    if bbox_initial is None:
        print("HATA: Şeklin ilk sınırlayıcı kutusu alınamadı.")
        return shape, 0, 0,0,0 
        
    _, _, z_min_i, _, _, _ = bbox_initial.Get()

    trsf_to_origin_base = gp_Trsf()
    trsf_to_origin_base.SetTranslation(gp_Vec(-center_initial.X(), -center_initial.Y(), -z_min_i))
    oriented_shape = BRepBuilderAPI_Transform(shape, trsf_to_origin_base, True).Shape()

    if flip_z:
        print("INFO: Mandrel Z ekseninde çevriliyor...")
        bbox_after_to_origin, _ = get_shape_bounds_and_center(oriented_shape)
        if bbox_after_to_origin is None: return oriented_shape, 0, 0,0,0
        _, _, temp_z_min, _, _, temp_z_max = bbox_after_to_origin.Get()
        current_height_for_flip = temp_z_max - temp_z_min
        rotation_point = gp_Pnt(0, 0, current_height_for_flip / 2.0) 
        rotation_axis = gp_Ax1(rotation_point, gp_Dir(1, 0, 0)) 
        trsf_flip = gp_Trsf(); trsf_flip.SetRotation(rotation_axis, math.pi) 
        oriented_shape = BRepBuilderAPI_Transform(oriented_shape, trsf_flip, True).Shape()
        bbox_after_flip, _ = get_shape_bounds_and_center(oriented_shape)
        if bbox_after_flip is None: return oriented_shape, 0, 0,0,0
        _, _, zf_min, _, _, _ = bbox_after_flip.Get()
        trsf_realign_z_base = gp_Trsf(); trsf_realign_z_base.SetTranslation(gp_Vec(0, 0, -zf_min)) 
        oriented_shape = BRepBuilderAPI_Transform(oriented_shape, trsf_realign_z_base, True).Shape()

    final_bbox, _ = get_shape_bounds_and_center(oriented_shape) # final_center'ı şimdilik kullanmıyoruz
    if final_bbox is None: return oriented_shape, 0, 0,0,0

    _, _, fz_min_final, _, _, fz_max_final = final_bbox.Get()
    
    est_h = fz_max_final - fz_min_final 
    blank_z = fz_max_final 

    shape_xy_center_for_sectioning = gp_Pnt(0,0,0) # Yönlendirilmiş şekil XY'de merkezli varsayılıyor
    
    base_z_for_radius_calc = fz_min_final + 0.01 # Tam sınırdan değil
    est_br = get_radius_at_z(oriented_shape, base_z_for_radius_calc, shape_xy_center_for_sectioning)
    
    top_z_for_radius_calc = fz_max_final - 0.01 
    est_tr = get_radius_at_z(oriented_shape, top_z_for_radius_calc, shape_xy_center_for_sectioning)

    if est_h < 0.1: est_tr = est_br # Neredeyse düz diskse
    if est_br < 1e-2: 
        print(f"UYARI: Tahmini taban yarıçapı kesitle çok küçük: {est_br:.3f}. BBox X/Y max kullanılacak.")
        fx_min, fy_min, _, fx_max, fy_max, _ = final_bbox.Get() # Sadece X,Y min/max alınır
        est_br = max(abs(fx_min), abs(fx_max), abs(fy_min), abs(fy_max)) 
            
    if est_tr < 1e-2:
        print(f"UYARI: Tahmini tepe yarıçapı kesitle çok küçük: {est_tr:.3f}. BBox X/Y max * 0.1 kullanılacak.")
        fx_min, fy_min, _, fx_max, fy_max, _ = final_bbox.Get()
        est_tr = max(abs(fx_min), abs(fx_max), abs(fy_min), abs(fy_max)) * 0.1 
        if est_tr < 1e-2: est_tr = 0.0 # Sivri uç

    print(f"Yönlendirilmiş Mandrel (Kesitli): Yükseklik={est_h:.2f}, Taban R={est_br:.2f}, Tepe R={est_tr:.2f}")
    print(f"  Levha Yerleşim Z: {blank_z:.2f}")

    return oriented_shape, blank_z, est_h, est_br, est_tr

def load_step_file(filename):
    step_reader = STEPControl_Reader(); status = step_reader.ReadFile(filename)
    if status == IFSelect_RetDone:
        step_reader.TransferRoots()
        if step_reader.NbShapes() > 0: return step_reader.Shape(1)
        else: print(f"HATA: STEP dosyasında ({filename}) şekil yok."); return None
    else: print(f"HATA: STEP dosyası ({filename}) okunamadı. Kod: {status}"); return None

def occ_to_pyvista(occ_shape, lin_def=0.1, ang_def=0.5):
    # ... (Bu fonksiyon öncekiyle aynı, eksiksiz olduğundan emin olun) ...
    if occ_shape.IsNull(): return None
    mesh_tool = BRepMesh_IncrementalMesh(occ_shape, lin_def, False, ang_def); mesh_tool.Perform()
    if not mesh_tool.IsDone(): return None
    all_vertices = []; all_faces_list = []; vertex_offset = 0
    face_explorer = TopExp_Explorer(occ_shape, TopAbs_FACE)
    while face_explorer.More():
        face = topods.Face(face_explorer.Current()); location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation(face, location)
        if triangulation is None: face_explorer.Next(); continue
        nb_nodes = triangulation.NbNodes(); tris = triangulation.Triangles()
        current_vertices_for_this_face = []
        for i in range(1, nb_nodes + 1):
            p_node = triangulation.Node(i); p_node.Transform(location.Transformation())
            current_vertices_for_this_face.append([p_node.X(), p_node.Y(), p_node.Z()])
        all_vertices.extend(current_vertices_for_this_face)
        for i in range(tris.Lower(), tris.Upper() + 1):
            triangle_node_indices = tris.Value(i); n1, n2, n3 = triangle_node_indices.Get()
            all_faces_list.extend([3, n1 - 1 + vertex_offset, n2 - 1 + vertex_offset, n3 - 1 + vertex_offset])
        vertex_offset += nb_nodes
        face_explorer.Next()
    if not all_vertices or not all_faces_list: return None
    return pv.PolyData(np.array(all_vertices), faces=np.array(all_faces_list))

# --- Ana Hesaplama ve Çizim Fonksiyonu ---
def calculate_and_draw_all(plotter_obj_ref):
    global params, raw_mandrel_shape 
    global mandrel_actor, blank_actor 
    global toolpath_actors, control_point_actors, control_point_label_actors, text_actors
    global approach_transition_actors # Global listeyi kullanacağımızı belirtiyoruz

# Önceki dinamik çizimleri temizle
    print("--- Temizleme Başladı ---")

    # --- TOOLPATH_ACTORS İÇİN ÖZEL TEMİZLEME ---
    print(f"[DEBUG] Temizleme öncesi toolpath_actors eleman sayısı: {len(toolpath_actors)}")
    #for i, act in enumerate(toolpath_actors): # Hangi aktörler olduğunu görmek için
    #    print(f"[DEBUG] toolpath_actors[{i}]: {act}")

    actors_to_remove_from_toolpath = list(toolpath_actors) # Kaldırılacakların bir kopyasını al
    for actor in actors_to_remove_from_toolpath:
        if actor:
            try:
                plotter_obj_ref.remove_actor(actor, render=False)
                # print(f"[DEBUG]  Kaldırıldı (toolpath_actors): {actor}")
            except Exception as e:
                print(f"[HATA] toolpath_actors içindeki aktör kaldırılamadı: {actor} - {e}")
    toolpath_actors.clear()
    print(f"[DEBUG] Temizleme sonrası toolpath_actors eleman sayısı: {len(toolpath_actors)}")
    # --- TOOLPATH_ACTORS TEMİZLEME SONU ---

    # Diğer aktör listeleri için temizleme (control_point_actors, control_point_label_actors)
    for actor_list_name, actor_list in [("control_point_actors", control_point_actors),
                                       ("control_point_label_actors", control_point_label_actors)]:
        # print(f"[DEBUG] Temizleniyor: {actor_list_name}, mevcut eleman sayısı: {len(actor_list)}")
        actors_to_remove_from_list = list(actor_list)
        for actor in actors_to_remove_from_list:
            if actor:
                try:
                    plotter_obj_ref.remove_actor(actor, render=False)
                except Exception as e:
                    print(f"[HATA] {actor_list_name} içindeki aktör kaldırılamadı: {actor} - {e}")
        actor_list.clear()

    # text_actors için temizleme
    # print(f"[DEBUG] Temizleniyor: text_actors, mevcut anahtar sayısı: {len(text_actors)}")
    for actor_name_key in list(text_actors.keys()):
        actor_to_remove = text_actors.pop(actor_name_key)
        if actor_to_remove:
            try:
                plotter_obj_ref.remove_actor(actor_to_remove, render=False)
            except Exception as e:
                print(f"[HATA] text_actors içindeki aktör '{actor_name_key}' kaldırılamadı: {e}")

    # approach_transition_actors için temizleme
    # print(f"[DEBUG] Temizleniyor: approach_transition_actors, mevcut eleman sayısı: {len(approach_transition_actors)}")
    actors_to_remove_from_approach = list(approach_transition_actors)
    for actor in actors_to_remove_from_approach:
        if actor:
            try:
                plotter_obj_ref.remove_actor(actor, render=False)
            except Exception as e:
                print(f"[HATA] approach_transition_actors içindeki aktör kaldırılamadı: {actor} - {e}")
    approach_transition_actors.clear()

    print("--- Temizleme Bitti ---")
    for actor_name_key in list(text_actors.keys()): 
        actor_to_remove = text_actors.pop(actor_name_key) 
        if actor_to_remove and plotter_obj_ref.actors.get(actor_name_key): 
             plotter_obj_ref.remove_actor(actor_to_remove, render=False)
    # text_actors.clear() # Zaten pop ile boşalıyor

    if raw_mandrel_shape is None:
        print("UYARI: Ham mandrel şekli yüklenmemiş.")
        # Uyarı metni ekle
        warn_actor_name = "warning_text_actor"
        plotter_obj_ref.remove_actor(warn_actor_name, render=False) # Önceki varsa kaldır
        actor = plotter_obj_ref.add_text("STEP dosyası yüklenemedi veya bulunamadı!", 
                                         position="center", font_size=12, color='red', name=warn_actor_name)
        text_actors[warn_actor_name] = actor
        plotter_obj_ref.render()
        return

    # 1. Mandreli Yeniden Yönlendir ve GÜNCEL Boyutlarını Al
    current_mandrel_occ, blank_z_pos_new, current_m_h, current_m_br, current_m_tr = \
        reorient_shape_and_get_properties(raw_mandrel_shape, params["flip_z_axis"])

    if current_mandrel_occ is None:
        print("HATA: Mandrel yönlendirmesi/boyutlandırması başarısız oldu.")
        plotter_obj_ref.render(); return

    # Mandrel Mesh'ini Güncelle
    if mandrel_actor: plotter_obj_ref.remove_actor(mandrel_actor, render=False)
    pv_mandrel_updated = occ_to_pyvista(current_mandrel_occ)
    if pv_mandrel_updated:
        mandrel_actor = plotter_obj_ref.add_mesh(pv_mandrel_updated, name="mandrel", color='dimgray', opacity=0.6, smooth_shading=True)
    
    # Levha Mesh'ini Güncelle
    if blank_actor: plotter_obj_ref.remove_actor(blank_actor, render=False)
    blank_origin_new = gp_Pnt(0, 0, blank_z_pos_new) 
    blank_placement_new = gp_Ax2(blank_origin_new, gp_Dir(0,0,1))
    current_blank_occ = BRepPrimAPI_MakeCylinder(blank_placement_new, blank_radius, blank_thickness).Shape() 
    pv_blank_updated = occ_to_pyvista(current_blank_occ)
    if pv_blank_updated:
        blank_actor = plotter_obj_ref.add_mesh(pv_blank_updated, name="blank", color='deepskyblue', opacity=0.6, smooth_shading=True)

    # --- Takım Yolu Hesaplamaları (current_m_h, current_m_br, current_m_tr kullanarak) ---
    num_sweeping_passes = int(params["num_sweeping_passes"])
    p1_p3_x_offset = params["p1_p3_x_offset_from_p2"]
    p1_z_offset = params["p1_z_offset_from_p2"]
    p3_z_offset = params["p3_z_offset_from_p2"]
    y_rotation_degrees_val = params["y_rotation_degrees"]
    roughing_step_radial_val = params["roughing_step_radial"]
    safety_clearance = params["safety_clearance_roller_to_part"]
    first_pass_p2_z_override = params.get("first_pass_p2_contact_z_abs")
    roller_nose_r = params["roller_nose_radius_param"]
    final_part_thick = params["final_part_thickness_on_mandrel"]
    
    original_toolpaths_xz = []
    original_control_points_xz = []
    num_pts_per_pass = 50
    
    z_start_of_current_segment_group = current_m_h 
    dz_small_for_normal = 0.1 # mm

    # print(f"\nTakım Yolu Hesaplama (Yerel Normallerle):")
    # print(f"  Kullanılan Mandrel Boyutları: H={current_m_h:.2f}, TabanR={current_m_br:.2f}, TepeR={current_m_tr:.2f}")

    for p_idx in range(num_sweeping_passes):
        pass_pts_list = []
        allowance = (num_sweeping_passes - 1 - p_idx) * roughing_step_radial_val
        total_offset_distance = roller_nose_r + final_part_thick + safety_clearance + allowance
        
        # P2 için hedef Z'yi belirle
        target_z_for_p2_this_pass_contact = 0.0
        if p_idx == 0:
            if first_pass_p2_z_override is not None:
                target_z_for_p2_this_pass_contact = max(dz_small_for_normal, min(first_pass_p2_z_override, current_m_h - dz_small_for_normal))
            else: 
                segment_h = current_m_h / num_sweeping_passes if num_sweeping_passes > 0 else current_m_h
                target_z_for_p2_this_pass_contact = current_m_h - 0.5 * segment_h
        else: 
            num_remaining_passes = num_sweeping_passes - p_idx
            remaining_height = z_start_of_current_segment_group
            segment_h_for_remaining = remaining_height / num_remaining_passes if num_remaining_passes > 0 else remaining_height
            current_pass_segment_top_z_contact = z_start_of_current_segment_group # Düzeltme: _contact olmadan
            current_pass_segment_bottom_z_contact = z_start_of_current_segment_group - segment_h_for_remaining
            if p_idx == num_sweeping_passes - 1: current_pass_segment_bottom_z_contact = 0.0
            target_z_for_p2_this_pass_contact = (current_pass_segment_top_z_contact + current_pass_segment_bottom_z_contact) / 2.0
        target_z_for_p2_this_pass_contact = max(dz_small_for_normal, min(target_z_for_p2_this_pass_contact, current_m_h - dz_small_for_normal))

        r_p2_contact = get_radius_at_z(current_mandrel_occ, target_z_for_p2_this_pass_contact, gp_Pnt(0,0,0))
        if r_p2_contact < 1e-3 and p_idx == num_sweeping_passes -1: # Son pasoda tepe noktası olabilir
             r_p2_contact = current_m_tr # Tahmini tepe yarıçapını kullan
        if r_p2_contact < 1e-3 and p_idx == 0 and abs(target_z_for_p2_this_pass_contact - current_m_h) < dz_small_for_normal * 2:
             r_p2_contact = current_m_tr # Tahmini tepe yarıçapını kullan


        # Yerel Yüzey Normali Hesaplanması
        r_p2_minus_dz = get_radius_at_z(current_mandrel_occ, target_z_for_p2_this_pass_contact - dz_small_for_normal, gp_Pnt(0,0,0))
        r_p2_plus_dz = get_radius_at_z(current_mandrel_occ, target_z_for_p2_this_pass_contact + dz_small_for_normal, gp_Pnt(0,0,0))
        delta_r_local_norm = r_p2_plus_dz - r_p2_minus_dz
        delta_z_local_norm = 2 * dz_small_for_normal
        local_normal_x = 1.0; local_normal_z = 0.0
        if abs(delta_z_local_norm) > 1e-6 : 
            norm_vec_x_un = delta_z_local_norm 
            norm_vec_z_un = -delta_r_local_norm 
            length = math.sqrt(norm_vec_x_un**2 + norm_vec_z_un**2)
            if length > 1e-6:
                local_normal_x = norm_vec_x_un / length
                local_normal_z = norm_vec_z_un / length
        
        p2_x = r_p2_contact + total_offset_distance * local_normal_x
        p2_z = target_z_for_p2_this_pass_contact + total_offset_distance * local_normal_z
        p2_gp = gp_Pnt(p2_x, 0, p2_z)
        p1_x = p2_gp.X() + p1_p3_x_offset; p1_z_calc = p2_gp.Z() + p1_z_offset
        if p_idx == 0: p1_z_calc = max(p1_z_calc, current_m_h + blank_thickness + safety_clearance + 5)
        p1_gp = gp_Pnt(p1_x, 0, p1_z_calc)
        p3_x = p2_gp.X() + p1_p3_x_offset; p3_z_calc = p2_gp.Z() + p3_z_offset
        p3_gp = gp_Pnt(p3_x, 0, p3_z_calc)
        current_cp_coords = np.array([[p1_gp.X(),0,p1_gp.Z()],[p2_gp.X(),0,p2_gp.Z()],[p3_gp.X(),0,p3_gp.Z()]])
        original_control_points_xz.append(current_cp_coords)
        
        # Zincirleme için bir sonraki segmentin başlangıç Z'si
        # P3'ün TEMAS Z'sini daha dikkatli hesaplayalım
        # P3 rulo merkezi, P3 temas noktasından normal boyunca total_offset_distance kadar uzakta.
        # Dolayısıyla P3 temas = P3_merkez - total_offset_distance * P3_normal
        # P3 için de normali hesaplamak yerine, bu pasonun hedeflediği en alt Z temasını kullanalım.
        # (z_contact_segment_lower gibi bir değer olmalıydı, ama P3'ün Z ofseti bunu değiştirebilir)
        # Şimdilik, P3 rulo merkezinin Z'sinden genel Z ofsetini çıkararak yaklaşıyoruz.
        # z_contact_at_p3_of_this_pass = p3_gp.Z() - (total_offset_distance * local_normal_z) # P2 normalini kullanmak burada hatalı olabilir
        # En basit ve sağlam yaklaşım: Bu pasonun hedeflediği en alt Z temas noktası
        # (Yukarıdaki Z segmentasyonundan gelen current_pass_segment_bottom_z_contact)
        if p_idx < num_sweeping_passes - 1:
            # Bu pasonun alt Z sınırını alalım (bir sonraki pasonun üst Z sınırı olacak)
            z_start_of_current_segment_group = current_m_h - ((p_idx + 1) * (current_m_h / num_sweeping_passes))
        else:
            z_start_of_current_segment_group = 0.0
        z_start_of_current_segment_group = max(0, min(z_start_of_current_segment_group, current_m_h))

        cp_array = TColgp_Array1OfPnt(1,3); cp_array.SetValue(1,p1_gp); cp_array.SetValue(2,p2_gp); cp_array.SetValue(3,p3_gp)
        bs_maker = GeomAPI_PointsToBSpline(cp_array)
        if bs_maker.IsDone(): 
            # ... (bspline nokta üretimi aynı) ...
            curve = bs_maker.Curve(); f_param = curve.FirstParameter(); l_param = curve.LastParameter()
            if abs(l_param - f_param) > 1e-6:
                for i in range(num_pts_per_pass):
                    param = f_param + (l_param - f_param) * (i / (num_pts_per_pass -1))
                    pt = curve.Value(param)
                    pass_pts_list.append([pt.X(), pt.Y(), pt.Z()])
            else: pass_pts_list.extend([ [p1_gp.X(),0,p1_gp.Z()], [p2_gp.X(),0,p2_gp.Z()], [p3_gp.X(),0,p3_gp.Z()] ])
        else: pass_pts_list.extend([ [p1_gp.X(),0,p1_gp.Z()], [p2_gp.X(),0,p2_gp.Z()], [p3_gp.X(),0,p3_gp.Z()] ])
        original_toolpaths_xz.append(np.array(pass_pts_list))
    
    # --- 4. Y-Ekseni Döndürme ---
    y_rot_rad = math.radians(y_rotation_degrees_val)
    final_toolpaths_to_plot = []; final_control_points_to_plot = []
    if abs(y_rotation_degrees_val) < 1e-3:
        final_toolpaths_to_plot = original_toolpaths_xz; final_control_points_to_plot = original_control_points_xz
    else: 
        for idx, orig_path_np in enumerate(original_toolpaths_xz):
            rot_path_pts = []; rot_cp_pts = []
            center_x = np.mean(orig_path_np[:,0]) if orig_path_np.size > 0 else 0
            center_z = np.mean(orig_path_np[:,2]) if orig_path_np.size > 0 else 0
            rot_center = gp_Pnt(center_x, 0, center_z); rot_axis = gp_Ax1(rot_center, gp_Dir(0,1,0))
            trsf = gp_Trsf(); trsf.SetRotation(rot_axis, y_rot_rad)
            if orig_path_np.ndim == 2 and orig_path_np.shape[0] > 0:
                for i in range(orig_path_np.shape[0]):
                    pt_orig = gp_Pnt(orig_path_np[i,0],0,orig_path_np[i,2]); pt_orig.Transform(trsf) 
                    rot_path_pts.append([pt_orig.X(),pt_orig.Y(),pt_orig.Z()])
            final_toolpaths_to_plot.append(np.array(rot_path_pts) if rot_path_pts else np.empty((0,3)))
            if idx < len(original_control_points_xz):
                orig_cp_set = original_control_points_xz[idx]
                if orig_cp_set.ndim == 2 and orig_cp_set.shape[0] > 0:
                    for i_cp in range(orig_cp_set.shape[0]):
                        cp_orig = gp_Pnt(orig_cp_set[i_cp,0],0,orig_cp_set[i_cp,2]); cp_orig.Transform(trsf)
                        rot_cp_pts.append([cp_orig.X(),cp_orig.Y(),cp_orig.Z()])
                final_control_points_to_plot.append(np.array(rot_cp_pts) if rot_cp_pts else np.empty((0,3)))
    
    # --- 5. Çizim Elemanlarını Plotter'a Ekle ---
    colors = ['red', 'green', 'blue', 'purple', 'orange', 'cyan', 'magenta'] 
    
    actor_name_title = "path_title_text_actor" 
    plotter_obj_ref.remove_actor(actor_name_title, render=False) # İsimle kaldırmayı dene
    title_text_content = f"{len(final_toolpaths_to_plot)} Adet Kavisli Paso"; 
    if abs(y_rotation_degrees_val) >= 1e-3 : title_text_content += f" ({y_rotation_degrees_val}° Y-Döndürülmüş)"
    actor_title = plotter_obj_ref.add_text(title_text_content, position="upper_right", font_size=10, color='black', name=actor_name_title)
    text_actors[actor_name_title] = actor_title 
    
    for idx, path_np in enumerate(final_toolpaths_to_plot): 
        if isinstance(path_np, np.ndarray) and path_np.ndim == 2 and path_np.shape[0] > 1:
            actor = plotter_obj_ref.add_lines(path_np, color=colors[idx % len(colors)], width=3+max(0,(num_sweeping_passes-1-idx))//2) 
            toolpath_actors.append(actor)

    actor_name_cp_title = "cp_title_text_actor"
    plotter_obj_ref.remove_actor(actor_name_cp_title, render=False)
    actor_cp_title = plotter_obj_ref.add_text("Kontrol Noktaları (P1,P2,P3)", position="ll", font_size=9, color='black', name=actor_name_cp_title)
    text_actors[actor_name_cp_title] = actor_cp_title
    
    for idx, cp_set in enumerate(final_control_points_to_plot):
        if isinstance(cp_set, np.ndarray) and cp_set.ndim == 2 and cp_set.shape[0] == 3:
            colors_cp = ['magenta', 'gold', 'lime']; labels_cp_base = [f"P1", f"P2", f"P3"]
            for i_pt in range(3): 
                # actor_pt_name = f"cp_actor_p{idx}_pt{i_pt}" # İsimle yönetmek daha iyi olabilir
                actor_pt = plotter_obj_ref.add_points(cp_set[i_pt:i_pt+1], color=colors_cp[i_pt], point_size=10, render_points_as_spheres=True)
                control_point_actors.append(actor_pt)
                label_text = f"{labels_cp_base[i_pt]}_{idx+1}\n({cp_set[i_pt,0]:.0f},{cp_set[i_pt,1]:.0f},{cp_set[i_pt,2]:.0f})"
                # actor_lbl_name = f"cp_label_p{idx}_pt{i_pt}"
                actor_lbl = plotter_obj_ref.add_point_labels(cp_set[i_pt:i_pt+1],[label_text],font_size=8,text_color=colors_cp[i_pt],shape_opacity=0,show_points=False,always_visible=True) # name=actor_lbl_name)
                control_point_label_actors.append(actor_lbl) 
    

    # --- YENİ BÖLÜM: Yaklaşma ve Geçiş Hareketlerini Çiz ---
    if final_control_points_to_plot and isinstance(final_control_points_to_plot, list) and len(final_control_points_to_plot) > 0:
        # Rulonun başlangıç X ve Z koordinatları (main'deki roller_visual_static tanımından)
        # Bu değerler kodunuzun en altındaki if __name__ == '__main__': bloğunda tanımlanıyor.
        # Oradaki roller_body_radius_vis_local, MACHINE_MAX_EXPECTED_RADIUS vb. sabitler burada da geçerli.
        roller_body_radius_vis_local = 25.0 # main'den alınan sabit değer
        initial_roller_x = MACHINE_MAX_EXPECTED_RADIUS + roller_body_radius_vis_local + 30
        initial_roller_z = MACHINE_MAX_EXPECTED_HEIGHT + blank_thickness + roller_body_radius_vis_local + 30

        # İlk P1 noktasını al (X, Y, Z)
        # final_control_points_to_plot içindeki noktalar zaten Y dönüşümü uygulanmış numpy array'leri olmalı.
        # Eğer değilse, np.array() ile sarmalamak gerekebilir. Önceki kodda np.array olarak eklendiği varsayılıyor.
        first_P1 = final_control_points_to_plot[0][0] # Bu zaten bir numpy array olmalı
        
        # Rulonun başlangıç 3D konumu (Y'si ilk P1 ile aynı)
        current_roller_pos = np.array([initial_roller_x, first_P1[1], initial_roller_z])

        # 1. İlk Pasoya Yaklaşma (Köşeli Hareket)
        #   Adım 1 (X Hareketi): (X_roller_start, Y_P1, Z_roller_start) -> (X_P1, Y_P1, Z_roller_start)
        point_after_x_move = np.array([first_P1[0], current_roller_pos[1], current_roller_pos[2]])
        
        if not np.array_equal(current_roller_pos, point_after_x_move): # Sadece gerçekten hareket varsa çiz
            actor_ax = plotter_obj_ref.add_lines(np.array([current_roller_pos, point_after_x_move]), color='black', width=2)
            approach_transition_actors.append(actor_ax)
        
        #   Adım 2 (Z Hareketi): (X_P1, Y_P1, Z_roller_start) -> (X_P1, Y_P1, Z_P1)
        #   hedef nokta first_P1
        if not np.array_equal(point_after_x_move, first_P1): # Sadece gerçekten hareket varsa çiz
            actor_az = plotter_obj_ref.add_lines(np.array([point_after_x_move, first_P1]), color='black', width=2)
            approach_transition_actors.append(actor_az)

        # 2. Pasolar Arası Geçişler
        num_total_passes = len(final_control_points_to_plot)
        for i in range(num_total_passes - 1):
            # Bir önceki pasonun P3 noktası (bu zaten bir numpy array olmalı)
            prev_pass_P3 = final_control_points_to_plot[i][2]
            
            # Sonraki pasonun P1 noktası (bu zaten bir numpy array olmalı)
            next_pass_P1 = final_control_points_to_plot[i+1][0]
            
            # Direkt geçiş hareketini çiz
            if not np.array_equal(prev_pass_P3, next_pass_P1):
                actor_tr = plotter_obj_ref.add_lines(np.array([prev_pass_P3, next_pass_P1]), color='black', width=2)
                approach_transition_actors.append(actor_tr)
    # --- YENİ BÖLÜM SONU ---

    # --- 6. Kamera Ayarını Güncelle ---
    base_focal_point_x = 0 
    base_focal_point_z = current_m_h / 2.0 # GÜNCELLENDİ: current_m_h kullan
    current_focal_x = base_focal_point_x + params["camera_focal_x_offset"]
    current_focal_z = base_focal_point_z + params["camera_focal_z_offset"]
    cam_distance = params["camera_y_distance"]
    plotter_obj_ref.camera_position = [(current_focal_x, cam_distance, current_focal_z), (current_focal_x, 0, current_focal_z), (1, 0, 0)] 
    plotter_obj_ref.reset_camera_clipping_range() 
    plotter_obj_ref.render()

# --- Callback Fonksiyonları (Slider'lar ve Checkbox'lar için) ---
# (Bu fonksiyonlar bir önceki mesajdaki gibi kalacak, sadece plotter global olmalı)
def cb_num_passes(value): params["num_sweeping_passes"] = int(round(value)); calculate_and_draw_all(plotter)
def cb_p1p3_x_offset(value): params["p1_p3_x_offset_from_p2"] = float(value); calculate_and_draw_all(plotter)
# ... (diğer cb_ fonksiyonları aynı) ...
def cb_p1_z_offset(value): params["p1_z_offset_from_p2"] = float(value); calculate_and_draw_all(plotter)
def cb_p3_z_offset(value): params["p3_z_offset_from_p2"] = float(value); calculate_and_draw_all(plotter)
def cb_y_rotation(value): params["y_rotation_degrees"] = float(value); calculate_and_draw_all(plotter)
def cb_rough_step(value): params["roughing_step_radial"] = float(value); calculate_and_draw_all(plotter)
def cb_first_pass_p2z_abs(value):
    val = float(value); params["first_pass_p2_contact_z_abs"] = val 
    calculate_and_draw_all(plotter)
def cb_cam_focal_x_offset(value): params["camera_focal_x_offset"] = float(value); calculate_and_draw_all(plotter)
def cb_cam_focal_z_offset(value): params["camera_focal_z_offset"] = float(value); calculate_and_draw_all(plotter)
def cb_cam_y_distance(value): params["camera_y_distance"] = float(value); calculate_and_draw_all(plotter)
def cb_flip_z(state):
    global params, plotter 
    params["flip_z_axis"] = bool(state)
    if plotter: calculate_and_draw_all(plotter)
def toggle_advanced_sliders(is_checked):
    global params, slider_widgets, plotter
    params["show_advanced_sliders"] = is_checked
    advanced_slider_keys = ["p1p3_x_offset", "p1_z_offset", "p3_z_offset", "rough_step"]
    for key in advanced_slider_keys:
        if key in slider_widgets and slider_widgets[key] is not None:
            slider_widgets[key].SetEnabled(is_checked)
    if plotter: plotter.render()
def reset_camera_to_home_view(state): 
    global params, slider_widgets, plotter, initial_camera_params 
    if not initial_camera_params: return
    params["camera_focal_x_offset"] = initial_camera_params.get("focal_x_offset", 0.0)
    params["camera_focal_z_offset"] = initial_camera_params.get("focal_z_offset", 0.0)
    params["camera_y_distance"] = initial_camera_params.get("y_distance", 400.0) 
    if "cam_focal_x" in slider_widgets and slider_widgets["cam_focal_x"]:
        slider_widgets["cam_focal_x"].GetRepresentation().SetValue(params["camera_focal_x_offset"])
    if "cam_focal_z" in slider_widgets and slider_widgets["cam_focal_z"]:
        slider_widgets["cam_focal_z"].GetRepresentation().SetValue(params["camera_focal_z_offset"])
    if "cam_y_dist" in slider_widgets and slider_widgets["cam_y_dist"]:
        slider_widgets["cam_y_dist"].GetRepresentation().SetValue(params["camera_y_distance"])
    if plotter: calculate_and_draw_all(plotter)

# --- Ana Script Başlangıcı (`if __name__ == '__main__':`) ---
if __name__ == '__main__':
    initial_camera_params["focal_x_offset"] = params["camera_focal_x_offset"]
    initial_camera_params["focal_z_offset"] = params["camera_focal_z_offset"]
    initial_camera_params["y_distance"] = params["camera_y_distance"]    

    default_step_path = "C:/Users/PC/Documents/CAD_Files/deneme_mandrel.step" # Varsayılan bir yol
    step_file_path = input(f"Lütfen STEP dosyasının tam yolunu girin (Enter'a basarsanız varsayılan: {default_step_path}): ") or default_step_path
    
    raw_mandrel_shape = load_step_file(step_file_path) 
    if raw_mandrel_shape is None:
        print("STEP YÜKLENEMEDİ. Varsayılan konik mandrel (global sabitlerden) kullanılacak.")
        mandrel_origin_def = gp_Pnt(0,0,0); mandrel_axis_dir_def = gp_Dir(0,0,1)
        mandrel_placement_def = gp_Ax2(mandrel_origin_def, mandrel_axis_dir_def)
        raw_mandrel_shape = BRepPrimAPI_MakeCone(mandrel_placement_def, 
                                                 INITIAL_MANDREL_BASE_RADIUS, 
                                                 INITIAL_MANDREL_TOP_RADIUS, 
                                                 INITIAL_MANDREL_HEIGHT).Shape() # Global sabitleri kullan
        if raw_mandrel_shape.IsNull():
            print("HATA: Varsayılan mandrel de oluşturulamadı. Program sonlandırılıyor.")
            exit()
        else: print("Varsayılan konik mandrel oluşturuldu.")

    plotter = pv.Plotter(window_size=[1200, 900])
    
    # Roller_vis (SABİT GÖRSEL)
    roller_body_radius_vis_local = 25.0; roller_length_vis_local = 40.0    
    roller_visual_tilt_degrees_around_x_local = 0.0 # Sabit veya params'tan okunabilir
    fixed_roller_start_x = MACHINE_MAX_EXPECTED_RADIUS + roller_body_radius_vis_local + 30 
    fixed_roller_start_z = MACHINE_MAX_EXPECTED_HEIGHT + blank_thickness + roller_body_radius_vis_local + 30
    roller_center_pnt_vis = gp_Pnt(fixed_roller_start_x, 0, fixed_roller_start_z)
    roller_main_axis_vis_dir = gp_Dir(0,1,0) 
    if abs(roller_visual_tilt_degrees_around_x_local) > 1e-3:
        tilt_rad = math.radians(roller_visual_tilt_degrees_around_x_local)
        roller_main_axis_vis_dir = gp_Dir(0, math.cos(tilt_rad), math.sin(tilt_rad))
    ref_direction_for_ax2_roller = gp_Dir(1,0,0)
    if roller_main_axis_vis_dir.IsParallel(ref_direction_for_ax2_roller, 1e-5): 
        ref_direction_for_ax2_roller = gp_Dir(0,0,1) if not roller_main_axis_vis_dir.IsParallel(gp_Dir(0,0,1), 1e-5) else gp_Dir(0,1,0)
    try: roller_placement_vis = gp_Ax2(roller_center_pnt_vis, roller_main_axis_vis_dir, ref_direction_for_ax2_roller)
    except RuntimeError:
        try: alt_ref_dir = gp_Dir(0,0,1) if not roller_main_axis_vis_dir.IsParallel(gp_Dir(0,0,1),1e-5) else gp_Dir(1,0,0)
        except RuntimeError: roller_placement_vis = gp_Ax2(roller_center_pnt_vis, roller_main_axis_vis_dir)             
    roller_shape_vis_occ = BRepPrimAPI_MakeCylinder(roller_placement_vis, roller_body_radius_vis_local, roller_length_vis_local).Shape()
    pv_roller_vis = occ_to_pyvista(roller_shape_vis_occ)
    if pv_roller_vis: plotter.add_mesh(pv_roller_vis, name="roller_visual_static", color='darkgoldenrod', smooth_shading=True)
    
    # --- Widget'ları Ekle ---
    s_x = slider_config["start_x"]; e_x = slider_config["end_x"]; 
    s_y = slider_config["start_y"]; s_gap = slider_config["vertical_gap"]
    
    # Temel Slider'lar
    plotter.add_slider_widget(cb_num_passes, rng=[1, 10], value=params["num_sweeping_passes"], title="Paso Sayısı", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.0f")
    s_y -= s_gap
    plotter.add_slider_widget(cb_y_rotation, rng=[-90, 90], value=params["y_rotation_degrees"], title="Y Rotasyon (Derece)", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.0f")
    s_y -= s_gap
    
    # "İlk P2 Z Temas" slider'ı (Gelişmiş Ayarlar'dan bağımsız)
    # Bu slider'ın aralığı, o anki mandrel_height'a göre dinamik olmalı. 
    # Şimdilik MACHINE_MAX_EXPECTED_HEIGHT kullanalım, calculate_and_draw_all içinde değer kısıtlanır.
    initial_p2z_abs_val = params.get("first_pass_p2_contact_z_abs", INITIAL_MANDREL_HEIGHT * 0.98)
    slider_widgets["first_pass_p2z"] = plotter.add_slider_widget(cb_first_pass_p2z_abs, 
                                                                rng=[0.01, MACHINE_MAX_EXPECTED_HEIGHT], 
                                                                value=initial_p2z_abs_val, 
                                                                title="İlk P2 Z Temas (Mutlak)", 
                                                                pointa=(s_x, s_y), pointb=(e_x, s_y), 
                                                                style='modern', fmt="%.1f")
    s_y -= s_gap

    # Koşullu Görünecek (Gelişmiş) Slider'lar
    slider_widgets["p1p3_x_offset"] = plotter.add_slider_widget(cb_p1p3_x_offset, rng=[-100, 100], value=params["p1_p3_x_offset_from_p2"], title="P1/P3 X Ofset (P2'den)", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.1f")
    s_y -= s_gap 
    slider_widgets["p1_z_offset"] = plotter.add_slider_widget(cb_p1_z_offset, rng=[-100, 100], value=params["p1_z_offset_from_p2"], title="P1 Z Ofset (P2'den)", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.1f")
    s_y -= s_gap
    slider_widgets["p3_z_offset"] = plotter.add_slider_widget(cb_p3_z_offset, rng=[-100, 100], value=params["p3_z_offset_from_p2"], title="P3 Z Ofset (P2'den)", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.1f")
    s_y -= s_gap
    slider_widgets["rough_step"] = plotter.add_slider_widget(cb_rough_step, rng=[0, 10], value=params["roughing_step_radial"], title="Kaba Paso Radyal Adımı", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.1f")
    s_y -= s_gap 
    
    # Kamera Kontrol Slider'ları (Bunlar her zaman görünür olacak)
    slider_widgets["cam_focal_x"] = plotter.add_slider_widget(cb_cam_focal_x_offset, rng=[-MACHINE_MAX_EXPECTED_HEIGHT, MACHINE_MAX_EXPECTED_HEIGHT], value=params["camera_focal_x_offset"], title="Kamera Odak X Kaydır", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.0f")
    s_y -= s_gap
    slider_widgets["cam_focal_z"] = plotter.add_slider_widget(cb_cam_focal_z_offset, rng=[-MACHINE_MAX_EXPECTED_RADIUS, MACHINE_MAX_EXPECTED_RADIUS], value=params["camera_focal_z_offset"], title="Kamera Odak Z Kaydır", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.0f")
    s_y -= s_gap
    slider_widgets["cam_y_dist"] = plotter.add_slider_widget(cb_cam_y_distance, rng=[50, 1500], value=params["camera_y_distance"], title="Kamera Y Mesafesi", pointa=(s_x, s_y), pointb=(e_x, s_y), style='modern', fmt="%.0f")
    
    box_gap = 20
    box_gap_large = 100
    # --- Checkbox ve Butonları Sağ Alta Ekle ---
    cb_adv_x_pos = 1050; cb_adv_y_pos = 100 # Biraz yukarı ve sola aldım
    plotter.add_checkbox_button_widget(toggle_advanced_sliders, value=params["show_advanced_sliders"], position=(cb_adv_x_pos, cb_adv_y_pos), size=20, border_size=1, color_on='dodgerblue', color_off='lightgray')
    plotter.add_text("Gelişmiş Ayarlar",position=(cb_adv_x_pos - box_gap, cb_adv_y_pos + box_gap) , font_size=8, color="black")

    button_reset_x_pos = cb_adv_x_pos
    button_reset_y_pos = cb_adv_y_pos + box_gap_large 
    plotter.add_checkbox_button_widget(reset_camera_to_home_view, value=False, position=(button_reset_x_pos, button_reset_y_pos), size=(20), border_size=1, color_on='lightcoral', color_off='salmon')
    plotter.add_text("Reset View", position=(button_reset_x_pos - box_gap, button_reset_y_pos + box_gap), font_size=8, color="black")

    flip_cb_x_pos = cb_adv_x_pos 
    flip_cb_y_pos = button_reset_y_pos + box_gap_large
    plotter.add_checkbox_button_widget(cb_flip_z, value=params["flip_z_axis"], position=(flip_cb_x_pos, flip_cb_y_pos), size=20, border_size=1, color_on='forestgreen', color_off='lightgray')
    plotter.add_text("Mandreli Z'de Çevir", position=(flip_cb_x_pos - box_gap, flip_cb_y_pos + box_gap), font_size=8, color="black")
    
    toggle_advanced_sliders(params["show_advanced_sliders"])
    calculate_and_draw_all(plotter) 
    
    plotter.background_color = 'white'
    plotter.add_axes(interactive=True); plotter.show_grid()
    plotter.enable_parallel_projection() 
    plotter.add_title("İnteraktif Metal Sıvama Prototipi v1.003", font_size=12)
    
    print("PyVista penceresi gösteriliyor...")
    plotter.show() 
    
    print("PyVista penceresi kapatıldı.") 
    input("Konsolu kapatmak için Enter'a basın...")