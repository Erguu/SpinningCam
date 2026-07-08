import tkinter as tk
from tkinter import ttk
from ui.tabs.scrollable_tab_base import ScrollableTabBase
from i18n import t


class ProcessTab(ScrollableTabBase):
    def __init__(self, parent_frame, app, ui_root, ui_helper):
        self.app = app
        self.root = ui_root
        self.helper = ui_helper

        super().__init__(parent_frame)
        self._create_widgets()

    def rebuild(self):
        for widget in self.content.winfo_children():
            widget.destroy()
        self._create_widgets()

    def _create_widgets(self):
        # --- Visual Settings ---
        self.helper.add_section_header(self.content, t("section_visual"), color="darkgreen")

        self.helper.add_checkbox(self.content, self.app, "calc_active", t("cb_show_passes"),
                                 "Hesaplanan takım yollarını 3D görünümde göster/gizle.")
        self.helper.add_checkbox(self.content, self.app, "velocity_color_mode", t("cb_velocity_colors"),
                                 "Temas bölgesini (contact zone) 3D görünümde soluk kırmızı yarı saydam "
                                 "bir bant olarak göster. Bant, rulonun yavaşladığı (temas beslemesi) "
                                 "bölgeyi işaretler; içinde kalan pas kısımları yavaş, dışındakiler hızlıdır. "
                                 "Pasların rengine dokunmaz — yalnızca görsel bir katmandır.")
        self.helper.add_checkbox(self.content, self.app, "show_heatmap", t("cb_show_heatmap"),
                                 "Her pas noktasının mandrel yüzeyine olan mesafesini renk skalasıyla göster. "
                                 "Mavi=güvenli mesafe, kırmızı=mandrel'e çok yakın veya çarpışma riski.")
        self.helper.add_spinbox(self.content, self.app, "shell_thickness", t("sp_shell_thickness"), 0, 20, 0.1,
                                "3D görünümdeki shell (kabuk) meshinin kalınlığı (mm) — sadece görseldir, G-code'u etkilemez. "
                                "STL export için kullanılır.")

        f_tip_dist = ttk.Frame(self.content)
        f_tip_dist.pack(fill="x", padx=10, pady=(4, 2))
        var_tip_dist = tk.BooleanVar(value=bool(self.app.params.get("show_tip_distance", False)))
        def on_tip_dist_toggle():
            self.app.on_param_change("show_tip_distance", var_tip_dist.get(), "visual")
        cb_tip_dist = ttk.Checkbutton(f_tip_dist, text=t("cb_show_tip_dist"),
                                      variable=var_tip_dist, command=on_tip_dist_toggle)
        cb_tip_dist.pack(anchor="w")
        self.helper.bind_tooltip(cb_tip_dist,
            "3D görünümde rulo ucunun mandrel yüzeyine olan X ve Z mesafesini gösterir.\n"
            "Referans noktaları için de aynı gösterge çizilir.\n"
            "Paso hesaplamalarını ETKİLEMEZ.")

        self.helper.add_checkbox(self.content, self.app, "show_rulers", t("cb_show_rulers"),
                                 "3D görünüme yerleştirilebilir X ve Z ölçek çubukları (cetvel) ekler. "
                                 "Yatay X cetveli 'X cetveli Z konumu' değerindeki Z seviyesine, dikey Z "
                                 "cetveli 'Z cetveli X konumu' değerindeki X seviyesine yerleşir. "
                                 "Etiketler doğrudan makine X / Z değerini (mm) gösterir. "
                                 "Uzunluk sahneye göre otomatik ayarlanır. Yalnızca GÖRSELDİR — paso "
                                 "hesaplamalarını veya G-code'u ETKİLEMEZ.")
        self.helper.add_spinbox(self.content, self.app, "ruler_x_at_z", t("sp_ruler_x_at_z"), -500, 1000, 5,
                                "Yatay X cetvelinin oturacağı Z seviyesi (mm). Cetveli ilgilendiğin "
                                "Z konumuna taşımak için değiştir.")
        self.helper.add_spinbox(self.content, self.app, "ruler_x_start", t("sp_ruler_x_start"), -500, 1000, 5,
                                "X cetvelinin BAŞLANGIÇ noktası (mm) — cetvelin sıfır işareti burada durur. "
                                "Etiketler bu noktadan itibaren mesafeyi gösterir. Başlangıç→Bitiş yönü "
                                "cetvelin yönünü belirler.")
        self.helper.add_spinbox(self.content, self.app, "ruler_x_end", t("sp_ruler_x_end"), -500, 1000, 5,
                                "X cetvelinin BİTİŞ noktası (mm). Bitiş < Başlangıç ise cetvel -X yönünde "
                                "ilerler. Bitiş'i Başlangıç'a EŞİT bırakırsan uzunluk sahneye göre otomatik "
                                "ayarlanır (Başlangıç=0 iken etiketler gerçek makine X değerini okur).")
        self.helper.add_spinbox(self.content, self.app, "ruler_z_at_x", t("sp_ruler_z_at_x"), -500, 1000, 5,
                                "Dikey Z cetvelinin oturacağı X seviyesi (mm). Cetveli ilgilendiğin "
                                "X konumuna taşımak için değiştir.")
        self.helper.add_spinbox(self.content, self.app, "ruler_z_start", t("sp_ruler_z_start"), -500, 1000, 5,
                                "Z cetvelinin BAŞLANGIÇ noktası (mm) — cetvelin sıfır işareti burada durur. "
                                "Etiketler bu noktadan itibaren mesafeyi gösterir. Başlangıç→Bitiş yönü "
                                "cetvelin yönünü belirler.")
        self.helper.add_spinbox(self.content, self.app, "ruler_z_end", t("sp_ruler_z_end"), -500, 1000, 5,
                                "Z cetvelinin BİTİŞ noktası (mm). Bitiş < Başlangıç ise cetvel -Z yönünde "
                                "ilerler. Bitiş'i Başlangıç'a EŞİT bırakırsan uzunluk sahneye göre otomatik "
                                "ayarlanır (Başlangıç=0 iken etiketler gerçek makine Z değerini okur).")

        self.helper.add_checkbox(self.content, self.app, "show_analysis_lines", t("cb_show_analysis"),
                                 "Her pas noktasında mandrel yüzeyine olan clearance mesafesini çizgi olarak göster. "
                                 "Heatmap ile birlikte çarpışma noktalarını tespit etmek için kullanılır.")
        self.helper.add_checkbox(self.content, self.app, "show_pass_dist_lines", t("cb_show_dist_lines"),
                                 "Her pasın mandrel yüzeyine en yakın noktasından mandrel yüzeyine mesafe çizgisi göster. "
                                 "Siyan çizgi ve mm etiketi olarak görünür.")
        f_tip_paths = ttk.Frame(self.content)
        f_tip_paths.pack(fill="x", padx=10, pady=2)
        var_tip_paths = tk.BooleanVar(value=bool(self.app.params.get("show_tip_paths", False)))
        def on_tip_paths_toggle():
            # Visual-only: store the flag then redraw from the CACHED paths so no
            # recalculation is triggered (path data / G-code are never touched).
            self.app.params["show_tip_paths"] = var_tip_paths.get()
            self.app.redraw_paths_cached()
        cb_tip_paths = ttk.Checkbutton(f_tip_paths, text=t("cb_show_tip_paths"),
                                       variable=var_tip_paths, command=on_tip_paths_toggle)
        cb_tip_paths.pack(anchor="w")
        self.helper.bind_tooltip(cb_tip_paths,
            "Pasları rulo MERKEZİ yerine rulo TEMAS NOKTASINDA (uç) çiz.\n"
            "Her çizilen yol, o pasın rulo yarıçapı (r_tool) kadar mandrel eksenine\n"
            "doğru radyal olarak içeri kaydırılır — böylece sacın gerçekte nerede\n"
            "şekillendiğini görürsün. TAMAMEN GÖRSELDİR: yol hesaplamasını, G-code'u\n"
            "veya simülasyonu ETKİLEMEZ, yalnızca 3B'de gösterilen çizgiyi taşır.\n"
            "(Radyal yaklaşım; eğik yüzeylerde temas noktası normal boyunca hafifçe kayabilir.)")

        # Camera Controls
        f_cam = ttk.Frame(self.content)
        f_cam.pack(fill="x", padx=10, pady=5)

        def save_cam():
            if hasattr(self.app, 'plotter'):
                pos = self.app.plotter.camera.position
                foc = self.app.plotter.camera.focal_point
                up = self.app.plotter.camera.up
                self.app.params["camera"] = {"pos": pos, "foc": foc, "up": up}
                if hasattr(self.app, 'save_settings_json'):
                     self.app.save_settings_json()
                     tk.messagebox.showinfo(t("msg_camera_saved_title"), t("msg_camera_saved"))

        def reset_cam():
            if hasattr(self.app, 'plotter'):
                saved = self.app.params.get("camera", {})
                if saved and "pos" in saved:
                    self.app.plotter.camera.position = saved["pos"]
                    self.app.plotter.camera.focal_point = saved["foc"]
                    self.app.plotter.camera.up = saved["up"]
                else:
                    self.app.plotter.camera_position = [(500, 500, 500), (0, 0, 0), (0, 0, 1)]
                self.app.plotter.reset_camera()

        self.helper.add_button(self.content, t("btn_save_cam_angle"), save_cam, "lightgray",
                               "Mevcut kamera açısını settings.json'a kaydet. "
                               "Bir sonraki açılışta bu açıdan başlar.")
        self.helper.add_button(self.content, t("btn_reset_cam"), reset_cam, "lightgray",
                               "Kamerayı kaydedilmiş varsayılan açıya sıfırla. "
                               "Kayıtlı açı yoksa standart izometrik görünüme döner.")

        # Camera Presets
        ttk.Label(self.content, text=t("lbl_cam_presets"), font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(5,2))
        f_presets = ttk.Frame(self.content)
        f_presets.pack(fill="x", padx=10, pady=2)

        def set_view(direction):
            if not hasattr(self.app, 'plotter'): return
            d = 400
            views = {
                "front": [(0, d, 50), (0, 0, 50), (1, 0, 0)],
                "back": [(0, -d, 50), (0, 0, 50), (1, 0, 0)],
                "left": [(-d, 0, 50), (0, 0, 50), (1, 0, 0)],
                "right": [(d, 0, 50), (0, 0, 50), (1, 0, 0)],
                "top": [(0, 0, d+50), (0, 0, 50), (0, 1, 0)],
                "iso": [(d, d, d), (0, 0, 50), (1, 0, 0)],
            }
            v = views.get(direction)
            if v:
                self.app.plotter.camera.position = v[0]
                self.app.plotter.camera.focal_point = v[1]
                self.app.plotter.camera.up = v[2]
                self.app.plotter.reset_camera()

        btn_front = tk.Button(f_presets, text=t("btn_front"), command=lambda: set_view("front"), width=6)
        btn_front.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_front, "Önden görünüm: +Y ekseninden XZ düzlemine bakış.")

        btn_back = tk.Button(f_presets, text=t("btn_back_view"), command=lambda: set_view("back"), width=6)
        btn_back.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_back, "Arkadan görünüm: -Y ekseninden XZ düzlemine bakış.")

        btn_left = tk.Button(f_presets, text=t("btn_left"), command=lambda: set_view("left"), width=6)
        btn_left.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_left, "Sol görünüm: -X ekseninden bakış (aşağıdan).")

        btn_right = tk.Button(f_presets, text=t("btn_right"), command=lambda: set_view("right"), width=6)
        btn_right.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_right, "Sağ görünüm: +X ekseninden bakış (yukarıdan).")

        btn_top = tk.Button(f_presets, text=t("btn_top"), command=lambda: set_view("top"), width=6)
        btn_top.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_top, "Üstten görünüm: Z ekseni boyunca aşağı bakış.")

        btn_iso = tk.Button(f_presets, text=t("btn_iso"), command=lambda: set_view("iso"), width=6, bg="lightblue")
        btn_iso.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_iso, "İzometrik görünüm: mandrel ve pasların en iyi görüldüğü standart açı.")

        # Camera Rotation Buttons
        ttk.Label(self.content, text=t("lbl_rotate_view"), font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(5,2))
        f_rotate = ttk.Frame(self.content)
        f_rotate.pack(fill="x", padx=10, pady=2)

        def rotate_view(angle):
            if not hasattr(self.app, 'plotter'): return
            try:
                self.app.plotter.camera.azimuth += angle
                self.app.plotter.render()
            except Exception as e:
                print(f"Rotation error: {e}")

        btn_r45l = tk.Button(f_rotate, text="◀ -45°", command=lambda: rotate_view(-45), width=7)
        btn_r45l.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_r45l, "Görünümü saat yönünün tersine 45° döndür.")

        btn_r45r = tk.Button(f_rotate, text="+45° ▶", command=lambda: rotate_view(45), width=7)
        btn_r45r.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_r45r, "Görünümü saat yönünde 45° döndür.")

        btn_r15l = tk.Button(f_rotate, text="◀ -15°", command=lambda: rotate_view(-15), width=7)
        btn_r15l.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_r15l, "Görünümü saat yönünün tersine 15° döndür (ince ayar).")

        btn_r15r = tk.Button(f_rotate, text="+15° ▶", command=lambda: rotate_view(15), width=7)
        btn_r15r.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_r15r, "Görünümü saat yönünde 15° döndür (ince ayar).")

        def fix_clipping():
            if hasattr(self.app, 'plotter'):
                self.app.plotter.reset_camera()
                self.app.plotter.camera.clipping_range = (0.1, 10000)
                self.app.plotter.render()

        btn_fix = tk.Button(f_rotate, text=t("btn_fix_view"), command=fix_clipping, width=8, bg="yellow")
        btn_fix.pack(side="right", padx=2)
        self.helper.bind_tooltip(btn_fix, "Geometri görünmez hale gelirse veya kırpılıyorsa buna bas. "
                                          "Kamera clipping aralığını sıfırlayarak tüm objeleri tekrar görünür yapar.")

        # --- Safety & Correction Settings ---
        self.helper.add_section_header(self.content, t("section_safety"), color="purple")
        self.helper.add_spinbox(self.content, self.app, "collision_resolution", t("sp_collision_res"), 0.1, 5.0, 0.5,
                                "Çarpışma tespiti için tarama adımı (mm). "
                                "Küçük değer = daha hassas ama yavaş hesaplama. "
                                "Büyük değer = hızlı ama küçük çarpışmaları atlayabilir. Önerilen: 0.5–1.0 mm.")
        self.helper.add_spinbox(self.content, self.app, "min_safety_gap", t("sp_min_safety_gap"), 0.0, 10.0, 0.5,
                                "Rulo ile blank yüzeyi arasında ASLA ihlal edilmeyecek güvenlik tabanı (mm). "
                                "Tek yönlü çalışır: bir pas bu mesafeden yakına geçerse dışarı itilir, içeri çekilmez. "
                                "Asıl boşluğu her operasyonun 'Clearance' alanı belirler. 0 = yüzeye temasa izin ver.")
        self.helper.add_spinbox(self.content, self.app, "clamp_zone_length", t("sp_clamp_zone"), 0.0, 200.0, 1.0,
                                "Karşı baskı (counter-press) ile mandrel arasında sıkışan taban bölgesi (mm, mandrel tabanından yukarı). "
                                "Bu bölge işlenmez; 3B sahnede kırmızı bant olarak gösterilir. "
                                "Faz 1: sadece UYARI — bu bölgede başlayan operasyonlar loglanır, yol yine de üretilir. "
                                "0 = makine varsayılanını (Makine sekmesi) kullan.")

        # --- Conformal Path Settings ---
        self.helper.add_section_header(self.content, t("section_conformal"), color="teal")
        self.helper.add_checkbox(self.content, self.app, "conformal_clearance_all_operations", t("cb_conformal_rough"),
                                 "Kaba paso P2 konumunu yüzey normali X bileşeniyle ölçekler. "
                                 "Eğimli yüzeylerde paso giriş açısını mandrel yüzeyine adapte eder.")
        self.helper.add_checkbox(self.content, self.app, "finish_trace_mandrel_profile", t("cb_conformal_finish"),
                                 "Bitirme paso pathini spline yerine mandrel profiline konformal (per-point) offsetleyerek üret. "
                                 "Her Z noktasında yüzey normaline göre tam mesafe korunur.")
        self.helper.add_spinbox(self.content, self.app, "adaptive_bow_height", t("sp_bow_height"), 0.0, 100.0, 1.0,
                                "Konformal path modunda paso ortasını mandrel'den ne kadar uzaklaştır (parabolic bow, mm). "
                                "0 = tam konformal (her noktada eşit mesafe). "
                                "> 0 = pasoların uçları yüzeye değer, ortası daha uzak — konkav şekillerde tercih edilebilir.")
        self.helper.add_spinbox(self.content, self.app, "finish_trace_resolution", t("sp_conformal_res"), 0.1, 5.0, 0.1,
                                "Konformal path modunda Z boyunca örnekleme adımı (mm). "
                                "Küçük = daha yumuşak path ama daha fazla G-code satırı. Önerilen: 0.5–1.0 mm.")
        self.helper.add_checkbox(self.content, self.app, "auto_calc_angle", t("cb_auto_calc_angle"),
                                 "Rulonun mandrel yüzeyine olan açısını (Y rotasyonu) otomatik hesapla. "
                                 "Kapalıysa, operasyon ayarlarındaki Rotation (Deg) değeri kullanılır.")
        self.helper.add_checkbox(self.content, self.app, "clearance_correction_per_point", t("cb_normal_aligned"),
                                 "Spline kontrol noktalarını X ekseni yerine mandrel yüzey normali yönünde kaydır. "
                                 "Eğik/eğri yüzeylerde çarpışma düzeltmesini daha doğru yapar. "
                                 "Konik/düz mandrel için gereksiz; küresel veya konkav şekillerde etkili.")
        self.helper.add_spinbox(self.content, self.app, "exit_arc_angle", t("lbl_exit_arc"), 0.0, 180.0, 1.0,
                                "Çıkış yayının (T2→P3) tanjant-kiriş açısı (derece). 0 = düz çizgi.")

        # --- Geometry Settings ---
        self.helper.add_section_header(self.content, t("section_geometry"), color="darkblue")

        self.helper.add_button(self.content, t("btn_load_model"), self.root.load_step_prompt, "orange",
                               "STEP veya STP formatında 3D mandrel modeli yükle. "
                               "Model yüklendikten sonra profil otomatik analiz edilir.")

        self.helper.add_scale(self.content, self.app, "blank_radius", t("sc_blank_radius"), 50, 500, "all",
                              "Sıvama işleminde kullanılan metal diskin (blank) yarıçapı (mm). "
                              "3D görünümde başlangıç disk boyutunu belirler.")
        self.helper.add_spinbox(self.content, self.app, "final_part_thickness_on_mandrel", t("sp_part_thickness"), 0, 20, 0.1,
                                "Oluşturulan parçanın hedef et kalınlığı (mm). "
                                "Tüm paso yolları mandrel yüzeyinden bu kadar uzakta hesaplanır. "
                                "Kaba ve bitirme paslarını etkiler. Sac malzemenin gerçek kalınlığına eşit olmalı.")
        self.helper.add_scale(self.content, self.app, "blank_z_shift", t("sc_blank_z"), -100, 100, "all",
                              "Blank diskin Z konumunu ince ayarla (mm). "
                              "Pozitif: yukarı, negatif: aşağı. Yeni STEP yüklenince otomatik hizalanır, bu ayar üzerine eklenir.")
        self.helper.add_scale(self.content, self.app, "mandrel_pos_x_offset", t("sc_mandrel_x"), -500, 500, "all",
                              "Mandrel modelini X ekseninde kaydır (mm). "
                              "Model STEP dosyasında yanlış konumda yüklendiyse hizalamak için kullanılır.")
        self.helper.add_scale(self.content, self.app, "mandrel_pos_z_offset", t("sc_mandrel_z"), -500, 500, "all",
                              "Mandrel modelini Z ekseninde kaydır (mm). "
                              "Model STEP dosyasında yanlış konumda yüklendiyse hizalamak için kullanılır.")

        # Mandrel Rotation
        f_rot = ttk.Frame(self.content)
        f_rot.pack(fill="x", padx=10, pady=5)
        ttk.Label(f_rot, text=t("lbl_mandrel_rot")).pack(side="left")

        def rot_x(): self.app.rotate_mandrel('x')
        def rot_y(): self.app.rotate_mandrel('y')
        def rot_z(): self.app.rotate_mandrel('z')
        def reset_rot():
            self.app.params["mandrel_rot_x"] = 0.0
            self.app.params["mandrel_rot_y"] = 0.0
            self.app.params["mandrel_rot_z"] = 0.0
            self.app.update_scene("all")

        btn_rx = tk.Button(f_rot, text="X+90", command=rot_x, width=6)
        btn_rx.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_rx, "Mandrel modelini X ekseni etrafında 90° döndür.")

        btn_ry = tk.Button(f_rot, text="Y+90", command=rot_y, width=6)
        btn_ry.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_ry, "Mandrel modelini Y ekseni etrafında 90° döndür.")

        btn_rz = tk.Button(f_rot, text="Z+90", command=rot_z, width=6)
        btn_rz.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_rz, "Mandrel modelini Z ekseni etrafında 90° döndür.")

        btn_rreset = tk.Button(f_rot, text=t("btn_reset_rot"), command=reset_rot, bg="lightgray", width=8)
        btn_rreset.pack(side="left", padx=2)
        self.helper.bind_tooltip(btn_rreset, "Mandrel rotasyonunu sıfırla (tüm eksenler 0°). "
                                             "Model orijinal STEP yönüne döner.")

        # --- Actions ---
        self.helper.add_section_header(self.content, t("section_actions"), color="darkblue")

        def force_calc():
             # R3 (one calc path, #76): route through the SAME background worker
             # the Program tab uses — no more synchronous UI-thread recalc here.
             # Time estimate + clamp status refresh when the result lands.
             self.root.ui_program._start_async_calc()

        self.helper.add_button(self.content, t("btn_calculate"), force_calc, "orange",
                               "Mevcut ayarlara göre tüm takım yollarını yeniden hesapla ve görünümü güncelle.")

        self.helper.add_button(self.content, t("btn_save_gcode"), self.root.save_gcode_logic, "lightgreen",
                               "Hesaplanan takım yollarını standart G-code formatında .NC dosyasına kaydet.")
        self.helper.add_button(self.content, t("btn_export_pdf"), self.root.export_pdf_action, "#4169E1",
                               "Operasyon bilgilerini (takım, hız, pas sayısı) içeren PDF tezgah kartı oluştur.")
        self.helper.add_button(self.content, t("btn_export_stl"), self.root.export_stl_action, "#20B2AA",
                               "Sıvama sonucu oluşan parça kabuğunu (shell) STL dosyası olarak dışa aktar.")

        # --- Simulation ---
        self.helper.add_section_header(self.content, t("section_simulation"), color="darkblue")
        self.helper.add_button(self.content, t("btn_run_sim"), self.root.run_sim, "cyan",
                               "Takım yollarını 3D görünümde adım adım simüle et.")
        self.helper.add_button(self.content, t("btn_stop_sim"), self.root.stop_sim, "red",
                               "Çalışan simülasyonu durdur.")
        self._btn_pause_sim = tk.Button(
            self.content, text="Pause Sim", command=self._toggle_sim_pause,
            bg="#FF9800", fg="black", font=("Arial", 9, "bold"), state="disabled")
        self._btn_pause_sim.pack(fill="x", padx=10, pady=2)
        self.helper.bind_tooltip(self._btn_pause_sim,
            "Simülasyonu durdur / devam ettir.\n"
            "Duraklatıldığında takım mevcut konumda bekler.")

        f_simspd = ttk.Frame(self.content)
        f_simspd.pack(fill="x", padx=10, pady=(4, 2))
        ttk.Label(f_simspd, text=t("lbl_sim_speed"), font=("Arial", 9)).pack(anchor="w")
        f_simspd_row = ttk.Frame(f_simspd)
        f_simspd_row.pack(fill="x")
        self._sim_speed_lbl = tk.Label(f_simspd_row, text="1.00x", width=6,
                                       font=("Arial", 9, "bold"), fg="#004488")
        self._sim_speed_lbl.pack(side="right")
        self._sim_speed_var = tk.DoubleVar(value=1.0)
        def _on_sim_speed(val):
            multiplier = round(float(val), 2)
            self.app.sim_controller.speed_multiplier = multiplier
            self._sim_speed_lbl.config(text=f"{multiplier:.2f}x")
        sim_slider = tk.Scale(
            f_simspd_row, variable=self._sim_speed_var,
            from_=0.01, to=2.0, resolution=0.01, orient="horizontal", showvalue=False,
            command=_on_sim_speed, bg="#f0f0f0", highlightthickness=0)
        sim_slider.pack(side="left", fill="x", expand=True)
        self.helper.bind_tooltip(f_simspd,
            "Simülasyon oynatma hızını ayarla.\n"
            "Sol uç = 0.01x (çok yavaş / inceleme modu)\n"
            "Orta    = 1.00x (normal hız)\n"
            "Sağ uç = 2.00x (hızlı önizleme)")


    def _toggle_sim_pause(self):
        sc = self.app.sim_controller
        if not sc.is_running:
            return
        if sc._general_pause_event.is_set():
            sc.pause()
        else:
            sc.resume()
        self.refresh_sim_controls()

    def refresh_sim_controls(self):
        if not hasattr(self, "_btn_pause_sim"):
            return
        sc = self.app.sim_controller
        if sc.is_running:
            self._btn_pause_sim.config(state="normal")
            if sc._general_pause_event.is_set():
                self._btn_pause_sim.config(text="Pause Sim", bg="#FF9800")
            else:
                self._btn_pause_sim.config(text="Resume Sim", bg="#4CAF50")
        else:
            self._btn_pause_sim.config(state="disabled", text="Pause Sim", bg="#FF9800")

    def sync_params(self):
        pass
