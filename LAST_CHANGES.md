# Son Değişiklikler

Bu dosya önemli düzeltme ve geliştirmeleri kronolojik sırayla tutar.
Sorun çıkarsa buraya bak — hangi satır değişti, neden, ne bekleniyor.

---

## 2026-05-03 — İlk Paso Düz Çizgi Görünümü Bugfix (Fix 4 — P2 Radyal Yerleşim)

**Semptom:** İlk paso (target_z=start_z, mandrel tabanı) normal bir yay yerine
mandrel yüzeyine paralel düz bir çizgi gibi görünüyordu.

**Kök neden:** Rotasyon geometrik kısıtı eksikti. Adım adım:

1. Mandrel tabanında (z≈0) köşegen profil → yüzey normali nz ≈ -0.707
2. `surface_angle = atan2(-0.707, 0.707) = -45°`
3. `raw_rot = -(-45°) + 30° = 75°` → Fix2 tarafından **45°**'e kırpıldı
4. Y ekseni etrafında 45° rotasyon sonrası P3 konumu:
   - P3_relatif = (40, 0, 20) → `z' = -40*sin(45°) + 20*cos(45°) = -14.1mm`
   - **P3, P2'nin 14mm ALTINA indi!**
5. Hem P1 hem P3, P2'nin altında → spline P2'de tepe yapıyor → zirvenin
   küçük görünür kısmı (~5mm) neredeyse düz çizgi gibi görünüyor

**Geometrik kısıt:** Y ekseni rotasyonu θ sonrası:
`P3.z_rel = -p1_x·sin(θ) + p3_z·cos(θ) > 0` için: `θ < atan2(p3_z, p1_x)`

Varsayılan değerlerde: `atan2(20, 40) = 26.6°`. 45° kırpma çok gevşekti.

**Değişiklik:** `path_generator.py:386–400` (yaklaşık)

```python
# ÖNCE (Fix2):
raw_rot = -surface_angle + base_rot
final_rot = max(-45.0, min(45.0, raw_rot))

# SONRA (Fix4):
raw_rot = -surface_angle + base_rot
raw_rot = max(-45.0, min(45.0, raw_rot))          # Clamp 1: dejenere normal önleme
_px = abs(p1_x_offset); _p3z = abs(p3_z_offset); _p1z = abs(p1_z_offset)
if _px > 0.001 and _p3z > 0.001:
    geo_max_rot = math.degrees(math.atan2(_p3z, _px)) * 0.9  # P3 > P2 in Z
    raw_rot = min(raw_rot, geo_max_rot)
if _px > 0.001 and _p1z > 0.001:
    geo_max_neg_rot = math.degrees(math.atan2(_p1z, _px)) * 0.9  # P1 < P2 in Z
    raw_rot = max(raw_rot, -geo_max_neg_rot)
final_rot = raw_rot
```

**Etki:** Rotasyon artık P3'ün P2'nin üzerinde kalmasını garanti ediyor.
`p1_x=40, p3_z=20` → max_pos_rot = 23.9°. Bu açıda P3, P2'nin 2.1mm üzerinde kalır.

**Geri almak için (rotation clamp):** `raw_rot = max(-45.0, min(45.0, raw_rot))` satırını koru,
sonraki iki `if` bloğunu sil ve `final_rot = raw_rot` yap.

---

## 2026-05-03 — İlk Paso Düz Çizgi Görünümü Bugfix (Fix 5 — P2 Radyal Yerleşim)

**Semptom:** İlk roughing paso (target_z=0, mandrel tabanı) mandrel yüzeyine paralel
düz çizgi gibi görünüyordu; diğer pasolar normal yay şeklindeydi.

**Kök neden (log'dan tespit edildi):**
```
'Roughing 1' | P2=(x=142.2, z=122.2) | target_z=0  ← P2 122mm yukarıda!
'Roughing 2' | P2=(x=235.5, z=44.4)  | target_z=44.4 ← normal
```

Mandrel tabanı (z=0) düz yüzey → nz≈0.998. Eski P2 hesabı:
- `p2_x = r_contact + nx*122.5 = 134.5 + 0.063*122.5 = 142.2mm` (sadece 7.7mm radiyal offset!)
- `p2_z = 0 + 0.998*122.5 = 122.2mm` (temas noktasından 122mm yukarıda!)

P2, z=122mm'deki konik bölgede ve radiyal clearance'ı yetersiz (7.7 << 103mm).
`normal_aligned_shift` her spline noktasını mandrel yüzeyine hizaladı → paralel çizgi.

Pas 2–10 için nz≈0 → mevcut formül zaten `P2.Z = target_z` veriyordu. Sadece pas 1 etkileniyordu.

**Değişiklik:** `path_generator.py:192–196`

```python
# ÖNCE:
p2_x = center_x + r_contact + (nx * total_off)
p2_z = target_z + (nz * total_off)

# SONRA:
p2_x = center_x + r_contact + total_off   # her zaman tam radiyal offset
p2_z = target_z                            # temas noktasının Z'si
```

**Neden bu çalışıyor:** Auto_align rotasyonu yaklaşım açısını zaten yüzey normaline
hizalıyor. P2'nin normal yönünde ötelenmesi gereksiz. Düz yüzeylerde (nz≈1) bu öteleme
P2'yi yanlış Z'ye fırlatıyordu.

**Etki:** Pas 2–10 değişmez (nz≈0 için `p2_z = target_z` zaten aynıydı).
Sadece düz/dik yüzey bölgeleri düzelir.

**Geri almak için:** `p2_x = center_x + r_contact + (nx * total_off)` ve
`p2_z = target_z + (nz * total_off)` satırlarını geri yaz.

---

---

---

## 2026-05-03 — Spline Paso Bozulma Bugfix

**Semptom:** Bazı paso ayarlarında (özellikle ilk ve son paso) spline tamamen absürt şekil alıyordu.
Normal sapmalar değil, devasa bozulmalar.

**Kök neden:** Üç ayrı sorunun zincirleme etkisi. Mandrel tepesi/tabanına yakın `target_z`'de tetikleniyor.

---

### Fix 1 — `mandrel_analyzer.py:203–204`

**Sorun:** `get_normal_at_z()` içinde `get_radius_fast(z + delta)` çağrısı mandrel sınırını aşıyor.
Konik/küresel uçlarda profil azaldığı için ekstrapolasyon negatif radius döndürüyordu.
`get_radius_fast()` zaten `max(0.0, ...)` clamp'i yoktu bu fonksiyonda.
Sonuç: `nz` değeri ~0.99 (neredeyse tam dikey) çıkıyordu → auto_align ile ~82° rotation → spline bozulması.

**Değişiklik:**
```python
# ÖNCE:
r1 = self.get_radius_fast(z_level - delta)
r2 = self.get_radius_fast(z_level + delta)

# SONRA:
r1 = max(0.0, self.get_radius_fast(z_level - delta))
r2 = max(0.0, self.get_radius_fast(z_level + delta))
```

**Etki:** Normal hesabı için negatif ekstrapolasyon değerleri artık 0.0'a sınırlandırılıyor.
Mandrel uçlarında normal vektörü artık makul açıda kalıyor.

---

### Fix 2 — `path_generator.py:386–390`

**Sorun:** `auto_align` etkinken `surface_angle` mandrel ucunda ~80–90° çıkıyordu.
Bu açı P1/P3'ü (P2'den 50–70mm uzakta) büyük rotasyonla tamamen farklı konumlara fırlatıyordu.
P3 mandrel içine giriyordu → clearance düzeltme döngüsü 20 iterasyona ıraksıyordu → bozuk spline yazılıyordu.

**Değişiklik:**
```python
# ÖNCE:
final_rot = -surface_angle + base_rot

# SONRA:
raw_rot = -surface_angle + base_rot
final_rot = max(-45.0, min(45.0, raw_rot))
```

**Etki:** Auto-align rotasyonu ±45° ile sınırlandırıldı. Tipik mandrel yüzey açıları 0–30° arasında,
45° sınırı dik koniklere bile yeterli. Mandrel ucundaki dejenere normaller artık spline'ı bozmuyor.

**Not:** 45° sınırı kullanıcı davranışını değiştirirse `params["auto_align_max_deg"]` gibi bir
parametre eklenebilir. Şimdilik sabit.

---

### Fix 3 — `path_generator.py:399–435` (clearance check döngüleri)

**Sorun:** Spline'ın mandrel sınırı dışına çıkan noktaları (P1/P3 yakını) clearance check'e giriyordu.
Bu bölgede `get_radius_fast()` saçma/negatif değer → `max(0.0, ...)` ile 0'a çekilince
`required = 0 + r_tool + blank = ~27mm` gibi küçük değer → clearance pozitif görünüyor ama yanlış.
Veya negatif radius → büyük clearance ihlali → aşırı X shift → spline daha da bozuluyor.

**Değişiklik:**
- Her iki clearance loop'tan (normal_aligned_shift ve uniform_shift) önce mandrel Z sınırları alındı
- Her iki loop içine sınır dışı noktalar için `continue` (ya da `append(list(pt))`) eklendi
- Uniform shift için `min_clearance == float('inf')` durumu (tüm noktalar sınır dışı) `break` ile güvenli çıkış

```python
# Eklendi (iki loop öncesinde):
_m_min_z = mandrel_mgr.props.get("min_z", float('-inf'))
_m_top_z = mandrel_mgr.props.get("top_z", float('inf'))

# Normal_aligned_shift loop içinde:
if sim_z < _m_min_z or sim_z > _m_top_z:
    corrected.append(list(pt))  # noktayı olduğu gibi bırak
    continue

# Uniform_shift loop içinde:
if sim_z < _m_min_z or sim_z > _m_top_z:
    continue  # clearance hesabına dahil etme

# Uniform_shift sonrasında:
if min_clearance == float('inf'):
    break  # tüm noktalar dışarıda, çarpışma riski yok
```

**Etki:** Mandrel sınırları dışındaki spline noktaları clearance düzeltmesini tetiklemiyor.
Giriş/çıkış geometrisi (P1/P3) serbestçe mandrel dışına uzanabilir, düzeltme sadece
mandrel ile temas eden bölgede uygulanıyor.

---

### Özet

| # | Dosya | Satır | Değişiklik |
|---|-------|-------|------------|
| Fix 1 | `mandrel_analyzer.py` | 203–204 | `get_normal_at_z`: r1/r2 max(0.0) clamp |
| Fix 2 | `path_generator.py` | 386–390 | auto_align rotasyon ±45° sınırı |
| Fix 3 | `path_generator.py` | 399–440 | Clearance check mandrel Z sınırı dışını atlıyor |

**Geri almak için:** Yukarıdaki "ÖNCE" kodlarını geri koy.
Fix 2'yi geri almak istersen sadece `raw_rot = ...` satırını kaldır ve `final_rot = raw_rot` yap.

---

## 2026-05-03 — Rapid Çift Render Bugfix + Paso Seçimi

### Fix A — `main.py:416–419` (silindi)

**Sorun:** Rapid hareketleri iki kez render ediliyordu.
- 1. kez: solid kırmızı, width=1 (eski kod, silinmedi)
- 2. kez: dashed turuncu, width=2 (yeni kod)
Her rapid segmenti ekranda iki farklı çizgi olarak görünüyordu.

**Değişiklik:** Solid kırmızı rapid render döngüsü (4 satır) silindi.
`show_rapids` kontrolü dashed turuncu döngüye taşındı.

---

### Fix B — `ui/tabs/program_tab.py: on_op_select()`

**Sorun:** ProgramTab'da operasyona tıklamak `active_editing_pass_idx`'i güncellemiyordu.
Yani hangi operasyona tıklanırsa tıklansın, ekrandaki magenta paso hep idx=0 (ilk paso) kalıyordu.

**Değişiklik:** `on_op_select()` başına eklendi:
- Tıklanan operasyonun global (cumulative) pas indeksi hesaplanıyor
- `app.active_editing_pass_idx` güncelleniyor
- `update_scene("paths")` tetikleniyor (calc_active açıksa)
- `count > 1` olan operasyonlar için property editor'ın üstüne **◀ Paso: X/N ▶** navigatörü eklendi
- Operasyon değiştirildiğinde within-op sayacı sıfırlanıyor

---

### Ekstra Bilgi: Çizgi Türleri (ne neyi temsil ediyor)

| Renk | Çizgi türü | Simülasyon takip eder mi? |
|------|-----------|--------------------------|
| Magenta kalın | Aktif seçili paso | Evet |
| Mavi kalın | Roughing pasları | Evet |
| Turuncu kalın | Finishing pasları | Evet |
| Turuncu dashed ince | Rapid hareketleri (G0) | Evet |
| Cyan ince | Projeksiyon çizgileri (mandrel yüzey referansı) | **Hayır** |
| Siyah ince | Approach line (roller → ilk pas) | Hayır |

Cyan projeksiyon çizgileri görsel yardımcı; simülasyon bunları takip etmez.
Bozuk görünüyorlarsa o pasın Z bölgesinde mandrel ekstrapolasyon sorunu var demektir.

---

## 2026-05-21 — SCL Export: Dosyasız, Bellekten Doğrudan

**Dosyalar:** `ui/main_window.py`, `export_manager.py`

**Eski akış:** G-code kaydet (.nc) → dosya seç → SCL'e dönüştür
**Yeni akış:** Export SCL butonuna bas → direkt SCL kaydedilir

**Değişiklikler:**
- `export_scl_action` — dosya seçme dialogu kaldırıldı; `path_gen.generate_gcode(params)` ile
  string üretilip direkt `parse_gcode()` ve `generate_scl()`'e aktarılıyor
- `ExportManager.export_scl` — yeni `gcode_string=None` parametresi eklendi;
  verilince dosya okumayı atlar, string üzerinden dönüşüm yapar
- `ui_machine.sync_params()` export öncesi çağrılıyor (header/footer senkronizasyonu)
- Eski `gcode_filepath` yolu hâlâ çalışıyor (geriye dönük uyumlu)

---

## 2026-05-21 — Silindir (CMD=40) Enable/Disable

**Dosyalar:** `machine_tab.py`, `path_generator.py`, `main.py`

- Yeni param: `cylinder_enabled` (default `True` — geriye dönük uyumlu)
- `machine_tab.py`: Cylinder bölümüne "Enable (G-code'a M40 yaz)" checkbox eklendi
- `path_generator.py:783`: G-code gate `cylinder_enabled and cyl_pos_mm > 0` oldu
- Kapalıyken M40 komutu tamamen atlanır, 3D görsel etkilenmez

---

## 2026-05-21 — Home Gap Göstergesi Renk/Pozisyon Düzeltmesi

**Dosya:** `main.py` — home gap indicator bloğu

- Çizgi ve etiket rengi her zaman kırmızı (önceden boşluk pozitifse cyan, negatifse kırmızıydı)
- Etiket Z ofseti yarıya indirildi: `r_rad + 15` → `(r_rad + 15) / 2.0` (çizgiye daha yakın)

---

## 2026-05-21 — Home Gap Göstergesi (Yeni Özellik)

**Dosya:** `main.py` — "4. Roller & Measurement" bloğu (`dist_line` / `dist_label` aktörleri)

**Ne eklendi:** Home pozisyonunda mandrel yüzey kenarı → rulo kenarı arası mesafeyi
gösteren görsel çizgi + etiket. Pass distance indicator ile aynı konsept fakat
home/başlangıç duruşu için.

- Cyan çizgi: pozitif boşluk (güvenli)
- Kırmızı çizgi + "COLLISION" etiketi: negatif boşluk (çarpışma)
- `HOME GAP +XX.Xmm` etiketi çizginin ortasında görünür

**Detaylar:**
- Mandrel Z sınırı dışında home duruyorsa (yaygın senaryo) `rz_tip` mandrel
  `[min_z, top_z]` aralığına clamp edilerek en yakın yüzey noktasından ölçülür
- Boşluk değeri (`edge_gap`) gerçek kenar pozisyonlarından hesaplanır,
  eskiden kullanılan `gap_x` (clamp'siz, dışarıda sıfır dönüyordu) değil

**Geri almak için:** `dist_line` / `dist_label` aktör bloğunu sil (try...except dahil).

---

## 2026-05-21 — `_add_prop_entry` Auto-Calculate Bugfix

**Dosya:** `ui/tabs/program_tab.py:543`

**Semptom:** Operasyon parametresi her değiştiğinde (FocusOut / Return) program
yeniden hesaplama yapıyordu; "auto-calculate" kapalı olsa bile.

**Kök neden:** `save()` içindeki guard `calc_active` kullanıyordu — bu flag her zaman
`True` (startup'ta hardcode). `on_param_change` içindeki doğru guard olan
`auto_calculate_paths` kullanılmıyordu.

```python
# ÖNCE (hatalı):
if self.app.params.get("calc_active", False):
    self.app.update_scene("paths")

# SONRA (doğru):
if self.app.params.get("auto_calculate_paths", False):
    self.app.update_scene("paths")
```

---

## 2026-05-03 — Dokümantasyon Düzeltmeleri

| Dosya | Değişiklik |
|-------|------------|
| `PLC_Recipe_Format_Spec.md` | DEPRECATED başlığı eklendi (negatif Z, yanlış limitler, Header.Name hatası) |
| `CAM_INTERFACE_SPEC.md` | Bölüm 10 eklendi: RecipeHeader + RecipeLine UDT struct tanımları (sName ile doğru) |
| `recipe_to_scl.py` | Docstring'deki `Array[0..1399]` hatası düzeltildi (2 yerde) |
| `CODE_NAVIGATION.md` | Yeni dosya: konu→dosya:satır navigasyon kılavuzu |
