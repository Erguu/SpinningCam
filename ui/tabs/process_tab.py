import tkinter as tk
from tkinter import ttk
from ui.tabs.scrollable_tab_base import ScrollableTabBase
from i18n import t
import pass_colors


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

    def _add_pass_colors(self):
        """Pass colour palette — one editable colour per operation category.

        VISUAL ONLY. Changing a colour redraws from the CACHED toolpaths
        (``redraw_paths_cached``) so nothing is recalculated and no path, feed
        or exported file can be affected by a colour.

        The swatch is a tk.Button rather than a ttk one on purpose: ttk widgets
        take their background from the theme and ignore ``bg=``, which would
        leave every swatch looking identical.
        """
        self.helper.add_section_header(self.content, t("section_pass_colors"),
                                       color="darkgreen")
        frame = ttk.Frame(self.content)
        frame.pack(fill="x", padx=10, pady=2)

        def make_row(category):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=t(f"col_cat_{category}"), width=18).pack(side="left")
            swatch = tk.Button(row, width=6, relief="ridge", bd=1,
                               bg=pass_colors.resolve_palette(self.app.params)[category])

            def pick():
                from tkinter import colorchooser
                current = pass_colors.resolve_palette(self.app.params)[category]
                chosen = colorchooser.askcolor(
                    color=current, parent=self.content.winfo_toplevel(),
                    title=t("col_pick_title"))[1]
                if not chosen:
                    return                      # Cancel must change nothing.
                stored = dict(self.app.params.get("pass_colors") or {})
                stored[category] = chosen
                self.app.params["pass_colors"] = stored
                swatch.configure(bg=chosen)
                self._apply_pass_colors()

            swatch.configure(command=pick)
            swatch.pack(side="left", padx=4)
            self._color_swatches[category] = swatch

        self._color_swatches = {}
        for category in pass_colors.CATEGORIES:
            make_row(category)

        f_reset = ttk.Frame(frame)
        f_reset.pack(fill="x", pady=(4, 0))
        ttk.Button(f_reset, text=t("btn_colors_reset"),
                   command=self._reset_pass_colors).pack(side="left")
        self.helper.bind_tooltip(
            frame,
            "Pas renkleri — SADECE GÖRSEL. Yol hesabını, G-code'u veya reçeteyi\n"
            "etkilemez.\n\n"
            "TERS pas kendi rengini alır ve operasyon tipini EZER: 3B görünümde\n"
            "ilk bakışta görmek istediğin şey odur.\n\n"
            "Renkler operasyon listesinde satır arka planı olarak da görünür.\n"
            "Düzenlenen pas her zaman macenta kalır (seçim göstergesi).")

    def _apply_pass_colors(self):
        """Push a palette change to both views that use it."""
        self.app.redraw_paths_cached()          # 3D, from cache — no recalculation
        try:
            self.root.ui_program.refresh_ops_tree()   # operation list tints
        except Exception:
            pass                                 # tab not built yet (startup)

    def _reset_pass_colors(self):
        self.app.params["pass_colors"] = {}
        defaults = pass_colors.resolve_palette(self.app.params)
        for category, swatch in getattr(self, "_color_swatches", {}).items():
            swatch.configure(bg=defaults[category])
        self._apply_pass_colors()

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

        # Bent-sheet (deformed-blank) overlay toggle. Purely visual — the faded-blue
        # revolved surface (#63) that shows how the SELECTED pass bends the blank.
        # Rebuilding it is the single biggest per-click cost when selecting ops, so
        # turning it OFF makes op selection noticeably snappier on large programs.
        # Wired to a light redraw (update_deformed_blank) instead of a full scene
        # rebuild, so the toggle itself is instant and never recomputes toolpaths.
        f_db = ttk.Frame(self.content)
        f_db.pack(fill="x", padx=10, pady=2)
        self._db_var = tk.BooleanVar(value=bool(self.app.params.get("show_deformed_blank", True)))
        def _toggle_deformed_blank():
            self.app.params["show_deformed_blank"] = self._db_var.get()
            try:
                self.app.update_deformed_blank(render=True)
            except Exception:
                pass
            self.app.save_settings_json()
        cb_db = ttk.Checkbutton(f_db, text=t("cb_show_deformed_blank"),
                                variable=self._db_var, command=_toggle_deformed_blank)
        cb_db.pack(anchor="w")
        self.helper.bind_tooltip(cb_db,
            "Seçili pasın sacı nasıl büktüğünü gösteren soluk mavi kaplamayı aç/kapat. "
            "SADECE görsel — takım yolunu veya G-code'u etkilemez. Kapatmak, çok operasyonlu "
            "programlarda operasyon seçimini belirgin şekilde hızlandırır (her tıklamada bu "
            "yüzey yeniden hesaplanır).")
        # Predicted blank-edge rings: one ring per forming pass at the estimated
        # unformed-sheet edge. Separate layer from the bent-sheet overlay above —
        # it shows ALL passes at once, so it does not change while stepping passes.
        self._be_var = tk.BooleanVar(value=bool(self.app.params.get("show_blank_edge", True)))
        def _toggle_blank_edge():
            self.app.params["show_blank_edge"] = self._be_var.get()
            try:
                self.app.update_blank_edge(render=True)
            except Exception:
                pass
            self.app.save_settings_json()
        cb_be = ttk.Checkbutton(f_db, text=t("cb_show_blank_edge"),
                                variable=self._be_var, command=_toggle_blank_edge)
        cb_be.pack(anchor="w")
        self.helper.bind_tooltip(cb_be,
            "Her şekillendirme pasosu için sacın işlenmemiş KENARININ nerede olduğu "
            "TAHMİNİNİ halka olarak gösterir. SADECE görsel — takım yolunu veya G-code'u "
            "etkilemez. TAHMİNDİR: model sabit kalınlık ve düz flanş varsayar, bu yüzden "
            "kenarın geri çekilme BİÇİMİ doğrudur, kesin yarıçap değil.")

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
                                 "hesaplamalarını veya G-code'u ETKİLEMEZ.", mode="rulers")
        self.helper.add_spinbox(self.content, self.app, "ruler_x_at_z", t("sp_ruler_x_at_z"), -500, 1000, 5,
                                "Yatay X cetvelinin oturacağı Z seviyesi (mm). Cetveli ilgilendiğin "
                                "Z konumuna taşımak için değiştir.", mode="rulers")
        self.helper.add_spinbox(self.content, self.app, "ruler_x_start", t("sp_ruler_x_start"), -500, 1000, 5,
                                "X cetvelinin BAŞLANGIÇ noktası (mm) — cetvelin sıfır işareti burada durur. "
                                "Etiketler bu noktadan itibaren mesafeyi gösterir. Başlangıç→Bitiş yönü "
                                "cetvelin yönünü belirler.", mode="rulers")
        self.helper.add_spinbox(self.content, self.app, "ruler_x_end", t("sp_ruler_x_end"), -500, 1000, 5,
                                "X cetvelinin BİTİŞ noktası (mm). Bitiş < Başlangıç ise cetvel -X yönünde "
                                "ilerler. Bitiş'i Başlangıç'a EŞİT bırakırsan uzunluk sahneye göre otomatik "
                                "ayarlanır (Başlangıç=0 iken etiketler gerçek makine X değerini okur).", mode="rulers")
        self.helper.add_spinbox(self.content, self.app, "ruler_z_at_x", t("sp_ruler_z_at_x"), -500, 1000, 5,
                                "Dikey Z cetvelinin oturacağı X seviyesi (mm). Cetveli ilgilendiğin "
                                "X konumuna taşımak için değiştir.", mode="rulers")
        self.helper.add_spinbox(self.content, self.app, "ruler_z_start", t("sp_ruler_z_start"), -500, 1000, 5,
                                "Z cetvelinin BAŞLANGIÇ noktası (mm) — cetvelin sıfır işareti burada durur. "
                                "Etiketler bu noktadan itibaren mesafeyi gösterir. Başlangıç→Bitiş yönü "
                                "cetvelin yönünü belirler.", mode="rulers")
        self.helper.add_spinbox(self.content, self.app, "ruler_z_end", t("sp_ruler_z_end"), -500, 1000, 5,
                                "Z cetvelinin BİTİŞ noktası (mm). Bitiş < Başlangıç ise cetvel -Z yönünde "
                                "ilerler. Bitiş'i Başlangıç'a EŞİT bırakırsan uzunluk sahneye göre otomatik "
                                "ayarlanır (Başlangıç=0 iken etiketler gerçek makine Z değerini okur).", mode="rulers")

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
            "(Radyal yaklaşım; eğik yüzeylerde temas noktası normal boyunca hafifçe kayabilir.)\n"
            "Turuncu hızlı hareket çizgileri ve Nokta üçgenleri de birlikte kayar.")

        f_rapids = ttk.Frame(self.content)
        f_rapids.pack(fill="x", padx=10, pady=2)
        var_rapids = tk.BooleanVar(value=bool(self.app.params.get("show_rapids", True)))
        def on_rapids_toggle():
            # Visual-only, same as the tip-paths toggle above: store the flag and
            # redraw from the CACHED paths so nothing is recalculated.
            self.app.params["show_rapids"] = var_rapids.get()
            self.app.save_settings_json()
            self.app.redraw_paths_cached()
        cb_rapids = ttk.Checkbutton(self.content, text=t("cb_show_rapids"),
                                    variable=var_rapids, command=on_rapids_toggle)
        cb_rapids.pack(anchor="w", padx=10)
        self.helper.bind_tooltip(cb_rapids,
            "Turuncu kesikli G0 (hızlı) hareket çizgilerini göster/gizle.\n"
            "Kapatınca yalnızca kesme pasoları kalır — çok pasolu programlarda\n"
            "yolları okumak kolaylaşır. Rulonun ilk pasoya gidiş çizgisi de\n"
            "bu ayara uyar.\n"
            "TAMAMEN GÖRSELDİR: hareketler silinmez, G-code ve reçete AYNEN kalır.")

        self._add_pass_colors()

        # ---------------- Back-support cylinder (3D view only) ----------------
        # Moved here from the Machine tab (2026-07-30): these three fields only
        # affect how the cylinder is DRAWN. Its actual command (M40) is now an
        # ordinary program_start entry in Machine ▸ Custom Commands, and the
        # extension drawn below is read straight from that command — the picture
        # cannot disagree with the program.
        self.helper.add_section_header(self.content, t("section_cylinder"), color="darkgreen")

        tk.Label(self.content, text=t("lbl_cyl_visual_info"),
                 font=("Arial", 8, "italic"), fg="gray", justify="left",
                 wraplength=300).pack(anchor="w", padx=10, pady=(0, 4))

        var_cyl_show = tk.BooleanVar(value=bool(self.app.params.get("cylinder_show", True)))
        def on_cyl_show_toggle():
            self.app.on_param_change("cylinder_show", var_cyl_show.get(), "all")
        cb_cyl_show = ttk.Checkbutton(self.content, text=t("cb_show_in_3d"),
                                      variable=var_cyl_show, command=on_cyl_show_toggle)
        cb_cyl_show.pack(anchor="w", padx=10)
        self.helper.bind_tooltip(cb_cyl_show,
            "Silindiri 3D sahnede göster/gizle. G-code/PLC çıktısını ETKİLEMEZ.")

        def add_cyl_entry(param_key, label, default, tooltip):
            f = ttk.Frame(self.content)
            f.pack(fill="x", padx=10, pady=3)
            tk.Label(f, text=label, width=18, anchor="w").pack(side="left")
            var = tk.DoubleVar(value=self.app.params.get(param_key, default))
            def on_change(v=var, k=param_key):
                try: self.app.on_param_change(k, v.get(), "all")
                except Exception: pass
            e = ttk.Entry(f, textvariable=var, width=10)
            e.pack(side="left", padx=4)
            e.bind("<Return>",   lambda ev, fn=on_change: fn())
            e.bind("<FocusOut>", lambda ev, fn=on_change: fn())
            e.bind("<Button-1>", lambda event: event.widget.focus_force())
            self.helper.bind_tooltip(e, tooltip)
            return var

        add_cyl_entry("cylinder_x_pos", t("lbl_cyl_x"), 0.0,
            "Silindirin 3D sahnedeki X koordinatı (radyal konum, mm). Sadece görsel.")
        add_cyl_entry("cylinder_z_base", t("lbl_cyl_z"), 200.0,
            "Silindirin monte edildiği Z konumu (mm). Sadece görsel.")

        # ---------------- Camera Controls ----------------
        # All camera buttons drive the CANONICAL orbit params
        # (cam_azimuth / cam_elevation / cam_roll / cam_distance) through
        # on_param_change(..., "camera"). The live camera object is rebuilt from
        # those params on every full scene redraw (main.py ~1320), so poking the
        # camera directly would just snap back — going through the params makes
        # every view PERSIST. Purely visual: never touches toolpaths / G-code / sim.
        app = self.app

        def cam_get(key, default):
            return float(app.params.get(key, default))

        def cam_apply(**vals):
            """Write one or more camera params, then trigger a single camera-only
            scene update (the last key carries the render)."""
            keys = list(vals.keys())
            for k in keys[:-1]:
                app.params[k] = vals[k]
            app.on_param_change(keys[-1], vals[keys[-1]], "camera")

        def _wrap180(v):
            return ((v + 180.0) % 360.0) - 180.0

        def nudge_az(delta):
            cam_apply(cam_azimuth=_wrap180(cam_get("cam_azimuth", 0.0) + delta))

        def nudge_el(delta):
            # Wrap like azimuth/roll so vertical tilt rotates CONTINUOUSLY in both
            # directions (over the top and back), instead of stopping at ±90°.
            # The reconstruction (main.py) stays orthonormal for any elevation, so
            # tumbling past the pole just flips the view upside-down like a trackball.
            cam_apply(cam_elevation=_wrap180(cam_get("cam_elevation", 0.0) + delta))

        def nudge_roll(delta):
            cam_apply(cam_roll=_wrap180(cam_get("cam_roll", 90.0) + delta))

        def zoom_cam(factor):
            v = max(50.0, min(20000.0, cam_get("cam_distance", 800.0) * factor))
            cam_apply(cam_distance=v)

        # --- Preset views (azimuth, elevation, roll) ---
        def set_view(direction):
            views = {
                "front": (0.0, 0.0, 90.0),
                "back":  (180.0, 0.0, 90.0),
                "left":  (-90.0, 0.0, 90.0),
                "right": (90.0, 0.0, 90.0),
                "top":   (0.0, 90.0, 90.0),
                "iso":   (45.0, 30.0, 90.0),
            }
            v = views.get(direction)
            if v:
                cam_apply(cam_elevation=v[1], cam_roll=v[2], cam_azimuth=v[0])

        ttk.Label(self.content, text=t("lbl_cam_presets"), font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(6,2))
        f_presets = ttk.Frame(self.content)
        f_presets.pack(fill="x", padx=10, pady=2)

        btn_front = tk.Button(f_presets, text=t("btn_front"), command=lambda: set_view("front"), width=6)
        btn_front.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_front, "Önden görünüm (Yatay=0°, Dikey=0°).")

        btn_back = tk.Button(f_presets, text=t("btn_back_view"), command=lambda: set_view("back"), width=6)
        btn_back.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_back, "Arkadan görünüm (Yatay=180°).")

        btn_left = tk.Button(f_presets, text=t("btn_left"), command=lambda: set_view("left"), width=6)
        btn_left.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_left, "Sol görünüm (Yatay=-90°).")

        btn_right = tk.Button(f_presets, text=t("btn_right"), command=lambda: set_view("right"), width=6)
        btn_right.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_right, "Sağ görünüm (Yatay=+90°).")

        btn_top = tk.Button(f_presets, text=t("btn_top"), command=lambda: set_view("top"), width=6)
        btn_top.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_top, "Üstten görünüm (Dikey=89°).")

        btn_iso = tk.Button(f_presets, text=t("btn_iso"), command=lambda: set_view("iso"), width=6, bg="lightblue")
        btn_iso.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_iso, "İzometrik görünüm (Yatay=45°, Dikey=30°).")

        # --- Rotation / zoom (full orbit control) ---
        ttk.Label(self.content, text=t("lbl_rotate_view"), font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(6,2))

        # HORIZONTAL screen rotation (◀ ▶). The default roll (90°) lays the part
        # sideways, so it is ELEVATION — not azimuth — that moves the view left/
        # right on screen (measured: az moves the scene vertically, el moves it
        # horizontally). So this row drives cam_elevation, with signs chosen so the
        # scene follows the arrow (like a mouse drag): ▶ = scene right = -el.
        f_h = ttk.Frame(self.content); f_h.pack(fill="x", padx=10, pady=1)
        ttk.Label(f_h, text=t("lbl_cam_azimuth"), width=8, anchor="w").pack(side="left")
        for txt, dv, tip in (("◀◀ 15", 15, "Görünümü sola döndür (15°)"),
                             ("◀ 5", 5, "Görünümü sola döndür (5°, ince)"),
                             ("5 ▶", -5, "Görünümü sağa döndür (5°, ince)"),
                             ("15 ▶▶", -15, "Görünümü sağa döndür (15°)")):
            b = tk.Button(f_h, text=txt, width=6, command=lambda d=dv: nudge_el(d))
            b.pack(side="left", padx=1); self.helper.bind_tooltip(b, tip)

        # VERTICAL screen rotation (▲ ▼) → drives cam_azimuth (see note above).
        # Scene follows the arrow: ▲ = scene up = -az.
        f_v = ttk.Frame(self.content); f_v.pack(fill="x", padx=10, pady=1)
        ttk.Label(f_v, text=t("lbl_cam_elevation"), width=8, anchor="w").pack(side="left")
        for txt, dv, tip in (("▲▲ 15", -15, "Görünümü yukarı döndür (15°)"),
                             ("▲ 5", -5, "Görünümü yukarı döndür (5°, ince)"),
                             ("▼ 5", 5, "Görünümü aşağı döndür (5°, ince)"),
                             ("▼▼ 15", 15, "Görünümü aşağı döndür (15°)")):
            b = tk.Button(f_v, text=txt, width=6, command=lambda d=dv: nudge_az(d))
            b.pack(side="left", padx=1); self.helper.bind_tooltip(b, tip)

        # Roll + Zoom + Fix
        f_rz = ttk.Frame(self.content); f_rz.pack(fill="x", padx=10, pady=1)
        ttk.Label(f_rz, text=t("lbl_cam_roll_zoom"), width=8, anchor="w").pack(side="left")
        b = tk.Button(f_rz, text="⟲", width=3, command=lambda: nudge_roll(-15))
        b.pack(side="left", padx=1); self.helper.bind_tooltip(b, "Ekseni saat yönü tersine 15° döndür (ufuk çizgisini eğ).")
        b = tk.Button(f_rz, text="⟳", width=3, command=lambda: nudge_roll(15))
        b.pack(side="left", padx=1); self.helper.bind_tooltip(b, "Ekseni saat yönünde 15° döndür (ufuk çizgisini eğ).")
        b = tk.Button(f_rz, text="🔍＋", width=4, command=lambda: zoom_cam(0.85))
        b.pack(side="left", padx=(8,1)); self.helper.bind_tooltip(b, "Yakınlaştır (kamera mesafesini azalt).")
        b = tk.Button(f_rz, text="🔍－", width=4, command=lambda: zoom_cam(1.0/0.85))
        b.pack(side="left", padx=1); self.helper.bind_tooltip(b, "Uzaklaştır (kamera mesafesini artır).")

        def fix_clipping():
            if hasattr(self.app, 'plotter'):
                self.app.plotter.reset_camera()
                self.app.plotter.camera.clipping_range = (0.1, 500000)
                self.app.plotter.render()

        btn_fix = tk.Button(f_rz, text=t("btn_fix_view"), command=fix_clipping, width=10, bg="yellow")
        btn_fix.pack(side="right", padx=2)
        self.helper.bind_tooltip(btn_fix, "Geometri görünmez hale gelirse veya kırpılıyorsa buna bas. "
                                          "Kamera clipping aralığını sıfırlayarak tüm objeleri tekrar görünür yapar.")

        # --- Saved (named) custom views ---
        def reset_cam():
            cam_apply(cam_elevation=0.0, cam_roll=90.0, cam_distance=800.0, cam_azimuth=0.0)

        self.helper.add_button(self.content, t("btn_reset_cam"), reset_cam, "lightgray",
                               "Kamerayı varsayılan görünüme (Yatay=0, Dikey=0, mesafe=800) döndür.")

        ttk.Label(self.content, text=t("lbl_saved_views"), font=("Arial", 9, "bold")).pack(anchor="w", padx=10, pady=(6,2))
        ttk.Label(self.content, text=t("lbl_preset_keys_hint"), foreground="gray").pack(anchor="w", padx=10)

        presets_container = ttk.Frame(self.content)

        def delete_preset(idx):
            lst = app.params.get("camera_presets", [])
            if 0 <= idx < len(lst):
                del lst[idx]
                if hasattr(app, "save_settings_json"):
                    app.save_settings_json()
                refresh_presets()

        def refresh_presets():
            for w in presets_container.winfo_children():
                w.destroy()
            lst = app.params.get("camera_presets", []) or []
            if not lst:
                ttk.Label(presets_container, text=t("lbl_no_presets"),
                          foreground="gray").pack(anchor="w", padx=6, pady=2)
                return
            for i, p in enumerate(lst):
                row = ttk.Frame(presets_container); row.pack(fill="x", pady=1)
                # Prefix with the number key (1-9) that jumps to this view.
                prefix = f"{i+1}. " if i < 9 else "   "
                ttk.Label(row, text=prefix + p.get("name", f"View {i+1}"),
                          width=18, anchor="w").pack(side="left")
                bg = tk.Button(row, text=t("btn_preset_go"), width=4,
                               command=lambda ii=i: app.apply_camera_preset(ii))
                bg.pack(side="left", padx=1)
                self.helper.bind_tooltip(
                    bg, f"Bu kayıtlı görünüme geç" + (f" (klavye: {i+1})" if i < 9 else "") + ".")
                bd = tk.Button(row, text="✕", width=2, fg="red",
                               command=lambda ii=i: delete_preset(ii))
                bd.pack(side="left", padx=1)
                self.helper.bind_tooltip(bd, "Bu görünümü sil.")

        def save_view():
            from tkinter import simpledialog
            name = simpledialog.askstring(t("dlg_save_view_title"), t("dlg_save_view_prompt"),
                                          parent=self.content)
            if not name:
                return
            lst = app.params.setdefault("camera_presets", [])
            lst.append({
                "name": name.strip(),
                "az": cam_get("cam_azimuth", 0.0),
                "el": cam_get("cam_elevation", 0.0),
                "roll": cam_get("cam_roll", 90.0),
                "dist": cam_get("cam_distance", 800.0),
            })
            if hasattr(app, "save_settings_json"):
                app.save_settings_json()
            refresh_presets()

        self.helper.add_button(self.content, t("btn_save_view"), save_view, "lightgreen",
                               "Mevcut kamera açısını adlandırarak kaydet. "
                               "Aşağıdaki listeden istediğin zaman geri çağırabilirsin. "
                               "Kaydedilen görünümler settings.json'da saklanır.")
        presets_container.pack(fill="x", padx=10, pady=2)
        refresh_presets()

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
        self.helper.add_checkbox(self.content, self.app, "straighten_start_fillet", t("cb_straighten_fillet"),
                                 "Silindir/koni mandrel'in duvarı ile alın yüzü arasındaki küçük yuvarlatma "
                                 "(fileto) radiusunu YOK SAY. Açıkken, fileto→duvar geçişinin ALTINDA işleyen "
                                 "paslar gerçek fileto eğrisini izlemek yerine EKSTRAPOLE edilmiş düz duvar "
                                 "çizgisini izler — böylece ilk paslar küçük radiusu 'tırmanmaz'. Geçiş noktası "
                                 "otomatik bulunur (düz-başlangıç ipucuyla aynı dedektör); düz bölümü olmayan "
                                 "(tamamen eğri) mandrel asla düzleştirilmez. Fileto içbükey olduğu için "
                                 "düzleştirilen çizgi mandrel'in DIŞINDA kalır (mandrel'e gömülme riski yok). "
                                 "SADECE straight-line bitirme + kaba pasoya uygulanır — sweeping/adaptive "
                                 "(konformal) bitirme bilerek hariçtir (o mod gerçek yüzeyi izler). "
                                 "Varsayılan KAPALI (eski davranış birebir).")

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

        # --- Actions section removed (2026-07-30) ---
        # Calculate moved to the action bar above the 3D view: it applies to the
        # whole program, and living in this tab meant the Machine tab had no way
        # to recalculate. G-code / PDF / STL moved to the Export menu. Both still
        # call the same handlers (ui_program._start_async_calc, root.export_*).

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
        self._sim_speed_var = tk.DoubleVar(value=1.0)

        def _apply_sim_speed(*_):
            try:
                m = float(self._sim_speed_var.get())
            except (tk.TclError, ValueError):
                return
            if m <= 0:
                m = 0.01
                self._sim_speed_var.set(m)
            self.app.sim_controller.speed_multiplier = m
            self.refresh_process_time()

        sim_spin = ttk.Spinbox(
            f_simspd_row, textvariable=self._sim_speed_var,
            from_=0.01, to=1000.0, increment=0.25, width=8,
            command=_apply_sim_speed)
        sim_spin.pack(side="left")
        sim_spin.bind("<Return>", _apply_sim_speed)
        sim_spin.bind("<FocusOut>", _apply_sim_speed)
        ttk.Label(f_simspd_row, text="×", font=("Arial", 10, "bold")).pack(side="left", padx=(3, 0))
        self._sim_speed_spin = sim_spin
        self.helper.bind_tooltip(sim_spin,
            "Simülasyon oynatma hız çarpanı. İstediğiniz değeri yazın (ör. 0.25, 1, 5, 50)\n"
            "veya okçuklarla artırıp azaltın.\n"
            "1× = gerçek işlem süresi. 2× = yarı sürede oynatır.")

        # Process time: the real machine time (at 1×) and the scaled playback time.
        self._proc_time_lbl = tk.Label(f_simspd, text="", font=("Arial", 9),
                                       fg="#004488", anchor="w", justify="left")
        self._proc_time_lbl.pack(anchor="w", pady=(3, 0))
        self.refresh_process_time()

    def refresh_process_time(self):
        """Update the sim process-time readout: real machining time (speed 1×) and
        the scaled playback time (real ÷ speed multiplier)."""
        lbl = getattr(self, "_proc_time_lbl", None)
        if lbl is None:
            return
        try:
            from simulation_controller import estimate_process_seconds
            seq = getattr(self.app.path_gen, "last_calculated_sequence", None)
            real = estimate_process_seconds(seq, self.app.params)
        except Exception:
            real = 0.0
        try:
            mult = float(self._sim_speed_var.get())
        except (tk.TclError, ValueError):
            mult = 1.0
        if mult <= 0:
            mult = 1.0

        def _fmt(sec):
            sec = max(0, int(round(sec)))
            m, s = divmod(sec, 60)
            h, m = divmod(m, 60)
            return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

        if real <= 0:
            lbl.config(text=t("lbl_proc_time_none"))
        else:
            lbl.config(text=t("lbl_proc_time").format(
                real=_fmt(real), play=_fmt(real / mult), mult=f"{mult:g}"))


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
