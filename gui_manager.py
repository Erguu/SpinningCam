import pyvista as pv
import tkinter as tk
from tkinter import simpledialog
import json
import os
import sys
from logger_config import logger

class GuiManager:
    def __init__(self, plotter, win_w=1920, win_h=1080):
        self.p = plotter
        self.elements = []
        
        # Tkinter (Popup için)
        self.root = tk.Tk()
        self.root.withdraw() 
        
        self.win_w = win_w
        self.win_h = win_h
        
        # --- LAYOUT AYARLARINI YÜKLE ---
        self.layout = self.load_layout_config()
        
        self.sx = self.layout.get("slider_start_x", 0.02)
        self.ex = self.layout.get("slider_end_x", 0.15)
        self.gap = self.layout.get("vertical_gap", 0.12)
        
    def load_layout_config(self):
        default_layout = {
            "slider_start_x": 0.02, "slider_end_x": 0.15,
            "vertical_gap": 0.12, "header_gap": 0.06,
            "scroll_bar_x": 0.30, "scroll_bar_width": 0.004,
            "checkbox_x": 0.02, 
            "multi_btn_start_x": 0.02, "multi_btn_spacing": 0.06
        }
        
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        json_path = os.path.join(base_path, "layout.json")
        
        json_path = os.path.join(base_path, "layout.json")
        
        logger.info(f"Loading layout config from: {json_path}")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding='utf-8') as f:
                    data = json.load(f)
                    default_layout.update(data)
                    logger.info("Layout loaded successfully.")
            except Exception as e:
                logger.error(f"Layout JSON corrupt: {e}")
        else:
            logger.warning("layout.json not found. Using defaults.")
            
        return default_layout

    # [YENİ] OTOMATİK MENZİL HESAPLAYICI
    def _calculate_scroll_range(self, show_adv, show_vis):
        """En alttaki öğeyi bulur ve gerekli kaydırma miktarını hesaplar"""
        min_y = 1.0 # Ekranın en tepesi
        
        for item in self.elements:
            # Sadece görünür grupları hesaba kat
            if item["group"] == "adv" and not show_adv: continue
            if item["group"] == "vis" and not show_vis: continue
            
            # En düşük Y koordinatını (en alttaki öğe) bul
            if item["base_y"] < min_y:
                min_y = item["base_y"]
                
        # Eğer en alttaki öğe ekranın altındaysa (örneğin -0.5), 
        # onu ekranın içine (örneğin 0.1'e) getirmek için ne kadar offset lazım?
        # Hedef: En alt öğe Y=0.05 hizasında dursun.
        
        target_bottom_margin = 0.20
        
        # Eğer her şey ekrana sığıyorsa (min_y > margin), kaydırmaya gerek yok (0 offset)
        if min_y > target_bottom_margin:
            return 0.0
        
        # Gerekli kaydırma miktarı
        needed_offset = target_bottom_margin - min_y
        return needed_offset

    def update_positions(self, scroll_val, show_adv, show_vis):
        self.win_w, self.win_h = self.p.window_size
        
        # Dinamik maksimum offset hesabı
        max_offset = self._calculate_scroll_range(show_adv, show_vis)
        
        # Scroll hesabı
        offset = ((100.0 - scroll_val) / 100.0) * max_offset
        
        for item in self.elements:
            # 1. Hedef Y konumunu hesapla
            current_y = item["base_y"] + offset
            
            # 2. Mantıksal Görünürlük (Sekme Kontrolü)
            is_logically_visible = True
            if item["group"] == "adv" and not show_adv: is_logically_visible = False
            if item["group"] == "vis" and not show_vis: is_logically_visible = False
            
            # 3. Ekran Sınırı Kontrolü
            is_on_screen = (-0.1 < current_y < 0.98)
            
            # GÖSTERİLECEK Mİ?
            should_show = (is_logically_visible and is_on_screen)

            if should_show:
                # Ekranda görünecekse: Doğru yerine taşı ve aç
                self._move_item(item, current_y)
                self._set_visibility(item, True)
            else:
                # Gizlenecekse:
                # 1. Önce ekranın çok dışına (-10.0 koordinatına) fırlat.
                # Bu, eğer 'hayalet' kalırsa ekran dışında kalmasını garanti eder.
                self._move_item(item, -10.0) 
                
                # 2. Sonra görünürlüğünü kapat
                self._set_visibility(item, False)
        
        # [Ekstra Güvenlik] Sahne yenilemesini zorla
        self.p.render()
        self.win_w, self.win_h = self.p.window_size
        
        # Dinamik maksimum offset hesabı
        max_offset = self._calculate_scroll_range(show_adv, show_vis)
        
        # Scroll hesabı
        offset = ((100.0 - scroll_val) / 100.0) * max_offset
        
        for item in self.elements:
            # 1. Hedef Y konumunu hesapla
            current_y = item["base_y"] + offset
            
            # 2. Grup görünürlüğünü kontrol et (Sekmeler)
            is_logically_visible = True
            if item["group"] == "adv" and not show_adv: is_logically_visible = False
            if item["group"] == "vis" and not show_vis: is_logically_visible = False
            
            # 3. Ekran sınırlarını kontrol et
            is_on_screen = (-0.1 < current_y < 0.98)
            
            # [KRİTİK DÜZELTME]
            # Öğeyi gizleyecek olsak bile önce MUTLAKA yeni yerine taşıyoruz.
            # Bu, butonların eski koordinatlarda "hayalet" olarak kalmasını engeller.
            if is_logically_visible:
                self._move_item(item, current_y)

            # 4. Son olarak görünürlüğü ayarla
            if is_logically_visible and is_on_screen:
                self._set_visibility(item, True)
            else:
                self._set_visibility(item, False)
        self.win_w, self.win_h = self.p.window_size
        
        # [YENİ] Dinamik maksimum offset hesabı
        max_offset = self._calculate_scroll_range(show_adv, show_vis)
        
        # Scroll 100 ise (En tepe) -> Offset 0
        # Scroll 0 ise (En dip) -> Offset = max_offset
        # Formül: (100 - Scroll) / 100 * Max_Offset
        offset = ((100.0 - scroll_val) / 100.0) * max_offset
        
        for item in self.elements:
            is_visible = True
            if item["group"] == "adv" and not show_adv: is_visible = False
            if item["group"] == "vis" and not show_vis: is_visible = False
            
            if not is_visible:
                self._set_visibility(item, False)
                continue

            current_y = item["base_y"] + offset
            
            # Ekran dışı kontrolü (-0.1 ile 1.0 arası görünür olsun)
            if current_y < -0.1 or current_y > 0.98:
                self._set_visibility(item, False)
            else:
                self._set_visibility(item, True)
                self._move_item(item, current_y)

    def add_section_header(self, text, y_pos, color_name, group="std"):
        txt_actor = self.p.add_text(f"  {text}  ", position=(40, 500), font_size=12, color='white', shadow=False)
        prop = txt_actor.GetTextProperty()
        prop.SetBackgroundColor(pv.Color(color_name).float_rgb)
        prop.SetBackgroundOpacity(1.0); prop.SetFrame(True); prop.SetFrameWidth(2); prop.SetFrameColor(0.2, 0.2, 0.2); prop.SetBold(True)
        self.elements.append({"type": "header", "actor": txt_actor, "base_y": y_pos, "group": group})

    def add_slider(self, callback, rng, val, title, y_pos, color, group="std", fmt="%.1f"):
        s = self.p.add_slider_widget(callback=callback, rng=rng, value=val, title=title, 
                                     pointa=(self.sx, y_pos), pointb=(self.ex, y_pos), 
                                     style='classic', color=color, fmt=fmt)
        rep = s.GetRepresentation()
        rep.SetTubeWidth(0.007); rep.SetSliderLength(0.025); rep.SetSliderWidth(0.025)
        try: rep.SetEndCapLength(0.01)
        except: pass
        rep.GetTubeProperty().SetColor(0.8, 0.8, 0.8)
        rep.GetSelectedProperty().SetColor(pv.Color(color).float_rgb)
        prop = rep.GetTitleProperty(); prop.SetFontSize(11); prop.SetColor(0,0,0); prop.SetBold(True); prop.SetShadow(False)
        lprop = rep.GetLabelProperty(); lprop.SetFontSize(11); lprop.SetColor(0.1, 0.1, 0.1); lprop.SetShadow(False)
        
        self.elements.append({"type": "slider", "widget": s, "base_y": y_pos, "group": group})
        return s

    def add_tuner_buttons(self, callback_minus, callback_plus, callback_input, y_pos, group="std"):
        size = 18
        b_min = self.p.add_checkbox_button_widget(callback_minus, position=(0, 0), size=size, color_on='lightcoral', color_off='lightcoral')
        b_inp = self.p.add_checkbox_button_widget(callback_input, position=(0, 0), size=size, color_on='gold', color_off='gold')
        b_plus = self.p.add_checkbox_button_widget(callback_plus, position=(0, 0), size=size, color_on='lightgreen', color_off='lightgreen')
        
        self.elements.append({
            "type": "tuner", 
            "w_min": b_min, "w_inp": b_inp, "w_plus": b_plus, 
            "base_y": y_pos, "group": group
        })

    def add_checkbox(self, callback, val, y_pos, color, text, group="std"):
        btn = self.p.add_checkbox_button_widget(callback, value=val, position=(0, 0), size=20, color_on=color, color_off='lightgray')
        txt = self.p.add_text(text, position=(0, 0), color='black', font_size=10)
        self.elements.append({"type": "checkbox", "widget": btn, "text": txt, "base_y": y_pos, "group": group})

    def add_multi_buttons(self, buttons_data, y_pos, group="std"):
        widgets = []; texts = []
        size = 20
        for i, (cb, lbl, col) in enumerate(buttons_data):
            w = self.p.add_checkbox_button_widget(cb, value=False, position=(0, 0), size=size, color_on=col, color_off='lightgray')
            t = self.p.add_text(lbl, position=(0, 0), color='black', font_size=10)
            widgets.append(w); texts.append(t)
        self.elements.append({"type": "multi_btn", "widgets": widgets, "texts": texts, "base_y": y_pos, "group": group})

    def add_action_button(self, callback, val, pos_x, pos_y, color, text):
        w = self.p.add_checkbox_button_widget(callback, value=val, position=(pos_x, pos_y), size=22, color_on=color, color_off='lightgray')
        self.p.add_checkbox_button_widget(callback, value=val, position=(pos_x, pos_y), size=22, color_on=color, color_off='lightgray')
        self.p.add_text(text, position=(pos_x - 160, pos_y + 5), color='black', font_size=11)
        return w  # <--- BU SATIRI EKLEYİN
    
    def ask_float(self, title, prompt, initial_value):
        self.root.update() 
        val = simpledialog.askfloat(title, prompt, initialvalue=initial_value, parent=self.root)
        self.root.update()
        return val
    def update_slider_val(self, slider_widget, new_val):
        """Slider değerini dışarıdan güvenli şekilde günceller ve olası hataları önler"""
        rep = slider_widget.GetRepresentation()
        min_v = rep.GetMinimumValue()
        max_v = rep.GetMaximumValue()
        
        # Sınır kontrolü
        if new_val < min_v: new_val = min_v
        if new_val > max_v: new_val = max_v
        
        # Değeri ata
        rep.SetValue(new_val)
        # Not: Bu fonksiyon sadece görseli günceller, callback'i tetiklemez. 
        # Callback tetiklemek için main.py içindeki wrappers kullanılır.
    def _set_visibility(self, item, state):
        s = int(state)
        if item["type"] == "slider": item["widget"].SetEnabled(s)
        elif item["type"] == "header": item["actor"].SetVisibility(state)
        elif item["type"] == "tuner": 
            item["w_min"].SetEnabled(s); item["w_inp"].SetEnabled(s); item["w_plus"].SetEnabled(s)
        elif item["type"] == "checkbox": item["widget"].SetEnabled(s); item["text"].SetVisibility(state)
        elif item["type"] == "multi_btn":
            for w in item["widgets"]: w.SetEnabled(s)
            for t in item["texts"]: t.SetVisibility(state)

    def _move_item(self, item, y):
        y_px = int(y * self.win_h)
        if item["type"] == "slider":
            rep = item["widget"].GetRepresentation()
            p1 = rep.GetPoint1Coordinate(); p2 = rep.GetPoint2Coordinate()
            p1.SetCoordinateSystemToNormalizedViewport(); p2.SetCoordinateSystemToNormalizedViewport()
            old_p1 = p1.GetValue(); old_p2 = p2.GetValue()
            p1.SetValue(old_p1[0], y, 0); p2.SetValue(old_p2[0], y, 0)
            
        elif item["type"] == "header":
            item["actor"].SetPosition(40, y_px)
            
        elif item["type"] == "tuner":
            size = 18
            bx_min = int((self.ex + 0.01) * self.win_w)
            bx_inp = int((self.ex + 0.03) * self.win_w)
            bx_plus = int((self.ex + 0.05) * self.win_w)
            
            item["w_min"].GetRepresentation().PlaceWidget([bx_min, bx_min+size, y_px-9, y_px+9, 0, 0])
            item["w_inp"].GetRepresentation().PlaceWidget([bx_inp, bx_inp+size, y_px-9, y_px+9, 0, 0])
            item["w_plus"].GetRepresentation().PlaceWidget([bx_plus, bx_plus+size, y_px-9, y_px+9, 0, 0])
            
        elif item["type"] == "checkbox":
            size = 20; bx = int(self.layout.get("checkbox_x", 0.02) * self.win_w)
            item["widget"].GetRepresentation().PlaceWidget([bx, bx+size, y_px, y_px+size, 0, 0])
            item["text"].SetPosition(bx + 30, y_px + 5)
            
        elif item["type"] == "multi_btn":
            size = 20
            start_x = int(self.layout.get("multi_btn_start_x", 0.02) * self.win_w)
            spacing = int(self.layout.get("multi_btn_spacing", 0.06) * self.win_w)
            for i, (w, t) in enumerate(zip(item["widgets"], item["texts"])):
                bx = start_x + (i * spacing)
                w.GetRepresentation().PlaceWidget([bx, bx+size, y_px, y_px+size, 0, 0])
    def build_interface(self, app):
        """
        Constructs the entire UI interface.
        Args:
            app: The SpinningApp instance containing callbacks and params.
        """
        # --- Scroll Bar ---
        sb_x = self.layout.get("scroll_bar_x", 0.30)
        sb_w = self.layout.get("scroll_bar_width", 0.004)
        
        scroll_slider = self.p.add_slider_widget(app.cb_scroll, [0, 100], value=100, title="", 
                                                  pointa=(sb_x, 0.1), pointb=(sb_x, 0.9), 
                                                  style='modern', color='lightgray')
        scroll_slider.GetRepresentation().SetTubeWidth(sb_w)
        scroll_slider.GetRepresentation().SetSliderLength(0.05)
        scroll_slider.GetRepresentation().SetSliderWidth(0.02)
        scroll_slider.GetRepresentation().GetTitleProperty().SetOpacity(0)
        scroll_slider.GetRepresentation().GetLabelProperty().SetOpacity(0)

        current_y = 0.85
        GAP = self.layout.get("vertical_gap", 0.12)
        HEADER_GAP = self.layout.get("header_gap", 0.06)
        C_STD = 'cornflowerblue'; C_ADV = 'mediumaquamarine'; C_VIS = 'orange'
        
        # --- Checkbox: Pasoları Göster ---
        self.add_checkbox(lambda v: app.on_param_change("calc_active", v, "paths"), app.params["calc_active"], current_y+0.05, 'red', "PASOLARI GOSTER")
        
        # --- 1. TEMEL AYARLAR ---
        self.add_section_header("TEMEL AYARLAR", current_y, C_STD); current_y -= HEADER_GAP
        
        s_num = self.add_slider(lambda v: app.on_param_change("num_sweeping_passes", int(v), "paths"), [1, 50], app.params["num_sweeping_passes"], "Paso Sayisi", current_y, C_STD, fmt="%.0f")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("num_sweeping_passes", -1, s_num, "paths"), 
                                  lambda v: app.adjust_val_wrapper("num_sweeping_passes", 1, s_num, "paths"), 
                                  lambda v: app.ask_val_wrapper("num_sweeping_passes", "Paso Sayisi", s_num, "paths"), current_y); current_y -= GAP

        s_idx = self.add_slider(app.cb_idx, [0, 49], 0, "Aktif Paso", current_y, C_STD, fmt="%.0f")
        self.add_tuner_buttons(lambda v: self.update_slider_val(s_idx, s_idx.GetRepresentation().GetValue() - 1), 
                                  lambda v: self.update_slider_val(s_idx, s_idx.GetRepresentation().GetValue() + 1), lambda v: None, current_y); current_y -= GAP

        s_first = self.add_slider(lambda v: app.on_param_change("first_pass_p2_contact_z_abs", v, "paths"), [-50, 200], app.params["first_pass_p2_contact_z_abs"], "Ilk Paso Z", current_y, C_STD)
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("first_pass_p2_contact_z_abs", -0.5, s_first, "paths"), 
                                  lambda v: app.adjust_val_wrapper("first_pass_p2_contact_z_abs", 0.5, s_first, "paths"), 
                                  lambda v: app.ask_val_wrapper("first_pass_p2_contact_z_abs", "Ilk Paso Z", s_first, "paths"), current_y); current_y -= GAP

        s_last = self.add_slider(lambda v: app.on_param_change("last_pass_extension_z", v, "paths"), [-50, 100], app.params["last_pass_extension_z"], "Son Paso Uzatma", current_y, C_STD)
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("last_pass_extension_z", -0.5, s_last, "paths"), 
                                  lambda v: app.adjust_val_wrapper("last_pass_extension_z", 0.5, s_last, "paths"), 
                                  lambda v: app.ask_val_wrapper("last_pass_extension_z", "Son Paso Uzatma", s_last, "paths"), current_y); current_y -= GAP
        
        self.add_checkbox(lambda v: app.on_param_change("auto_align_rotation", v, "paths"), app.params["auto_align_rotation"], current_y, 'forestgreen', "Otomatik Aci"); current_y -= GAP
    
        # --- KAMERA ---
        current_y -= 0.02
        self.add_section_header("KAMERA", current_y, 'gray'); current_y -= HEADER_GAP
        self.add_slider(lambda v: app.on_param_change("cam_azimuth", v, "camera"), [-180, 180], app.params["cam_azimuth"], "Yatay Aci", current_y, 'gray', fmt="%.0f"); current_y -= GAP
        self.add_slider(lambda v: app.on_param_change("cam_elevation", v, "camera"), [-90, 90], app.params["cam_elevation"], "Dikey Aci", current_y, 'gray', fmt="%.0f"); current_y -= GAP
        self.add_slider(lambda v: app.on_param_change("cam_roll", v, "camera"), [-180, 180], app.params["cam_roll"], "Eksen (Roll)", current_y, 'gray', fmt="%.0f"); current_y -= GAP

        # --- GELİŞMİŞ AYARLAR ---
        ay = current_y - 0.05
        self.add_section_header("GELISMIS AYARLAR", ay, C_ADV, "adv"); ay -= HEADER_GAP
        s_p1x = self.add_slider(lambda v: app.on_param_change("p1_p3_x_offset_from_p2", v, "paths"), [-100, 100], app.params["p1_p3_x_offset_from_p2"], "P1/P3 X Ofset", ay, C_ADV, "adv")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("p1_p3_x_offset_from_p2", -0.5, s_p1x, "paths"), lambda v: app.adjust_val_wrapper("p1_p3_x_offset_from_p2", 0.5, s_p1x, "paths"), lambda v: app.ask_val_wrapper("p1_p3_x_offset_from_p2", "P1/P3 X Ofset", s_p1x, "paths"), ay, "adv"); ay -= GAP
        s_p1z = self.add_slider(lambda v: app.on_param_change("p1_z_offset_from_p2", v, "paths"), [-100, 100], app.params["p1_z_offset_from_p2"], "P1 Z Ofset", ay, C_ADV, "adv")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("p1_z_offset_from_p2", -0.5, s_p1z, "paths"), lambda v: app.adjust_val_wrapper("p1_z_offset_from_p2", 0.5, s_p1z, "paths"), lambda v: app.ask_val_wrapper("p1_z_offset_from_p2", "P1 Z Ofset", s_p1z, "paths"), ay, "adv"); ay -= GAP
        s_p3z = self.add_slider(lambda v: app.on_param_change("p3_z_offset_from_p2", v, "paths"), [-100, 100], app.params["p3_z_offset_from_p2"], "P3 Z Ofset", ay, C_ADV, "adv")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("p3_z_offset_from_p2", -0.5, s_p3z, "paths"), lambda v: app.adjust_val_wrapper("p3_z_offset_from_p2", 0.5, s_p3z, "paths"), lambda v: app.ask_val_wrapper("p3_z_offset_from_p2", "P3 Z Ofset", s_p3z, "paths"), ay, "adv"); ay -= GAP
        s_yrot = self.add_slider(lambda v: app.on_param_change("y_rotation_degrees", v, "paths"), [-90, 90], app.params["y_rotation_degrees"], "Y Rotasyon", ay, C_ADV, "adv")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("y_rotation_degrees", -1.0, s_yrot, "paths"), lambda v: app.adjust_val_wrapper("y_rotation_degrees", 1.0, s_yrot, "paths"), lambda v: app.ask_val_wrapper("y_rotation_degrees", "Y Rotasyon", s_yrot, "paths"), ay, "adv"); ay -= GAP
        s_rough = self.add_slider(lambda v: app.on_param_change("roughing_step_radial", v, "paths"), [-50, 10], app.params["roughing_step_radial"], "Kaba Paso", ay, C_ADV, "adv")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("roughing_step_radial", -0.5, s_rough, "paths"), lambda v: app.adjust_val_wrapper("roughing_step_radial", 0.5, s_rough, "paths"), lambda v: app.ask_val_wrapper("roughing_step_radial", "Kaba Paso", s_rough, "paths"), ay, "adv"); ay -= GAP

        # --- GÖRSEL AYARLAR ---
        vy = current_y - 0.05
        self.add_section_header("GORSEL AYARLAR", vy, C_VIS, "vis"); vy -= HEADER_GAP
        s_blank = self.add_slider(lambda v: app.on_param_change("blank_radius", v, "all"), [50, 500], app.params["blank_radius"], "Sac Yaricapi", vy, C_VIS, "vis")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("blank_radius", -1, s_blank, "all"), lambda v: app.adjust_val_wrapper("blank_radius", 1, s_blank, "all"), lambda v: app.ask_val_wrapper("blank_radius", "Sac Yaricapi", s_blank, "all"), vy, "vis"); vy -= GAP
        s_rrad = self.add_slider(lambda v: app.on_param_change("roller_visual_radius", v, "visual"), [5, 100], app.params["roller_visual_radius"], "Rulo Cap", vy, C_VIS, "vis")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("roller_visual_radius", -1, s_rrad, "visual"), lambda v: app.adjust_val_wrapper("roller_visual_radius", 1, s_rrad, "visual"), lambda v: app.ask_val_wrapper("roller_visual_radius", "Rulo Cap", s_rrad, "visual"), vy, "vis"); vy -= GAP
        s_rx = self.add_slider(lambda v: app.on_param_change("roller_visual_x_offset", v, "visual"), [0, 500], app.params["roller_visual_x_offset"], "Rulo X", vy, C_VIS, "vis")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("roller_visual_x_offset", -1, s_rx, "visual"), lambda v: app.adjust_val_wrapper("roller_visual_x_offset", 1, s_rx, "visual"), lambda v: app.ask_val_wrapper("roller_visual_x_offset", "Rulo X", s_rx, "visual"), vy, "vis"); vy -= GAP
        s_rz = self.add_slider(lambda v: app.on_param_change("roller_visual_z_offset", v, "visual"), [-100, 500], app.params["roller_visual_z_offset"], "Rulo Z", vy, C_VIS, "vis")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("roller_visual_z_offset", -1, s_rz, "visual"), lambda v: app.adjust_val_wrapper("roller_visual_z_offset", 1, s_rz, "visual"), lambda v: app.ask_val_wrapper("roller_visual_z_offset", "Rulo Z", s_rz, "visual"), vy, "vis"); vy -= GAP
        s_mx = self.add_slider(lambda v: app.on_param_change("mandrel_pos_x_offset", v, "all"), [-200, 200], app.params["mandrel_pos_x_offset"], "Mandrel X", vy, C_VIS, "vis")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("mandrel_pos_x_offset", -1, s_mx, "all"), lambda v: app.adjust_val_wrapper("mandrel_pos_x_offset", 1, s_mx, "all"), lambda v: app.ask_val_wrapper("mandrel_pos_x_offset", "Mandrel X", s_mx, "all"), vy, "vis"); vy -= GAP
        s_mz = self.add_slider(lambda v: app.on_param_change("mandrel_pos_z_offset", v, "all"), [-200, 200], app.params["mandrel_pos_z_offset"], "Mandrel Z", vy, C_VIS, "vis")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("mandrel_pos_z_offset", -1, s_mz, "all"), lambda v: app.adjust_val_wrapper("mandrel_pos_z_offset", 1, s_mz, "all"), lambda v: app.ask_val_wrapper("mandrel_pos_z_offset", "Mandrel Z", s_mz, "all"), vy, "vis"); vy -= GAP
        s_th = self.add_slider(lambda v: app.on_param_change("shell_thickness", v, "shell_and_paths"), [0, 20], app.params["shell_thickness"], "Kabuk Kalinligi", vy, C_VIS, "vis")
        self.add_tuner_buttons(lambda v: app.adjust_val_wrapper("shell_thickness", -0.5, s_th, "shell_and_paths"), lambda v: app.adjust_val_wrapper("shell_thickness", 0.5, s_th, "shell_and_paths"), lambda v: app.ask_val_wrapper("shell_thickness", "Kabuk Kalinligi", s_th, "shell_and_paths"), vy, "vis"); vy -= GAP

        # --- MULTI BUTTONS ---
        self.add_multi_buttons([
            (lambda v: app.rotate_mandrel("x"), "Rot X", 'orange'),
            (lambda v: app.rotate_mandrel("y"), "Rot Y", 'orange'),
            (lambda v: app.rotate_mandrel("z"), "Rot Z", 'orange')
        ], vy, "vis")

        bx, by = 1920 - 200, 1080 - 80
        self.add_action_button(app.save_gcode, False, bx, by, 'lightgreen', "G-Kodu Kaydet"); by -= 40
        self.add_action_button(app.save_project, False, bx, by, 'darkslateblue', "Projeyi Kaydet"); by -= 40
        self.add_action_button(app.load_project, False, bx, by, 'darkslateblue', "Proje Yukle"); by -= 40
        self.add_action_button(lambda v: app.update_scene("camera"), False, bx, by, 'lightcoral', "Kamera Sifirla"); by -= 40
        self.add_action_button(app.toggle_scope, False, bx, by, 'mediumseagreen', "Sadece Secili Pasoya"); by -= 40
        by -= 20
        self.add_action_button(lambda v: app.toggle_tabs("advanced" if v else ""), False, bx, by, C_ADV, "Gelismis Ayarlar"); by -= 40
        self.add_action_button(lambda v: app.toggle_tabs("visual" if v else ""), False, bx, by, C_VIS, "Gorsel Ayarlar"); by -= 40

        # --- OYNAT / DURDUR ---
        start_btn = self.add_action_button(
            lambda v: app.sim_controller.run(v, app.path_gen.last_calculated_paths, app.params), 
            False, bx, by, 'cyan', "SIMULASYON OYNAT"
        )
        by -= 40
        
        stop_btn = self.add_action_button(app.sim_controller.stop, False, bx, by, 'red', "SIMULASYON DURDUR")
        
        # Controller'a butonları tanıt
        app.sim_controller.set_widgets(start_btn, stop_btn)