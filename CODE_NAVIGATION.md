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
| **Mil hızı tekrarları elenir (2026-08-31)** | `path_generator.py` | `_last_spindle` = son YAZILAN `(hız kodu, int devir)`; aynıysa `S..M3` yazılmaz. İKİ MUAFİYET: takım değişimi hep yeniden komutlar; özel `M3`/`M5` komutu `_emit_custom()` ile izlemeyi sıfırlar. recipe1: 28 → 3 ON. **AÇIK RİSK:** `CMD=20` saf setpoint mi, senkron noktası mı — PLC'ye sorulmadı. Test: `_test_spindle_dedup.py` |
| **Takım değişimi mili DURDURMAZ (2026-08-31)** | `path_generator.py` | Takım değişim bloğu (`tool_differs and current_tool is not None`) — eski `M5`+`M1` SİLİNDİ; taret otomatik, geri çekilme `G0`'ı asıl güvenlik. `M1` reçetede `CMD=1 F=0` oluyordu. Geri alma: `gcode.extend(["M5"])`. Test: `_test_toolchange_no_spindle_stop.py` |
| **Mil hızı modu (CSS KAPALI, 2026-08-31)** | `path_generator.py` | `CSS_SPEED_MODE_ENABLED` + `resolve_speed_mode(op)` — TEK doğruluk kaynağı. `op["speed_mode"]`'u DOĞRUDAN OKUMA: PLC'de CSS yok (`CMD=20` sabit devir), CSS m/dak'ı devirmiş gibi gidiyordu. Eski op'lar diskte "CSS" kalır, okurken RPM'e normalize edilir → reçetede sayı DEĞİŞMEZ. Test: `_test_speed_mode_css_off.py` |
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
| **DB blok öznitelikleri (load-memory, 2026-08-06)** | `recipe_to_scl.py` | `generate_scl()` DATA_BLOCK bloğu — `'FALSE'` erişim + `UNLINKED` (NON_RETAIN'den ÖNCE) + `VERSION : 0.2`; dizi boyu DİNAMİK (kullanıcı isteği, varsayılan 1000 = `DB_SelectedRecipe`); sözleşme = `02b_RecipePrograms.scl` başlık yorumu |
| **Parçalı diziler `Lines1..LinesN` (2026-08-14)** | `recipe_to_scl.py` | `chunk_geometry()` (saf matematik: g → `Lines[g//m+1][g%m]`, kapasite tam diziye yuvarlanır) + `generate_scl(chunk_size=...)`; `// CHUNKS: n x m` başlık satırı; `chunk_size=0` = eski tek dizi |
| **Üretilen dosyanın kendi kendini doğrulaması** | `recipe_to_scl.py` | `check_scl_geometry()` — `generate_scl` kendi çıktısını doğrular, tutmazsa `ValueError('GEOMETRY:...')` (dosya YAZILMAZ); CLI: `python recipe_to_scl.py --check dosya.scl` |
| **Başlık sağlaması (checksum, 2026-08-14)** | `recipe_to_scl.py` | `recipe_checksum()` — iki 32-bit akümülatör, `sumB` sıra-duyarlı, `LineCount` XOR'lanır; SADECE `CMD+Param+F` (X/Z float32↔float64 yüzünden BİLEREK hariç). Mutabık örnek = **1383**. Emisyon: `Header.ProvidesChecksum` + `Header.Checksum`, `ToolAngle_List`'ten SONRA. `emit_checksum=False` / CLI `--no-checksum` = kaçış kapağı (PLC UDT'si alanları alana kadar). PLC uyuşmazlıkta `16#0316` |
| **Paso işaretleri CMD=50/51 (2026-09-06, opt-in)** | `recipe_to_scl.py` | `scan_pass_markers()` (numaralar `(Op7:…)` + `(--- OP n: TIP - PASO m ---)` YORUMLARINDAN okunur, yeniden hesaplanmaz) + `count_pass_markers()` + `GCodeToSCLConverter(emit_pass_markers=)`. Kaynak yorum: `path_generator.generate_gcode` → `(--- OP n START: TIP ---)`, **SADECE `for_recipe`**. Anahtar `plc_pass_markers` (makine profili, varsayılan False). **KAPALI = bayt bayt eski çıktı.** Geri pas kendi no'sunu ALMAZ; Nokta op'u CMD=50 alır CMD=51 almaz. **`TotalOps` = op listesindeki SATIR sayısı** (kapalılar dâhil) — mektuptan BİLEREK sapma, bkz. LAST_CHANGES 2026-09-06. Bütçe: `auto_fit_plc_tolerance(emit_pass_markers=)` işaretleri fit'in İÇİNDE sayar. Test: `_test_pass_markers.py` (22) |
| Düzen sorma penceresi (kapasite + parça boyutu, canlı önizleme) | `ui/dialogs/scl_layout.py` | `SclLayoutDialog` — PLC referans geometrisi `PLC_REFERENCE_GEOMETRY` (10 × 100); ayar `params["scl_chunk_size"]` (makine profiline yazılır) |

### 4c. .ssp içindeki MAKİNE ayarları — 2026-08-14 (saha olayı)

`save_project` TÜM `params`'ı yazar (43/50 makine anahtarı dahil). Eskiden
`load_project` bunu süzmeden uyguluyordu → eski program açmak makine ayarlarını
geri alıyor, sonraki Makine-sekmesi düzenlemesi `autosave_machine_profile` ile
KALICI yapıyordu. Artık makine anahtarları dosyadan uygulanmaz; fark varsa sorulur.

| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Fark tespiti (sadece `MACHINE_PROFILE_KEYS`, normalize karşılaştırma) | `machine_loader.py` | `diff_machine_params()`, `_same_value()` (JSON gidiş-dönüşü fark DEĞİL; `True` ≠ `1.0`) |
| Makine anahtarlarını süz | `machine_loader.py` | `strip_machine_params()` |
| Yükleme politikası (varsayılan "benimki"; `None` = iptal) | `main.py` | `load_project(filepath, on_machine_conflict=None)` |
| Soru penceresi (Ayar/Sizinki/Programdaki/Kullanılacak) | `ui/dialogs/project_params_diff.py` | `ProjectParamsDiffDialog`; etiket haritası `_LABELS` (mevcut Makine-sekmesi i18n anahtarları) |
| Pencereyi bağlama | `ui/main_window.py` | `open_project_action` → `_ask_machine_conflicts` |

**GOTCHA:** `save_project` makine anahtarlarını yazmaya DEVAM ediyor — bilerek;
karşılaştırmanın "programdaki" tarafı odur. Yazmayı kesersek eski dosyalarla
karşılaştırma yapılamaz.

| Kütüphanede olmayan takım → export ENGELİ | `main.py` `missing_library_tools()` + `ui/main_window.py` `_blocked_by_missing_tools()` (hem .nc hem .scl) | `sync_operation_r_tools`'un kör noktası: bulunamayan takım ATLANIR → op, .ssp'deki bayat `r_tool`'u (başka makinenin kalibrasyonu) kullanmaya devam eder |

### 4b. Kesme / Kıvırma (cutting / bending) — 2026-07-31, v1.015

| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Başlangıç/bitiş çözücü (+ eski alan geri düşüşü) | `path_generator.py` | `resolve_bend_points()` (`resolve_pass_retract` yanında) |
| Motor dalı (tek 2-noktalı besleme çizgisi) | `path_generator.py` | `calculate_paths` içinde `if op_type_str in ("cutting","bending")` |
| Emitter pas sayısı kilidi (desync guard) | `path_generator.py` | `generate_gcode` → `emit_count` |
| Migrasyon (`z_pos`+`plunge_x` → 4 alan) | `config_schema.py` | `migrate_bend_points()`; çağrı `main.py` `load_project` |
| UI alanları / evren / sütun / batch | `ui/tabs/program_tab.py` | `_CUT_BEND_POINTS`, `on_op_select` cut/bend dalı, `_factory_op` |
| Takım değişim alanları (TÜM tipler, paylaşılan) | `ui/tabs/program_tab.py` | `_add_tool_change_fields()` — ortak yoldan VE cut/bend dalından çağrılır |
| Test | `_test_bend_points.py` | 7 paket |

**Model:** op = START → END arası TEK düz besleme çizgisi. `plunge_start_x/z` →
`plunge_end_x/z`, ikisi de kullanıcı girer. Start Z ≠ End Z → eğik/eksenel kıvırma.
Feed = op'un kendi Feed'i. `count` YOK SAYILIR (her zaman 1 yol).

**GOTCHA'lar:**
- `plunge_*` X'leri **makine/DRO X'i** (takım referansı) — parça yarıçapı DEĞİL.
  Temas noktası `r_tool` kadar içeride; `measure_min_clearance` de böyle varsayar.
- Bu dalda **clearance/gouge kontrolü YOK** — girilen nokta aynen sürülür.
- **v1.015 ÖNCESİ:** sadece `z_pos` + `plunge_x` vardı, başlangıç GİZLİCE
  `plunge_x + |retract_x|` idi → geri çekilme alanı besleme mesafesini belirliyordu.
  Migrasyondan geçmemiş op'lar (preset, `ops_library.json`) hâlâ bu yoldan çalışır.
- **`OP_PARAM_UNIVERSE` ↔ `on_op_select` senkron sözleşmesi:** universe'te olup
  editörde render EDİLMEYEN bir anahtar = Görünümü Özelleştir'de sütun seçilebilir
  ama düzenlenemez alan. Takım değişim anahtarları 2026-07-21'den 07-31'e kadar tam
  olarak bu durumdaydı. Yeni alan eklerken İKİ tarafı da güncelle.

### 4f. Pas geri çekilmesinde EKSEN SIRASI — 2026-09-03, v1.028

Op alanı `retract_motion`: `synchronized` (VARSAYILAN) / `x_first` / `z_first`.

| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| **TEK doğruluk kaynağı** | `path_generator.py` | `retract_segments(end_pt, dx, dz, motion)` — 5 çağrı yeri |
| Mod çözücü + risk yüklemi | `path_generator.py` | `resolve_retract_motion()`, `retract_motion_is_risky()` (= `z_first`) |
| Emitter (2 yer) | `path_generator.py` | `generate_gcode` → ileri pas retract + geri pas (BP) retract |
| Sim (3 yer) | `path_generator.py` | `calculate_paths` → kesme/kıvırma, ileri pas, geri pas |
| Uyarı toplama | `path_generator.py` | `last_retract_motion_warnings`; log `[RETRACT]` |
| UI alanı (İKİ editör dalından çağrılır) | `ui/tabs/program_tab.py` | `_add_retract_motion_field()` |
| Uyarı yüzeyi (SAKİN not, MODAL YOK) | `ui/main_window.py` | `refresh_retract_motion_status()` |

**`dx` fonksiyona YÖNÜNÜ ALMIŞ gelmeli** (`retract_x_offset_real` emitter'da,
`abs()` kanonik sim'de). `retract_segments` sadece ŞEKLE karar verir —
bkz. [[project_retract_sign_rule]].

**`z_first` = parçayı çizme riski.** Geri çekilme rulo İŞ ÜZERİNDEYKEN başlar.
Takım değişimi bloğu da önce Z gider ama SORUN DEĞİL: oraya gelindiğinde pas
retract'ı ruloyu zaten kaldırmıştır. Uyarı var, ENGEL YOK (kullanıcı kararı).

**SATIR MALİYETİ:** bölünmüş retract satırları İKİYE katlar → 1000 satır PLC
tavanı ([[project_scl_loadmem_format]]).

Ortak söz dağarcığı Nokta ile: `AXIS_MOTION_MODES`, `motion_waypoints`.
Test: `_test_retract_motion.py` (10), `_test_retract_motion_gui.py` (4).

### 4e. "Nokta" (Point) operasyonu — 2026-09-03, v1.027

Tek bir X/Z'ye git ve dur. Pas DEĞİL, konumlandırma hareketi.

| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Saf çözücüler | `path_generator.py` | `resolve_point_target()` (kanonik/gerçek çerçeve), `resolve_point_motion()`, `point_motion_waypoints()`, `resolve_point_feed()`; sabit `POINT_MOTION_MODES` |
| Sim dalı (takım yolu EKLEMEZ) | `path_generator.py` | `calculate_paths` → `if op_type_str == "point"` (kesme/kıvırma dalından ÖNCE) |
| Emitter dalı (`global_path_idx`'e DOKUNMAZ) | `path_generator.py` | `generate_gcode` → `emit_count` satırından ÖNCE |
| 3B üçgen | `main.py` | `update_point_markers()`; veri `path_gen.last_point_markers` (sonda aynalanır) |
| UI editörü | `ui/tabs/program_tab.py` | `on_op_select` → `if op_type == "point"`; `_POINT_KEYS`, `_factory_op` |
| Pas üretmeyen tipler (TEK isim) | `ui/tabs/program_tab.py` | `_NO_PASS_OP_TYPES` — Böl/Birleştir/Erişim/Açı/Pas tablosu guard'ları |

**KRİTİK KURAL — Point SIFIR takım yolu üretir.** `calculate_paths` ve
`generate_gcode` `paths_to_use` üzerinde ORTAK indeksle yürür; bir taraf ekleyip
diğeri eklemezse sonraki tüm paslar YANLIŞ operasyona kayar. Aynalar da atlamalı:
`pass_colors.path_categories`, `pass_table.compute_pass_rows` + `_op_start_pass_idx`,
`pass_compare._NO_PASS_TYPES`, `program_tab._op_logical_count` (**0** döner).

**REFERANS MODLARI (v1.029):** `point_mode` = `absolute` (VARSAYILAN, eski
davranış) / `surface` (X mandrelden — pasonun aynı yığını, `point_surface_x`) /
`relative` (önceki pasın FORMING sonundan ΔX/ΔZ) / `home` (Program Başlangıcından).
Okunamayan değer → `absolute`.

**⚠ `resolve_point_target` içinde `side`'ın İKİ İŞİ VAR:**
`side` = RULO tarafı (surface geometrisi, HER İKİ çağıranda);
`frame_flip = 1.0 if center_x is None else side` = çerçeve dönüşümü (ofsetler).
Karıştırılırsa `relative`/`home` negatif taraflı makinede TERS yönde uygulanır.
`resolve_tool_change_point` emitter'dan `side` OLMADAN çağrıldığı için orada bu
ayrım kendiliğinden doğru.

**ΔX işareti HARFİDİR** (retract'ın tersi, [[project_retract_sign_rule]]).

**X ÇERÇEVESİ:** `point_x` = MAKİNE/DRO X'i. `resolve_point_target(center_x=, side=)`
`resolve_tool_change_point` ile aynı dönüşümü yapar — bkz. [[project_canonical_x_frame]].
Yanlışı pozitif taraflı makinede TAMAMEN sessizdir.

`surface` modunda profil dışı Z → `last_point_warnings` + `refresh_point_status`
(amber, modal yok); editörde hesaplanan X `_point_surface_preview` ile gösterilir.

**Geri çekilme alanı YOK** (bilerek): hareketten sonra çalışır, konumu bozar.

Test: `_test_point_op.py` (15), `_test_point_op_gui.py` (6).

### 4c. Pas geri çekilmesi — işaret/yön kuralı (2026-07-31)

| Ne | Dosya | Fonksiyon |
|----|-------|-----------|
| Değer çözümü (op → global → 50 mm) | `path_generator.py` | `resolve_pass_retract()` |
| **Gerçek çerçevede YÖN** | `path_generator.py` | `retract_x_offset_real(retract_x, side)` = `abs(rx)*sign(side)` |
| Sim uygulaması (kanonik çerçeve, sonra aynalanır) | `path_generator.py` | `op_retract_x_can = abs(...)`; 3 nokta (cut/bend, ileri pas, geri pas) |
| Emitter uygulaması (gerçek çerçeve) | `path_generator.py` | `generate_gcode` → `ret_side`; ileri pas + geri pas retract satırları |
| Test | `_test_retract_sign.py` | 6 paket |

**Kural:** geri çekilme = "işten uzaklaş". BÜYÜKLÜK kullanıcının, YÖN makinenin
(`roller_positive_x_side`). Girilen işaret YOK SAYILIR.

**KAPSAM DIŞI:** `resolve_tool_change_point` ofsetleri harfi işaretini KORUR (orası
nişan alınan bir KONUM). `retract_z` de dokunulmadı (Z'de ayna yok).

**v1.015 ÖNCESİ HATA:** emitter işareti harfiyen kullanıyordu → negatif taraflı
makinede pozitif retract_x .nc'de parçaya doğru sürüyordu, sim ise uzaklaşıyordu.

### 4d. Program Sonu park noktası + temas kalibrasyonu hatırlatması (2026-08-03)

| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Çözücü (TEK doğruluk kaynağı) | `path_generator.py` | `resolve_program_end(params)` — `resolve_pass_retract` yanında |
| Emitter (post-processor'dan geçer) | `path_generator.py` | `generate_gcode` sonu, `_xf_pt(_end_x_cam, _end_z_cam)` |
| Sim (kanonik çerçeve, sonra aynalanır) | `path_generator.py` | `calculate_paths` sonu, `end_x_can` |
| UI bölümü + kilit mantığı | `ui/tabs/machine_tab.py` | `f_end`, `_sync_end_state()`, `add_end_spinbox` |
| Kalibrasyon hatırlatma etiketi | `ui/tabs/machine_tab.py` | `_calibration_note()`, `_add_calibration_note()`, `_refresh_cal_notes()` |
| Profil anahtarları | `machine_loader.py` | `end_use_home`, `end_x`, `end_z` |
| Test | `_test_program_end.py` (15), `_test_program_end_gui.py` (7) | — |

**Kural:** `end_use_home` varsayılan **True** → bitiş = Program Başlangıcı = eski davranış
birebir. Boş/bozuk alan O EKSENDE home'a düşer.

**GOTCHA — footer bunun yerine GEÇMEZ:** `gcode_footer` metni `generate_gcode` sonunda
`splitlines()` ile AYNEN eklenir. Post-processor dönüşümü YOK, makine profili
değişikliğini takip ETMEZ, simülasyona HİÇ girmez. Park hareketi için daima
`resolve_program_end` kullan.

**GOTCHA — hatırlatma etiketi bilerek DÖNÜŞTÜRMEZ:** `calibration_last_session`'daki
`entry_x`/`entry_z` ham DRO okumasıdır ve Program Başlangıcı bir CAM koordinatıdır;
etiket ikisi arasında matematik YAPMAZ (kullanıcı kararı 2026-08-03) — yoksa kalibrasyon
diyaloğuyla sessizce çelişebilecek ikinci bir dönüşüm yolu doğardı.

### 5. Operasyon yönetimi (roughing / finishing)
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Operasyon listesi UI | `ui/tabs/program_tab.py` | `ProgramTab` sınıfı |
| Yeni operasyon ekleme | `ui/tabs/program_tab.py` | `add_op()` satır 295 |
| Operasyon seçme / düzenleme | `ui/tabs/program_tab.py` | `on_op_select()` satır 109 |
| Süre tahmini | `ui/tabs/program_tab.py` | `update_time_estimate()` satır 102 |
| Op tablosu yatay kaydırma (çok sütun kırpılmasın) | `ui/tabs/program_tab.py` | `_create_widgets` `sb_x` (tree_ops `xscrollcommand`) |
| "Gerçek Bitiş Z" DEĞERİ (son forming pas, CAM Z, p2_z_extend dâhil) | `path_generator.py` | `calculate_paths` → `self.last_op_end_z[op_index]` (end_h belirlendikten hemen sonra) |
| "Gerçek Bitiş Z" SÜTUNU (değeri okur) | `ui/tabs/program_tab.py` | `_compute_op_end_z()` (sadece `path_gen.last_op_end_z` okur); `rebuild_tree_columns`/`refresh_ops_tree` "RealEndZ"; hook `main_window.py:47` |
| Zone Start/End Z sütunları (planlanan, yapılandırılabilir) | `ui/tabs/program_tab.py` | `start_z`/`end_z` → `OP_PARAM_UNIVERSE`/`_DEFAULT_COLUMNS`; etiket `lbl_zone_start`/`lbl_zone_end` |
| p2_z_extend → contact_z matematiği | `path_generator.py` | satır ~299–300 (`contact_z = target_z + p2_z_extend`); son pas `target_z = count<=1 ? start_h : end_h` |
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

### 12b. 3B görünüm anahtarları (görsel-only) — 2026-09-04, v1.030

| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Hızlı hareketleri göster/gizle | `main.py` | `params["show_rapids"]`; render `update_scene` rapid bloğu + siyah yaklaşma çizgisi |
| Uç kayması (temas noktasında çiz) | `main.py` | `params["show_tip_paths"]`; `_shift_path_to_tip()` |
| Hızlı hareket başına `r_tool` | `main.py` | `_rapid_rtools()` — `last_calculated_sequence`'i yürür (cut→rapid sırası); uzunluk tutmazsa TEK fallback |
| Nokta üçgeni uç kayması | `main.py` | `update_point_markers()` → `marker["op_index"]` → op `r_tool` |
| **.ssp'den geri yüklenmez** | `main.py` | `_VIEW_ONLY_PREF_KEYS` + `load_project` restore |
| Kutular | `ui/tabs/process_tab.py` | `cb_show_tip_paths`, `cb_show_rapids` (ikisi de `redraw_paths_cached()`) |

**KURAL:** uç kayması PASO + HIZLI HAREKET + NOKTA üçgenini BİRLİKTE kaydırmalı.
Hızlı hareket bir pasonun bittiği yerden başlar; biri kayıp diğeri kalmazsa
çizgiler buluşmaz. Test: `_test_view_toggles.py` (4 kombinasyon → AYNI G-code).

**Yeni görsel-only anahtar eklersen `_VIEW_ONLY_PREF_KEYS`'e de ekle**, yoksa
başkasının .ssp'si operatörün görünümünü sessizce değiştirir.

### 13. Görsel / kamera ayarları
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| **Pas renkleri (2026-08-31)** | `pass_colors.py` | `op_category()` (öncelik: kesme/kıvırma → **TERS** → tip), `path_categories()` (toolpath sırası, `calculate_paths` aynası), `resolve_palette()`, `tint()`, `ACTIVE_COLOR`. 3B (`main.py update_scene`) ve op listesi (`program_tab._op_color_tag`) AYNI fonksiyonları okur — ayrılırlarsa liste ile resim çelişir. Palet `params["pass_colors"]`, .ssp'den UYGULANMAZ (`load_project` korur). UI: `process_tab._add_pass_colors()`. Test: `_test_pass_colors.py`, `_test_pass_colors_gui.py` |
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
| Taşınabilir geometri: ID-adlı STEP çözümü (konvansiyon → fallback) | `tool_step_loader.py` | `_resolve_step_path()` + `TOOL_GEOMETRY_DIR="tool_geometry"` |
| Geometri kopya/rename + zip dışa/içe aktarma | `tool_library_io.py` | `sync_tool_geometry`, `export_library`, `import_library` |
| Takım penceresi Dışa/İçe Aktar düğmeleri + auto-copy | `ui/dialogs/tool_manager.py` | `export_library`/`import_library`/`_sync_geometry`; add/update_tool |
| Takım STEP dosyaları (ID-adlı: T0103.STEP) | `tool_geometry/` | SHIP_NEXT_TO_EXE'de; git'te izlenir |
| STEP'ten disk yarıçapı hesabı (VARSAYILAN, kiriş/2) | `tool_step_loader.py` | `get_contact_radius()` satır 171 |
| Challenger erişim (eksen-fit, SADECE kalibrasyon ekranı — opt-in) | `tool_step_loader.py` | `get_contact_radius_axis()` satır ~189 |
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
| **Challenger Rr (eksen-fit) etiket + "Use ▸"** | `touch_calibration.py` | `_refresh_challenger()`, `_use_challenger_rt()` (Rr satırı altı) |
| **Apply → sekme kutusunu tazeleme (2026-08-03b)** | `helpers_ui.py` | `register_param_var()`, `refresh_from_params(app)`; kanca `touch_calibration._show_applied` → `on_applied` |

> **GOTCHA — params'ı UI'ın arkasından değiştiren HER KOD bunu okumalı (2026-08-03b):**
> Sekmelerdeki girdi kutuları `app.params`'tan **BİR KEZ**, widget kurulurken tohumlanan
> bir Tk değişkeni tutar ve `<FocusOut>`'ta o değişkeni params'a **geri yazar**. Yani
> params'a dışarıdan yazmak yetmez: kutu eski sayıyı göstermeye devam eder (düğme
> çalışmamış görünür) **ve bir sonraki focus-out düzeltmenin üzerine bayat değeri yazar.**
> Böyle bir yazımdan sonra `helper.refresh_from_params(app)` çağır. Kalibrasyonun beş
> Apply düğmesi tam olarak bu yüzden bozuktu.
>
> **GOTCHA — Apply'lar `mode="all"` kullanmalı, `"paths"` DEĞİL:** `on_param_change`,
> "sadece bu pasa uygula" açıkken `mode=="paths"` düzenlemelerini `gui_pass_overrides`'a
> saptırır (`main.py:1575`) → global bir kalibrasyon düzeltmesi tek bir pasa yazılır.
> `_apply_blank` 2026-08-03b'ye kadar bu durumdaydı. Makine profili anahtarları
> (`_is_machine_key`) muaf, ama `final_part_thickness_on_mandrel` öyle DEĞİL.

> **Challenger Rr (2026-07-04, opt-in test):** mevcut `get_contact_radius` (kiriş/2)
> DEĞİŞMEDİ. Kalibrasyon ekranında seçili takım için `get_contact_radius_axis` değeri
> gösterilir; "Use ▸" değeri SADECE diyalogdaki Rr alanına yazar. `tools.json` yazılmaz
> (yalnızca okunur), hiçbir Apply düğmesi r_tool'a dokunmaz. Amaç: takım-A ile kalibre
> edip takım-B çalıştırınca kalan ~1 mm boşluğu fiziksel test etmek. Detay: LAST_CHANGES
> 2026-07-04, TODO #56.

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
Eğim dizileri geometriden deterministik — her iki modda da noktanın Z'sinden:
normal modda yüzey normali, interp modda op'un Start Z→End Z aralığında doğrusal
(bölge dışı uç açılara kırpılır; 2026-07-03'te pas-bazlıdan Z-bazlıya çevrildi) →
PLC decimation alt kümesinde yeniden hesaplanınca birebir aynı ve yön-bağımsız
(geri paslar özel işlem gerektirmez — aynı Z aynı açıyı verir).
Per-op anahtarlar: `tilt_mode` ("normal"|"interp"), `tilt_offset`, `tilt_start`
(op Başlangıç Z'sindeki açı), `tilt_end` (op Bitiş Z'sindeki açı).

### 20. Operasyon önerici (process planner) — 2026-07-03

| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Profil analizi (duvar açısı, sac Ø tahmini) | `process_planner.py` | `analyze_profile()` |
| Öneri motoru (paso sayısı, RPM, besleme) | `process_planner.py` | `suggest_operations()` |
| Malzeme tablosu yükleme / varsayılanlar | `process_planner.py` | `load_materials()`, `DEFAULT_MATERIALS` |
| Sezgisel sabitler (ayarlanabilir) | `materials.json` | — (yoksa ilk açılışta oluşur) |
| Öneri diyaloğu | `ui/dialogs/op_suggester.py` | `OpSuggesterDialog` |
| ✨Öner düğmesi + apply callback | `ui/tabs/program_tab.py` | `open_op_suggester()`, `_apply_suggested_ops()` |
| "+ Ekle ▾" dropdown + Aç/Kapat toggle | `ui/tabs/program_tab.py` | `_create_widgets` toolbar, `toggle_op_enabled()`, `_on_tree_double_click()` |
| Geri pas önerisi eşiği | `process_planner.py` | `BACK_PASS_BEND_THRESHOLD_DEG` (45°) |
| Yelpaze bitiş açısı (progressive_angle_end) | `path_generator.py` | pass_angle bloğu ~255; UI: `program_tab.py` Kademeli checkbox altı |
| Kademeli uzunluk (progressive_reach_end) | `path_generator.py` | pass_angle bloğu ~265 (`_L3` interp — yön açıdan, uzunluk bundan); UI: `program_tab.py` Kademeli Açı satırı altı |
| Sürüklenebilir panel ayırıcı + sidebar_width | `ui/main_window.py` | `_setup_layout` `_paned` (tk.PanedWindow) |
| Durum çubuğu yükseklik kilidi (banner zıplama fix) | `ui/main_window.py` | `_setup_layout` `frame_status.pack_propagate(False)` + `helpers_ui.py` `bind_tooltip` newline flatten |

**Kurallar:** advisory-only — "Yeni operasyon olarak ekle"ye kadar
`params["operations"]`'a dokunmaz. Paso sayısı = ceil(maks duvar açısı /
malzeme açı-per-paso), maks 12. Sıvama oranı β = Ø_sac / Ø_mandrel-MAJÖR.
RPM/besleme PLC sınırlarına kırpılır (2550 RPM / 3000 mm/dak).
Uyarılar/notlar (key, kwargs) → i18n `sug_warn_*` / `sug_note_*` ("neden" satırları).
Op pasifleştirme: `enabled` alanı — tree "Aktif" sütunu ✓/—, çift-tık toggle,
pasif op'lar hesaplamaya/G-code'a girmez (zaten `op.get("enabled")` ile atlanıyordu).

### 21. Görünümü Özelleştir — yapılandırılabilir sütunlar + Temel/Gelişmiş — 2026-07-04

| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Parametre evreni (tip başına, `on_op_select` ile ELLE senkron) | `ui/tabs/program_tab.py` | `OP_PARAM_UNIVERSE` (modül düzeyi) |
| Etiketler / grup bağımlılıkları / bölüm→anahtar | `program_tab.py` | `OP_PARAM_LABELS`, `GROUP_DEPS`, `SECTION_KEYS` |
| Varsayılan seed (temel set + sütunlar) | `program_tab.py` | `_DEFAULT_BASIC`, `_DEFAULT_COLUMNS`, `_default_cfg()` |
| Config çözücü (program → yoksa default) | `program_tab.py` | `_view_cfg()`, `_universe_for()` (tilt filtre) |
| Gizlenecek anahtarlar (grup bağımlılığı genişletir) | `program_tab.py` | `_hidden_keys()` |
| Editör görünürlük uygula (alan + boş başlık gizle) | `program_tab.py` | `_apply_field_visibility()`, `_add_section_header()` |
| Dinamik tablo sütunları | `program_tab.py` | `rebuild_tree_columns()`, `_column_union()`, `_cell_value()` |
| **#91 Sütun SIRASI** (görsel-only) | `program_tab.py` + `view_customizer.py` | `_display_order()` (Sel PINNED — ☑ handler'ları `"#1"` konumuna bakar), `_col_label()`; dialog: `_build_order_tab()`/`_move_col()`; config `op_view_col_order` (.ssp) |
| Alan satırı etiketleri | `program_tab.py` | helper'larda `f._pkey`, inline blok'larda `_pkey`, başlıklarda `_section` |
| Araç çubuğu düğme + Gelişmiş kutusu | `program_tab.py` | `_create_widgets` (`btn_customize`, `var_show_adv`) |
| Özelleştir diyaloğu | `ui/dialogs/view_customizer.py` | `ViewCustomizerDialog` (Column/Advanced/Batch/**Border** sütunları) |
| Kalıcılık + yükleme düzeltmesi | `main.py` | `load_project` (global anahtar korunur, .ssp'de config yoksa reset) |
| **#84 Etiket renkli çerçeve vurgusu** (GÖRSEL, opt-in) | `program_tab.py` | `BORDER_COLORS`, `_apply_label_highlights()`; config `op_view_config[tip]["highlight"]={key:renk}` |

**Kurallar:** SADECE görünüm katmanı — gizli alan değeri/takım yolu DEĞİŞMEZ.
`op_view_config` (program başına, .ssp) = {tip: {columns, advanced}}; `op_view_show_advanced`
= global (settings.json). Sütun başlığı/satır etiketi `OP_PARAM_LABELS` i18n anahtarından.
Tablo sütunu tüm tiplerin union'ı; satırın tipine uygulanmayan hücre "—". Yeni/eski
program yoksa `_default_cfg` ile makul varsayılana düşer.

### 22. Paketleme / exe doğrulama — 2026-07-04

| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Ne paketlenecek (TEK doğruluk kaynağı) | `packaging_manifest.py` | `SHIP_NEXT_TO_EXE`, `MUST_NOT_SHIP`, `NOT_SHIPPED`, `CRITICAL_MODULES` |
| Frozen exe öz-testi (GUI'siz) | `packaging_manifest.py` | `run_selfcheck()`, `ship_base_path()` |
| `--selfcheck` bayrağı | `main_tk.py` | `if "--selfcheck" in sys.argv` |
| Statik + post-build kontrol + kaynak tarama | `check_packaging.py` | `check_static()`, `check_post_build()`, `_DATA_RE` |
| Tek build reçetesi (+ manifest kopyala + kontrol çağır) | `build_exe.py` | post-build kopyalama döngüsü + `check_packaging --post-build` |
| Derleme sarmalayıcı (conda env aktive) | `build_exe.bat` | — |

**Kritik gerçekler:**
- Frozen'da `get_base_path()` = `dirname(sys.executable)` = **exe klasörü**, `_internal/`
  DEĞİL. Bu yüzden veri dosyaları exe YANINA kopyalanır (`--add-data` işe yaramaz).
- `cryptography` (lisans backend'i) derlenmiş backend içerir → `build_exe.py`'de
  `--collect-all=cryptography` ŞART.
- `images/` uygulama tarafından OKUNMUYOR (dev ekran görüntüleri) — paketlenmez.
- `license_private_key.pem` / `admin.lic` = `MUST_NOT_SHIP`; post-build sızıntı kontrolü var.
- DAİMA `spinning_cam` conda env'de çalıştır (OCC/fpdf/cryptography orada).
- Yeni runtime veri dosyası → `SHIP_NEXT_TO_EXE`'ye ekle; unutulursa kaynak tarayıcı uyarır.

### 22b. İlk-çalıştırma tohumlama (tohum/canlı ayrımı) — 2026-07-10 FAZ 2
| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Tohum → canlı kopyalama | `first_run_seed.py` | `seed_all()`, `seed_tools()`, `seed_machines()`, `_seed_one()` |
| Çağrı yeri (machine/tools YÜKLEMEDEN önce) | `ui/main_window.py` | `__init__`, `SpinningApp` sonrası (~satır 83) |
| İzlenen tohumlar | `tools.default.json`, `machines/<id>.default.json` | — |
| İgnore'lu canlı dosyalar | `.gitignore` | `tools.json`, `machines/*.json`, `!machines/*.default.json` |

**Kritik gerçekler:**
- Canlı dosya VARSA tohum ASLA üzerine yazmaz (idempotent, non-destructive).
- `settings.json` (FAZ 1) koddan yeniden kurulur; `tools`/`machines` KODDA YOK →
  izlenen `.default` tohumu ŞART. `machines/ID112-1` kendini yaratmaz → tohum kritik.
- Tohum ekini `_DEFAULT_SUFFIX = ".default"+".json"` parçalı yazılır ki kaynak
  tarayıcı (`_DATA_RE`) onu shiplenecek dosya sanmasın.

### 23. Değer KÖKENİ (provenance) + reçete denetimi — 2026-07-28

**ÇÖZÜM SIRASI (resolution order) — motorun tek doğruluk kaynağı `path_generator.py:556-675`:**

```
UZUNLUK (reach): |p3| ham  <  op.reach  <  kademeli yelpaze  <  takip(sac kenarı)  <  pas pin'i
YÖN   (angle)  : op.pass_angle          <  kademeli yelpaze  <  pas pin'i
ANKRAJ(target_z)/EXTEND/CLEARANCE      : op alanı            <  pas pin'i
```
Son yazan kazanır. Pin = `op["pass_edits"][str(i)][alan]`; staged = pas tablosunda
henüz Uygula'ya basılmamış düzenleme (pin'i de geçer).

⚠️ **ÖLÜ ALANLAR** (motor OKUMAZ, `export_manager._skip` içinde): op içindeki
`pass_overrides`. CANLI eski mekanizma = **üst düzey** `overrides`
(`app.gui_pass_overrides`, .ssp kökünde). İkisini karıştırma — ölü olanı kovalamak
klasik zaman kaybı.

| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Alan-başına köken kaydı (`row["prov"]`) | `ui/dialogs/pass_table.py` | `compute_pass_rows` içinde `_rec()`/`_org()`; `{alan: {source, value, losers}}` |
| Düz-dil açıklama + bulgu üretimi (SAF, Tk YOK) | `recipe_explain.py` | `explain_field()`, `find_overrides()`, `audit_operations()`, `format_report()` |
| **Alan-bazında gruplama — TEK doğruluk kaynağı** | `recipe_explain.py` | `group_overrides(rows)` → `{"ramp":…, "odd":…}`; `outlier_fields(rows)` → `{pas: {alan}}`. Hem denetim hem pas tablosu vurgusu bunu kullanır → ASLA çelişemezler |
| Pas tablosu açıklama çubuğu (hücreye tıkla) | `ui/dialogs/pass_table.py` | `_on_cell_click()`, `_PROV_COL`, `lbl_explain` (aykırıysa KIRMIZI + `rx_odd_prefix`) |
| Pas tablosu aykırı vurgusu | `ui/dialogs/pass_table.py` | `refresh()` içinde `_odd_map`; satır etiketi `"odd"` (kırmızı), hücrede `◆` öneki (`_mark(key, val, field)`) |
| "Pasım neden tuhaf?" penceresi | `ui/dialogs/recipe_audit.py` | `RecipeAuditDialog`, `SEV_MARK`; menü **Yardım (Help) altında** — Araçlar'da DEĞİL (kullanıcı kararı 2026-07-28) → `main_window.open_recipe_audit` |
| CLI (kayıtlı .ssp üzerinde, başsız) | `explain.py` | `--op N`, `--pass N`, `--step`, `--all`, `--lang` |
| Test | `_test_recipe_explain.py` | 24 kontrol |

### 23b. İki pası KARŞILAŞTIR (#104) — 2026-09-02

"Pasım neden tuhaf?" TEK pası açıklar; bu ise **KARŞILAŞTIRMALI** soruyu yanıtlar:
*şu iki pas aynı davranmalıydı, neden davranmıyor?* Cevap genelde pasın kendi
değerinde değil, **operasyon-seviyesi bir alanda** — bu yüzden tablo İKİ bölümlü.

| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Saf model (Tk YOK) | `pass_compare.py` | `list_passes()`, `pass_row()`, `build_rows()`, `apply_edits()`, `format_report()` |
| Pencere (tablo + hücre düzenleme) | `ui/dialogs/pass_compare_dialog.py` | `PassCompareDialog` |
| **İKİ ADIMLI seçim** (op → pas; düz liste 20 op'ta kullanılamaz) | `pass_compare.py` + dialog | `list_operations()`, `pass_choices()`, `op_label()`; dialog: `_build_pickers()`, `_sync_pickers()`, `_on_op_pick()` (pas no. SIĞDIĞI SÜRECE korunur), `_on_pass_pick()` |
| Giriş noktaları | `ui/tabs/program_tab.py` | `open_pass_compare()`; araç çubuğu `btn_compare` (seçime bağlı DEĞİL) + `_on_tree_right_click` satırı |
| Düzenlemenin hedefi | `pass_compare.py` | `edit_scope_options(row, op_type)` → `["pin"]` / `["pin","op"]` / `["op"]`; `PIN_KEYS` = motorun pas-başına OKUDUĞU beş alan (`path_generator.py:849`) |
| Bekleme (iki AYRI sözlük) | `pass_compare_dialog.py` | `staged_pins {(op,pas):{...}}` + `staged_ops {op:{...}}` — AYNI op'un iki pası karşılaştırılırken tek sözlük çakışırdı |
| Boş alanın gerçek varsayılanı | `pass_compare.py` | `_implied_default()`; sayılar `OP_PARAM_DEFAULTS`, mod/boolean `_IMPLIED_DEFAULTS` |
| Ölü (grup anahtarı kapalı) alanlar | `pass_compare.py` | `_DEP_OF` (= `GROUP_DEPS` tersi) → `_is_inert()`; fark sayılmaz |
| Test | `_test_pass_compare.py` (45), `_test_pass_compare_gui.py` | — |

**GOTCHA — `_IMPLIED_DEFAULTS`'taki iki `True` yazım hatası DEĞİL:**
`exit_bow_trim` ve `exit_mid_trim` varsayılanı **KIRP (True)** —
`path_generator.py:2341` ve `:2455`. False sayılırsa ikisi de kırpan iki
operasyon "farklı" raporlanır. `conformal_clearance_operation_specific` ise
False'a değil **GLOBAL** `conformal_clearance_all_operations`'a düşer.

**GOTCHA — hücrede `pc_src_*` kullanılır, `recipe_explain.source_label` DEĞİL:**
ikincisi cümle parçasıdır ("the operation setting") ve hücrede annote ettiği
sayıyı boğar. Uzun hâli yalnız alttaki açıklama çubuğunda.

**SALT-EK:** motorda, `compute_pass_rows`'ta ve op şemasında hiçbir değişiklik yok.

**Kurallar:**
- `prov` **tamamen ek** — hiçbir hesaplanan sayıyı değiştirmez (`_test_recipe_explain.py`
  motorla çapraz doğrular).
- Denetim **alan bazında gruplar**, pas bazında değil: bir alan TÜM paslarda pinliyse
  = bilinçli rampa (info); YALNIZCA BAZI paslarda pinliyse = **anomali**. Aranan
  sinyal budur. Otomatik değerin aynısını tekrarlayan pin gürültü sayılır (`_TOL`).
- **Şiddet katmanları** (`SEV_ORDER`): `error` (fiziksel tehlike — gouge) >
  **`hidden`** (düzene uymayan elle ayarlı değer — KIRMIZI+kalın, insanların bu
  pencereyi açma sebebi) > `warn` (tavsiye: boşta hareket, negatif klerens, eski
  override) > `info` (bilinçli rampa, kapalı op, artık veri). `hidden` KASITLI olarak
  amber tavsiyelerin ÜSTÜNDE — yoksa aranan satır onların arasında kayboluyor.
  Renk TEK BAŞINA yeterli değil → `SEV_MARK` metin işareti (‼ ◆ !) + kopyalanan
  raporda `=>` öneki.
- `mgr=None` (mandrel yok) → dosya-seviyesi kontroller yine çalışır (pin/gouge/artık).
- Salt-okunur: params'a yazmaz, takım yolu üretmez.

> **AYNA UYARISI:** `compute_pass_rows` motorun ELLE tutulan aynasıdır. 2026-07-22'de
> motora eklenen dejenere-flanş koruması (`reach_follow_min`, varsayılan 10mm +
> `target_z <= min_z`) aynaya İŞLENMEMİŞTİ → tablo ~9.8mm gösterirken makine ~39mm
> koşuyordu. 2026-07-28'de düzeltildi (`_test_pass_table.py` #2 artık geçiyor).
> Motorun çözüm zincirine dokunan HER değişikliği aynaya da taşı.

### 15. PLC mod decimation
| Ne | Dosya | Satır/Fonksiyon |
|----|-------|-----------------|
| Ana decimation fonksiyonu | `path_generator.py` | `_decimate_path_for_plc()` ~1518 |
| RDP yardımcısı | `path_generator.py` | `_rdp_decimate()` ~1481 |
| PLC modu etkinleştirme | `generate_gcode()` | satır ~1098 |
| **SCL İnceleyici** (PLC çıktısı görüntüleyici, 2026-07-26d) | `ui/dialogs/scl_inspector.py` | `analyze_plc_output()` = Tk'siz saf analiz (tolerans çözümü + seyreltme + pas metrikleri), `SclInspectorDialog` = 2B overlay. Durum: **flat** (kavis ≤ tolerans → tamamen silinebilir) / **coarse** (1–3 kiriş) / ok. ⚠ Kavis SADECE kıvrımın kendisinden ölçülür (`_curved_part`), tüm çıkış bölümünden DEĞİL. Menü: Araçlar ▸, `"scl" in formats` kapılı. Test: `_test_scl_inspector.py` |
| **`.nc` export'u PLC'den BAĞIMSIZ** (2026-07-26c) | `main.py` | `save_gcode()` → `_p["plc_mode"]=False` zorlar. `.nc` HER ZAMAN tam çözünürlük; PLC dosyasını **SCL export'undan** alır. Motor değişmedi. Test: `_test_gcode_not_plc.py` |
| Yaklaşım kolu ayrımı (2026-06-17) | `path_generator.py` | `approach_end_idx` parametresi ~1518 |
| Tüm yolları decimate (PLC dalı buna delege) | `path_generator.py` | `decimate_all_paths()` |
| Son decimate edilmiş yollar (auto-tune/guard için) | `path_generator.py` | `self.last_plc_paths` |

**PLC otomatik ayar (2026-07-11, opt-in #86):**
| Ne | Dosya | Fonksiyon/Anahtar |
|----|-------|-------------------|
| Kiriş-boyu min clearance ölçümü (köşe-kesmesini yakalar) | `path_generator.py` | `measure_min_clearance(paths, params)` |
| Tolerans→satır-bütçesi bisection (saf/read-only) | `export_manager.py` | `ExportManager.auto_fit_plc_tolerance()` |
| Onay kutusu + hedef + `_sync_plc_states()` | `ui/tabs/machine_tab.py` | PLC bölümü (`cb_auto`/`e_target`) |
| Export akışı (dizi sorusunu atlar, uyarı, not) | `ui/main_window.py` | `export_scl_action()` `auto` dalı |
| Parametreler | `main.py` / `machine_loader.py` | `plc_auto_tune`, `plc_target_lines` (MACHINE_PROFILE_KEYS) |
| Test | `_test_plc_autotune.py` | — |

**Kurallar:** SADECE opt-in — `plc_auto_tune` False iken davranış birebir eski. Guard:
decimate clearance ≥ tam çözünürlüklü yolun clearance'ı (floor = `measure_min_clearance(last_calculated_paths)`);
düşerse `clearance_limited` uyarısı. Satır sayısı toleransta monoton azalır → bisection.
Auto'da exit toleransı ana toleransla eşitlenir; tolerans alanları read-only olur.

**Parametreler (`_decimate_path_for_plc`):**
| Parametre | Kaynak | Açıklama |
|-----------|--------|----------|
| `approach_end_idx` | `last_render_split_idx[i][0]` (T1) | Yaklaşım kolunu RDP'den ayırır; 2 pt korunur |
| `arc_end_idx` | `last_render_split_idx[i][1]` (T2) | Fileto ile exit eğrisini ayırır; exit kendi T2→P3 kirişini alır |
| `exit_tolerance` | `params["plc_exit_tolerance"]` | Exit bölümü için bağımsız RDP toleransı |

**Exit yolu şekli (`path_generator.py` ~814):**
| Parametre | Açıklama |
|-----------|----------|
| `exit_arc_angle` (°) | T2→P3 dairesel yayı için tanjant-kiriş açısı. 0=düz. Pozitif=dışa (X artar), negatif=içe. R=chord/(2·sin α). UYARI: sweep=2·α, ~90°'den sonra KATLANIR. |
| `exit_bow` (mm) | (2026-07-08e) exit_arc_angle'a kararlı alternatif: kavis YÜKSEKLİĞİ ile parametrize kuadratik Bézier (`_bezier_bow`, path_generator.py). Uç noktalar birebir korunur → P3 oynamaz; asla katlanmaz. SABİT el-yönü (perp=kiriş+90°) → yelpazede ilk-pas ters-yön YOK. Set ise arc yerine geçer. Sadece linear şekiller. `exit_curve_tension` (ölü hayalet alan) bununla değiştirildi. |
| `exit_bow_bias` (0–1, vars. 0.5) | (2026-07-09) kavisin tepe noktasının P2→P3 bacağı üzerindeki konumu. `_bezier_bow`/`_make_bow_leg` `bias=` param; Bézier ctrl kiriş boyunca kayar (`ctrl = A + bias·(B−A) + 2·bow·perp`). Tepe YÜKSEKLİĞİ = exit_bow mm sabit, uçlar sabit — sadece konum kayar. 0.05–0.95'e kırpılır. Sadece exit_bow doluyken etkili. |
| `exit_mid_radius` (mm, işaretli) + `exit_mid_t` | (2026-07-25, #92 FAZ 1) ÇIKIŞ KIVRIMI: T2→M **DÜMDÜZ** (PLC RDP'de 2 satıra iner), M'den sonra sabit-yarıçap **teğet** yay → M'de KÖŞE YOK. M, T2→P3 **KİRİŞİ** üzerinde `exit_mid_t` oranında (⚠ `exit_mid_rotation` aynı alanı NOKTA DİZİSİ oranı olarak okur — iki anlam bilerek). Kuyruk uzunluğu = kalan \|M→P3\| → pas boyu sabit, **bitiş noktası SERBEST/oynar**. İşaret = `_bezier_bow` ile aynı SABİT el-yönü (+ = +Z). **YARIÇAP AYNEN uygulanır** — dönüş 90°'de (`CURL_SWEEP_CAP_DEG`) durur, kalan uzunluk teğet DÜZ devam eder (`_curl_tail`). ⚠ İLK SÜRÜMDEKİ HATA (2026-07-26 saha raporu): cap yarıçapı `arc_len·2/π` ile EZİYORDU → \|R\| eşiğin altındaki TÜM değerler aynı yolu üretiyordu, sadece işaret etkiliydi. Boş/0 = bit-aynı. DOLUYSA `exit_bow`+`exit_arc_angle`+`exit_mid_rotation`'ın yerine geçer. Sadece ileri yön + `linear_approach`. `_tangent_arc`/`_make_curl_leg` (path_generator.py) |
| `exit_mid_radius_end` (mm) + `_spiral_tail` | (2026-07-26b, ARA FAZ) Kuyruk boyunca **DEĞİŞEN eğrilik** (klotoid: κ doğrusal k0→k1). BOŞ/eşit = sabit yarıçap → **analitik yay yolu kullanılır, bit-aynı**. Amaç: sabit yayın M'deki **EĞRİLİK SIÇRAMASINI** (yön sürekli ama κ: 0→1/R) yok etmek. Yalnız bu alan doluysa kuyruk M'den DÜMDÜZ çıkıp yarıçaba yumuşak girer (önerilen kullanım). Yön dolu olan İLK alandan; bu alanın yalnız BÜYÜKLÜĞÜ → ters işaretle S OLMAZ. DÜZLEŞTİR iki yarıçabı birlikte ölçekler |
| `exit_mid_trim` (bool, vars. True) + `_curl_penetration` | Kıvrım clearance modu — `exit_bow_trim` ile aynı model. AÇIK=KIRP (kontura bin), KAPALI=DÜZLEŞTİR (**genlik değil YARIÇAP büyütülür**). ⚠ FARK: DÜZLEŞTİR'in sonunda **backstop kırpma** var → kıvrım HER İKİ modda clearance'ı korur (`exit_bow`'un CLAMP'ı bunu garanti ETMEZ, dokunulmadı). `_curl_penetration` son noktayı DA kontrol eder (uç serbest) |
| `exit_bow_trim` (bool, vars. True) + `_make_bow_leg`/`_bow_penetration` | (2026-07-08e 2.tur) bow clearance'ı asla ihlal etmez, op'un KENDİ clearance'ında korunur (üniform shift'e düşmez → P3/kol sabit). True=KIRP (tam bow, ihlal eden noktalar kontura biner), False=KISALT (genlik küçültülür, pürüzsüz). `_create_and_store_pass(op_clearance=)` yeni param. |

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
