# SpinningCam — Kod Navigasyon Kılavuzu

Hangi konuya bakacaksın → hangi dosya ve satır.
Token tasarrufu için bu kılavuzu bağlam olarak ver, tüm dosyaları okutma.

---

## Mimari Özet

```
SpinningCamWindow (ui/main_window.py)   ← Tkinter penceresi, menü, export
    ├── SpinningApp (main.py)            ← Tüm state: self.params dict
    │       ├── MandrelManager           ← STEP yükleme, profil analizi
    │       ├── PathGenerator            ← Yol hesaplama + G-code üretimi
    │       └── SimulationController     ← Animasyon döngüsü
    ├── ProcessTab (ui/tabs/process_tab.py)   ← Görsel + güvenlik ayarları
    ├── ProgramTab (ui/tabs/program_tab.py)   ← Operasyon listesi
    └── MachineTab (ui/tabs/machine_tab.py)   ← Makine + post-processor

GCodeToSCLConverter (recipe_to_scl.py)  ← G-code → SCL dönüşümü
ExportManager (export_manager.py)        ← PDF / STL / SCL export koordinasyonu
i18n.py                                  ← Çok dilli metin (EN/TR/ES), t(key) fonksiyonu
```

---

## Konu → Dosya Haritası

### 1. Koordinat sistemi / Post-processor dönüşümü
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Dönüşüm formülü (X_machine = ...) | `path_generator.py` | `transform_pt()` ~670 |
| Makine origin, invert, offset ayarları UI | `ui/tabs/machine_tab.py` | `_create_widgets()` satır 19–119 |
| Home/retract parametreleri | `ui/tabs/machine_tab.py` | satır 193–238 |
| PLC koordinat sistemi referansı | `CAM_INTERFACE_SPEC.md` | Bölüm 2 |

### 2. Yol hesaplama (toolpath)
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Ana giriş noktası | `path_generator.py` | `calculate_paths()` satır 61 |
| Spline (standart) pas | `path_generator.py` | `_create_and_store_pass()` satır 353 |
| Konformal (adaptive) pas | `path_generator.py` | `_create_adaptive_pass()` satır 266 |
| Sweeping/ironing pas | `path_generator.py` | `_create_sweeping_pass()` satır 873 |
| Rapid segment güvenli yol | `path_generator.py` | `_safe_rapid_segments()` satır 737 |
| Legacy → ops dict migration | `path_generator.py` | `_ensure_ops_dict()` satır 13 |

> **ÖNEMLİ — Offset yönü tutarsızlığı (2026-06-24 düzeltmesi)**
> `total_off = r_tool + blank_thick + safety + allowance` tüm pas türleri için aynı formüldür.
> Farkı: roughing P2 ve **straight-line finishing** bu değeri **radyal** uygular (`+total_off` sadece X'e).
> **Sweeping finishing** ise yüzey normali yönüne uygular (`nx*total_off`, `nz*total_off`).
> Roughing ile karşılaştırmalarda daima straight-line mi sweeping mi olduğuna bak.
> Bkz. LAST_CHANGES.md → 2026-06-24 girişi.

### 3. G-code üretimi
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| G-code string üretimi | `path_generator.py` | `generate_gcode()` satır 513 |
| G-code kaydetme (UI) | `ui/main_window.py` | `save_gcode_logic()` satır 374 |
| Başlık/footer template parametreleri | `main.py` `load_settings()` | `gcode_header`, `gcode_footer` |

### 4. SCL / TIA Portal export
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| G-code → recipe line parse | `recipe_to_scl.py` | `parse_gcode()` satır 110 |
| SCL text üretimi | `recipe_to_scl.py` | `generate_scl()` satır 288 |
| Dosyaya yaz | `recipe_to_scl.py` | `convert_file()` satır 414 |
| Export wrapper | `export_manager.py` | `export_scl()` satır 179 |
| UI dialog + limit kontrolü | `ui/main_window.py` | `export_scl_action()` satır 502 |
| PLC format tam spec | `CAM_INTERFACE_SPEC.md` | Tüm doküman |
| PLC data type tanımları | `CAM_INTERFACE_SPEC.md` | Bölüm 10 |

### 5. Operasyon yönetimi (roughing / finishing)
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Operasyon listesi UI | `ui/tabs/program_tab.py` | `ProgramTab` sınıfı |
| Yeni operasyon ekleme | `ui/tabs/program_tab.py` | `add_op()` satır 295 |
| Operasyon seçme / düzenleme | `ui/tabs/program_tab.py` | `on_op_select()` satır 109 |
| Süre tahmini | `ui/tabs/program_tab.py` | `update_time_estimate()` satır 102 |
| Hız bölgeleri (zones) dialog | `ui/dialogs/zone_manager.py` | — |
| Ops dict params içinde | `main.py` `load_settings()` | `params["operations"]` list |

### 6. Mandrel / STEP yükleme
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| STEP yükleme | `main.py` | `load_step_file()` satır 634 |
| Mandrel analizi (profil, radius) | `mandrel_analyzer.py` | `MandrelManager` sınıfı |
| Shell mesh üretimi | `mandrel_analyzer.py` | `generate_shell_mesh()` |
| STEP prompt (UI) | `ui/main_window.py` | `load_step_prompt()` satır 321 |

### 7. 3D sahne güncelleme
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Ana güncelleme fonksiyonu | `main.py` | `update_scene()` satır 218 |
| Mandrel + blank render | `main.py` | satır 280–300 |
| Workspace kutu render | `main.py` | satır 301–316 |
| Yol render (renkler, tubes) | `main.py` | satır 325–474 |
| Rulo + mesafe etiketi | `main.py` | satır 479–511 |
| Kamera konumu | `main.py` | satır 513–526 |

### 8. Parametre yönetimi (state)
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Tüm parametre varsayılanları | `main.py` | `load_settings()` satır 76–135 |
| Parametre güncelleme entry point | `main.py` | `on_param_change()` satır 530 |
| Nested key güncelleme (`operations[0].tool_id`) | `main.py` | satır 543–553 |
| JSON kayıt | `main.py` | `save_settings_json()` satır 165 |
| Kalıcı ayar dosyası | `settings.json` | — |

### 9. Çarpışma tespiti / clearance
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Normal-aligned clearance düzeltme | `path_generator.py` | satır 399–415 |
| Uniform shift düzeltme (iteratif) | `path_generator.py` | satır 418–435 |
| Debug lines hesaplama | `path_generator.py` | satır 438–471 |
| Debug lines görselleştirme | `main.py` | satır 421–474 |
| Ayarlar UI | `ui/tabs/process_tab.py` | "Safety & Correction" bölümü satır 159–175 |

### 10. Workspace sınır görselleştirme
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| 3D kutu render | `main.py` | satır 301–316 |
| Workspace UI ayarları | `ui/tabs/machine_tab.py` | satır 266–304 |
| Params varsayılanları | `main.py` `load_settings()` | `workspace_show`, `workspace_x_max`, `workspace_z_min`, `workspace_z_max` |

### 11. Export (PDF / STL / Recipe CSV)
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| PDF operation sheet | `export_manager.py` | `export_pdf()` satır 49 |
| STL part shell | `export_manager.py` | `export_stl()` satır 19 |
| CSV recipe (legacy) | `export_manager.py` | `export_recipe()` satır 144 |
| PDF UI trigger | `ui/main_window.py` | `export_pdf_action()` satır 392 |
| STL UI trigger | `ui/main_window.py` | `export_stl_action()` satır 417 |

### 12. Simülasyon
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Simülasyon motoru | `simulation_controller.py` | `SimulationController` sınıfı |
| Başlatma (UI) | `ui/main_window.py` | `run_sim()` satır 342 |
| Polling loop (50fps) | `ui/main_window.py` | `check_sim_loop()` satır 264 |
| Roller güncelleme | `main.py` | `update_roller_visual()` satır 612 |
| Live monitor (POS/S/F) | `ui/main_window.py` | `_update_live_monitor()` satır 278 |

### 13. Görsel / kamera ayarları
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Camera preset butonlar | `ui/tabs/process_tab.py` | satır 66–114 |
| Camera save/reset | `ui/tabs/process_tab.py` | satır 38–64 |
| Velocity color mode | `ui/tabs/process_tab.py` | satır 24 |
| Konformal path ayarları | `ui/tabs/process_tab.py` | satır 177–192 |

### 14. Takım kütüphanesi
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Yükleme/kayıt | `ui/main_window.py` | `load_tools()` / `save_tools()` satır 363 |
| Takım veri dosyası | `tools.json` | iki ayrı alan — bkz. aşağıdaki tablo |
| Tool manager dialog | `ui/dialogs/tool_manager.py` | `entry_r_tool` widget satır ~49 |
| Program tab'de tool seçimi | `ui/tabs/program_tab.py` | `on_tool_change` satır ~559, ~618 |
| STEP'ten disk yarıçapı hesabı | `tool_step_loader.py` | `get_contact_radius()` satır 162 |
| STEP canonical mesh (3D sim) | `tool_step_loader.py` | `get_canonical_mesh()` |
| STEP 2D profil (kalibrasyon canvas) | `tool_step_loader.py` | `get_2d_profile()` |
| 2D profil: Rx(-alpha) neden? | `LAST_CHANGES.md` | 2026-06-20 bloğu |
| r_tool semantics düzeltmesi | `LAST_CHANGES.md` | 2026-06-22 bloğu |

**`tools.json` alanları — kritik ayrım:**

| Alan | Örnek (T0103) | Kullanım | Kaynak |
|------|--------------|----------|--------|
| `radius` | 74.31 (≈çap/2) | Fallback; T0101/T0102 r_tool null ise operasyon r_tool'una yazar | `get_contact_radius()` / 2 (2026-06-22'den beri düzeltildi) |
| `r_tool` | 79.5 | **Path gen + kalibrasyon için esas değer.** Operasyon dropdown'ından seçim yapılınca buradan okunur | Manuel kalibrasyon |

**Kural:** `on_tool_change` önce `tools.json["r_tool"]` okur (kalibre); null ise `tools.json["radius"]`'e düşer.
`operations[i].r_tool` = path generator'ın kullandığı efektif mesafe (makine X ref → temas noktası).

### 16. Touch Point Calibration Dialog
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Diyalog sınıfı | `ui/dialogs/touch_calibration.py` | `TouchCalibrationDialog` |
| UI oluşturma | `touch_calibration.py` | `_create_widgets()` satır ~100 |
| X delta hesabı | `touch_calibration.py` | `_compute_x_delta()` satır 493 |
| Z delta hesabı | `touch_calibration.py` | `_compute_z_delta()` satır 522 |
| Calculate butonu | `touch_calibration.py` | `_calculate()` satır 951 |
| Apply butonları (5 adet) | `touch_calibration.py` | `_apply_home_x/z`, `_apply_cx` vb. |
| 2D canvas çizimi | `touch_calibration.py` | `_draw_scene()` satır ~1227 |
| STEP 2D profil noktaları | `touch_calibration.py` | `_get_tool_profile_pts()` satır ~1207 |
| Profil polygon çizimi | `touch_calibration.py` | `_profile_flat()` helper, satır ~1497 |
| Tutarlılık kontrolü | `touch_calibration.py` | `_check_consistency()` satır 1175 |
| Formül referans popup | `touch_calibration.py` | `_show_formula_reference()` |
| Makine parametreleri | `touch_calibration.py` | `_machine_params()` |
| CAM↔Machine dönüşümü | `touch_calibration.py` | `_cam_to_mach_x/z`, `_mach_to_cam_x/z` |

**Koordinat matematiği özeti:**
```
cam_x_contact = cx_man + side × (mandrel_R + blank + r_tool)
expected_mach_x = cam_x_contact × dir_x + offset_x   (home veya origin moduna göre)
delta = actual_DRO_X - expected_mach_x
new_home_x = home_x - delta / dir_x
```
`r_tool` (79.5mm T0103) = makine X referansından rulosu temas noktasına radyal mesafe.
Disc dış yarıçapı (148.62mm) ile AYNI DEĞİLDİR.

### 17. Uluslararasılaştırma (i18n) — 2026-06-21

| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| String sözlüğü + `t(key)` fonksiyonu | `i18n.py` | `STRINGS` dict, `t()`, `set_language()`, `get_language()` |
| Dil değiştirme, menü, rebuild tetikleyici | `ui/main_window.py` | `_change_language()`, `rebuild_all_tabs()`, `_create_menu()` |
| Dil kalıcılığı | `settings.json` | `"language"` alanı |
| ProcessTab rebuild | `ui/tabs/process_tab.py` | `rebuild()` |
| MachineTab rebuild | `ui/tabs/machine_tab.py` | `refresh_ui()` (zaten vardı) |
| ProgramTab rebuild + `t` çakışma düzeltmesi | `ui/tabs/program_tab.py` | `rebuild()`, tüm `t` → `tl` döngü değişkenleri |
| ToolManager dialog çevirisi | `ui/dialogs/tool_manager.py` | Tüm `t()` çağrıları |

**Yeni string ekleme kuralı:**
Her yeni UI string için `i18n.py`'deki `STRINGS` sözlüğüne EN / TR / ES üç karşılık birden eklenmelidir.

**Dil değişim akışı:**
```
Language menüsü → _change_language(lang)
  → set_language(lang)          # i18n._lang güncellenir
  → params["language"] = lang
  → save_settings_json()        # settings.json'a yazılır
  → _create_menu()              # menü radio button güncellenir
  → rebuild_all_tabs()          # tüm tab'ler widget'larını yeniden oluşturur
```

### 18. Makine tipleri / adapter katmanı — 2026-07-02

| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Adapter sınıfları + tip kodu → sınıf | `machine_adapter.py` | `ADAPTERS`, `TYPE_DESCRIPTIONS` |
| Yetenek kancaları | `machine_adapter.py` | `get_available_op_types/ui_sections/export_formats/kinematics`, `supports_heating` |
| Profil yükleme / MACHINE_PROFILE_KEYS | `machine_loader.py` | — |
| Profil dosyaları | `machines/ID111-1.json`, `machines/ID112-1.json` | — |
| Startup seçici (lisans + makine) | `ui/dialogs/machine_selector.py` | `MachineSelector` |
| Adapter atama + path-gen swap | `ui/main_window.py` | `_load_machine_profile()` |
| Op düğmeleri adapter'dan | `ui/tabs/program_tab.py` | `_op_buttons` haritası ~224 |
| Bölüm gizleme adapter'dan | `ui/tabs/machine_tab.py` | `_create_widgets` sonundaki `section_frames` |
| Export menü gating | `ui/main_window.py` | `_create_menu` (scl/recipe_csv) |

**Makine ID formatı:** `ID{tip}-{seri}` — hane1 kategori (1=lathe), hane2 proses
(1=spinning), hane3 varyant (1=two-axis basic, 2=hot/tilt-arm). 112 yol haritası:
TODO.md #50–#52.

### 19. Döner kol (B ekseni) kinematiği — ID112, 2026-07-02

| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Kinematik model (forward/inverse/clamp/reachable) | `kinematics.py` | `TiltArmKinematics`, `get_kinematics(params)` |
| Profil anahtarları (tilt_pivot_x/z, tilt_b_min/max/home/sign) | `machine_loader.py` | `MACHINE_PROFILE_KEYS` başı |
| Nokta başına eğim dizileri | `path_generator.py` | `last_tilt_angles`, `_compute_tilt_for_path()`, `_path_op_map` |
| G-code B kelimesi + erişilebilirlik uyarıları | `path_generator.py` | `generate_gcode` içinde `_b_word()`, `last_kinematic_warnings` |
| Rulo mesh eğimi | `tool_step_loader.py` | `_position_mesh(tilt_deg=)` |
| Statik sahne + canlı rulo eğimi | `main.py` | `update_scene` `_static_tilt`, `update_roller_visual(tilt_deg=)` |
| Simülasyonda anlık B | `simulation_controller.py` | `current_tilt`, `run(tilts=)` |
| Canlı monitörde B | `ui/main_window.py` | `check_sim_loop`, `_update_live_monitor` |
| Op editör eğim alanları (tilt_mode/offset/start/end) | `ui/tabs/program_tab.py` | direction combobox'tan sonra, tilt_arm-gated |
| Pas bilgisinde "B start → end" | `ui/tabs/program_tab.py` | `refresh_pass_info` |
| Makine sekmesi "Döner Kol" bölümü | `ui/tabs/machine_tab.py` | `f_tilt`, section_frames `"tilt_arm"` |
| PDF pas başına B tablosu | `export_manager.py` | `export_pdf(tilt_angles=)` |

**Konvansiyon:** eğim θ=0° = radyal kızak (ID111 duruşu); pozitif θ takımı +Z'ye eğer.
`B = θ·tilt_b_sign + tilt_b_home`. Forward: `tip_x = pivot_x + side·x_arm·cos θ`,
`tip_z = z_car + pivot_z + x_arm·sin θ` (side = roller_positive_x_side işareti).
Eğim dizileri geometriden deterministik (normal modda Z'den, interp modda yay
uzunluğundan) → PLC decimation alt kümesinde yeniden hesaplanınca birebir aynı.
Per-op anahtarlar: `tilt_mode` ("normal"|"interp"), `tilt_offset`, `tilt_start`, `tilt_end`.
Geri (back) paslarda interp uçları otomatik ters çevrilir.

### 15. PLC mod decimation
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Ana decimation fonksiyonu | `path_generator.py` | `_decimate_path_for_plc()` ~1518 |
| RDP yardımcısı | `path_generator.py` | `_rdp_decimate()` ~1481 |
| PLC modu etkinleştirme | `generate_gcode()` | satır ~1098 |
| Yaklaşım kolu ayrımı (2026-06-17) | `path_generator.py` | `approach_end_idx` parametresi ~1518 |

**Parametreler (`_decimate_path_for_plc`):**
| Parametre | Kaynak | Açıklama |
|-----------|--------|----------|
| `approach_end_idx` | `last_render_split_idx[i][0]` (T1) | Yaklaşım kolunu RDP'den ayırır; 2 pt korunur |
| `arc_end_idx` | `last_render_split_idx[i][1]` (T2) | Fileto ile exit eğrisini ayırır; exit kendi T2→P3 kirişini alır |
| `exit_tolerance` | `params["plc_exit_tolerance"]` | Exit bölümü için bağımsız RDP toleransı |

**Exit yolu şekli (`path_generator.py` ~814):**
| Parametre | Açıklama |
|-----------|----------|
| `exit_arc_angle` (°) | T2→P3 dairesel yayı için tanjant-kiriş açısı. 0=düz. Pozitif=dışa (X artar), negatif=içe. R=chord/(2·sin α). `exit_bow` ve `exit_curve_tension` kaldırıldı. |

Spline / geri pas: tüm parametreler `None` → orijinal critical-split davranışı.
Bkz. `LAST_CHANGES.md` 2026-06-17 (üç ayrı entry).

---

## Proje Başlatma Akışı

```
main.py → SpinningCamWindow.__init__()
  → SpinningApp(headless=True)          # params yüklenir
  → _setup_layout()                     # Tabs oluşturulur
  → app.plotter.show()                  # PyVista window açılır
  → after(600, load_step_prompt)        # STEP dialog
  → check_sim_loop()                    # 50fps polling başlar
  → embed_plotter()                     # Win32 API ile PyVista Tkinter'e embed edilir
```

## G-code → SCL Dönüşüm Akışı

```
save_gcode_logic() [main_window.py:374]
  → path_gen.generate_gcode() [path_generator.py:513]
  → dosya kaydedilir (.nc)

export_scl_action() [main_window.py:502]
  → ExportManager.export_scl() [export_manager.py:179]
  → GCodeToSCLConverter.convert_file() [recipe_to_scl.py:414]
      → parse_gcode() [satır 110]     # .nc → RecipeLineData listesi
      → generate_scl() [satır 288]    # listesi → SCL text
  → dosya kaydedilir (.scl)
```

---

## Parametre Davranış Rehberi

### Hangi parametre ne zaman etkili olur?

| Parametre | UI Adı | Roughing Spline | Roughing Linear | Finishing |
|---|---|---|---|---|
| `pass_angle` | Pass Angle (deg) | ✅ P3 yönünü değiştirir | ✅ | ❌ |
| `rot` | Rotation (deg) | ✅ Spline'ı P2 etrafında döndürür | ❌ sessizce yoksayılır | ❌ |
| `auto_calc_angle` | Auto-Calc Angle | ✅ Rotasyonu yüzey normalinden hesaplar | ❌ sessizce yoksayılır | ❌ |
| `normal_aligned_shift` | Normal-Aligned Correction | ✅ Clearance düzeltmesini normal yönünde yapar | ✅ | ❌ |
| `adaptive_rough_mode` / `conformal_clearance` | Conformal Path - Rough / Conformal Clr | ✅ P2'yi yüzey normali yönünde yerleştirir | ✅ | ❌ |
| `adaptive_finish_mode` | Conformal Path - Finish | ❌ | ❌ | ✅ per-point normal offset |

**Neden Rotation / Auto-Calc Angle linear'da çalışmıyor?**
`_create_and_store_pass()` line 851: `if pass_shape in ("linear_approach", "linear_full"): final_rot = 0.0` — unconditional. Linear şekillerde yön pass_angle ile kontrol edilir, rotation kilitlidir.

**Neden Normal-Aligned Correction finishing'de çalışmıyor?**
Finishing pasları `_create_and_store_pass()`'dan geçmez (`_create_sweeping_pass` veya `_create_adaptive_pass` kullanır). `normal_aligned_shift` sadece `_create_and_store_pass` içindedir.

### Hedefe Göre Doğru Parametre

| Hedef | Yanlış Parametre | Doğru Parametre |
|---|---|---|
| Pası mandrel yüzeyine daha dik yaklaştır | Pass Angle | **Rotation (Rot)** veya **Auto-Calc Angle** (spline) |
| P3 çıkış yönünü değiştir | Rotation | **Pass Angle** |
| Konik mandrel'de clearance'ı doğru tut | Sadece radyal offset | **Conformal Clr** (roughing) / **Conformal Path - Finish** |
| Clearance düzeltmesinde şekli koru | Uniform shift (varsayılan) | **Normal-Aligned Correction** |

### PARAM_DEBUG Log Çıktısı

`spinning_cam.log` dosyasında `[PARAM_DEBUG]` ile arama yapın. Her pas için:
```
[PARAM_DEBUG] 'roughing 1' (global pass 1): pass_angle=120.0° | θ_A=-51.3° θ_B=68.7° | P3 offset → X=+16.28mm Z=+41.69mm
[PARAM_DEBUG] 'Roughing 1' control pts: P1=(148.50, Z=10.00)  P2=(120.00, Z=60.00)  P3=(136.28, Z=101.69)
[PARAM_DEBUG] 'Roughing 1' rotation: auto_align ON | surface_angle=0.0° base_rot=0.0° | raw=0.0° → final=0.0°
[PARAM_DEBUG] 'Roughing 1' clearance iter 1: min_clearance=-2.145mm → shifting P2 X: 120.00 → 122.65
[PARAM_DEBUG] 'Roughing 1' RESULT: 87 pts | P2 X: 120.00 → 122.65 (shift +2.65mm) | rotation=0.00°
```

### Bilinen Sorunlar / Dead Code

- `auto_align_rotation` (`path_generator.py` line 76): okunuyor ama line 208'de `auto_calc_angle` tarafından üzerine yazılıyor — hiçbir zaman kullanılmıyor.
- `back_pass_arc_x/z`: spline pasları için **2026-06-17'de düzeltildi** (artık çalışıyor).

---

*Oluşturulma: 2026-05-03 — Kaynak: tüm .py dosyaları okunarak çıkarıldı*
*Son güncelleme: 2026-06-21 — i18n sistemi (Bölüm 17), mimari şemasına i18n.py eklendi*
