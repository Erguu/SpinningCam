import tkinter as tk
from tkinter import ttk, messagebox
from ui.tabs.scrollable_tab_base import ScrollableTabBase
from i18n import t


class MachineTab(ScrollableTabBase):
    def __init__(self, parent_frame, app, ui_helper):
        self.app = app
        self.helper = ui_helper

        super().__init__(parent_frame)
        self._create_widgets()

    def _create_widgets(self):
        tk.Label(self.content, text=t("lbl_machine_settings"), font=("Arial", 12, "bold"), pady=10).pack()

        # Active machine header + save button
        profile = getattr(self.app, "active_machine_profile", None)
        if profile:
            mid      = profile.get("machine_id", "")
            mname    = profile.get("machine_name", "")
            customer = self.app.params.get("_customer_name", "")
            hdr_text = f"{mname}  [{mid}]"
            if customer:
                hdr_text += f"  ·  {customer}"
            f_hdr = ttk.Frame(self.content)
            f_hdr.pack(fill="x", padx=10, pady=(0, 6))
            tk.Label(f_hdr, text=hdr_text,
                     font=("Arial", 10, "bold"), fg="steelblue").pack(side="left", padx=4)
            ttk.Button(f_hdr, text=t("btn_save_profile"),
                       command=self._save_machine_profile).pack(side="right", padx=4)

        # --- Machine Coordinate System ---
        f_coords = ttk.LabelFrame(self.content, text=t("frm_coords"))
        f_coords.pack(fill="x", padx=10, pady=10)

        tk.Label(f_coords, text=t("lbl_coords_info"),
                 font=("Arial", 8, "italic"), fg="gray").pack(anchor="w", padx=5)

        f_origin = ttk.Frame(f_coords)
        f_origin.pack(fill="x", padx=5, pady=5)
        tk.Label(f_origin, text=t("lbl_machine_origin")).pack(anchor="w")

        f_origin_inputs = ttk.Frame(f_coords)
        f_origin_inputs.pack(fill="x", padx=5, pady=2)

        tk.Label(f_origin_inputs, text="X:").pack(side="left", padx=2)
        var_origin_x = tk.DoubleVar(value=self.app.params.get("machine_origin_x", 0.0))
        def on_origin_x_change():
            try: self.app.on_param_change("machine_origin_x", var_origin_x.get(), "none")
            except: pass
        e_origin_x = ttk.Entry(f_origin_inputs, textvariable=var_origin_x, width=8)
        e_origin_x.pack(side="left", padx=2)
        e_origin_x.bind("<Return>", lambda ev: on_origin_x_change())
        e_origin_x.bind("<FocusOut>", lambda ev: on_origin_x_change())
        e_origin_x.bind("<Button-1>", lambda event: event.widget.focus_force())
        self.helper.bind_tooltip(e_origin_x, "CAM global X koordinatlarının makine X=0 noktasına karşılık gelen değeri.")

        tk.Label(f_origin_inputs, text="Z:").pack(side="left", padx=(10, 2))
        var_origin_z = tk.DoubleVar(value=self.app.params.get("machine_origin_z", 0.0))
        def on_origin_z_change():
            try: self.app.on_param_change("machine_origin_z", var_origin_z.get(), "none")
            except: pass
        e_origin_z = ttk.Entry(f_origin_inputs, textvariable=var_origin_z, width=8)
        e_origin_z.pack(side="left", padx=2)
        e_origin_z.bind("<Return>", lambda ev: on_origin_z_change())
        e_origin_z.bind("<FocusOut>", lambda ev: on_origin_z_change())
        e_origin_z.bind("<Button-1>", lambda event: event.widget.focus_force())
        self.helper.bind_tooltip(e_origin_z, "CAM global Z koordinatlarının makine Z=0 noktasına karşılık gelen değeri.")

        tk.Label(f_origin_inputs, text=t("lbl_mm")).pack(side="left", padx=2)

        # Origin = Safe Home Checkbox
        f_origin_use_home = ttk.Frame(f_coords)
        f_origin_use_home.pack(fill="x", padx=5, pady=(0, 4))

        var_origin_use_home = tk.BooleanVar(value=bool(self.app.params.get("origin_use_home", False)))

        def on_origin_use_home_toggle():
            use_home = var_origin_use_home.get()
            self.app.on_param_change("origin_use_home", use_home, "none")
            if use_home:
                hx = self.app.params.get("home_x", 300.0)
                hz = self.app.params.get("home_z", 150.0)
                var_origin_x.set(hx)
                var_origin_z.set(hz)
                e_origin_x.config(state="disabled")
                e_origin_z.config(state="disabled")
            else:
                e_origin_x.config(state="normal")
                e_origin_z.config(state="normal")

        cb_use_home = ttk.Checkbutton(
            f_origin_use_home,
            text=t("cb_origin_use_home"),
            variable=var_origin_use_home,
            command=on_origin_use_home_toggle
        )
        cb_use_home.pack(anchor="w", padx=5)
        self.helper.bind_tooltip(
            cb_use_home,
            "Aktifken makine koordinat orijini otomatik olarak 'Program Start' (Home) pozisyonuna eşitlenir. "
            "Fiziksel home = makine (0,0) olan tezgahlarda kullanın. "
            "Aktifken X/Z Origin alanları devre dışı kalır."
        )

        if var_origin_use_home.get():
            e_origin_x.config(state="disabled")
            e_origin_z.config(state="disabled")

        # Axis Direction Inversion
        f_invert = ttk.Frame(f_coords)
        f_invert.pack(fill="x", padx=5, pady=5)

        var_invert_x = tk.BooleanVar(value=bool(self.app.params.get("machine_invert_x", False)))
        def on_invert_x_toggle(): self.app.on_param_change("machine_invert_x", var_invert_x.get(), "none")
        cb_invert_x = ttk.Checkbutton(f_invert, text=t("cb_invert_x"), variable=var_invert_x, command=on_invert_x_toggle)
        cb_invert_x.pack(side="left", padx=5)
        self.helper.bind_tooltip(cb_invert_x, "X eksenini tersine çevirir. Makinenin X ekseni merkeze doğru artıyorsa işaretleyin.")

        var_invert_z = tk.BooleanVar(value=bool(self.app.params.get("machine_invert_z", False)))
        def on_invert_z_toggle(): self.app.on_param_change("machine_invert_z", var_invert_z.get(), "none")
        cb_invert_z = ttk.Checkbutton(f_invert, text=t("cb_invert_z"), variable=var_invert_z, command=on_invert_z_toggle)
        cb_invert_z.pack(side="left", padx=5)
        self.helper.bind_tooltip(cb_invert_z, "Z eksenini tersine çevirir. Makinenin Z ekseni mandrele doğru artıyorsa işaretleyin.")

        # Roller Approach Side
        f_roller_side = ttk.Frame(f_coords)
        f_roller_side.pack(fill="x", padx=5, pady=(0, 6))

        var_roller_pos_side = tk.BooleanVar(value=bool(self.app.params.get("roller_positive_x_side", True)))
        def on_roller_side_toggle():
            self.app.on_param_change("roller_positive_x_side", var_roller_pos_side.get(), "paths")
        cb_roller_side = ttk.Checkbutton(
            f_roller_side,
            text=t("cb_roller_pos_x"),
            variable=var_roller_pos_side,
            command=on_roller_side_toggle
        )
        cb_roller_side.pack(anchor="w", padx=5)
        self.helper.bind_tooltip(
            cb_roller_side,
            "İşaretli: Rulon mandrel merkezinden +X yönünde yaklaşır (varsayılan).\n"
            "İşaretsiz: Rulon -X yönünden yaklaşır. Tüm paso koordinatları otomatik olarak yansıtılır."
        )

        # Output Mode (Radius/Diameter)
        f_output_mode = ttk.LabelFrame(self.content, text=t("frm_output_mode"))
        f_output_mode.pack(fill="x", padx=10, pady=10)

        var_output_mode = tk.StringVar(value=self.app.params.get("output_mode", "diameter"))
        def on_output_mode_change(): self.app.on_param_change("output_mode", var_output_mode.get(), "none")

        rb_dia = ttk.Radiobutton(f_output_mode, text=t("rb_diameter"), variable=var_output_mode, value="diameter", command=on_output_mode_change)
        rb_dia.pack(anchor="w", padx=5, pady=2)
        self.helper.bind_tooltip(rb_dia, "X değerlerini çap olarak yazar (X × 2). Torna tezgahlarında yaygın olan çap programlama modu.")

        rb_rad = ttk.Radiobutton(f_output_mode, text=t("rb_radius"), variable=var_output_mode, value="radius", command=on_output_mode_change)
        rb_rad.pack(anchor="w", padx=5, pady=2)
        self.helper.bind_tooltip(rb_rad, "X değerlerini yarıçap olarak yazar.")

        # Additional Work Offsets (G54)
        f_offsets = ttk.LabelFrame(self.content, text=t("frm_offsets"))
        f_offsets.pack(fill="x", padx=10, pady=10)

        def add_offset_spinbox(p, key, title, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            val = self.app.params.get(key, 0.0)
            var = tk.DoubleVar(value=val)
            def on_change():
                try: self.app.on_param_change(key, var.get(), "none")
                except: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            self.helper.bind_tooltip(e, tooltip)
            self.helper.bind_tooltip(f, tooltip)

        add_offset_spinbox(f_offsets, "machine_gcode_offset_x", t("lbl_x_offset"),
                           "Origin dönüşümünden SONRA tüm X koordinatlarına eklenen sabit değer (G54 iş ofseti).")
        add_offset_spinbox(f_offsets, "machine_gcode_offset_z", t("lbl_z_offset"),
                           "Origin dönüşümünden SONRA tüm Z koordinatlarına eklenen sabit değer (G54 iş ofseti).")

        def add_int_entry(p, key, title, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            val = int(self.app.params.get(key, 1))
            var = tk.IntVar(value=val)
            def on_change():
                try: self.app.on_param_change(key, var.get(), "none")
                except: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            self.helper.bind_tooltip(e, tooltip)
            self.helper.bind_tooltip(f, tooltip)

        # Program Start / Retract
        f_home = ttk.LabelFrame(self.content, text=t("frm_home"))
        f_home.pack(fill="x", padx=10, pady=5)

        tk.Label(f_home, text=t("lbl_home_info"),
                 font=("Arial", 8, "italic"), fg="gray", wraplength=380, justify="left").pack(anchor="w", padx=5, pady=(2, 4))

        def add_home_spinbox(p, key, title, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            if "retract" in key: val_def = 50.0
            elif "x" in key: val_def = 300.0
            else: val_def = 150.0
            val = self.app.params.get(key, val_def)
            var = tk.DoubleVar(value=val)
            def on_change():
                try: self.app.on_param_change(key, var.get(), "paths")
                except: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            self.helper.bind_tooltip(e, tooltip)
            self.helper.bind_tooltip(f, tooltip)

        add_home_spinbox(f_home, "home_z", t("lbl_home_z"),
                         "Programın başladığı ve her pas sonrası geri dönülen Z pozisyonu (CAM koordinatı, mutlak).")
        add_home_spinbox(f_home, "home_x", t("lbl_home_x"),
                         "Programın başladığı ve her pas sonrası geri dönülen X pozisyonu (CAM koordinatı, mutlak).")

        tk.Label(f_home, text=t("lbl_home_hint"),
                 font=("Arial", 8, "italic"), fg="#0055aa", wraplength=380, justify="left"
                 ).pack(anchor="w", padx=5, pady=(0, 4))

        add_home_spinbox(f_home, "retract_x", t("lbl_retract_x"),
                         "Her pas sonrası rulonun X ekseninde geri çekilme miktarı (göreceli, mm).")
        add_home_spinbox(f_home, "retract_z", t("lbl_retract_z"),
                         "Her pas sonrası rulonun Z ekseninde geri çekilme miktarı (göreceli, mm).")

        # Touch Point Calibration
        f_touch = ttk.LabelFrame(self.content, text=t("frm_touch"))
        f_touch.pack(fill="x", padx=10, pady=10)

        tk.Label(f_touch, text=t("lbl_touch_info"),
                 font=("Arial", 8, "italic"), fg="#444", wraplength=460,
                 justify="left").pack(anchor="w", padx=8, pady=(4, 2))

        def _open_touch_calibration():
            from ui.dialogs.touch_calibration import TouchCalibrationDialog
            TouchCalibrationDialog(self.content.winfo_toplevel(), self.app)

        btn_touch = tk.Button(f_touch, text=t("btn_touch_cal"),
                              command=_open_touch_calibration,
                              bg="lightyellow", width=24)
        btn_touch.pack(anchor="w", padx=8, pady=(4, 8))
        self.helper.bind_tooltip(btn_touch,
            "Rulоyu mandrele veya blanka temas ettirin, DRO değerini okuyun ve programa aktarın.")

        # Helper to create label+text area
        def add_text_area(p, title, key, height=4, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=10, pady=5)
            lbl = tk.Label(f, text=title, font=("Arial", 9, "bold"), anchor="w")
            lbl.pack(fill="x")
            txt = tk.Text(f, height=height, font=("Consolas", 9))
            txt.pack(fill="x")
            val = self.app.params.get(key, "")
            txt.insert("1.0", val)
            self.helper.bind_tooltip(txt, tooltip)
            self.helper.bind_tooltip(lbl, tooltip)
            return txt

        # G-code Output Settings
        f_gcode_out = ttk.LabelFrame(self.content, text=t("frm_gcode_output"))
        f_gcode_out.pack(fill="x", padx=10, pady=10)
        add_int_entry(f_gcode_out, "max_spin_rpm", t("lbl_max_rpm"),
                      "G-code'a yazılacak maksimum mil devri sınırı (G50 S[değer]). Tipik: 1500-3000 RPM.")
        self.helper.add_spinbox(f_gcode_out, self.app, "gcode_resolution", t("sp_gcode_res"), 0.5, 20.0, 0.5,
                                "G-code çıktısında ardışık noktalar arası minimum mesafe (mm). "
                                "Büyük değer = daha az satır, daha küçük dosya. "
                                "2–5 mm çoğu tezgah için yeterli. PLC limitine (1000 satır) dikkat edin.")

        self.txt_header = add_text_area(self.content, t("lbl_gcode_header"), "gcode_header", height=6,
                                        tooltip="Her G-code dosyasının BAŞINA eklenen satırlar. "
                                                "Genellikle G21 G90 G18 G54.")
        self.txt_footer = add_text_area(self.content, t("lbl_gcode_footer"), "gcode_footer", height=4,
                                        tooltip="Her G-code dosyasının SONUNA eklenen satırlar. Örn: M5 / M30")

        # Working Area (Workspace)
        f_ws = ttk.LabelFrame(self.content, text=t("frm_workspace"))
        f_ws.pack(fill="x", padx=10, pady=10)

        tk.Label(f_ws, text=t("lbl_workspace_info"),
                 font=("Arial", 8, "italic"), fg="gray").pack(anchor="w", padx=5)

        var_ws_show = tk.BooleanVar(value=bool(self.app.params.get("workspace_show", True)))
        def on_ws_show_toggle():
            self.app.on_param_change("workspace_show", var_ws_show.get(), "all")
        cb_ws = ttk.Checkbutton(f_ws, text=t("cb_show_in_3d"), variable=var_ws_show, command=on_ws_show_toggle)
        cb_ws.pack(anchor="w", padx=5, pady=3)
        self.helper.bind_tooltip(cb_ws, "Makine çalışma alanını 3D sahnede şeffaf kutu olarak göster/gizle.")

        def add_ws_entry(p, key, title, default=0.0, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            var = tk.DoubleVar(value=self.app.params.get(key, default))
            def on_change():
                try: self.app.on_param_change(key, var.get(), "all")
                except: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>", lambda ev: on_change())
            e.bind("<FocusOut>", lambda ev: on_change())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            self.helper.bind_tooltip(e, tooltip)
            self.helper.bind_tooltip(f, tooltip)

        add_ws_entry(f_ws, "workspace_x_min", t("lbl_ws_x_min"), default=0.0,
                     tooltip="Çalışma alanının X başlangıç noktası (mm).")
        add_ws_entry(f_ws, "workspace_x_max", t("lbl_ws_x_max"), default=300.0,
                     tooltip="Makinenin X ekseninde ulaşabileceği maksimum yarıçap mesafesi (mm).")
        add_ws_entry(f_ws, "workspace_z_min", t("lbl_ws_z_min"), default=0.0,
                     tooltip="Makinenin Z ekseninde ulaşabileceği minimum pozisyon (mm, CAM koordinatları).")
        add_ws_entry(f_ws, "workspace_z_max", t("lbl_ws_z_max"), default=500.0,
                     tooltip="Makinenin Z ekseninde ulaşabileceği maksimum pozisyon (mm, CAM koordinatları).")
        add_ws_entry(f_ws, "clamp_zone_baseline", t("lbl_clamp_baseline"), default=0.0,
                     tooltip="Karşı baskının kavradığı taban derinliği için MAKİNE varsayılanı (mm, mandrel tabanından yukarı). "
                             "Bu bölge işlenmez (counter-press). Her program bunu Process sekmesindeki 'Kıskaç Bölgesi' "
                             "alanıyla geçersiz kılabilir (0 = bu varsayılanı kullan). TODO #62.")

        # Cylinder Section
        f_cyl = ttk.LabelFrame(self.content, text=t("frm_cylinder"))
        f_cyl.pack(fill="x", padx=10, pady=10)

        tk.Label(f_cyl, text=t("lbl_cyl_info"),
                 font=("Arial", 8, "italic"), fg="gray", justify="left").pack(anchor="w", padx=5, pady=(2, 4))

        var_cyl_enabled = tk.BooleanVar(value=bool(self.app.params.get("cylinder_enabled", True)))
        def on_cyl_enabled_toggle():
            self.app.on_param_change("cylinder_enabled", var_cyl_enabled.get(), "none")
        cb_cyl_enabled = ttk.Checkbutton(f_cyl, text=t("cb_cyl_enabled"), variable=var_cyl_enabled, command=on_cyl_enabled_toggle)
        cb_cyl_enabled.pack(anchor="w", padx=5, pady=(0, 2))
        self.helper.bind_tooltip(cb_cyl_enabled, "İşaretliyken program başında M40 P<mm> komutu G-code'a yazılır.")

        var_cyl_show = tk.BooleanVar(value=bool(self.app.params.get("cylinder_show", True)))
        def on_cyl_show_toggle():
            self.app.on_param_change("cylinder_show", var_cyl_show.get(), "all")
        cb_cyl_show = ttk.Checkbutton(f_cyl, text=t("cb_show_in_3d"), variable=var_cyl_show, command=on_cyl_show_toggle)
        cb_cyl_show.pack(anchor="w", padx=5, pady=(0, 4))
        self.helper.bind_tooltip(cb_cyl_show, "Silindiri 3D sahnede göster/gizle. G-code/PLC çıktısını etkilemez.")

        def add_cyl_entry(parent, param_key, label, default, tooltip):
            f = ttk.Frame(parent)
            f.pack(fill="x", padx=5, pady=3)
            tk.Label(f, text=label, width=18, anchor="w").pack(side="left")
            var = tk.DoubleVar(value=self.app.params.get(param_key, default))
            def on_change(v=var, k=param_key):
                try: self.app.on_param_change(k, v.get(), "all")
                except: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="left", padx=4)
            e.bind("<Return>",   lambda ev, fn=on_change: fn())
            e.bind("<FocusOut>", lambda ev, fn=on_change: fn())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            self.helper.bind_tooltip(e, tooltip)
            return var

        add_cyl_entry(f_cyl, "cylinder_position_mm", t("lbl_cyl_pos"), 0.0,
            "Silindirin hedef konumu (mm). PLC'ye Param = round(mm / 10) olarak gönderilir.")
        add_cyl_entry(f_cyl, "cylinder_x_pos", t("lbl_cyl_x"), 0.0,
            "Silindirin 3D sahnedeki X koordinatı (radyal konum, mm).")
        add_cyl_entry(f_cyl, "cylinder_z_base", t("lbl_cyl_z"), 200.0,
            "Silindirin monte edildiği Z konumu (mm).")

        # Tilt Arm (B Axis) — tilt-arm machines only (ID112); gated below via
        # section_frames like every other section.
        f_tilt = ttk.LabelFrame(self.content, text=t("frm_tilt_arm"))
        f_tilt.pack(fill="x", padx=10, pady=10)

        tk.Label(f_tilt, text=t("lbl_tilt_arm_info"),
                 font=("Arial", 8, "italic"), fg="gray",
                 wraplength=380, justify="left").pack(anchor="w", padx=5, pady=(4, 6))

        def add_tilt_entry(param_key, label, default, tooltip):
            f = ttk.Frame(f_tilt)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=label, width=18, anchor="w").pack(side="left")
            var = tk.DoubleVar(value=float(self.app.params.get(param_key, default)))
            def on_change(v=var, k=param_key):
                try: self.app.on_param_change(k, v.get(), "paths")
                except: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="right")
            e.bind("<Return>",   lambda ev, fn=on_change: fn())
            e.bind("<FocusOut>", lambda ev, fn=on_change: fn())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            self.helper.bind_tooltip(e, tooltip)
            self.helper.bind_tooltip(f, tooltip)

        add_tilt_entry("tilt_pivot_x", t("lbl_tilt_pivot_x"), 0.0,
            "Döner kol pivot noktasının X koordinatı (mm, CAM global). "
            "Makine çizimlerinden ölçülür — şimdilik geçici değer.")
        add_tilt_entry("tilt_pivot_z", t("lbl_tilt_pivot_z"), 0.0,
            "Pivot noktasının Z ofseti Z arabasına göre (mm). "
            "tip_z = z_araba + pivot_z + kol·sin(B).")
        add_tilt_entry("tilt_b_min", t("lbl_tilt_b_min"), -60.0,
            "B ekseninin mekanik alt limiti (°). Yol üretiminde eğim bu değere kırpılır; "
            "aşan noktalar kinematik uyarı üretir.")
        add_tilt_entry("tilt_b_max", t("lbl_tilt_b_max"), 60.0,
            "B ekseninin mekanik üst limiti (°).")
        add_tilt_entry("tilt_b_home", t("lbl_tilt_b_home"), 0.0,
            "B ekseni ev/sıfır konumu (°). Çıktıdaki B kelimesi = eğim·işaret + ev. "
            "Eğim 0° = radyal kızak (makine #1 duruşu).")
        add_tilt_entry("tilt_b_sign", t("lbl_tilt_b_sign"), 1.0,
            "B ekseni yön işareti: +1 veya −1. Kontrolcünün pozitif B yönü "
            "CAM'in +Z'ye yatma yönüyle tersse −1 girin.")

        # PLC Output Mode
        f_plc = ttk.LabelFrame(self.content, text=t("frm_plc"))
        f_plc.pack(fill="x", padx=10, pady=10)

        tk.Label(f_plc, text=t("lbl_plc_info"),
                 font=("Arial", 8, "italic"), fg="gray",
                 wraplength=380, justify="left").pack(anchor="w", padx=5, pady=(4, 6))

        f_plc_en = ttk.Frame(f_plc)
        f_plc_en.pack(fill="x", padx=5, pady=2)
        var_plc = tk.BooleanVar(value=bool(self.app.params.get("plc_mode", False)))

        def on_plc_toggle():
            self.app.on_param_change("plc_mode", var_plc.get(), "none")
            _sync_plc_states()

        cb_plc = ttk.Checkbutton(f_plc_en, text=t("cb_plc_enable"), variable=var_plc, command=on_plc_toggle)
        cb_plc.pack(anchor="w")
        self.helper.bind_tooltip(cb_plc,
            "Etkinleştirildiğinde G-code her pas için RDP algoritması ile sadeleştirilmiş nokta listesi üretir.\n"
            "CNC çıktısı (normal G-code kaydetme) bundan etkilenmez.")

        f_tol = ttk.Frame(f_plc)
        f_tol.pack(fill="x", padx=5, pady=2)
        tk.Label(f_tol, text=t("lbl_plc_tol"), width=18).pack(side="left")
        var_tol = tk.DoubleVar(value=float(self.app.params.get("plc_tolerance", 0.5)))
        def on_tol_change():
            try: self.app.on_param_change("plc_tolerance", var_tol.get(), "none")
            except: pass
        tol_state = "normal" if var_plc.get() else "disabled"
        e_tol = ttk.Entry(f_tol, textvariable=var_tol, width=10, state=tol_state)
        e_tol.pack(side="right")
        e_tol.bind("<Return>", lambda ev: on_tol_change())
        e_tol.bind("<FocusOut>", lambda ev: on_tol_change())
        e_tol.bind("<Button-1>", lambda event: event.widget.focus_force())
        self.helper.bind_tooltip(e_tol, "RDP basitleştirme toleransı (mm). Tipik öneri: 0.3 – 1.0 mm.")
        self.helper.bind_tooltip(f_tol, "RDP toleransı: PLC nokta sayısını ve profil doğruluğunu dengeler.")

        f_exit_tol = ttk.Frame(f_plc)
        f_exit_tol.pack(fill="x", padx=5, pady=2)
        tk.Label(f_exit_tol, text=t("lbl_plc_exit_tol"), width=18).pack(side="left")
        _exit_tol_default = float(self.app.params.get("plc_exit_tolerance",
                                  self.app.params.get("plc_tolerance", 0.5)))
        var_exit_tol = tk.DoubleVar(value=_exit_tol_default)
        def on_exit_tol_change():
            try: self.app.on_param_change("plc_exit_tolerance", var_exit_tol.get(), "none")
            except: pass
        exit_tol_state = "normal" if var_plc.get() else "disabled"
        e_exit_tol = ttk.Entry(f_exit_tol, textvariable=var_exit_tol, width=10, state=exit_tol_state)
        e_exit_tol.pack(side="right")
        e_exit_tol.bind("<Return>",   lambda ev: on_exit_tol_change())
        e_exit_tol.bind("<FocusOut>", lambda ev: on_exit_tol_change())
        e_exit_tol.bind("<Button-1>", lambda event: event.widget.focus_force())
        self.helper.bind_tooltip(e_exit_tol, "Çıkış eğrisi (T2→P3) için ayrı RDP toleransı.")

        # Auto-tune: fit the tolerance to a PLC line budget (opt-in).
        f_auto = ttk.Frame(f_plc)
        f_auto.pack(fill="x", padx=5, pady=2)
        var_auto = tk.BooleanVar(value=bool(self.app.params.get("plc_auto_tune", False)))
        def on_auto_toggle():
            self.app.on_param_change("plc_auto_tune", var_auto.get(), "none")
            _sync_plc_states()
        cb_auto = ttk.Checkbutton(f_auto, text=t("cb_plc_autotune"), variable=var_auto,
                                  command=on_auto_toggle)
        cb_auto.pack(anchor="w")
        self.helper.bind_tooltip(cb_auto,
            "Açıkken PLC toleransı, satır sayısı hedefin altına inecek şekilde SCL dışa\n"
            "aktarımında otomatik seçilir (tolerans alanları elle girilmez).\n"
            "Güvenlik: clearance normal G-code'un altına düşürülmez; düşerse uyarır.")

        f_target = ttk.Frame(f_plc)
        f_target.pack(fill="x", padx=5, pady=2)
        tk.Label(f_target, text=t("lbl_plc_target"), width=18).pack(side="left")
        var_target = tk.IntVar(value=int(self.app.params.get("plc_target_lines", 1000)))
        def on_target_change():
            try: self.app.on_param_change("plc_target_lines", int(var_target.get()), "none")
            except: pass
        e_target = ttk.Entry(f_target, textvariable=var_target, width=10)
        e_target.pack(side="right")
        e_target.bind("<Return>",   lambda ev: on_target_change())
        e_target.bind("<FocusOut>", lambda ev: on_target_change())
        e_target.bind("<Button-1>", lambda event: event.widget.focus_force())
        self.helper.bind_tooltip(e_target, "Hedef azami PLC satır sayısı (PLC bellek limiti, örn. 1000).")

        def _sync_plc_states():
            plc_on  = var_plc.get()
            auto_on = var_auto.get() and plc_on
            # Auto-tune is only selectable when PLC mode is on.
            cb_auto.config(state="normal" if plc_on else "disabled")
            e_target.config(state="normal" if auto_on else "disabled")
            # When auto-tune drives the tolerance, the manual fields are read-only.
            man_state = "normal" if (plc_on and not auto_on) else "disabled"
            e_tol.config(state=man_state)
            e_exit_tol.config(state=man_state)

        _sync_plc_states()

        tk.Label(f_plc, text=t("lbl_plc_hint"), font=("Arial", 8), fg="#555555").pack(anchor="w", padx=5, pady=(2, 6))

        # Custom Commands
        f_cc = ttk.LabelFrame(self.content, text=t("frm_custom_cmds"))
        f_cc.pack(fill="x", padx=10, pady=10)

        tv_cc = ttk.Treeview(f_cc, columns=("trigger", "value", "cmd"), show="headings", height=4)
        tv_cc.heading("trigger", text=t("cc_trigger_col")); tv_cc.column("trigger", width=70,  anchor="center")
        tv_cc.heading("value",   text=t("cc_value_col"));   tv_cc.column("value",   width=60,  anchor="center")
        tv_cc.heading("cmd",     text=t("cc_command_col")); tv_cc.column("cmd",     width=180)
        tv_cc.pack(fill="x", padx=5, pady=(5, 2))

        def refresh_cc_tree():
            for item in tv_cc.get_children():
                tv_cc.delete(item)
            for entry in self.app.params.get("custom_commands", []):
                tri = "Pass" if entry.get("trigger") == "pass" else "Z"
                tv_cc.insert("", "end", values=(tri, entry.get("value", ""), entry.get("cmd", "")))

        refresh_cc_tree()

        f_add = ttk.Frame(f_cc)
        f_add.pack(fill="x", padx=5, pady=2)

        tk.Label(f_add, text=t("lbl_trigger")).pack(side="left")
        var_trig = tk.StringVar(value="pass")
        cb_trig = ttk.Combobox(f_add, textvariable=var_trig, values=["pass", "z"], width=5, state="readonly")
        cb_trig.pack(side="left", padx=(2, 6))

        tk.Label(f_add, text=t("lbl_value")).pack(side="left")
        var_val = tk.StringVar(value="1")
        e_val = ttk.Entry(f_add, textvariable=var_val, width=7)
        e_val.pack(side="left", padx=(2, 6))
        e_val.bind("<Button-1>", lambda event: event.widget.focus_force())

        tk.Label(f_add, text=t("lbl_cmd")).pack(side="left")
        var_cmd = tk.StringVar()
        e_cmd = ttk.Entry(f_add, textvariable=var_cmd, width=16)
        e_cmd.pack(side="left", padx=2, fill="x", expand=True)
        e_cmd.bind("<Button-1>", lambda event: event.widget.focus_force())

        def add_cc():
            try:
                trig = var_trig.get()
                val = float(var_val.get()) if trig == "z" else int(float(var_val.get()))
                cmd = var_cmd.get().strip()
                if not cmd:
                    return
                if "custom_commands" not in self.app.params:
                    self.app.params["custom_commands"] = []
                self.app.params["custom_commands"].append({"trigger": trig, "value": val, "cmd": cmd})
                refresh_cc_tree()
                var_cmd.set("")
            except Exception:
                pass

        def del_cc():
            sel = tv_cc.selection()
            if not sel:
                return
            idx = tv_cc.index(sel[0])
            cmds = self.app.params.get("custom_commands", [])
            if 0 <= idx < len(cmds):
                cmds.pop(idx)
                refresh_cc_tree()

        f_btns = ttk.Frame(f_cc)
        f_btns.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Button(f_btns, text=t("btn_add"),    command=add_cc).pack(side="left", padx=2)
        ttk.Button(f_btns, text=t("btn_delete"), command=del_cc).pack(side="left", padx=2)
        self.helper.bind_tooltip(f_cc,
            "Trigger=pass → o global pas numarasının başında komutu ekler (1-indexed).\n"
            "Trigger=z → paso içinde Z o eşiği geçtiği anda komutu ekler.\n"
            "Örn: trigger=pass, value=1, cmd=M41 P1")

        # M-Code Descriptions
        f_md = ttk.LabelFrame(self.content, text=t("frm_mcode_desc"))
        f_md.pack(fill="x", padx=10, pady=10)

        tk.Label(f_md, text=t("lbl_mcode_info"),
                 font=("Arial", 8, "italic"), fg="gray").pack(anchor="w", padx=5, pady=(4, 0))

        tv_md = ttk.Treeview(f_md, columns=("code", "description"), show="headings", height=4)
        tv_md.heading("code",        text=t("mc_code_col"));  tv_md.column("code",        width=80,  anchor="center")
        tv_md.heading("description", text=t("mc_desc_col")); tv_md.column("description", width=230)
        tv_md.pack(fill="x", padx=5, pady=(5, 2))

        def refresh_md_tree():
            for item in tv_md.get_children():
                tv_md.delete(item)
            for code, desc in self.app.params.get("mcode_descriptions", {}).items():
                tv_md.insert("", "end", values=(f"M{code}", desc))

        refresh_md_tree()

        f_add_md = ttk.Frame(f_md)
        f_add_md.pack(fill="x", padx=5, pady=2)

        tk.Label(f_add_md, text=t("lbl_mcode_code")).pack(side="left")
        var_mcode = tk.StringVar(value="41")
        e_mcode = ttk.Entry(f_add_md, textvariable=var_mcode, width=6)
        e_mcode.pack(side="left", padx=(2, 6))
        e_mcode.bind("<Button-1>", lambda event: event.widget.focus_force())

        tk.Label(f_add_md, text=t("lbl_mcode_desc")).pack(side="left")
        var_mdesc = tk.StringVar(value="Clamp On")
        e_mdesc = ttk.Entry(f_add_md, textvariable=var_mdesc, width=22)
        e_mdesc.pack(side="left", padx=2, fill="x", expand=True)
        e_mdesc.bind("<Button-1>", lambda event: event.widget.focus_force())

        def add_md():
            try:
                code = var_mcode.get().strip().lstrip("Mm")
                desc = var_mdesc.get().strip()
                if not code.isdigit() or not desc:
                    return
                if "mcode_descriptions" not in self.app.params:
                    self.app.params["mcode_descriptions"] = {}
                self.app.params["mcode_descriptions"][code] = desc
                refresh_md_tree()
            except Exception:
                pass

        def del_md():
            sel = tv_md.selection()
            if not sel:
                return
            code = str(tv_md.item(sel[0])["values"][0]).lstrip("Mm")
            descs = self.app.params.get("mcode_descriptions", {})
            if code in descs:
                del descs[code]
                refresh_md_tree()

        f_btns_md = ttk.Frame(f_md)
        f_btns_md.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Button(f_btns_md, text=t("btn_add"),    command=add_md).pack(side="left", padx=2)
        ttk.Button(f_btns_md, text=t("btn_delete"), command=del_md).pack(side="left", padx=2)
        self.helper.bind_tooltip(f_md,
            "M-code numarasına açıklama tanımla.\n"
            "G-code çıktısında: M41 P1 (Clamp On)\n"
            "M-Code alanına sadece sayı gir (örn: 41), 'M' ön eki opsiyonel.")

        # ── Section gating by machine type ──────────────────────────────────
        # Sections are built unconditionally above; the active adapter decides
        # which ones this machine type actually shows (e.g. ID112 hot machine
        # hides the Siemens-SCL-specific PLC / custom-cmd / M-code sections).
        section_frames = {
            "coords": f_coords, "output_mode": f_output_mode, "offsets": f_offsets,
            "home": f_home, "touch": f_touch, "gcode_out": f_gcode_out,
            "workspace": f_ws, "cylinder": f_cyl, "tilt_arm": f_tilt, "plc": f_plc,
            "custom_cmds": f_cc, "mcode_desc": f_md,
        }
        adapter = getattr(self.app, "active_adapter", None)
        if adapter:
            allowed = set(adapter.get_ui_sections())
            for name, frame in section_frames.items():
                if name not in allowed:
                    frame.pack_forget()

    def _save_machine_profile(self):
        self.sync_params()
        profile = getattr(self.app, "active_machine_profile", None)
        if not profile:
            messagebox.showwarning(t("btn_save_profile"), "No active machine profile.", parent=self.content)
            return
        from machine_loader import MACHINE_PROFILE_KEYS, save_machine_profile
        for k in MACHINE_PROFILE_KEYS:
            if k in self.app.params:
                profile[k] = self.app.params[k]
        path = profile.get("_path", "")
        if not path:
            messagebox.showerror(t("btn_save_profile"), "Profile path not set.", parent=self.content)
            return
        save_machine_profile(path, profile)
        messagebox.showinfo(t("btn_save_profile"), f"Saved:\n{path}", parent=self.content)

    def sync_params(self):
        if hasattr(self, 'txt_header'):
            self.app.params["gcode_header"] = self.txt_header.get("1.0", "end-1c")
        if hasattr(self, 'txt_footer'):
            self.app.params["gcode_footer"] = self.txt_footer.get("1.0", "end-1c")

    def refresh_ui(self):
        for widget in self.content.winfo_children():
            widget.destroy()
        self._create_widgets()
