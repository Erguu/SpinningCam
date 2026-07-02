from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QDoubleSpinBox, 
    QSlider, QLabel, QGroupBox, QPushButton, QCheckBox,
    QTabWidget, QScrollArea
)
from qtpy.QtCore import Qt, Signal as pyqtSignal

class CollapsibleBox(QGroupBox):
    def __init__(self, title):
        super().__init__(title)
        self.setCheckable(True)
        self.setChecked(True)
        self.toggled.connect(self.on_toggled)
        
    def on_toggled(self, state):
        # Basitçe içeriği gizle/göster
        for i in range(self.layout().count()):
            w = self.layout().itemAt(i).widget()
            if w: w.setVisible(state)

class SidebarWidget(QWidget):
    # Sinyaller (Callback yerine sinyal kullanıyoruz)
    param_changed = pyqtSignal(str, float, str) # key, value, mode
    action_triggered = pyqtSignal(str) # action_name (save_gcode, etc)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        self.layout_content = QVBoxLayout()
        content_widget.setLayout(self.layout_content)
        scroll.setWidget(content_widget)
        
        main_layout.addWidget(scroll)

        # --- SECTIONS ---
        self.add_basic_settings()
        self.add_camera_settings()
        self.add_advanced_settings()
        self.add_visual_settings()
        self.add_action_buttons()
        
        main_layout.addStretch()

    def add_spin_slider(self, layout, key, title, min_val, max_val, step, mode="paths"):
        row = QWidget()
        h = QVBoxLayout() # Dikey dizilim daha temiz duralabilir mobilde ama masaüstünde FormLayout iyidir.
        h.setContentsMargins(0,0,0,0)
        row.setLayout(h)
        
        lbl = QLabel(title)
        
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(step)
        spin.setValue(self.params.get(key, 0.0))
        
        slider = QSlider(Qt.Orientation.Horizontal)
        # Slider integer çalışır, o yüzden float'ı scale ediyoruz (örn 100x)
        scale = 100.0
        slider.setRange(int(min_val*scale), int(max_val*scale))
        slider.setValue(int(self.params.get(key, 0.0)*scale))
        
        # Bağlantılar
        spin.valueChanged.connect(lambda v: self._sync_slider(slider, v, scale))
        spin.valueChanged.connect(lambda v: self.param_changed.emit(key, v, mode))
        
        slider.valueChanged.connect(lambda v: self._sync_spin(spin, v, scale))
        # Slider'dan gelen sinyali spinbox üzerinden emit ediyoruz ki duplicate olmasın
        
        form = QFormLayout()
        form.addRow(lbl, spin)
        h.addLayout(form)
        h.addWidget(slider)
        
        layout.addWidget(row)

    def _sync_slider(self, slider, val, scale):
        slider.blockSignals(True)
        slider.setValue(int(val*scale))
        slider.blockSignals(False)

    def _sync_spin(self, spin, val, scale):
        spin.blockSignals(True)
        spin.setValue(val/scale)
        spin.blockSignals(False)
        # Spinbox değeri değişince onun sinyali tetiklenir ve param_changed gider

    def add_basic_settings(self):
        box = QGroupBox("Temel Ayarlar")
        lay = QVBoxLayout()
        box.setLayout(lay)
        
        self.add_spin_slider(lay, "num_sweeping_passes", "Paso Sayısı", 1, 50, 1, "paths")
        self.add_spin_slider(lay, "first_pass_p2_contact_z_abs", "İlk Paso Z", -50, 200, 1, "paths")
        self.add_spin_slider(lay, "last_pass_extension_z", "Son Paso Uzatma", -50, 100, 1, "paths")
        
        chk = QCheckBox("Otomatik Açı")
        chk.setChecked(bool(self.params.get("auto_align_rotation", False)))
        chk.toggled.connect(lambda v: self.param_changed.emit("auto_align_rotation", float(v), "paths"))
        lay.addWidget(chk)
        
        chk_calc = QCheckBox("Pasoları Göster (Hesapla)")
        chk_calc.setChecked(bool(self.params.get("calc_active", False)))
        chk_calc.toggled.connect(lambda v: self.param_changed.emit("calc_active", float(v), "paths"))
        lay.addWidget(chk_calc)

        self.layout_content.addWidget(box)

    def add_camera_settings(self):
        box = QGroupBox("Kamera")
        lay = QVBoxLayout()
        box.setLayout(lay)
        
        self.add_spin_slider(lay, "cam_azimuth", "Yatay Açı", -180, 180, 5, "camera")
        self.add_spin_slider(lay, "cam_elevation", "Dikey Açı", -90, 90, 5, "camera")
        self.layout_content.addWidget(box)

    def add_advanced_settings(self):
        box = QGroupBox("Gelişmiş Ayarlar")
        lay = QVBoxLayout()
        box.setLayout(lay)
        
        self.add_spin_slider(lay, "p1_p3_x_offset_from_p2", "P1/P3 X Ofset", -100, 100, 1, "paths")
        self.add_spin_slider(lay, "p1_z_offset_from_p2", "P1 Z Ofset", -100, 100, 1, "paths")
        self.add_spin_slider(lay, "p3_z_offset_from_p2", "P3 Z Ofset", -100, 100, 1, "paths")
        self.add_spin_slider(lay, "roughing_step_radial", "Kaba Paso", -50, 10, 0.5, "paths")
        
        self.layout_content.addWidget(box)

    def add_visual_settings(self):
        box = QGroupBox("Görsel Ayarlar")
        lay = QVBoxLayout()
        box.setLayout(lay)
        
        self.add_spin_slider(lay, "blank_radius", "Sac Yarıçapı", 50, 500, 1, "all")
        self.add_spin_slider(lay, "blank_z_shift", "Sac Z Ince Ayar", -100, 100, 0.5, "all")
        self.add_spin_slider(lay, "roller_visual_radius", "Rulo Çapı", 5, 100, 1, "visual")
        self.add_spin_slider(lay, "shell_thickness", "Kabuk Kalınlığı", 0, 20, 0.1, "shell_and_paths")

        chk_tip_dist = QCheckBox("Show Tip Distance (ΔX / ΔZ to mandrel)")
        chk_tip_dist.setChecked(bool(self.params.get("show_tip_distance", False)))
        chk_tip_dist.toggled.connect(
            lambda v: self.param_changed.emit("show_tip_distance", float(v), "visual"))
        lay.addWidget(chk_tip_dist)

        self.layout_content.addWidget(box)

    def add_action_buttons(self):
        box = QGroupBox("İşlemler")
        lay = QVBoxLayout()
        box.setLayout(lay)
        
        btn_gcode = QPushButton("G-Kodu Kaydet")
        btn_gcode.clicked.connect(lambda: self.action_triggered.emit("save_gcode"))
        btn_gcode.setStyleSheet("background-color: lightgreen; font-weight: bold; padding: 5px;")
        lay.addWidget(btn_gcode)
        
        btn_sim = QPushButton("Simülasyon Oynat")
        btn_sim.clicked.connect(lambda: self.action_triggered.emit("run_sim"))
        btn_sim.setStyleSheet("background-color: cyan; font-weight: bold; padding: 5px;")
        lay.addWidget(btn_sim)

        btn_stop = QPushButton("DURDUR")
        btn_stop.clicked.connect(lambda: self.action_triggered.emit("stop_sim"))
        btn_stop.setStyleSheet("background-color: red; color: white; font-weight: bold; padding: 5px;")
        lay.addWidget(btn_stop)

        self.layout_content.addWidget(box)
