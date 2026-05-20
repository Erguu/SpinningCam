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
| Takım veri dosyası | `tools.json` | — |
| Tool manager dialog | `ui/dialogs/tool_manager.py` | — |
| Program tab'de tool seçimi | `ui/tabs/program_tab.py` | satır 163–187 |

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

*Oluşturulma: 2026-05-03 — Kaynak: tüm .py dosyaları okunarak çıkarıldı*
