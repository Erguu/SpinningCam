import tkinter as tk
from tkinter import ttk
from ui.dialogs.zone_manager import ZoneManager
from ui.dialogs.tool_manager import ToolManager

class ProgramTab:
    def __init__(self, parent_frame, app, ui_root, ui_helper):
        self.app = app
        self.ui_root = ui_root
        self.helper = ui_helper
        self.frame = parent_frame

        self._create_widgets()

    # ------------------------------------------------------------------
    # Pass Info helpers
    # ------------------------------------------------------------------

    def _get_pass_type_list(self):
        """Returns a list of (op_type, tool_id) tuples, one per calculated path."""
        result = []
        for op in self.app.params.get("operations", []):
            if not op.get("enabled", True):
                continue
            op_type = op.get("type", "roughing")
            tool_id = op.get("tool_id", "?")
            # cutting/bending always produces exactly 1 path regardless of count
            count = 1 if op_type in ("cutting", "bending") else int(op.get("count", 1))
            for _ in range(count):
                result.append((op_type, tool_id))
        return result

    def refresh_pass_info(self):
        """Rebuild the pass-info text box from last_calculated_paths."""
        try:
            txt = self.txt_pass_info
        except AttributeError:
            return  # widget not yet built

        paths = getattr(self.app.path_gen, "last_calculated_paths", [])
        center_x = float(self.app.params.get("mandrel_pos_x_offset", 0.0))

        # Coordinate transform parameters (mirror what generate_gcode does)
        invert_x = self.app.params.get("machine_invert_x", False)
        invert_z = self.app.params.get("machine_invert_z", False)
        dir_x = -1.0 if invert_x else 1.0
        dir_z = -1.0 if invert_z else 1.0
        if self.app.params.get("origin_use_home", False):
            origin_x = float(self.app.params.get("home_x", 0.0))
            origin_z = float(self.app.params.get("home_z", 0.0))
        else:
            origin_x = float(self.app.params.get("machine_origin_x", 0.0))
            origin_z = float(self.app.params.get("machine_origin_z", 0.0))
        off_x = float(self.app.params.get("machine_gcode_offset_x", 0.0))
        off_z = float(self.app.params.get("machine_gcode_offset_z", 0.0))
        dia_mode = self.app.params.get("machine_output_diameter_mode", False)

        def to_machine(pt):
            x_out = ((pt[0] - origin_x) * dir_x) + off_x
            z_out = ((pt[2] - origin_z) * dir_z) + off_z
            if dia_mode:
                x_out *= 2.0
            return x_out, z_out

        pass_types = self._get_pass_type_list()

        txt.config(state="normal")
        txt.delete("1.0", "end")

        import numpy as np

        if not paths:
            txt.insert("end", "  No paths calculated yet.\n  Press CALCULATE or enable auto-calculate.", "dim")
            txt.config(state="disabled")
            return

        for i, path in enumerate(paths):
            if len(path) == 0:
                continue

            op_type = pass_types[i][0] if i < len(pass_types) else "roughing"
            tool_id = pass_types[i][1] if i < len(pass_types) else "?"

            tag_map = {"finishing": "finish_hdr", "cutting": "cut_hdr", "bending": "bend_hdr"}
            tag = tag_map.get(op_type, "rough_hdr")
            lbl_map = {"finishing": "FINISHING", "cutting": "CUTTING", "bending": "BENDING"}
            lbl = lbl_map.get(op_type, "ROUGHING")

            pts = np.array(path)

            txt.insert("end", f" Pass {i+1}  [{lbl}]  {tool_id} \n", tag)

            if op_type in ("cutting", "bending"):
                # Path is [approach, plunge] — just show the plunge target
                plunge_xm, plunge_zm = to_machine(pts[-1])
                approach_xm, approach_zm = to_machine(pts[0])
                txt.insert("end", f"  Approach →  X: {approach_xm:>8.3f}   Z: {approach_zm:>8.3f}\n", "data")
                txt.insert("end", f"  Plunge   →  X: {plunge_xm:>8.3f}   Z: {plunge_zm:>8.3f}\n", "contact")
            else:
                # Start / End
                s_xm, s_zm = to_machine(pts[0])
                e_xm, e_zm = to_machine(pts[-1])

                # Closest to mandrel = minimum X distance from center_x
                x_dists = np.abs(pts[:, 0] - center_x)
                crit_idx = int(np.argmin(x_dists))
                c_xm, c_zm = to_machine(pts[crit_idx])
                crit_x_dist = float(x_dists[crit_idx])  # in CAM space

                txt.insert("end", f"  Start   →  X: {s_xm:>8.3f}   Z: {s_zm:>8.3f}\n", "data")
                txt.insert("end", f"  End     →  X: {e_xm:>8.3f}   Z: {e_zm:>8.3f}\n", "data")
                txt.insert("end", f"  Contact →  X: {c_xm:>8.3f}   Z: {c_zm:>8.3f}"
                                   f"   (Δ mandrel: {crit_x_dist:.3f} mm)\n", "contact")
            txt.insert("end", "\n")

        txt.config(state="disabled")

    def _flush_entries(self):
        """Force-save all active entry widgets to params (call before destroying widgets or closing)."""
        for fn in self._active_entry_savers:
            try:
                fn()
            except:
                pass

    def _create_widgets(self):
        self._active_entry_savers = []
        # Frame for Treeview
        f_tree = ttk.Frame(self.frame)
        f_tree.pack(fill="both", expand=True, padx=5, pady=5)

        cols = ("Idx", "Type", "Count", "Tool")
        self.tree_ops = ttk.Treeview(f_tree, columns=cols, show="headings", height=6)
        self.tree_ops.heading("Idx", text="#"); self.tree_ops.column("Idx", width=30)
        self.tree_ops.heading("Type", text="TYPE"); self.tree_ops.column("Type", width=70)
        self.tree_ops.heading("Count", text="Count"); self.tree_ops.column("Count", width=40)
        self.tree_ops.heading("Tool", text="Tool"); self.tree_ops.column("Tool", width=50)
        self.tree_ops.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(f_tree, orient="vertical", command=self.tree_ops.yview)
        sb.pack(side="right", fill="y")
        self.tree_ops.configure(yscrollcommand=sb.set)
        self.tree_ops.bind("<<TreeviewSelect>>", self.on_op_select)

        # Toolbar
        f_tools = ttk.Frame(self.frame)
        f_tools.pack(fill="x", padx=5, pady=2)

        # Actions
        btn_rough = ttk.Button(f_tools, text="+ Rough", width=7, command=lambda: self.add_op("roughing"))
        btn_rough.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_rough, "Yeni kaba işlem (roughing) operasyonu ekle. "
                                            "Kaba işlem, malzemeyi mandrel profiline yaklaştırmak için birden fazla pas kullanır.")

        btn_finish = ttk.Button(f_tools, text="+ Finish", width=7, command=lambda: self.add_op("finishing"))
        btn_finish.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_finish, "Yeni bitirme (finishing) operasyonu ekle. "
                                             "Bitirme, kaba işlemden sonra mandrel profilini takip ederek yüzey kalitesini artırır.")

        btn_cut = ttk.Button(f_tools, text="+ Cut", width=6, command=lambda: self.add_op("cutting"))
        btn_cut.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_cut, "Yeni kesme (cutting) operasyonu ekle. "
                                          "Mandrel ucunda bıçakla tek geçişli radyal kesim yapar.")

        btn_bend = ttk.Button(f_tools, text="+ Bend", width=6, command=lambda: self.add_op("bending"))
        btn_bend.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_bend, "Yeni kıvırma (bending) operasyonu ekle. "
                                           "Mandrel ucunda kenarı kıvırmak için tek geçişli radyal baskı yapar.")

        btn_del = ttk.Button(f_tools, text="Delete", width=4, command=self.del_op)
        btn_del.pack(side="left", padx=1)
        self.helper.bind_tooltip(btn_del, "Seçili operasyonu listeden sil.")

        btn_tools = ttk.Button(f_tools, text="Tools", width=5, command=self.open_tool_manager)
        btn_tools.pack(side="left", padx=5)
        self.helper.bind_tooltip(btn_tools, "Takım kütüphanesini aç. "
                                            "Rulo geometrilerini (ID, yarıçap) buradan tanımlayabilirsin.")

        # Navigation & Info (Right side)
        btn_up = ttk.Button(f_tools, text="▲", width=3, command=lambda: self.move_op(-1))
        btn_up.pack(side="right", padx=1)
        self.helper.bind_tooltip(btn_up, "Seçili operasyonu listede yukarı taşı. "
                                         "Operasyonlar listede göründükleri sırayla G-code'a yazılır.")

        btn_dn = ttk.Button(f_tools, text="▼", width=3, command=lambda: self.move_op(1))
        btn_dn.pack(side="right", padx=1)
        self.helper.bind_tooltip(btn_dn, "Seçili operasyonu listede aşağı taşı. "
                                         "Operasyonlar listede göründükleri sırayla G-code'a yazılır.")

        # Time Label (Right of buttons, Left of Arrows)
        self.lbl_time = ttk.Label(f_tools, text="--:--", font=("Arial", 10, "bold"), foreground="#004488")
        self.lbl_time.pack(side="right", padx=10)
        self.helper.bind_tooltip(self.lbl_time, "Tahmini toplam program süresi (dakika:saniye). "
                                                 "Tüm pasların toplam yol uzunluğuna ve besleme hızına göre hesaplanır.")

        # Property Editor
        self.f_prop_editor = ttk.LabelFrame(self.frame, text="Operation Settings")
        self.f_prop_editor.pack(fill="x", padx=5, pady=5)

        if "operations" not in self.app.params:
             self.app.params["operations"] = self.app.path_gen._ensure_ops_dict(self.app.params)
        self.refresh_ops_tree()

        # --- Pass Info Panel ---
        f_info = ttk.LabelFrame(self.frame, text="Pass Info  (roller positions in machine coords)")
        f_info.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        self.txt_pass_info = tk.Text(
            f_info,
            height=10,
            font=("Consolas", 9),
            bg="#1e1e2e",
            fg="#cdd6f4",
            state="disabled",
            wrap="none",
            relief="flat",
            bd=0,
            padx=4,
            pady=4,
        )
        sb_info_y = ttk.Scrollbar(f_info, orient="vertical",   command=self.txt_pass_info.yview)
        sb_info_x = ttk.Scrollbar(f_info, orient="horizontal", command=self.txt_pass_info.xview)
        self.txt_pass_info.configure(yscrollcommand=sb_info_y.set,
                                     xscrollcommand=sb_info_x.set)
        sb_info_y.pack(side="right",  fill="y")
        sb_info_x.pack(side="bottom", fill="x")
        self.txt_pass_info.pack(fill="both", expand=True)

        # Colour tags
        self.txt_pass_info.tag_configure("rough_hdr",   background="#1d4d99", foreground="#a8d8ff",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("finish_hdr",  background="#7a4500", foreground="#ffd580",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("cut_hdr",     background="#1a4a1a", foreground="#b5e8b5",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("bend_hdr",    background="#4a1a4a", foreground="#e8b5e8",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("data",        foreground="#cdd6f4",
                                         font=("Consolas", 9))
        self.txt_pass_info.tag_configure("contact",     foreground="#a6e3a1",
                                         font=("Consolas", 9, "bold"))
        self.txt_pass_info.tag_configure("dim",         foreground="#6c7086",
                                         font=("Consolas", 9, "italic"))

        # Initial fill (may be empty until paths are calculated)
        self.refresh_pass_info()

    def open_tool_manager(self):
        ToolManager(self.frame.winfo_toplevel(), self.ui_root)

    def refresh_ops_tree(self):
        ops = self.app.params.get("operations", [])
        existing_items = self.tree_ops.get_children()

        for i, op in enumerate(ops):
            vals = (i+1, op.get("type", "?").upper(), op.get("count", 1), op.get("tool_id", "?"))
            if i < len(existing_items):
                self.tree_ops.item(existing_items[i], values=vals)
            else:
                self.tree_ops.insert("", "end", iid=str(i), values=vals)

        if len(existing_items) > len(ops):
            for i in range(len(ops), len(existing_items)):
                self.tree_ops.delete(existing_items[i])

        self.update_time_estimate()

    def update_time_estimate(self):
        try:
            sec = self.app.path_gen.calculate_estimated_time(self.app.params)
            m, s = divmod(int(sec), 60)
            if self.lbl_time: self.lbl_time.config(text=f"Est. Time: {m:02d}:{s:02d}")
        except: pass

    def on_op_select(self, event):
        sel = self.tree_ops.selection()
        if not sel:
            for w in self.f_prop_editor.winfo_children(): w.destroy()
            return

        try:
            idx = int(sel[0])
            if idx >= len(self.app.params["operations"]): return
            op = self.app.params["operations"][idx]
        except: return

        # Seçili operasyonun global pas indeksini hesapla
        cumulative = 0
        for i, o in enumerate(self.app.params.get("operations", [])):
            if i == idx: break
            if o.get("enabled", True):
                cumulative += int(o.get("count", 1))

        # Operasyon değiştiyse within-op sayacını sıfırla
        if not hasattr(self, '_active_op_idx') or self._active_op_idx != idx:
            self._within_op_idx = 0
            self._active_op_idx = idx
        self._op_start_pass_idx = cumulative
        self.app.active_editing_pass_idx = cumulative + self._within_op_idx
        self.app.recolor_paths()

        self._flush_entries()
        self._active_entry_savers = []
        for w in self.f_prop_editor.winfo_children(): w.destroy()

        op_type = op.get("type", "roughing")

        # Paso navigatörü — count > 1 olan operasyonlar için
        count = int(op.get("count", 1))
        if count > 1:
            f_nav = ttk.Frame(self.f_prop_editor)
            f_nav.pack(fill="x", padx=5, pady=(5, 2))

            self._lbl_pass_nav = ttk.Label(
                f_nav, text=f"Paso:  {self._within_op_idx + 1} / {count}",
                font=("Arial", 10, "bold"), foreground="purple")

            def go_prev(c=count):
                if self._within_op_idx > 0:
                    self._within_op_idx -= 1
                    self.app.active_editing_pass_idx = self._op_start_pass_idx + self._within_op_idx
                    self._lbl_pass_nav.config(text=f"Paso:  {self._within_op_idx + 1} / {c}")
                    self.app.recolor_paths()

            def go_next(c=count):
                if self._within_op_idx < c - 1:
                    self._within_op_idx += 1
                    self.app.active_editing_pass_idx = self._op_start_pass_idx + self._within_op_idx
                    self._lbl_pass_nav.config(text=f"Paso:  {self._within_op_idx + 1} / {c}")
                    self.app.recolor_paths()

            ttk.Button(f_nav, text="◀", width=3, command=go_prev).pack(side="left")
            self._lbl_pass_nav.pack(side="left", padx=8)
            ttk.Button(f_nav, text="▶", width=3, command=go_next).pack(side="left")
            ttk.Separator(self.f_prop_editor, orient="horizontal").pack(fill="x", pady=(4, 2))

        # --- Speed & Feed ---
        # Speed
        self._add_prop_combo(idx, "speed_mode", "Speed Mode", ["CSS", "RPM"], op,
                             "CSS (G96): Sabit yüzey hızı — mil devri çapa göre otomatik ayarlanır, yüzey kalitesi daha düzgün. "
                             "RPM (G97): Sabit devir — mil hızı sabit kalır.")
        s_lbl = "Speed (m/min)" if op.get("speed_mode", "CSS") == "CSS" else "Speed (RPM)"
        s_tooltip = ("Yüzey hızı değeri (m/dak). CSS modunda kullanılır. "
                     "Metal sıvama için tipik değer: 100–400 m/dak."
                     if op.get("speed_mode", "CSS") == "CSS" else
                     "Mil devri (RPM). Sabit RPM modunda kullanılır. "
                     "Tipik değer: 300–2000 RPM, malzeme ve çapa göre değişir.")
        self._add_prop_entry(idx, "speed", s_lbl, op, is_float=True, tooltip=s_tooltip)

        # Feed
        self._add_prop_combo(idx, "feed_mode", "Feed Mode", ["mm_min", "mm_rev"], op,
                             "mm/min (G98): Besleme hızı dakikada mm olarak. "
                             "mm/rev (G99): Tur başına mm olarak — devir değişse de talaş kalınlığı sabit kalır.")
        f_lbl = "Feed (mm/min)" if op.get("feed_mode", "mm_min") == "mm_min" else "Feed (mm/rev)"
        f_tooltip = ("Besleme hızı (mm/dak). "
                     "Metal sıvama için tipik değer: 100–600 mm/dak. "
                     "Düşük değer = daha iyi yüzey, yüksek değer = hızlı üretim."
                     if op.get("feed_mode", "mm_min") == "mm_min" else
                     "Tur başına besleme (mm/dev). "
                     "Tipik değer: 0.1–1.0 mm/dev. Devir değişse de talaş kalınlığı sabit kalır.")
        self._add_prop_entry(idx, "feed", f_lbl, op, is_float=True, tooltip=f_tooltip)

        # --- Cutting / Bending: simplified property set ---
        if op_type in ("cutting", "bending"):
            ttk.Separator(self.f_prop_editor, orient="horizontal").pack(fill="x", pady=5)

            # Tool ID
            f_tool = ttk.Frame(self.f_prop_editor)
            f_tool.pack(fill="x", padx=10, pady=2)
            tk.Label(f_tool, text="Tool ID").pack(side="left")
            tool_ids = [t["id"] for t in self.ui_root.tool_library]
            if not tool_ids: tool_ids = ["T0101", "T0202"]
            cb_tool = ttk.Combobox(f_tool, values=tool_ids, width=15)
            cb_tool.pack(side="right")
            cb_tool.set(op.get("tool_id", "T0101"))
            def on_tool_change_cb(event=None, _idx=idx):
                tid = cb_tool.get().strip()
                if tid:
                    self.app.on_param_change(f"operations[{_idx}].tool_id", tid, "paths")
            cb_tool.bind("<<ComboboxSelected>>", on_tool_change_cb)
            cb_tool.bind("<Return>", on_tool_change_cb)
            cb_tool.bind("<FocusOut>", on_tool_change_cb)

            self._add_prop_entry(idx, "r_tool", "Tool Radius", op, is_float=True,
                                 tooltip="Bıçak / kıvırma kafasının uç yarıçapı (mm). "
                                         "Temas noktası hesabı ve görselleştirme için kullanılır.")
            self._add_prop_entry(idx, "z_pos", "Z Position", op, is_float=True,
                                 tooltip="Kesim / kıvırma Z pozisyonu (mm, global koordinat). "
                                         "Takım bu Z koordinatında radyal hareket yapar.")
            self._add_prop_entry(idx, "plunge_x", "Plunge X", op, is_float=True,
                                 tooltip="Takımın plunge yapacağı hedef X koordinatı (mm, global koordinat). "
                                         "Mandrel merkezinden itibaren radyal mesafe. "
                                         "Takım bu X'e kadar besleme hızında ilerler.")
            return

        # Zones Button
        f_z = ttk.Frame(self.f_prop_editor)
        f_z.pack(fill="x", padx=2, pady=5)
        def open_zones():
            ZoneManager(self.frame.winfo_toplevel(), self.app, idx)

        btn_z = tk.Button(f_z, text="Variable Speed Zones...", bg="lightblue", command=open_zones)
        btn_z.pack(fill="x")
        self.helper.bind_tooltip(btn_z, "Belirli Z derinliklerinde hız ve besleme değişimi tanımla. "
                                        "Örn: mandrel boynunda daha yavaş besleme, düz bölgede hızlı.")

        ttk.Separator(self.f_prop_editor, orient="horizontal").pack(fill="x", pady=5)

        # Common Props
        # Tool ID Selector
        f_tool = ttk.Frame(self.f_prop_editor)
        f_tool.pack(fill="x", padx=10, pady=2)
        tk.Label(f_tool, text="Tool ID").pack(side="left")

        tool_ids = [t["id"] for t in self.ui_root.tool_library]
        if not tool_ids: tool_ids = ["T0101", "T0202"]

        cb_tool = ttk.Combobox(f_tool, values=tool_ids, width=15)
        cb_tool.pack(side="right")
        cb_tool.set(op.get("tool_id", "T0101"))

        def on_tool_change(event=None):
            tid = cb_tool.get().strip()
            if not tid:
                return
            self.app.on_param_change(f"operations[{idx}].tool_id", tid, "paths")
            # Auto-update radius if found
            found = next((t for t in self.ui_root.tool_library if t["id"] == tid), None)
            if found:
                r = found.get("radius", 0.0)
                self.app.on_param_change(f"operations[{idx}].r_tool", r, "paths")

        cb_tool.bind("<<ComboboxSelected>>", on_tool_change)
        cb_tool.bind("<Return>", on_tool_change)
        cb_tool.bind("<FocusOut>", on_tool_change)
        self.helper.bind_tooltip(cb_tool, "Bu operasyon için kullanılacak takımı seç. "
                                          "Takım kütüphanesinde tanımlı rulolar listelenir. "
                                          "Seçim yapıldığında Tool Radius otomatik güncellenir.")

        self._add_prop_entry(idx, "r_tool", "Tool Radius", op, is_float=True,
                             tooltip="Rulonun uç yarıçapı (mm). Temas noktası hesabında kullanılır. "
                                     "Takım seçildiğinde kütüphaneden otomatik gelir, buradan override edilebilir.")
        self._add_prop_entry(idx, "count", "Pass Count", op, is_int=True,
                             tooltip="Bu operasyonda oluşturulacak pas sayısı. "
                                     "Kaba işlemde: malzemeyi mandrel'e adım adım yaklaştıran pas sayısı. "
                                     "Bitirmede: genellikle 1–3 pas yeterlidir.")

        # Zone range: Start Z to End Z
        self._add_prop_entry(idx, "start_z", "Zone Start Z", op, is_float=True,
                             tooltip="Bu operasyonun başladığı Z pozisyonu (mm, global koordinat). "
                                     "Pasların ilk temas noktasının Z değeri. "
                                     "Mandrel yüzünden itibaren ölçülür.")
        self._add_prop_entry(idx, "end_z", "Zone End Z", op, is_float=True,
                             tooltip="Bu operasyonun bittiği Z pozisyonu (mm, global koordinat). "
                                     "Pas bitiş noktasının Z değeri. "
                                     "Start Z'den büyük olmalı.")
        self._add_prop_entry(idx, "proj_extend_bottom", "Proj Extend Bottom", op, is_float=True,
                             tooltip="Turkuaz projeksiyon çizgisini mandrel alt sınırının kaç mm altına uzat. "
                                     "Lineer şekillerde pozitif değer gir, küresel şekillerde 0 bırak.")
        self._add_prop_entry(idx, "proj_extend_top", "Proj Extend Top", op, is_float=True,
                             tooltip="Turkuaz projeksiyon çizgisini mandrel üst sınırının kaç mm üstüne uzat. "
                                     "Lineer şekillerde pozitif değer gir, küresel şekillerde 0 bırak.")

        if op_type == "roughing":
            self._add_prop_entry(idx, "p1_x", "P1 X (Entry)", op, is_float=True,
                                 tooltip="Spline giriş noktasının (P1) temas noktasından X eksenindeki uzaklığı (mm). "
                                         "Büyük değer = rulo daha dışarıdan yanaşır, yumuşak giriş eğrisi. "
                                         "Tipik: 30–60 mm.")
            self._add_prop_entry(idx, "p1_z", "P1 Z (Entry)", op, is_float=True,
                                 tooltip="Spline giriş noktasının (P1) temas noktasından Z eksenindeki uzaklığı (mm). "
                                         "Büyük değer = rulo temas öncesi daha uzaktan yaklaşır. "
                                         "Tipik: 30–70 mm.")
            self._add_prop_entry(idx, "p3_z", "P3 Z (Exit)", op, is_float=True,
                                 tooltip="Spline çıkış noktasının (P3) temas noktasından Z eksenindeki uzaklığı (mm). "
                                         "Negatif değer = rulo temas sonrası mandrel'in içine doğru ilerler (pas uzunluğu). "
                                         "Tipik: -10 ile -40 mm arası.")
            self._add_prop_entry(idx, "step", "Step (mm)", op, is_float=True,
                                 tooltip="Her pas arasındaki radyal adım mesafesi (mm). "
                                         "Temas noktası her pasa bu kadar daha içeriye (mandrel'e doğru) kayar. "
                                         "Küçük değer = daha fazla pas, daha az şekillendirme kuvveti. Tipik: 5–25 mm.")
            self._add_prop_entry(idx, "rot", "Rotation (Deg)", op, is_float=True,
                                 tooltip="Rulonun spline yolunun mandrel yüzeyine göre açısı (derece). "
                                         "Auto-Calc Angle açıksa bu değer otomatik hesaplanır. "
                                         "Manuel modda: 0° = Z eksenine paralel, pozitif değer = mandrel'e dönük.")
        else:
            self._add_prop_entry(idx, "finish_allowance", "Allowance (mm)", op, is_float=True,
                                 tooltip="Finishing pasının mandrel yüzeyinden ekstra uzaklığı (mm). "
                                         "0 = tam yüzey teması (r_tool + part_thickness). "
                                         "Pozitif değer = paso yüzeyden bu kadar daha uzakta kalır.")

            # Straight Line Mode
            f_sl = ttk.Frame(self.f_prop_editor)
            f_sl.pack(fill="x", padx=2, pady=1)
            ttk.Label(f_sl, text="Straight Line", width=15).pack(side="left")
            sl_var = tk.BooleanVar(value=bool(op.get("straight_line_mode", False)))

            def toggle_straight_line(i=idx):
                self.app.params["operations"][i]["straight_line_mode"] = sl_var.get()
                if self.app.params.get("calc_active", False):
                    self.app.update_scene("paths")

            ttk.Checkbutton(f_sl, variable=sl_var, command=toggle_straight_line).pack(side="right")
            self.helper.bind_tooltip(f_sl, "Bitirme pasını mandrel konturunu takip eden çok noktalı yol yerine "
                                           "iki nokta arası tek düz G1 hamlesi olarak oluştur. "
                                           "Basit konik veya düz yüzeyler için idealdir.")

    def _add_prop_combo(self, op_idx, key, label, values, op_dict, tooltip=""):
        f = ttk.Frame(self.f_prop_editor)
        f.pack(fill="x", padx=2, pady=1)
        ttk.Label(f, text=label, width=15).pack(side="left")

        curr = op_dict.get(key, values[0])
        cb = ttk.Combobox(f, values=values, state="readonly")
        cb.set(curr)
        cb.pack(side="right", fill="x", expand=True)

        def save(e):
            self._flush_entries()
            self.app.params["operations"][op_idx][key] = cb.get()
            self.on_op_select(None)
            self.update_time_estimate()

        cb.bind("<<ComboboxSelected>>", save)
        self.helper.bind_tooltip(cb, tooltip)
        self.helper.bind_tooltip(f, tooltip)

    def _add_prop_entry(self, op_idx, key, label, op_dict, is_int=False, is_float=False, tooltip=""):
        f = ttk.Frame(self.f_prop_editor)
        f.pack(fill="x", padx=2, pady=1)
        ttk.Label(f, text=label, width=15).pack(side="left")

        val = op_dict.get(key, "")
        var = tk.StringVar(value=str(val))

        def save(e=None):
            try:
                v = var.get()
                if is_int: v = int(v)
                elif is_float: v = float(v)

                self.app.params["operations"][op_idx][key] = v
                self.refresh_ops_tree()
                if self.app.params.get("auto_calculate_paths", False):
                     self.app.update_scene("paths")
            except: pass

        self._active_entry_savers.append(save)
        entry = ttk.Entry(f, textvariable=var)
        entry.pack(side="right", fill="x", expand=True)
        entry.bind("<FocusOut>", save)
        entry.bind("<Return>", save)
        entry.bind("<Button-1>", lambda e: e.widget.focus_force())
        self.helper.bind_tooltip(entry, tooltip)
        self.helper.bind_tooltip(f, tooltip)

    def add_op(self, mode):
        if "operations" not in self.app.params:
            self.app.params["operations"] = []

        if mode in ("cutting", "bending"):
            # Cutting/bending: single radial plunge at mandrel end
            def_tool_id = "T0303"
            for t in self.ui_root.tool_library:
                if t["id"] == def_tool_id:
                    break
            else:
                # Fall back to first tool in library if T0303 not found
                if self.ui_root.tool_library:
                    def_tool_id = self.ui_root.tool_library[0].get("id", "T0303")

            new_op = {
                "type": mode, "enabled": True, "count": 1,
                "tool_id": def_tool_id,
                "r_tool": 0.0,
                "z_pos": 0.0,
                "plunge_x": 50.0,
                "feed": 50.0, "feed_mode": "mm_min",
                "speed": 300.0, "speed_mode": "RPM",
            }
            self.app.params["operations"].append(new_op)
            self.refresh_ops_tree()
            return

        # Inherit rotation from last op
        def_rot = 10.0
        if self.app.params["operations"]:
             def_rot = self.app.params["operations"][-1].get("rot", 10.0)

        # Choose default tool based on mode
        if mode == "roughing":
            def_tool_id = "T0101"
        else:
            def_tool_id = "T0202"

        # Look up tool radius from library
        def_r_tool = 25.0  # fallback default
        for t in self.ui_root.tool_library:
            if t["id"] == def_tool_id:
                def_r_tool = t.get("radius", 25.0)
                break

        # If not found by default ID, try to use first available tool of matching type
        if def_r_tool == 25.0 and self.ui_root.tool_library:
            first_tool = self.ui_root.tool_library[0]
            def_tool_id = first_tool.get("id", def_tool_id)
            def_r_tool = first_tool.get("radius", 25.0)

        new_op = {
            "type": mode, "enabled": True, "count": 1,
            "tool_id": def_tool_id,
            "r_tool": def_r_tool,
            "p1_x": 40.0, "p1_z": 50.0, "p3_z": -20.0,
            "start_z": 0.0, "end_z": 200.0,
            "step": 1.0,
            "rot": def_rot,
            "feed": 100.0, "speed": 500.0
        }
        self.app.params["operations"].append(new_op)
        self.refresh_ops_tree()

    def del_op(self):
        sel = self.tree_ops.selection()
        if sel:
            idx = int(sel[0])
            self.app.params["operations"].pop(idx)
            self.refresh_ops_tree()

    def move_op(self, d):
        sel = self.tree_ops.selection()
        if sel:
            idx = int(sel[0])
            new_idx = idx + d
            if 0 <= new_idx < len(self.app.params["operations"]):
                self.app.params["operations"][idx], self.app.params["operations"][new_idx] = self.app.params["operations"][new_idx], self.app.params["operations"][idx]
                self.refresh_ops_tree()
                self.tree_ops.selection_set(str(new_idx))
