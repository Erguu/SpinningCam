import tkinter as tk
from tkinter import ttk
from ui.tabs.scrollable_tab_base import ScrollableTabBase


class MachineTab(ScrollableTabBase):
    def __init__(self, parent_frame, app, ui_helper):
        self.app = app
        self.helper = ui_helper

        # Initialize scrollable area from base class
        super().__init__(parent_frame)

        self._create_widgets()

    def _create_widgets(self):
        tk.Label(self.content, text="Machine Settings", font=("Arial", 12, "bold"), pady=10).pack()

        # --- Machine Coordinate System (Post-Processor) ---
        f_coords = ttk.LabelFrame(self.content, text="Machine Coordinate System (Post-Processor)")
        f_coords.pack(fill="x", padx=10, pady=10)

        # Info Label
        tk.Label(f_coords, text="Dönüşüm: X_machine = (X_global - Origin_X) × direction + offset",
                 font=("Arial", 8, "italic"), fg="gray").pack(anchor="w", padx=5)

        # Machine Origin (in Global Coords)
        f_origin = ttk.Frame(f_coords)
        f_origin.pack(fill="x", padx=5, pady=5)
        tk.Label(f_origin, text="Machine Origin (Global Coords):").pack(anchor="w")

        f_origin_inputs = ttk.Frame(f_coords)
        f_origin_inputs.pack(fill="x", padx=5, pady=2)

        # Origin X
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
        self.helper.bind_tooltip(e_origin_x, "CAM global X koordinatlarının makine X=0 noktasına karşılık gelen değeri. "
                                              "Örn: CAM'de rulonun başlangıç X'i 50mm ise ve makine X=0'dan başlıyorsa, Origin X = 50 girilir.")

        # Origin Z
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
        self.helper.bind_tooltip(e_origin_z, "CAM global Z koordinatlarının makine Z=0 noktasına karşılık gelen değeri. "
                                              "Örn: CAM'de home_z = -150 ise ve makine Z=0'a gitmesini istiyorsanız, Origin Z = -150 girilir.")

        tk.Label(f_origin_inputs, text="mm").pack(side="left", padx=2)

        # --- Origin = Safe Home Checkbox ---
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
            text="Origin = Safe Home (Program Start X/Z)",
            variable=var_origin_use_home,
            command=on_origin_use_home_toggle
        )
        cb_use_home.pack(anchor="w", padx=5)
        self.helper.bind_tooltip(
            cb_use_home,
            "Aktifken makine koordinat orijini otomatik olarak 'Program Start' (Home) pozisyonuna eşitlenir. "
            "Fiziksel home = makine (0,0) olan tezgahlarda kullanın. "
            "G-Code koordinatları home'dan itibaren mesafe olarak üretilir. "
            "Aktifken X/Z Origin alanları devre dışı kalır."
        )

        # Apply initial disabled state if checkbox is already on
        if var_origin_use_home.get():
            e_origin_x.config(state="disabled")
            e_origin_z.config(state="disabled")

        # Axis Direction Inversion
        f_invert = ttk.Frame(f_coords)
        f_invert.pack(fill="x", padx=5, pady=5)

        var_invert_x = tk.BooleanVar(value=bool(self.app.params.get("machine_invert_x", False)))
        def on_invert_x_toggle(): self.app.on_param_change("machine_invert_x", var_invert_x.get(), "none")
        cb_invert_x = ttk.Checkbutton(f_invert, text="Invert X Axis (+↔-)", variable=var_invert_x, command=on_invert_x_toggle)
        cb_invert_x.pack(side="left", padx=5)
        self.helper.bind_tooltip(cb_invert_x, "X eksenini tersine çevirir. Makinenin X ekseni merkeze doğru artıyorsa (dışa doğru değil) işaretleyin.")

        var_invert_z = tk.BooleanVar(value=bool(self.app.params.get("machine_invert_z", False)))
        def on_invert_z_toggle(): self.app.on_param_change("machine_invert_z", var_invert_z.get(), "none")
        cb_invert_z = ttk.Checkbutton(f_invert, text="Invert Z Axis (+↔-)", variable=var_invert_z, command=on_invert_z_toggle)
        cb_invert_z.pack(side="left", padx=5)
        self.helper.bind_tooltip(cb_invert_z, "Z eksenini tersine çevirir. Makinenin Z ekseni mandrele doğru artıyorsa (operatörden uzaklaşma değil) işaretleyin.")

        # Roller Approach Side
        f_roller_side = ttk.Frame(f_coords)
        f_roller_side.pack(fill="x", padx=5, pady=(0, 6))

        var_roller_pos_side = tk.BooleanVar(value=bool(self.app.params.get("roller_positive_x_side", True)))
        def on_roller_side_toggle():
            self.app.on_param_change("roller_positive_x_side", var_roller_pos_side.get(), "paths")
        cb_roller_side = ttk.Checkbutton(
            f_roller_side,
            text="Roller Positive X Tarafında (mandrelin üstünde)",
            variable=var_roller_pos_side,
            command=on_roller_side_toggle
        )
        cb_roller_side.pack(anchor="w", padx=5)
        self.helper.bind_tooltip(
            cb_roller_side,
            "İşaretli: Rulon mandrel merkezinden +X yönünde yaklaşır (varsayılan, CAM görünümüyle örtüşür).\n"
            "İşaretsiz: Rulon -X yönünden yaklaşır (mandrel 'alttan' işleme). "
            "Tüm paso koordinatları otomatik olarak yansıtılır."
        )

        # Output Mode (Radius/Diameter)
        f_output_mode = ttk.LabelFrame(self.content, text="Output Mode")
        f_output_mode.pack(fill="x", padx=10, pady=10)

        var_output_mode = tk.StringVar(value=self.app.params.get("output_mode", "diameter"))
        def on_output_mode_change(): self.app.on_param_change("output_mode", var_output_mode.get(), "none")

        rb_dia = ttk.Radiobutton(f_output_mode, text="Diameter", variable=var_output_mode, value="diameter", command=on_output_mode_change)
        rb_dia.pack(anchor="w", padx=5, pady=2)
        self.helper.bind_tooltip(rb_dia, "X değerlerini çap olarak yazar (X × 2). Torna tezgahlarında yaygın olan çap programlama modu.")

        rb_rad = ttk.Radiobutton(f_output_mode, text="Radius", variable=var_output_mode, value="radius", command=on_output_mode_change)
        rb_rad.pack(anchor="w", padx=5, pady=2)
        self.helper.bind_tooltip(rb_rad, "X değerlerini yarıçap olarak yazar. Makine gerçek radyal mesafeyi bekliyorsa bu modu seçin.")

        # Additional Work Offsets (G54)
        f_offsets = ttk.LabelFrame(self.content, text="Additional Work Offsets (G54)")
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

        add_offset_spinbox(f_offsets, "machine_gcode_offset_x", "X Offset (mm)",
                           "Origin dönüşümünden SONRA tüm X koordinatlarına eklenen sabit değer. "
                           "Makine sıfır noktası ince ayarı için kullanılır (G54 iş ofseti gibi).")
        add_offset_spinbox(f_offsets, "machine_gcode_offset_z", "Z Offset (mm)",
                           "Origin dönüşümünden SONRA tüm Z koordinatlarına eklenen sabit değer. "
                           "Makine sıfır noktası ince ayarı için kullanılır (G54 iş ofseti gibi).")

        # Safety & Limits
        f_safety = ttk.LabelFrame(self.content, text="Safety & Limits")
        f_safety.pack(fill="x", padx=10, pady=10)

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

        add_int_entry(f_safety, "max_spin_rpm", "Max Spin (RPM):",
                      "G-code'a yazılacak maksimum mil devri sınırı (G50 S[değer]). "
                      "Makine bu değerin üzerinde çalışmaz. Tipik: 1500-3000 RPM.")

        # --- Safety Settings ---
        f_home = ttk.LabelFrame(self.content, text="Program Start / Retract")
        f_home.pack(fill="x", padx=10, pady=5)

        tk.Label(f_home, text="Gerçek homing PLC tarafından yapılır. Bu konum programın başladığı ve paslar arası döndüğü noktadır.",
                 font=("Arial", 8, "italic"), fg="gray", wraplength=380, justify="left").pack(anchor="w", padx=5, pady=(2, 4))

        def add_home_spinbox(p, key, title, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=5, pady=2)
            tk.Label(f, text=title).pack(side="left")
            # Default fallback
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
            # Bind Tooltip
            self.helper.bind_tooltip(e, tooltip)
            self.helper.bind_tooltip(f, tooltip)

        add_home_spinbox(f_home, "home_z", "Program Start Z:",
                         "Programın başladığı ve her pas sonrası geri dönülen Z pozisyonu (CAM koordinatı, mutlak). "
                         "PLC homing'den sonra takımın beklediği Z konumu olmalı. "
                         "Ruloyu mandrel geometrisinden tamamen uzaklaştıracak bir değer girilmeli.")
        add_home_spinbox(f_home, "home_x", "Program Start X:",
                         "Programın başladığı ve her pas sonrası geri dönülen X pozisyonu (CAM koordinatı, mutlak). "
                         "PLC homing'den sonra takımın beklediği X konumu olmalı. "
                         "Ruloyu merkez ekseninden yeterince uzaklaştıracak bir değer girilmeli.")
        add_home_spinbox(f_home, "retract_x", "Pass Retract X (Rel):",
                         "Her pas sonrası rulonun X ekseninde geri çekilme miktarı (göreceli, mm). "
                         "Pozitif değer rulоyu dışarı (merkez ekseninden uzağa) taşır.")
        add_home_spinbox(f_home, "retract_z", "Pass Retract Z (Rel):",
                         "Her pas sonrası rulonun Z ekseninde geri çekilme miktarı (göreceli, mm). "
                         "Pozitif değer rulоyu operatör tarafına (mandrel yüzeyinden uzağa) taşır.")

        # Helper to create label+text area
        def add_text_area(p, title, key, height=4, tooltip=""):
            f = ttk.Frame(p)
            f.pack(fill="x", padx=10, pady=5)
            lbl = tk.Label(f, text=title, font=("Arial", 9, "bold"), anchor="w")
            lbl.pack(fill="x")

            txt = tk.Text(f, height=height, font=("Consolas", 9))
            txt.pack(fill="x")
            # Load initial value
            val = self.app.params.get(key, "")
            txt.insert("1.0", val)
            self.helper.bind_tooltip(txt, tooltip)
            self.helper.bind_tooltip(lbl, tooltip)

            return txt

        self.txt_header = add_text_area(self.content, "G-Code Header", "gcode_header", height=6,
                                        tooltip="Her G-code dosyasının BAŞINA eklenen satırlar. "
                                                "Genellikle birim (G21=mm), düzlem (G18=XZ), mutlak mod (G90) ve iş ofseti (G54) komutları. "
                                                "Örn: G21 G90 G18 / G54")
        self.txt_footer = add_text_area(self.content, "G-Code Footer", "gcode_footer", height=4,
                                        tooltip="Her G-code dosyasının SONUNA eklenen satırlar. "
                                                "Genellikle mil durdurma (M5) ve program sonu (M30) komutları. "
                                                "Örn: M5 / M30")

        # --- Working Area (Workspace) ---
        f_ws = ttk.LabelFrame(self.content, text="Working Area (Workspace)")
        f_ws.pack(fill="x", padx=10, pady=10)

        tk.Label(f_ws, text="Makinenin fiziksel hareket sınırları (CAM koordinatları)",
                 font=("Arial", 8, "italic"), fg="gray").pack(anchor="w", padx=5)

        var_ws_show = tk.BooleanVar(value=bool(self.app.params.get("workspace_show", True)))
        def on_ws_show_toggle():
            self.app.on_param_change("workspace_show", var_ws_show.get(), "all")
        cb_ws = ttk.Checkbutton(f_ws, text="3D Sahnede Göster", variable=var_ws_show, command=on_ws_show_toggle)
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

        add_ws_entry(f_ws, "workspace_x_min", "Min X / Radius (mm):", default=0.0,
                     tooltip="Çalışma alanının X başlangıç noktası (mm). "
                             "Genellikle 0 (mandrel merkezi) veya rulonun en yakın konumu. "
                             "-X tarafı seçiliyse otomatik olarak yansıtılır.")
        add_ws_entry(f_ws, "workspace_x_max", "Max X / Radius (mm):", default=300.0,
                     tooltip="Makinenin X ekseninde ulaşabileceği maksimum yarıçap mesafesi (mm). "
                             "3D sahnede çalışma alanı kutusunun X sınırını belirler.")
        add_ws_entry(f_ws, "workspace_z_min", "Min Z (mm):", default=0.0,
                     tooltip="Makinenin Z ekseninde ulaşabileceği minimum pozisyon (mm, CAM koordinatları). "
                             "Negatif değer girilirse mandrel gerisine uzanabilir.")
        add_ws_entry(f_ws, "workspace_z_max", "Max Z (mm):", default=500.0,
                     tooltip="Makinenin Z ekseninde ulaşabileceği maksimum pozisyon (mm, CAM koordinatları). "
                             "Rulonun gittiği en ileri Z noktasından büyük olmalı.")

        # --- Cylinder Section ---
        f_cyl = ttk.LabelFrame(self.content, text="Cylinder (CMD=40)")
        f_cyl.pack(fill="x", padx=10, pady=10)

        tk.Label(f_cyl, text="Silindir eksen servoların yanında, mandrel ile paralel.\n"
                              "Program başında, mil çalışmadan önce konuma gider. (M40 P<mm>)",
                 font=("Arial", 8, "italic"), fg="gray", justify="left").pack(anchor="w", padx=5, pady=(2, 4))

        var_cyl_enabled = tk.BooleanVar(value=bool(self.app.params.get("cylinder_enabled", True)))
        def on_cyl_enabled_toggle():
            self.app.on_param_change("cylinder_enabled", var_cyl_enabled.get(), "none")
        cb_cyl_enabled = ttk.Checkbutton(f_cyl, text="Enable (G-code'a M40 yaz)", variable=var_cyl_enabled, command=on_cyl_enabled_toggle)
        cb_cyl_enabled.pack(anchor="w", padx=5, pady=(0, 2))
        self.helper.bind_tooltip(cb_cyl_enabled, "İşaretliyken program başında M40 P<mm> komutu G-code'a yazılır. "
                                                  "İşaretsizken silindir komutu tamamen atlanır.")

        var_cyl_show = tk.BooleanVar(value=bool(self.app.params.get("cylinder_show", True)))
        def on_cyl_show_toggle():
            self.app.on_param_change("cylinder_show", var_cyl_show.get(), "all")
        cb_cyl_show = ttk.Checkbutton(f_cyl, text="3D Sahnede Göster", variable=var_cyl_show, command=on_cyl_show_toggle)
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

        add_cyl_entry(f_cyl, "cylinder_position_mm", "Position (mm):", 0.0,
            "Silindirin hedef konumu (mm). PLC'ye Param = round(mm / 10) olarak gönderilir. "
            "0 = hareket yok (G-code'a yazılmaz). 3D sahnede T-şekli olarak görselleştirilir.")
        add_cyl_entry(f_cyl, "cylinder_x_pos", "X Position (mm):", 0.0,
            "Silindirin 3D sahnedeki X koordinatı (radyal konum, mm). "
            "Mandrel merkezinden ne kadar uzakta olduğunu belirler.")
        add_cyl_entry(f_cyl, "cylinder_z_base", "Z Base (mm):", 200.0,
            "Silindirin monte edildiği Z konumu (mm) — gövdenin bağlı olduğu uç. "
            "Silindir buradan mandrel/rulo yönüne doğru (daha küçük Z'ye) uzar.")

        # --- PLC Output Mode ---
        f_plc = ttk.LabelFrame(self.content, text="PLC Output Mode")
        f_plc.pack(fill="x", padx=10, pady=10)

        tk.Label(
            f_plc,
            text=(
                "PLC modunda G-code her pas için çok daha az nokta içerir.\n"
                "Nokta-nokta hareket eden PLC kontrolörler için idealdir.\n"
                "Mandrel'e en yakın kritik temas noktası her zaman korunur.\n"
                "CNC kontrol için normal G-code üretimini etkilemez."
            ),
            font=("Arial", 8, "italic"), fg="gray",
            wraplength=380, justify="left"
        ).pack(anchor="w", padx=5, pady=(4, 6))

        # Enable checkbox
        f_plc_en = ttk.Frame(f_plc)
        f_plc_en.pack(fill="x", padx=5, pady=2)
        var_plc = tk.BooleanVar(value=bool(self.app.params.get("plc_mode", False)))

        def on_plc_toggle():
            self.app.on_param_change("plc_mode", var_plc.get(), "none")
            # Enable/disable tolerance entry
            state = "normal" if var_plc.get() else "disabled"
            e_tol.config(state=state)

        cb_plc = ttk.Checkbutton(
            f_plc_en,
            text="Enable PLC Mode (Low-Poly G-Code Output)",
            variable=var_plc,
            command=on_plc_toggle
        )
        cb_plc.pack(anchor="w")
        self.helper.bind_tooltip(
            cb_plc,
            "Etkinleştirildiğinde G-code her pas için Ramer-Douglas-Peucker algoritması "
            "ile sadeleştirilmiş nokta listesi üretir.\n"
            "Tüm pasların mandrel'e en yakın noktası (en kritik temas yeri) korunur.\n"
            "CNC çıktısı (normal G-code kaydetme) bundan etkilenmez — bu sadece "
            "PLC için 'Save G-Code' çıktısında aktif olur."
        )

        # Tolerance entry
        f_tol = ttk.Frame(f_plc)
        f_tol.pack(fill="x", padx=5, pady=2)
        tk.Label(f_tol, text="Tolerance (mm)", width=18).pack(side="left")

        var_tol = tk.DoubleVar(value=float(self.app.params.get("plc_tolerance", 0.5)))

        def on_tol_change():
            try:
                self.app.on_param_change("plc_tolerance", var_tol.get(), "none")
            except Exception:
                pass

        tol_state = "normal" if var_plc.get() else "disabled"
        e_tol = ttk.Entry(f_tol, textvariable=var_tol, width=10, state=tol_state)
        e_tol.pack(side="right")
        e_tol.bind("<Return>", lambda ev: on_tol_change())
        e_tol.bind("<FocusOut>", lambda ev: on_tol_change())
        e_tol.bind("<Button-1>", lambda event: event.widget.focus_force())
        self.helper.bind_tooltip(
            e_tol,
            "RDP basitleştirme toleransı (mm). Orijinal yoldan bu mesafeden daha az "
            "sapan aradaki noktalar kaldırılır.\n"
            "Küçük değer (ör. 0.2 mm) = daha fazla nokta, daha yüksek doğruluk.\n"
            "Büyük değer (ör. 2.0 mm) = çok daha az nokta, PLC belleği daha az kullanır.\n"
            "Tipik öneri: 0.3 – 1.0 mm."
        )
        self.helper.bind_tooltip(f_tol, "RDP toleransı: PLC nokta sayısını ve profil doğruluğunu dengeler.")

        # Info label that shows estimated point reduction live (static hint)
        tk.Label(
            f_plc,
            text="💡 Yol hesaplandıktan sonra G-code kaydet → log'da nokta azaltma oranı görünür.",
            font=("Arial", 8), fg="#555555"
        ).pack(anchor="w", padx=5, pady=(2, 6))

        # --- Custom Commands ---
        f_cc = ttk.LabelFrame(self.content, text="Custom Commands")
        f_cc.pack(fill="x", padx=10, pady=10)

        tv_cc = ttk.Treeview(f_cc, columns=("trigger", "value", "cmd"), show="headings", height=4)
        tv_cc.heading("trigger", text="Trigger");  tv_cc.column("trigger", width=70,  anchor="center")
        tv_cc.heading("value",   text="Value");    tv_cc.column("value",   width=60,  anchor="center")
        tv_cc.heading("cmd",     text="Command");  tv_cc.column("cmd",     width=180)
        tv_cc.pack(fill="x", padx=5, pady=(5, 2))

        def refresh_cc_tree():
            for item in tv_cc.get_children():
                tv_cc.delete(item)
            for entry in self.app.params.get("custom_commands", []):
                t = "Pass" if entry.get("trigger") == "pass" else "Z"
                tv_cc.insert("", "end", values=(t, entry.get("value", ""), entry.get("cmd", "")))

        refresh_cc_tree()

        # Add form row
        f_add = ttk.Frame(f_cc)
        f_add.pack(fill="x", padx=5, pady=2)

        tk.Label(f_add, text="Trigger:").pack(side="left")
        var_trig = tk.StringVar(value="pass")
        cb_trig = ttk.Combobox(f_add, textvariable=var_trig, values=["pass", "z"], width=5, state="readonly")
        cb_trig.pack(side="left", padx=(2, 6))

        tk.Label(f_add, text="Value:").pack(side="left")
        var_val = tk.StringVar(value="1")
        e_val = ttk.Entry(f_add, textvariable=var_val, width=7)
        e_val.pack(side="left", padx=(2, 6))
        e_val.bind("<Button-1>", lambda event: event.widget.focus_force())

        tk.Label(f_add, text="Cmd:").pack(side="left")
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
        ttk.Button(f_btns, text="Add",    command=add_cc).pack(side="left", padx=2)
        ttk.Button(f_btns, text="Delete", command=del_cc).pack(side="left", padx=2)
        self.helper.bind_tooltip(f_cc,
            "Trigger=pass → o global pas numarasının başında komutu ekler (1-indexed).\n"
            "Trigger=z → paso içinde Z o eşiği geçtiği anda komutu ekler.\n"
            "Örn: trigger=pass, value=1, cmd=M41 P1")

        # --- M-Code Descriptions ---
        f_md = ttk.LabelFrame(self.content, text="M-Code Descriptions")
        f_md.pack(fill="x", padx=10, pady=10)

        tk.Label(f_md,
                 text="Tanımlanan M-code'lar G-code ve SCL çıktısında otomatik yorum olarak eklenir.",
                 font=("Arial", 8, "italic"), fg="gray").pack(anchor="w", padx=5, pady=(4, 0))

        tv_md = ttk.Treeview(f_md, columns=("code", "description"), show="headings", height=4)
        tv_md.heading("code",        text="M-Code");      tv_md.column("code",        width=80,  anchor="center")
        tv_md.heading("description", text="Description"); tv_md.column("description", width=230)
        tv_md.pack(fill="x", padx=5, pady=(5, 2))

        def refresh_md_tree():
            for item in tv_md.get_children():
                tv_md.delete(item)
            for code, desc in self.app.params.get("mcode_descriptions", {}).items():
                tv_md.insert("", "end", values=(f"M{code}", desc))

        refresh_md_tree()

        f_add_md = ttk.Frame(f_md)
        f_add_md.pack(fill="x", padx=5, pady=2)

        tk.Label(f_add_md, text="M-Code:").pack(side="left")
        var_mcode = tk.StringVar(value="41")
        e_mcode = ttk.Entry(f_add_md, textvariable=var_mcode, width=6)
        e_mcode.pack(side="left", padx=(2, 6))
        e_mcode.bind("<Button-1>", lambda event: event.widget.focus_force())

        tk.Label(f_add_md, text="Description:").pack(side="left")
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
        ttk.Button(f_btns_md, text="Add",    command=add_md).pack(side="left", padx=2)
        ttk.Button(f_btns_md, text="Delete", command=del_md).pack(side="left", padx=2)
        self.helper.bind_tooltip(f_md,
            "M-code numarasına açıklama tanımla.\n"
            "G-code çıktısında: M41 P1 (Clamp On)\n"
            "SCL çıktısında:  // M41 (Clamp On) P1\n"
            "M-Code alanına sadece sayı gir (örn: 41), 'M' ön eki opsiyonel.")

    def sync_params(self):
        # Manually sync text widgets to params
        if hasattr(self, 'txt_header'):
            self.app.params["gcode_header"] = self.txt_header.get("1.0", "end-1c")
        if hasattr(self, 'txt_footer'):
            self.app.params["gcode_footer"] = self.txt_footer.get("1.0", "end-1c")


    def refresh_ui(self):
        # Refresh all widgets from app.params
        # NOTE: Since we didn't store widget references in a dict, we have to rely on the closures? NO.
        # The closures use 'var' which is local.
        # Actually, standard Tkinter Vars (BooleanVar, etc) are objects.
        # If we stored them, we could update them.
        # But we didn't store most of them in 'self'.
        # Solution: Re-create widgets? Too heavy.
        # Better: UIHelper should store references or we should have stored them.
        # Given current structure, simplest way is to destroy and recreate the content.
        for widget in self.content.winfo_children():
            widget.destroy()
        self._create_widgets()
        # This is fast enough for Tabs.
