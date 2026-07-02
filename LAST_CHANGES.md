# Son Değişiklikler

Bu dosya önemli düzeltme ve geliştirmeleri kronolojik sırayla tutar.
Sorun çıkarsa buraya bak — hangi satır değişti, neden, ne bekleniyor.

---

## 2026-07-02b — Performans: tek render / grid cache / logging tracebacks

### 1. update_scene artık TEK render yapıyor (en büyük kazanç)
`plotter.add_mesh` ve `remove_actor` varsayılan olarak `render=True` — `update_scene("all")`
30–80 actor dokunuşu = 30–80 TAM sahne render'ı tetikliyordu (PHASE-8 "visual loading
glitches" şikayetinin muhtemel kök nedeni). Düzeltme: `update_scene` artık bir wrapper;
gövde `_update_scene_impl`'e taşındı, `plotter.suppress_rendering=True` ile sarıldı,
sonda TEK `plotter.render()`. İç içe çağrılarda (was_suppressed) render tekrarı yok.
`main_window._hooked_update_scene` public isimle çalıştığı için etkilenmez.

### 2. _update_grid_dynamic: bounds değişmediyse show_grid atlanıyor
`show_grid` her çağrıda cube-axes actor'ı yıkıp yeniden kuruyordu. Bounds 0.1'e
yuvarlanıp cache'leniyor (`_last_grid_bounds`); değişmediyse no-op.

### 3. logger_config: cp1254 konsolunda UnicodeEncodeError seli
PARAM_DEBUG mesajlarındaki θ/→/° karakterleri Türkçe konsolda (cp1254) encode edilemiyor;
her satır için stderr'e tam traceback basılıyordu (tek hesaplamada 40 adet!).
`sys.stdout.reconfigure(errors="replace")` eklendi — headless smoke testte 40 → 0.

### Doğrulama
Aktive env: py_compile OK; `SpinningApp(headless=True)` kuruldu (init update_scene
wrapper'dan geçiyor), ikinci `update_scene("all")` + `update_scene("visual")` OK,
suppress_rendering False'a geri döndü, logging error 0. GUI smoke test edilmedi.

### Geri alma
1: wrapper'ı kaldır, `_update_scene_impl` adını `update_scene` yap. 2: `_last_grid_bounds`
bloğunu sil. 3: `reconfigure` satırını sil.

### Yapılmayan öneriler (opt-in bekliyor)
- Process tab "Hesapla" + auto-calc modu hâlâ SENKRON `calculate_paths` (UI donuyor);
  Program tab'daki `calculate_async` + `_poll_calc_queue` deseni oraya da taşınabilir.
- `update_scene("all")` her seferinde mandrel mesh copy + shell mesh regen yapıyor —
  değişmeyen durumlar için daha dar mode kullanımı mümkün (refactor).
- `gui_manager.py` Tk uygulamasında ölü kod (`self.ui = None`); `update_positions`
  gövdesi 3 kez kopyalanmış — silinme adayı, çalışma zamanına etkisi yok.

---

## 2026-07-02 — Lisans sistemi: audit sonrası bug düzeltmeleri

### Sorunlar ve düzeltmeler
1. **MAC format uyuşmazlığı (kritik):** Üretici UI müşteriye MAC'i `ipconfig /all`'dan
   okutuyor — Windows tire kullanır (`AA-BB-...`), `get_mac_address()` iki nokta üretir
   (`AA:BB:...`). Karşılaştırma ham stringdi → tireli MAC'li lisans ASLA eşleşmezdi.
   Düzeltme: `license_manager.normalize_mac()` (sadece hex rakamları, uppercase) —
   `check_machine_binding` her iki tarafı normalize ederek karşılaştırıyor.
2. **Bozuk GUID parmak izi:** Registry okunamazsa `get_windows_guid()` `"unavailable"`
   döner ve `get_machine_fingerprint()` bunu hash'liyordu → GUID'i okunamayan HER makine
   aynı parmak izini paylaşırdı. Düzeltme: `""` döner; `check_machine_binding` fail-closed
   (`UNAVAILABLE` işareti, MAC yolundaki desenle aynı). `machine_info.py` de artık
   "unavailable" gösteriyor (sahte hash yerine).
3. **Bozuk `_sig` çökmesi:** `.lic` içinde `_sig` string değilse (`123` vb.)
   `bytes.fromhex` TypeError fırlatıp browse diyaloğunu çökertiyordu. Düzeltme:
   `verify_license` isinstance kontrolü → False.
4. **Bayat admin durumu (machine_selector):** Geçerli admin lisansı yüklendikten sonra
   bozuk dosya seçilirse `_license_data=None` olur ama `_is_admin`, `_allowed_machines`,
   makine filtresi ve "Generate License" düğmesi eski halinde kalırdı. Düzeltme: yeni
   `_reset_license_state()` tüm başarısızlık dallarında çağrılıyor.
5. **`ttk.Label(fg=...)` TclError (license_generator):** profil bulunamayınca çöküyordu
   (ttk `foreground` ister). Düzeltildi.
6. **UI metni + girdi doğrulama (license_generator):** "Strong (MAC + Windows GUID
   combined)" → "Strong (Windows GUID fingerprint)" (GUID-only gerçeğine uyumlu).
   Generate öncesi doğrulama: MAC 12 hex hane, fingerprint 32 hex karakter (typo →
   asla çalışmayan lisans üretimini engeller). Fingerprint lowercase normalize ediliyor
   (hexdigest lowercase üretir; büyük harf yapıştırılırsa eşleşmezdi). "Read from THIS PC"
   boş değer okursa uyarı veriyor.

### Doğrulama
Aktive `spinning_cam` env ile: py_compile 4 dosya OK; birim testleri (tire-vs-iki nokta
MAC eşleşmesi, GUID-yok fail-closed, bozuk _sig tipleri, Ed25519 imza/doğrulama + tamper)
hepsi PASS; mevcut `admin.lic` gömülü public key ile hâlâ geçerli + binding OK.
GUI smoke test edilmedi.

### Geri alma
`license_manager.py`, `machine_selector.py`, `license_generator.py`, `machine_info.py`
bu tarihli değişiklikleri geri al. Not: #1 geri alınırsa tireli MAC'li lisanslar yine
çalışmaz olur.

---

## 2026-07-01 — Machine settings (Program Start home_x/z vb.) otomatik kaydediliyor

### Sorun
Makine sekmesindeki "Program Start" X/Z (`home_x`/`home_z`) ve diğer makine alanları
değiştirildiğinde yeniden başlatınca eski değere dönüyordu. Neden: bu anahtarlar
`MACHINE_PROFILE_KEYS` içinde ve `save_settings_json` onları settings.json'dan **hariç
tutuyor** (main.py:194). Kalıcı olmaları yalnızca "Makine Profilini Kaydet" düğmesiyle
oluyordu; admin akışında aktif profil varken düğme görünse de kullanıcı elle basmadıkça
kayıp oluyordu. Yüklemede `params.update(profile)` (main_window.py:221) eski değeri geri
yazıyor.

### Ne değişti
- `main.py` `on_param_change`: değişen anahtar `MACHINE_PROFILE_KEYS` içindeyse
  (`_is_machine_key`) → (1) per-pass override dalına **girmesi engellendi** (mode="paths"
  ile geliyorlardı, "apply to specific pass only" açıkken yanlış yönlendirilebiliyordu),
  (2) `autosave_machine_profile()` çağrılarak aktif profile anında diske yazılıyor.
- `main.py` yeni `autosave_machine_profile()`: aktif profil + `_path` varsa
  `MACHINE_PROFILE_KEYS`'i params'tan profile kopyalar ve `save_machine_profile` ile yazar.
  Profil yoksa sessiz no-op. `_save_machine_profile` (buton) mantığının sessiz eşdeğeri.
- `help_window.py`: machine bölümüne "Saving machine settings / Makine ayarlarını kaydetme"
  notu (EN+TR): alanlar profile otomatik kaydedilir; sağ üst düğme aynı işi elle yapar.

### Doğrulama
`main.py` derleniyor. İzole test: `save_machine_profile` home_x/home_z'yi dosyaya yazıyor,
`_path` sızmıyor. (Tam GUI headless init bu ortamda VTK'de çöktüğü için buton/tam akış
GUI smoke test'te doğrulanmalı.)

### Geri alma
`autosave_machine_profile` çağrısını ve `_is_machine_key` guard'ını kaldır → eski davranış
(yalnız düğmeyle kayıt). Profil yokken zaten no-op olduğu için risk düşük.

---

## 2026-06-25 — Pass Direction (Forward / Reverse) per operation — TODO #49

### Ne eklendi
Roughing ve finishing operasyonlarına per-op **`direction`** alanı (`forward` varsayılan | `reverse`).
`reverse` seçilince pasın **kesim yönü** ters çevrilir (uç→kök) — geometri değişmez, sadece
nokta sırası ters döner. Çok paslı işlemde sadece her pasın kesim yönü döner; pasların
oluşturulma sırası aynı kalır. Mevcut mirror back pass korundu (ters pasta whole-path-mirror
dalını kullanarak uyumlu çalışır).

### Nerede
- `path_generator.py` (~325, `len(toolpaths) > prev_paths_len` bloğunun başı): `direction == "reverse"`
  ise `toolpaths[-1]`, `projections[-1]`, `deviations[-1]` ters çevrilir; `last_render_split_idx`'ten
  o pasın split index'i silinir (ters dizide artık eşleşmiyor → render/PLC köşe-tespiti fallback'ine
  düşer, geometri aynı). Back pass bloğu doğal olarak ters yol üzerinde çalışır.
- `program_tab.py` (count entry'sinden hemen sonra): Direction combobox (roughing/finishing).
- `i18n.py`: `lbl_direction`, `opt_forward`, `opt_reverse` (EN/TR/ES).

### Doğrulama
Headless: 3-paslı roughing forward vs reverse — her pas tam ters (`f[::-1] == r`), nokta kümesi
aynı, G-code geçerli ve farklı. `forward` (varsayılan) çıktısı eskisiyle birebir aynı.

### Geri alma
`direction` alanı yoksa veya `forward` ise davranış öncekiyle aynı (geriye dönük uyumlu).
Özelliği kaldırmak için 3 dosyadaki eklemeleri geri al.

---

## 2026-06-25 — Clearance model unified (one `clearance` per op + safety floor)

### Problem
Roughing and finishing computed the roller-to-blank gap from DIFFERENT knobs, so the same
intent produced different contact standoffs. Roughing's final gap was pinned to `target_clearance`
by a two-way correction loop that OVERRODE its allowance; finishing's gap was
`safety_clearance + finish_allowance` with no correction. Two formulas → inconsistent contact
even with "the same" settings.

### New model (one definition for every pass type)
- Per-op **`clearance`** = gap between the roller contact and the blank surface. `0` = touch.
  `standoff = r_tool + blank + clearance` for roughing AND finishing (straight/sweep/adaptive).
- **`min_safety_gap`** (renamed from `target_clearance`) = a ONE-WAY collision floor: pushes a
  shaped pass OUT if its closest point gets nearer than the floor, never pulls it in (pulling in
  was what overrode clearance). The `path_generator` correction loop is now one-way.
- `finish_allowance` and the global `safety_clearance_roller_to_part` fold into `clearance`.
  Back-pass clearance now follows the op's `clearance` (was `target_clearance`).

### Back-compat (old recipes unchanged)
- `config_schema.migrate_clearance(params)` (idempotent) upgrades any recipe on load
  (`main.load_settings` + `load_project`): roughing.clearance = old target_clearance;
  finishing.clearance = finish_allowance + safety; min_safety_gap = old target_clearance.
- `path_generator.calculate_paths` also falls back to the old keys inline when an op has no
  `clearance`, so an un-migrated op calculates exactly as before.

### Data change (this recipe — INTENDED)
settings.json ops both set `clearance = 0` (finishing should TOUCH like roughing) and
`min_safety_gap = 0`. Net effect: the finishing pass moves IN 0.5 mm (81.0 → 80.5) to match
roughing. Verified headless: roughing 80.51 / finishing 80.50 (gap −0.01); clearance=0.5 moves
both to 81.0; stripping the new keys reproduces the original 0.5 mm gap (fallback proven).

### UI / naming
- Program tab: every op now shows a **Clearance (mm)** field (`lbl_clearance`); finishing's old
  "Allowance" field rebinds to it; roughing gains one (before the Step field).
- Process tab: "Target Clearance" spinbox → **Min Safety Gap** (`min_safety_gap`); the redundant
  "Safety Standoff" spinbox removed (folded into clearance).
- i18n `lbl_clearance` / `sp_min_safety_gap` (EN/TR/ES); help_window standoff formula updated;
  `recipe_to_scl` info comment → "Min Safety Gap".

### Files
`path_generator.py`, `main.py`, `settings.json`, `constants.py`, `config_schema.py`,
`ui/tabs/program_tab.py`, `ui/tabs/process_tab.py`, `i18n.py`, `ui/dialogs/help_window.py`,
`recipe_to_scl.py`.

### `step` field hidden (was inert)
The per-op `step` field ("each pass goes radially deeper" = progressive depth) had NO effect on the
toolpath (it fed an `allowance` var the unification stopped using). Per user request it is now HIDDEN
from the Program tab, and the dead `def_step`/`allowance` chain removed from
`path_generator.calculate_paths`. The `step` value stays in the data (pass-diagram popups read it;
reserved for Phase 3). Making `step` actually work is Phase 3 — deferred until the stepping behaviour
is defined (it must not clash with Z-distributed passes).

### To undo
Revert the listed files (old recipes are unaffected regardless — fallback + shim). To restore the
old finishing standoff without reverting code, set the finishing op `clearance` to 0.5.

---

## 2026-06-25 — r_tool mismatch (finishing 4.7mm closer) — FIXED + auto-sync added

### Problem (the real root cause; 2026-06-24's normal-projection theory was a dead end)
Roughing and finishing operations used the SAME tool (T0103) but stored two DIFFERENT
snapshotted `r_tool` values — roughing 79.5, finishing 74.31. `r_tool` is copied into each op
at tool-pick time (`program_tab.py`) and never re-synced, so when `tools.json` T0103 was later
changed to 74.31, only the finishing op picked it up. That 5.19mm delta = the entire ~4.7mm gap
(finishing sat closer → gouge risk). Verified headless: `nx≈1.0` where the passes run, so the
radial-vs-normal projection (2026-06-24) was a no-op here — not the cause.

### Fix
1. `tools.json` T0103 `r_tool`: 74.31 → **79.5** (calibrated reach; user chose the SAFE value —
   a too-small r_tool drives the roller INTO the part). `radius` stays 74.31 (true disc geometry;
   `r_tool − radius = 5.19mm` mounting offset, as intended).
2. `settings.json` finishing op `r_tool`: 74.31 → 79.5 (immediate data fix).
3. `main.py` new `SpinningApp.sync_operation_r_tools()` — operations re-pull `r_tool` from the
   tool library (single source of truth) by `tool_id`. Called before BOTH `calculate_paths`
   sites (`calculate_async` pre-deepcopy; `update_scene` sync fallback) and at startup via
   `ui/main_window.py` `load_tools()`. Explicit `is None` test (NOT `or`, so `r_tool==0.0` is
   honored); logs drift; WARNS if calibrated `r_tool < disc radius` (gouge guard).

### Verified (headless, real settings.json + 18 konik kap.STEP)
Roughing min standoff 80.50, finishing 81.00 → gap **+0.50mm** (finishing now slightly FURTHER =
safe direction). Was −4.69mm. Sync unit-tested: stale op re-synced, `0.0` honored, `radius`
fallback works, unknown `tool_id` left untouched.

### To undo
Revert the edits above. Or set `tools.json` T0103 `r_tool` back to 74.31 (sync propagates it to
all T0103 ops on next Calculate). NEVER set `r_tool` below the disc radius — gouge.

### Residuals (NOT changed — separate from this bug)
- Roughing op `finish_allowance`=1.5 vs finishing=0.5; the +0.50mm residual above is partly this
  plus linear-approach pass geometry. Revisit only if the allowance design is actually wrong.
- On-screen pass-distance labels still misalign back passes (`main.py` ~746-789) — cosmetic, does
  not affect exported toolpaths (handover "SECONDARY ISSUE").

---

## 2026-06-24 — Straight-line finishing pass: radial offset — ATTEMPTED FIX, REVERTED (UNSOLVED)

### Problem
Finishing operations with `straight_line_mode=True` were computing endpoint positions using
the mandrel surface **normal direction** (`nx * total_off`, `nz * total_off`).  Roughing passes
use a **purely radial** offset (`total_off` in X, no Z shift).  On a curved/tapered mandrel
(e.g. 20° taper, nx ≈ 0.94) this caused finishing to sit ~4–5 mm closer to the mandrel than
roughing even when both had identical step/allowance values and the same tool.  The gap also
appeared in the exported G-code/SCL — it was not only a visualisation artifact.

### Root cause
`path_generator.py` ~line 292–299 (straight-line branch of the `is_finish` block):

```python
# BEFORE (wrong — normal-direction projection)
nx_s, nz_s = mandrel_mgr.get_normal_at_z(start_h)
p_s = np.array([center_x + r_s + nx_s * total_off, 0.0, start_h + nz_s * total_off])
nx_e, nz_e = mandrel_mgr.get_normal_at_z(end_h)
p_e = np.array([center_x + r_e + nx_e * total_off, 0.0, end_h + nz_e * total_off])

# AFTER (correct — purely radial, consistent with roughing P2 formula)
p_s = np.array([center_x + r_s + total_off, 0.0, start_h])
p_e = np.array([center_x + r_e + total_off, 0.0, end_h])
```

### Why this matters
A user setting the same allowance on roughing and finishing expects the same physical
clearance.  The old code silently gave less clearance on finishing for any non-flat mandrel
section.  This is a **safety issue**: an operator assuming equal standoff could crash the tool.

### What is NOT changed
- Sweeping (non-straight-line) finishing still uses normal-direction projection — that is
  intentional for surface-following passes and the user is expected to know the behavior
  differs from roughing.
- Roughing conformal mode (per-op or global `conformal_clearance_*` flag) also uses normal
  direction deliberately; it is an opt-in feature.

### Status: REVERTED
Both attempted fixes (radial-only offset) were reverted because the problem persisted
even after applying them — meaning the root cause is NOT the nx/nz projection in
straight-line mode.  The real cause is still unknown.  See handover document
`backup/HANDOVER_2026-06-24b.md` for full investigation notes.

### Rollback (already done)
Code is back to original (nx/nz projection). No code change is live.

---

## 2026-06-23 — Multi-machine support: profiles + startup selector (#48 Phase 1)

### New files
- `machine_adapter.py` — `MachineAdapter` base class + `StandardTwoAxisSpinningAdapter` (type 111); `ADAPTERS` dict; `parse_machine_id()` / `get_adapter()` helpers
- `machine_loader.py` — `MACHINE_PROFILE_KEYS` list (~32 keys); `list_machine_profiles()`, `load_machine_profile()`, `save_machine_profile()`, `migrate_from_settings()`
- `machines/ID111-1.json` — machine profile for the current lathe; all machine params extracted verbatim from old settings.json
- `ui/dialogs/machine_selector.py` — startup Toplevel dialog; auto-skips if only 1 profile and `show_machine_selector` not set

### Modified files
- `main.py` — `SpinningApp` gains `active_machine_profile` / `active_adapter`; `save_settings_json()` now strips machine keys before writing settings.json
- `main_window.py` — new `_load_machine_profile()` method called between language setup and `_setup_layout()`; `_machine_ready` flag guards against destroyed window
- `ui/tabs/machine_tab.py` — active machine header (name + ID in steelblue) + "Save Machine Profile" button at top; `_save_machine_profile()` method; `messagebox` import added
- `settings.json` — machine-specific keys removed (~32 keys); they now live in `machines/*.json`
- `config_schema.py` — `MachineProfileSchema` + `validate_machine_profile()` added
- `i18n.py` — `btn_save_profile` key added (EN/TR/ES)

### Rollback
1. Delete `machines/`, `machine_adapter.py`, `machine_loader.py`, `ui/dialogs/machine_selector.py`
2. Revert `main.py` (remove two attrs, restore `save_settings_json`)
3. Revert `main_window.py` (remove `_load_machine_profile` + `_machine_ready` + call)
4. Revert `machine_tab.py` (remove header block + save button + `_save_machine_profile`)
5. Restore machine keys to `settings.json` from `machines/ID111-1.json`

---

## 2026-06-23 — GUI Parameter Reorganisation + Help Window (#45)

### 1. Parameter layout cleanup (process_tab.py + machine_tab.py)

**Moved to Process Tab → Visual Settings:**
- `show_analysis_lines` (was in Safety section)
- `show_pass_dist_lines` (was in Safety section)

**Moved to Process Tab → Conformal Path Settings:**
- `auto_calc_angle` (was in Safety section)
- `clearance_correction_per_point` (was in Safety section)
- `exit_arc_angle` (was in Machine Tab → PLC section — wrong location, it's a path geometry param)

**Process Tab → Safety section** now contains only its 3 true safety params:
`collision_resolution`, `target_clearance`, `safety_clearance_roller_to_part`

**Machine Tab changes:**
- Removed the sparse "Safety & Limits" LabelFrame (had only `max_spin_rpm`)
- `max_spin_rpm` moved into "G-code Output" section (it produces `G50 S[val]`, it's a G-code param)
- `exit_arc_angle` removed from PLC section entirely (now lives in Process Tab → Conformal)

**Geri alma:** Reverse the `add_checkbox` / `add_spinbox` calls in each section.

---

### 2. Help window — `ui/dialogs/help_window.py` (TODO #45)

New file. Accessible via `Help → User Guide` in the menu bar.

**Design:** `tk.Toplevel` with `ttk.Notebook`, 5 tabs, scrollable read-only `tk.Text` per tab.
Content stored as `_C` dict in the file itself (not in i18n.py — too long for a string table).
Tab labels go through `t()`. Content has `"EN"` and `"TR"` keys per section.

**5 tabs:**
- Getting Started — 7-step workflow
- 3D View — navigation, colour legend, overlay explanations
- Operations — roughing/finishing/cutting/bending concepts, back pass, Calculate
- Machine & Export — coordinate system, home, calibration procedure, export formats
- Troubleshooting — 7 common problems with diagnosis logic

**Content policy:** No specific parameter names or UI locations. Conceptual terms only, so
content stays valid as the UI evolves. Update `_C` in `help_window.py` whenever a meaningful
feature or workflow changes.

**Files changed:**
- New: `ui/dialogs/help_window.py`
- `ui/main_window.py` — `_create_menu`: added `menu_user_guide` item + separator before About
- `i18n.py` — added 8 keys: `menu_user_guide`, `help_win_title`, `help_tab_*` (×5), `help_btn_close`

**Geri alma:** Delete `help_window.py`, revert menu to remove the User Guide item and separator,
remove the 8 i18n keys.

---

## 2026-06-22 — Touch Tip Audit: 3 Bugs Fixed (shell_offset, blank param, add_op r_tool)

### Özet

Roller touch tip hesabının tüm zinciri denetlendi: `tools.json` → `on_tool_change` → `operations[i].r_tool` → path generator → kalibrasyon diyaloğu. Üç gerçek hata bulundu ve düzeltildi.

---

### Bug 1 — `_create_sweeping_pass` ve straight-line finishing'de `shell_offset` eksikliği

**Dosya:** `path_generator.py`

**Problem:**
Roughing ve adaptive finishing, mandrel yarıçapına `shell_offset` (`shell_thickness` parametresi) ekler:
```python
r_contact = mandrel_mgr.get_radius_fast(z) + shell_offset   # roughing / adaptive
```
Ancak `_create_sweeping_pass` ve straight-line finishing modu `shell_offset` parametresini hiç almıyor, ham `m_rad` kullanıyordu:
```python
# HATA (önce):
m_rad = mandrel_mgr.get_radius_fast(current_z)          # shell_offset yok
rx    = center_x + m_rad + (nx * total_off)

# straight-line (önce):
r_s = mandrel_mgr.get_radius_fast(start_h)              # shell_offset yok
```

**Etki:** `shell_thickness > 0` olduğunda sweeping/straight-line finishing pasaları, roughing pasalarından `shell_thickness` mm kadar mandrel'e daha yakın konumlandırılıyordu. Roughing ve finishing aynı yüzey referansını görmüyordu.

**Düzeltme:**

`_create_sweeping_pass` imzasına `shell_offset` eklendi, fonksiyon içinde `m_rad` güncellendi:
```python
# SONRA — _create_sweeping_pass imzası:
def _create_sweeping_pass(self, start_z, end_z, mandrel_mgr, center_x,
                          r_tool, blank_thick, finish_allowance, shell_offset,
                          pass_name, t_list, p_list, c_list, d_list):
    ...
    m_rad = mandrel_mgr.get_radius_fast(current_z) + shell_offset   # ✅
```

`calculate_paths` içindeki çağrı güncellendi (satır ~304):
```python
self._create_sweeping_pass(..., shell_offset, pass_label, ...)
```

Straight-line finishing (satır ~293–298):
```python
# SONRA:
r_s = mandrel_mgr.get_radius_fast(start_h) + shell_offset   # ✅
r_e = mandrel_mgr.get_radius_fast(end_h)   + shell_offset   # ✅
```

**Geri alma:** Her iki satırdan `+ shell_offset` kaldır, `_create_sweeping_pass` imzasından `shell_offset` parametresini ve çağrısından argümanı çıkar.

---

### Bug 2 — Kalibrasyon diyaloğu blank thickness yanlış parametreden okuyor/yazıyordu

**Dosya:** `ui/dialogs/touch_calibration.py`

**Problem:**
Kalibrasyon diyaloğundaki "Blank thickness" alanı başlangıç değerini `shell_thickness`'tan alıyor, "Apply" butonu da `shell_thickness`'a yazıyordu:
```python
# HATA (önce) — satır 264:
_blank_default = float(p0.get("shell_thickness", 0.0))

# HATA (önce) — _apply_blank:
self.app.on_param_change("shell_thickness", self._new_blank, "paths")
```

Ama path generator'da blank kalınlığı olarak `final_part_thickness_on_mandrel` kullanılır:
```python
# path_generator.py:
blank_thick = params.get("final_part_thickness_on_mandrel", 2.0)
total_off   = r_tool + blank_thick + safety + allowance
```

`shell_thickness` ise mandrel yarıçapına eklenen ayrı bir görsel/geometrik offset. Blank touch kalibrasyonu bu ikisini karıştırıyordu.

**Düzeltme:**
```python
# SONRA — satır 264:
_blank_default = float(p0.get("final_part_thickness_on_mandrel",
                               p0.get("shell_thickness", 0.0)))

# SONRA — _apply_blank:
self.app.on_param_change("final_part_thickness_on_mandrel", self._new_blank, "paths")

# SONRA — except fallback'ler (3 lokasyon):
blank = float(p.get("final_part_thickness_on_mandrel", p.get("shell_thickness", 0.0)))
```

Hint ve button metinleri de güncellendi (`shell_thickness` → `final_part_thickness_on_mandrel`).

**Geri alma:** Yukarıdaki 5 lokasyonu `shell_thickness` ile geri yaz.

---

### Bug 3 — `add_op` yeni operasyon için `r_tool` yerine `radius` okuyor

**Dosya:** `ui/tabs/program_tab.py` satır ~1725

**Problem:**
Yeni operasyon eklenirken (`add_op`) varsayılan r_tool değeri `tools.json["radius"]`'ten (STEP geometrisinden hesaplanan disk yarıçapı) alınıyordu:
```python
# HATA (önce):
def_r_tool = tl.get("radius", 25.0)
```

Oysa tool seçim callback'i (`on_tool_change`) önce `r_tool`'a (kalibre değer) bakıyor, fallback olarak `radius`'a düşüyor. Tutarsızlık oluşuyordu.

**Düzeltme:**
```python
# SONRA:
def_r_tool = tl.get("r_tool") or tl.get("radius", 25.0)
```

Her iki fallback satırı da (varsayılan ID bulunmadığında ilk tool'dan okuma) aynı şekilde düzeltildi.

**Not:** Mevcut `tools.json`'da `radius` ve `r_tool` aynı değer (73.79 / 77.53 / 74.31) olduğundan bu bug şu an görünür etki yaratmıyor. `r_tool` kalibre edilince (örneğin 79.5 gibi) fark ortaya çıkacak.

**Geri alma:** `tl.get("r_tool") or tl.get("radius", 25.0)` → `tl.get("radius", 25.0)`

---

### Tasarım Notu: Adaptive finishing'de fazladan safety clearance

Düzeltilmedi ama kayıt altına alındı:

`_create_adaptive_pass` `safety_clearance_roller_to_part` (varsayılan 0.5 mm) ekliyor.
`_create_sweeping_pass` eklemıyor.

Her ikisi de finishing modu. Metal sivama'da finishing pasası yüzeye temas etmeli → sweeping doğru, adaptive 0.5 mm fazla uzakta. Kasıtlı mı yoksa hata mı — ayrı karar.

---

## 2026-06-22 — r_tool Semantics Fix: tool selection callback & get_contact_radius()

### Özet / Problem

Roughing + finishing operasyonları aynı takımı (T0103) kullanmasına rağmen finishing straight-line pasası roughing'den ~69mm uzakta görünüyordu.

### Root Cause

`tools.json` içinde **iki farklı** takım boyutu alanı var:

| Alan | T0103 değeri | Ne anlama gelir |
|------|-------------|-----------------|
| `radius` | 148.62 | Disk **çapı** (diameter) — `get_contact_radius()` tarafından hesaplanır, görselleştirme referansı |
| `r_tool` | 79.5 | Kalibre edilmiş efektif ulaşma mesafesi (makine X referansı → temas noktası) — path gen için doğru değer |

**`get_contact_radius()` neden çap döndürüyor?**
`_build_canonical()` sonrası TIP (mandrel'e en yakın nokta) orijine taşınır. Disk ekseninden (Y) en uzak nokta = diğer tarraftaki disk kenarı = TIP'ten 2R uzakta. `sqrt(X²+Z²).max()` → 2R = çap, R değil.

45° `step_rotation[1]` (Ry = mil ekseni etrafı dönüş) simetrik disk için bu ölçümü değiştirmez.

**Callback hatası:**
`program_tab.py`'daki `on_tool_change` her iki yerde de `found.get("radius", 0.0)` okuyordu (148.62 = çap), bunu operasyonun `r_tool` alanına yazıyordu. Path generator bu değeri disk yarıçapı gibi kullanınca takım yüzeye 69mm fazla uzakta konumlandı.

### Yapılan Değişiklikler

**`tool_step_loader.py` — `get_contact_radius()`**
```python
# Önce:
return float(np.sqrt(pts[:, 0] ** 2 + pts[:, 2] ** 2).max())
# Sonra:
return float(np.sqrt(pts[:, 0] ** 2 + pts[:, 2] ** 2).max()) / 2.0
```
"Calc Radius from STEP" butonu artık disk yarıçapını (~74mm) verir, çapı değil (~148mm).

**`program_tab.py` — 4 lokasyon** (satır ~555, ~565, ~614, ~625)
`on_tool_change` ve `_init_*_var` fonksiyonları artık öncelik sırası:
```python
# Önce:
r = found.get("radius", 0.0)

# Sonra:
r_cal = found.get("r_tool")
r = r_cal if r_cal is not None else found.get("radius", 0.0)
```
T0103 için → 79.5 (kalibre). T0101/T0102 için (r_tool=null) → radius'a düşer (eski davranış korunur).

**`settings.json` — Her iki operasyon düzeltildi**
`r_tool: 148.62` → `r_tool: 79.5` (roughing ve finishing).

### Geri Alma

1. `tool_step_loader.py:171` — `/ 2.0` kaldır
2. `program_tab.py` 4 lokasyon — `r_cal / r =` bloklarını `r = found.get("radius", 0.0)` ile değiştir
3. `settings.json` — her iki op'ta `r_tool` tekrar 148.62 yap

### Neden `r_tool` ≠ disk yarıçapı?

Disk 45° eğimli monte edildiğinden efektif X uzanımı `R·cos(45°) ≈ 52mm`'dir — ama kalibre edilen 79.5mm hem bu eğim açısını hem de mekanik offset'i içerir. "Calc Radius" butonu geometrik disk yarıçapını verir (~74mm); path gen için her zaman kalibre `r_tool` alanı kullanılmalıdır.

---

## 2026-06-22 — TODO Audit & Cleanup: Dead Code, Dead Params, Param Renames

### Özet
TODO listesi gözden geçirildi. Tamamlananlar işaretlendi, gereksizler kaldırıldı.
Kod temizliği yapıldı: dead code, dead parametre, ve yanıltıcı parametre isimleri.

### Tamamlandı olarak işaretlendi
- **#27** UI Internationalization — `i18n.py` zaten mevcut, 638 `t()` çağrısı var
- **#3** Roughing Clearance — `conformal_clearance_operation_specific` per-op checkbox ile zaten çözülmüş
- **#10** Linear Approach Forward Pass Geometry — `_ap_split` + `last_render_split_idx` zaten implemente
- **#11** Linear Approach Back Pass Geometry — back pass approach arm hiç dahil edilmiyor, sorun yok

### Kaldırıldı / İptal edildi
- **#2** Finishing Pass Count > 1 — kullanıcı birden fazla finishing op ekleyebilir, gerek yok
- **#21** `last_pass_extension_z` — hiç kullanılmıyordu, **tamamen kaldırıldı**

---

### `path_generator.py` — `visual_shell_offset` kaldırıldı

`visual_shell_offset = shell_offset + (1.0 if is_finish else 0.0)` satırı silindi.
Bu değişken gizlice finishing pasolarına +1mm standoff ekliyordu:
- `_create_adaptive_pass` içinde `r_contact` hesabına giriyordu
- Back pass clearance correction'ına giriyordu
- Back pass deviation görselleştirmesine giriyordu

Tüm 5 kullanım `shell_offset` ile değiştirildi. Kalibrasyon etkilenmez.

**Geri alma:** `visual_shell_offset = shell_offset + (1.0 if is_finish else 0.0)` satırını
`pass_label` tanımından önce ekle; 5 `shell_offset` → `visual_shell_offset` geri al.

---

### `path_generator.py` — Dead code kaldırıldı

- `safety_tolerance = 0.05` — hiç kullanılmıyordu, silindi
- `_calculate_adaptive_z_distribution()` — `return []` stub, silindi

---

### Parametre kaldırıldı: `last_pass_extension_z`

**Dosyalar:** `path_generator.py`, `main.py`, `constants.py`, `settings.json`, `test_headless.py`

Son pasoyu mandrel tepesinin ötesine uzatmak için planlanmıştı ama hiç kullanılmadı.
`end_h = top_z + last_pass_ext` → `end_h = top_z`

---

### Parametre kaldırıldı: `roller_nose_radius_param`

**Dosyalar:** `main.py`, `constants.py`, `settings.json`, `test_headless.py`, `deneme_mandrel.ssp`

Rulonun burun yarıçapı için planlanmıştı (CNC freze'deki kesici yarıçap kompanzasyonu gibi).
Hiç okunan bir yerde `params.get("roller_nose_radius_param")` bulunmuyordu — ölü parametre.

---

### Parametre yeniden adlandırmaları

| Eski İsim | Yeni İsim | Dosyalar |
|-----------|-----------|----------|
| `adaptive_rough_mode` | `conformal_clearance_all_operations` | `main.py`, `path_generator.py`, `process_tab.py`, `settings.json` |
| `conformal_clearance` | `conformal_clearance_operation_specific` | `path_generator.py`, `program_tab.py`, `settings.json` |
| `normal_aligned_shift` | `clearance_correction_per_point` | `main.py`, `path_generator.py`, `process_tab.py`, `settings.json` |
| `adaptive_finish_mode` | `finish_trace_mandrel_profile` | `main.py`, `path_generator.py`, `process_tab.py`, `settings.json`, `test_path_generator.py` |
| `adaptive_resolution` | `finish_trace_resolution` | `main.py`, `path_generator.py`, `process_tab.py`, `settings.json` |

**Geri alma:** her ismi eski haline çevir (tüm dosyalarda replace).

---

## 2026-06-21 — Dinamik Dil Seçimi (i18n): EN / TR / ES

### Genel

Programdaki tüm görünür metin artık `i18n.py`'deki `t(key)` fonksiyonundan gelir.
Dil, menü çubuğundan seçilir; seçim `settings.json`'a kaydedilir ve program yeniden
başlatılsa bile korunur. Dil değiştirildiğinde tüm tab'ler widget'larını yeniden oluşturur.

**Kural:** Bundan sonra yapılan her değişiklikte yeni string'ler için `i18n.py`'e
EN / TR / ES üç dil karşılığı birlikte eklenmelidir.

---

### `i18n.py` — YENİ DOSYA

- `STRINGS = { key: {"EN": ..., "TR": ..., "ES": ...} }` — ~215 anahtar
- `t(key)` — aktif dilde string döndürür; anahtar eksikse EN'e düşer, EN de yoksa key döner
- `set_language(lang)` / `get_language()` — global dil durumu
- `LANGUAGES = ["EN", "TR", "ES"]`, `LANGUAGE_NAMES` — UI için

**Geri alma:** Dosyayı sil ve tüm `from i18n import t` / `t("...")` çağrılarını eski
string literalleriyle değiştir (ama bu büyük bir geri alma olur).

---

### `main.py`

- `load_settings()` `default_params` sözlüğüne `"language": "EN"` eklendi (~satır 135).
  Program ilk açıldığında dil varsayılanı İngilizce.

---

### `ui/main_window.py`

- `import i18n` + `from i18n import t, set_language, get_language, LANGUAGES, LANGUAGE_NAMES` eklendi.
- Startup'ta: `set_language(self.app.params.get("language", "EN"))`.
- `_create_menu()`: `"Language"` cascade menüsü eklendi — her dil için `add_radiobutton`.
- `_change_language(lang)`: dil değiştirir, `settings.json`'a kaydeder, menüyü ve tab'leri yeniden oluşturur.
- `rebuild_all_tabs()`: tab başlıklarını günceller, her tab'in `rebuild()` / `refresh_ui()` metodunu çağırır.
- Menü öğeleri, dosya dialogları, mesaj kutuları, durum çubuğu — hepsi `t()` kullanıyor.

---

### `ui/tabs/process_tab.py`

- `from i18n import t` eklendi.
- `rebuild()` metodu eklendi: `self.content` altındaki widget'ları yok eder, `_create_widgets()` yeniden çağırır.
- Tüm bölüm başlıkları, butonlar, checkbox'lar, mesaj kutuları `t()` kullanıyor.

---

### `ui/tabs/machine_tab.py`

- `from i18n import t` eklendi.
- `refresh_ui()` zaten vardı (destroy + recreate pattern) → `rebuild()` yoktur, `refresh_ui()` kullanılır.
- LabelFrame başlıkları, label'lar, butonlar, treeview sütunları, mesaj kutuları `t()` kullanıyor.

---

### `ui/tabs/program_tab.py`

- `from i18n import t` eklendi (satır 5).
- **`t` değişken çakışması düzeltildi:** Dosyada `t` loop değişkeni olarak kullanılan 8 yer
  `tl` olarak yeniden adlandırıldı (list comprehension'lar, `next(...)` atamaları, `for t in` döngüleri).
- `rebuild()` metodu eklendi (dosyanın sonunda): `self.frame` altındaki widget'ları yok eder,
  `_create_widgets()` yeniden çağırır.
- Treeview başlıkları, toolbar butonları, LabelFrame'ler, prop editor label'ları, pass navigator,
  hız/besleme başlıkları, referans noktası dialog'u, pass diyagramı popup — hepsi `t()` kullanıyor.
- `update_time_estimate()`: `f"Est. Time: ..."` → `f"{t('lbl_est_time')} {m:02d}:{s:02d}"`

---

### `ui/dialogs/tool_manager.py`

- `from i18n import t` eklendi.
- Başlık, LabelFrame'ler, label'lar, butonlar, mesaj kutuları, durum label'ı — hepsi `t()` kullanıyor.
- `for t in self.ui.tool_library` döngüleri → `for tl in ...` (çakışma önleme).

---

### `i18n.py`'e eklenen yeni anahtarlar (2026-06-21 sonu itibariyle)
`btn_ok`, `btn_cancel`, `btn_edit`, `btn_ref_add`, `btn_ref_remove`,
`dlg_add_ref_point`, `dlg_edit_ref_point`,
`lbl_z_offset_tip`, `lbl_x_offset_tip`, `lbl_label_colon`

---

## 2026-06-20 — Calibration Dialog: STEP-based roller silhouette, view fixes, consistency fix

### `ui/dialogs/touch_calibration.py`

**1. STEP-based roller silhouette in 2D canvas** (replaces circle fallback)
- `_get_tool_profile_pts(tid, side)` — now delegates to `loader.get_2d_profile()` (was inline mesh processing)
- `_draw_scene` (lines ~1490–1565): roller drawn as polygon instead of oval
  - Expected roller: dashed green `create_polygon(fill="", outline=C_GOOD, dash=(4,3))`
  - Measured roller: solid yellow `create_polygon(fill=C_RFILL, outline=C_TOUCH)`
  - Tip at `cam_x_surf`; measured polygon shifted by `cam_x_actual − cam_x_exp`
  - Falls back to circles if no STEP file or mesh load fails

**2. Full mandrel cross-section in 2D canvas**
- `x_top` changed from `cx_man − side*r_max*0.25` → `cx_man − side*r_max*1.15`
  - Old: showed only 25% of mandrel radius above axis → roller looked disproportionately large
  - New: shows full mandrel diameter (both sides of spindle axis)
- Mirror half of mandrel polygon added (same profile, X-flipped, lighter outline)

**3. Consistency check surface fix**
- `self._x_surface` added to state (line ~46); saved in `_calculate` after `self._x_delta`
- `_check_consistency` now uses `self._x_surface` instead of hardcoded `"mandrel"`
  - If first touch was on blank, second touch also computed as blank → deltas truly comparable
  - Result label now shows surface name: `✓ Consistent (blank)` / `✓ Consistent (mandrel)`
- Hint text updated: "Touch a second Z location using the same surface as the first touch."

**Geri Alma:** Yukarıdaki üç değişiklik için ilgili satırları eski hâliyle değiştir.
  `x_top` ve `x_signed_span` hesabı `py_per_cam`'ı da etkiler — birlikte döndür.

### `tool_step_loader.py`

**4. `get_2d_profile(tool_entry, side)` — new public method**
- Canonical mesh al (`_get_canonical`, cached) → `rotate_x(-alpha)` uygula (alpha = step_rotation[1])
  - Ry(alpha) canonical'da eksenin etrafında döner → XZ projeksiyonunu değiştirmez (simetrik disk)
  - Rx(-alpha) diski XZ düzleminden dışarı eğer → yan görünümde doğru açı görünür
- Side flip uygula, XZ convex hull hesapla (scipy), CCW sıralı [[x,z],...] döndür
- Sonuç `self._cache`'e `("2d", path, mtime, shaft, rot, tip, side)` anahtarıyla kaydedilir

**Neden Ry değil Rx?**
Canonical'da mil Y ekseninde. Ry(45°) Y ekseni etrafında döner → simetrik disk için sıfır görsel etki.
Rx(-45°) diski Y ekseninden X-Z düzlemine eğer → XZ projeksiyonunda 45° elips görünür.

**tools.json**
- `r_tool` değerleri düzeltildi: T0103=79.5 (ölçülmüş), T0101/T0102=null (henüz ölçülmedi)
  (Kullanıcı Tool Manager'dan disc yarıçapı ile üzerine yazmıştı)

---

## 2026-06-19 — Touch Point Calibration v3 (Z-axis + canvas visualization)

### `ui/dialogs/touch_calibration.py` — tam yeniden yazım

**Yeni özellikler:**
- **Z ekseni kalibrasyonu:** Operatör bilinen bir Z referans noktasına (mandrel tabanı=Z0,
  mandrel tepesi=oto, özel CAM Z) rulоyu götürür, DRO Z değerini girer.
  `Program Start Z (home_z)` veya `G-code Z Offset (machine_gcode_offset_z)` ile düzeltilir.
- **Canvas görselleştirme** (sola yerleştirilmiş, yeniden boyutlandırılabilir, zoom+pan):
  - XZ kesit görünümü: mandrel profili (dolgulu + tarama çizgileri), blank halkası, ruloların dairesi
  - Beklenen konum (yeşil kesik daire) + ölçülen konum (sarı dolgu daire) ayrı gösterilir
  - Delta hata oku: `|ΔX|>2mm` → kırmızı, `>0.5mm` → turuncu
  - Z referans çizgileri: beklenen Z (yeşil dikine) vs ölçülen Z (sarı dikine) + ΔZ oku
  - Ölçü köşeli parantezleri: mandrel R, blank kalınlığı, ruло yarıçapı
  - Makine orijinleri: Z-origin (pembe kesik) + X-origin (yeşil kesik) referans çizgileri
  - Lejant + "scroll=zoom drag=pan dbl-click=reset" ipucu
- **Apply butonları** (5 adet): Program Start X/Z, Mandrel Offset, Blank Thickness, G-code Z Offset.
  `origin_use_home=True` iken ★ (yeşil) = Program Start X/Z; aksi hâlde Mandrel Offset + G-code Z Offset önerilir.
- **İkinci temas kontrolü** (opsiyonel X ekseni STEP tutarlılık testi) → korundu.

**Koordinat matematiği:**
```
X_machine = (cam_x - origin_x) * dir_x + off_x
Z_machine = (cam_z - origin_z) * dir_z + off_z

new_home_x  = home_x  - delta_x / dir_x
new_cx      = cx       + delta_x / dir_x
new_blank   = blank    + (delta_x / dir_x) * side
new_home_z  = home_z  - delta_z / dir_z
new_off_z   = off_z   - delta_z           (G54 Z offset'e doğrudan eklenir)
```

**Geri Alma:** `ui/dialogs/touch_calibration.py`'yi bir önceki sürümle değiştir.
  Machine Tab butonu değişmedi; `machine_gcode_offset_z` parametresi zaten mevcut.
**Dosyalar:** `ui/dialogs/touch_calibration.py` (tamamen yeniden yazıldı)

---

## 2026-06-18 — Touch Point Calibration Dialog (v2 — final)

### Touch Calibration (`ui/dialogs/touch_calibration.py` — NEW, rewritten twice this session)
Operatör rulоyu mandrele veya blanka temas ettirip DRO değerini okuyarak
program başlangıç pozisyonunu, mandrel ofsetini veya blank kalınlığını kalibre edebilir.

**Son durum (v2):**
- **Mode banner:** Diyalog açılışında mevcut `origin_use_home` durumu, `home_x` ve X yönü gösterilir.
- **Step 1:** Touch Z, Machine X, surface type (mandrel / blank)
- **Step 2:** Calculate → monospace sonuç kutusu:
  - Expected machine X (koordinat dönüşümü uygulanmış), machine X, delta (machine space)
  - Üç parametre için current → recommended yan yana: `home_x`, `mandrel_pos_x_offset`, `shell_thickness`
  - delta > 2 mm → kırmızı, > 0.5 mm → turuncu
- **Step 3:** Üç Apply butonu:
  - **Apply as Program Start X** — `home_x` günceller; `origin_use_home=True` ise yeşil + "← recommended" etiketi
  - **Apply as Mandrel Offset** — `mandrel_pos_x_offset` günceller; `origin_use_home=False` ise yeşil
  - **Apply as Blank Thickness** — `shell_thickness` günceller
- **Optional:** İkinci temas noktası + "Check Consistency"

**Koordinat matematiği (v1'de eksikti — DÜZELTİLDİ):**
`expected_machine_x = (cam_x - origin_x) * dir_x + off_x`  
Uygulama formülleri:
- `new_home_x  = home_x - delta / dir_x`
- `new_cx      = cx + delta / dir_x`
- `new_blank   = blank + (delta / dir_x) * side`

**Neden home_x çalışır:** `origin_use_home=True` olduğunda `machine_origin_x = home_x`.
Tüm G-code koordinatları home'dan mesafe olarak üretildiğinden home_x'i değiştirmek
tüm pasları machine space'te eşit miktarda kaydırır.

**Geri Alma:** `ui/dialogs/touch_calibration.py` sil; `machine_tab.py`'deki `f_touch` bloğunu kaldır.
**Dosyalar:** `ui/dialogs/touch_calibration.py` (yeni), `ui/tabs/machine_tab.py`

---

## 2026-06-18 — 6 Toplu Düzeltme / Geliştirme

### #26 Roller Radius — Auto-Calc from STEP
`ToolStepLoader.get_contact_radius()` eklendi: canonical mesh yüklendikten sonra
`sqrt(x²+z²).max()` ile XZ-düzleminde maksimum mesafeyi hesaplar.
Tool Manager'a "Calc Radius from STEP" butonu + sonuç etiketi eklendi.
**Dosyalar:** `tool_step_loader.py`, `ui/dialogs/tool_manager.py`

### #14 Safety Standoff — UI'da Görünür
`safety_clearance_roller_to_part` Process Tab → Safety & Correction bölümüne "Safety Standoff (mm)"
spinbox olarak eklendi. Daha önce path_generator'da 0.5 mm hardcode olarak kalıyordu.
**Dosyalar:** `ui/tabs/process_tab.py`
**Geri Alma:** `add_spinbox` satırını sil; path_generator.py zaten varsayılan 0.5 mm kullanıyor.

### #17 Pass Coloring — Operasyon Tipine Göre Doğru Renk
`op_types` listesi `op_feeds` ile birlikte derlendi (aynı döngü, aynı sıra).
`is_finish_pass = (i >= num_rough)` yerine `op_types[i] == "finishing"` kullanılıyor.
Back pass: yeni `is_back_pass` bayrağı → teal rengi.
`num_rough` (eski global) kaldırıldı.
**Dosyalar:** `main.py` ~525–595

### #18 Back-Pass Projections — Gerçek Yoldan Hesap
`PathGenerator._compute_proj_and_devs()` yardımcı metodu eklendi.
Back pass projection/deviation değerleri artık forward pass dizisinin tersi yerine
back pass'ın kendi noktalarından hesaplanıyor.
**Dosyalar:** `path_generator.py` ~376, ~1097

### #23 Mandrel Scan — Adaptif 2-Geçiş
Pass 1: 18 ışın (20° adım) → tüm Z dilimleri için hızlı coarse tarama.
Pass 2: 72 ışın yalnızca lokal bağlamdan >0.4 mm düşük kalan Z dilimlerinde.
Düzgün mandrellerde ~4× hızlanma; yüzey geçişlerinde doğruluk korunuyor.
`_COARSE_ANGLES` sınıf değişkeni eklendi.
**Dosyalar:** `mandrel_analyzer.py` ~115–165

### #15 Dead Code Cleanup
- `gui_manager` import kaldırıldı (`main.py`)
- `if not headless:` branchi + GuiManager instantiation kaldırıldı (`main.py`)
- `"auto_align_rotation": False` param default kaldırıldı (`main.py`)
- `auto_align = params.get("auto_align_rotation", False)` ölü okuma kaldırıldı (`path_generator.py:76`)
- `gui_manager.py`, `ui_sidebar.py` orphan dosyalar olarak kalıyor (silinmedi).
**Dosyalar:** `main.py`, `path_generator.py`

---

## 2026-06-17 — Exit Arc Angle Parametresi (`exit_arc_angle`) — exit_bow'u Değiştirdi

**Sorun:** `exit_bow` (mm) sezgisel değildi ve Bézier parabolik bir eğri üretiyordu.
Kullanıcı T2→P3 bölümünü açıyla kontrol edilebilen dairesel bir yay olarak istiyor.

**Çözüm:** `exit_arc_angle` (derece) parametresi eklendi.
T2'deki tanjant-kiriş açısını tanımlar ve gerçek bir dairesel yay üretir:

```
R = chord_len / (2 × sin(|α|))
arc_sweep = 2α  (pozitif = dışa, negatif = içe)
merkez = chord_orta - sign × R × cos(α) × perp_xz
```

`perp_xz`: XZ düzleminde kirişe dik, daima pozitif X (dışa) yönünde.
0° = düz çizgi. 20° = hafif yay, 45° = belirgin kavis.

**Geri Alma:**
`path_generator.py` ~814'te `else:` bloğunu önceki `exit_bow` Bézier koduna döndür.
`machine_tab.py`'de "Exit Arc Angle" girişini "Exit Bow" ile değiştir.
`settings.json`'da `exit_arc_angle` → `exit_bow: 0.0`.

**Değiştirilen Dosyalar:**
- `path_generator.py` ~814: dairesel yay hesabı
- `ui/tabs/machine_tab.py`: "Exit Arc Angle (°)" girişi
- `settings.json`: `exit_bow` → `exit_arc_angle: 0.0`
- `CODE_NAVIGATION.md` §15: güncellendi

---

## 2026-06-17 — Exit Bow Parametresi (`exit_bow`)

**Sorun:** `exit_curve_tension` exit eğrisini (T2→P3) hiç eğmiyordu.
Neden: `T2 = P2 + tangent_len * d2` ve `P3 = P2 + |P3-P2| * d2` olduğundan,
kontrol noktası `T2 + tension * d2` da aynı ışın üzerindeydi.
T2, ctrl_exit ve P3 üç nokta da eş doğrusal → Bézier her zaman düz çizgi.
Tek fark: `tension` değeri artınca noktalar P3 tarafında yoğunlaşıyordu
(kullanıcı "P3 yakınında nokta ekleniyor" olarak gözlemledi).

**Kök Neden:** `d2 = (P3 - P2) / |P3-P2|` yönünde konumlanan kontrol noktası,
T2'den P3'e giden kirişle paralel → sıfır eğrilik.

**Çözüm:** `exit_bow` (mm) parametresi eklendi.
Kontrol noktası, T2→P3 kirişinin **dik yönünde** kaydırılır:

```
ctrl_exit = 0.5*(T2 + P3) + 2.0 * exit_bow * perp_xz
```

`perp_xz`: XZ düzleminde kirişe dik vektör, daima pozitif X (dışa doğru) yönünde.
`2.0×`: Bézier orta noktası B(0.5) = 0.25T2 + 0.5ctrl + 0.25P3 formülünden,
ctrl'ü kirişten `exit_bow` kadar uzaklaştırmak için 2× çarpanı gerekir.

`exit_curve_tension` parametresi kaldırıldı (settings.json'da hâlâ varsa ignore edilir).

**Geri Alma:**
`path_generator.py` ~satır 814'te `else:` bloğunu şuna döndür:
```python
exit_tension = float((op or {}).get("exit_curve_tension", 0.4))
exit_len     = max(np.linalg.norm(p3_arr - T2), 0.1)
ph_dist      = exit_len * exit_tension
ctrl_exit    = T2 + ph_dist * d2
```
`machine_tab.py`'de "Exit Bow (mm)" frame bloğunu sil.

**Değiştirilen Dosyalar:**
- `path_generator.py` ~satır 814–833: Bézier kontrol noktası hesabı
- `ui/tabs/machine_tab.py` ~satır 488: "Exit Bow (mm)" girişi eklendi (PLC bölümünde)
- `CODE_NAVIGATION.md` §15: parametre tablosu güncellendi

---

## 2026-06-17 — PLC Mod: T2 Split + Exit Tolerance Parametresi

**Sorun:** `linear_approach` paslarında PLC modu exit eğrisini (T2→P3) her zaman tek
düz G1 çizgisine dönüştürüyordu. `exit_curve_tension` değeri yüksek olsa bile
düzelmiyordu. Neden: `_decimate_path_for_plc` T2'yi bilmiyordu; exit eğrisi fileto
ile aynı RDP half'ına düşüyordu. Bu half'ın kirişi `critical_pt → P3` (fileto içinden
P3'e, uzun ve çapraz) olduğundan exit noktalarının sapması küçük görünüyor ve
hepsi siliniyordu — `exit_curve_tension` ne olursa olsun.

**Çözüm:** İki bileşen:

1. **`arc_end_idx` parametresi (`_decimate_path_for_plc`)** — T2 pozisyonunu alarak
   yolu üç bağımsız RDP bölgesine ayırır:
   - Yaklaşım kolu `[ap_start..T1]` → 2 nokta olduğu gibi korunur (önceki fix)
   - Fileto `[T1..T2]` → `tolerance` ile RDP
   - Exit eğrisi `[T2..P3]` → `exit_tolerance` ile RDP, kiriş artık `T2→P3`
   
   `generate_gcode` içinde `last_render_split_idx[i][1]` (T2 konumu) `arc_end_idx`
   olarak iletilir. Spline / geri pas için `None` → mevcut davranış korunur.

2. **`plc_exit_tolerance` parametresi** — exit bölümü için bağımsız RDP toleransı.
   `None` / ayarlanmamışsa `plc_tolerance` değeri kullanılır.
   - Büyük değer (ör. 2.0 mm) → çıkış yolunda çok az nokta (retraksiyon yolu
     için yeterli; fileto hassasiyetini etkilemez)
   - Küçük değer (ör. 0.05 mm) → exit eğrisi şekli korunur

**Değişen dosyalar:**
- `path_generator.py` — `_decimate_path_for_plc`: yeni `arc_end_idx` ve
  `exit_tolerance` parametreleri; üç bölümlü dal eklendi (~1518)
- `path_generator.py` — `generate_gcode`: `_split[1]` ve `plc_exit_tolerance`
  iletimi (~1098)
- `ui/tabs/machine_tab.py` — PLC bölümüne "Exit Tolerance" giriş alanı eklendi

**Geri almak için:** `_decimate_path_for_plc` üç bölümlü dalı sil, `generate_gcode`
çağrısından `arc_end_idx` ve `exit_tolerance` kaldır, `machine_tab.py` exit tol
widgetını kaldır. Önceki iki bölümlü `approach_end_idx` davranışı korunur.

---

## 2026-06-17 — PLC Mod: Geri Pas Eğri Noktaları İleri Pasla Eşitlendi

**Sorun:** `linear_approach` + `plc_mode=True` kombinasyonunda geri pas, eğri
bölgesinde (P2 fileto + çıkış eğrisi) ileri pasa göre **daha fazla nokta**
üretiyordu. Nedeni `_decimate_path_for_plc`'nin RDP algoritmasının iki pas için
farklı referans kirişleri kullanmasıydı:

- **İleri pas half1 kirişi:** `ap_start (X büyük) → P2 (X küçük)` — düz yaklaşım
  kolunu da içerdiğinden çok uzun ve çapraz bir kiriş. RDP bu uzun kirişe göre
  ölçtüğünden fileto yayının sapmaları küçük görünüyor → fileto noktaları
  agresif siliniyor.
- **Geri pas half2 kirişi:** `P2 → T1` — sadece fileto bölümü; kiriş kısa ve
  fileto ölçeğinde. RDP daha fazla nokta koruyor.

Sonuç: aynı fiziksel fileto eğrisi ileri pas G-kod'unda az, geri pas G-kod'unda
fazla noktayla temsil ediliyordu — PLC programında tutarsız hız profili.

**Kök neden:** `_decimate_path_for_plc`, `last_render_split_idx`'ten habersizdi;
düz yaklaşım kolu (`ap_start → T1`) ile oluşturma eğrisini (`T1 → P3`) aynı
RDP çağrısında birleştiriyordu.

**Çözüm (`path_generator.py`):**

1. `_decimate_path_for_plc` yeni opsiyonel parametre aldı:
   `approach_end_idx=None` (satır ~1518).  
   Verildiğinde yaklaşım kolunu `[ap_start, T1]` (2 nokta) olduğu gibi korur,
   RDP'yi yalnızca `[T1..P3]` oluşturma eğrisine uygular.

2. `generate_gcode` PLC listesi artık her yol için `last_render_split_idx`
   tablosuna bakıp `approach_end_idx` değerini iletiyor (satır ~1098–1107).  
   Spline paslar ve geri paslar için tablo girişi yok → `None` → mevcut
   davranış korunuyor.

**Beklenen etki:**
- İleri pas PLC noktaları: fileto bölgesi artık `ap_start→P2` kirişi yerine
  `T1→P2` kirişine göre RDP uyguluyor → geri pasla aynı sayıda eğri noktası.
- Spline / geri pas / sweeping pas: parametre `None` → birebir eski davranış.
- Geriye uyumlu: `approach_end_idx` varsayılan `None`, mevcut testler etkilenmez.

**Geri almak için:** `generate_gcode`'daki liste-kavramayı eski haline getir
(`self._decimate_path_for_plc(p, plc_tolerance, center_x)`), `_decimate_path_for_plc`
imzasını eski haline getir ve `approach_end_idx` guard bloğunu sil.

---

## 2026-06-16 — Yaklaşım Kolu Yüzeye Paralel (`approach_follow_surface`)

**Sorun:** `linear_approach`'ta P1→P2 yaklaşım kolu sabit X'te (dik, Z eksenine paralel)
kuruluyordu — sadece P2 yüzeye göre yerleşiyor, kol açılı yüzeye paralel olmuyordu. Eğimli
duvarda kol boyunca clearance değişiyor; aşağı genişleyen koni gibi durumlarda kolun ALT ucu
bağlayıcı olup tüm pası dışarı itiyor, P2'yi fazla dışarı bırakıyordu (forming temasını
kaçırıyor).

**Çözüm:** yeni per-op `approach_follow_surface` (default KAPALI → mevcut davranış birebir
korunur). Açıkken `_create_and_store_pass` linear yaklaşım kolunu P2'deki yüzey TEĞETİ
boyunca kurar:
```python
_anx,_anz = mandrel_mgr.get_normal_at_z(p2.Z())
_appr = [ _anz, 0, -_anx ]   # normale dik = yüzey teğeti; alt Z'ye yönlendirilir
ap_start = p2_arr + p1_z_off * _appr
d1 = _appr                   # fileto da eğik kola teğet kalır
```
Dik yüzeyde `_appr → [0,0,-1]` olduğundan eski davranışa indirgenir.

**Doğrulandı (aşağı genişleyen koni, r=60−0.45·z):**
- OFF, parametre yokken ile BİREBİR aynı (geriye uyumlu).
- OFF: kol clearance 0.5→14.0 (spread 13.5mm), P2 = 14.0 (fazla itilmiş).
- ON: kol clearance 0.5→0.5 (spread 0.000), P2 = 0.5 (tam hedef, fazla itme yok).

**UI (`program_tab.py`):** Path Shape bölümünde Conformal Clr'in altına `Approach ∥ Surf`
checkbox'ı. Yalnızca linear_approach / linear_full'da anlamlı.

**Geri almak için:** `approach_follow_surface` dalını sil (`_appr` hep `[0,0,-1]`, `d1` hep
`[0,0,-1]`), UI checkbox'ını kaldır.

---

## 2026-06-16 — İleri Pas: Çıkış Kuyruğunu M'den Sonra Döndürme [TODO #13]

İlk tasarım (M'de G1 birleşen iki Bézier, kilitli T2→M) kullanıcı için fazla karmaşıktı.
Asıl ihtiyaca indirgendi: **çıkış eğrisi üzerinde bir M noktası seç, M'den sonrasını M
etrafında birkaç derece döndür.**

**`path_generator.py` (`linear_approach` çıkış bloğu):** çıkış yine tek quadratic T2→P3;
ardından `exit_mid_rotation` (derece) ≠ 0 ise:
- M = çıkış üzerinde `exit_mid_t` oranındaki nokta (default 0.5, 0.05–0.95 sınırlı).
- M'den sonraki tüm noktalar M etrafında `exit_mid_rotation` derece döndürülür (Y ekseni,
  XZ düzlemi, `_apply_rotation`). T2→M değişmez; P3 kuyrukla döner.
- `exit_mid_rotation = 0`/yok → identity (param yokken ile birebir aynı; geriye uyumlu).

**UI (`program_tab.py`):** iki alan — `Exit Mid Rot (deg)` ve `Exit Mid t`. (Eski
`exit_mid_enabled` / `exit_mid_x/z` / `exit_curve_tension_2` kaldırıldı.)

**Doğrulandı:** `rot=20°` kuyruğu döndürür (P3 ~6mm kayar, nokta sayısı sabit = rijit
rotasyon); clearance düzeltmesi yine uygulanıyor (rot −30° mandrel'e doğru → en kötü
clearance 0.500); geri pas otomatik takip eder.

**Geri almak için:** `exit_mid_rotation` rotasyon bloğunu sil (çıkış yine tek Bézier kalır),
UI'daki iki alanı kaldır.

---

## 2026-06-16 — Geri Pas: Retract Yok + Paso Seçimi

### 1. İleri→Geri pas arası retract kaldırıldı (`path_generator.py`)

İleri pas P3'te bitiyor, (mirror) geri pas aynı P3'ten başlıyor — aralarındaki retract +
yeniden yaklaşım gereksizdi.

- **`calculate_paths` (sequence/sim + rapids):** ileri cut sonrası `current_pt = end_pt`;
  geri pas varsa retract YOK, doğrudan geri cut'a akar. Sadece `bp_arc` bombesi/clearance
  kayması geri pas başlangıcını P3'ten uzaklaştırmışsa (`norm > 1e-3`) kısa güvenli köprü
  eklenir. Geri pas yoksa eskisi gibi retract.
- **`generate_gcode`:** `_back_follows = (global_path_idx + 1) in _bp_meta` ise ileri pas
  retract'ı atlanır; geri pas G0 yaklaşımı da, başlangıç ileri pas sonuyla çakışıyorsa
  (`norm > 1e-3` değilse) atlanır → araya hiç G0 girmeden `G1 F{back_feed}` ile devam.
- **Doğrulandı:** count=3 + geri pas → ileri/geri arası 0 retract; yalnızca her geri pas
  sonunda retract.

**Geri almak için:** ileri cut sonrası koşulsuz retract'ı geri koy, `_back_follows`
guard'ını ve geri pas G0 atlamasını kaldır.

### 2. Geri paslar Paso navigatöründe seçilebilir (`ui/tabs/program_tab.py`)

Önceden "Paso X/N" navigatörü `within * stride` ile yalnızca İLERİ pasları geziyordu;
geri paslar atlanıyordu. Artık `_within_op_idx` doğrudan toolpath-girdi offset'i:
`active_editing_pass_idx = op_start + _within_op_idx`. Navigatör `count * stride` girdiyi
gezer (ör. 5 pas + geri = 10 girdi: F1,B1,F2,B2,…). Etiket ileri/geri ayrımını gösterir
(`▶ İleri pas` / `◀ Geri pas`). Seçilen girdi 3D sahnede magenta vurgulanır (highlight
zaten `i == active_editing_pass_idx` toolpath indeks eşleşmesi). Navigatör artık
`n_entries > 1` ise gösterilir (count=1 + geri pas durumunda da geri pas seçilebilir).

**Geri almak için:** `active_editing_pass_idx = op_start + _within_op_idx * stride` ve
navigatörü `count` mantıksal pas ile sınırlayan eski sürüme dön.

### 3. Per-pas override indeks uzayı uzlaştırıldı (`main.py`)

`gui_pass_overrides` (per-pas slider override'ı, yalnızca `apply_to_specific_pass_only`
modunda) `active_editing_pass_idx` (toolpath indeks) ile anahtarlanırken `calculate_paths`
override'ları `global_pass_idx` (ileri-pas sayacı) ile okuyordu. Geri pas içeren op'larda
bu iki indeks uzayı örtüşmüyor, override'lar yanlış pasa uygulanıyor/uygulanmıyordu.

- **Yeni `SpinningApp._active_fwd_pass_idx()`:** toolpath indeksini → ileri-pas indeksine
  çevirir (geri pas girdisi ebeveyn ileri pasına eşlenir). `calculate_paths` düzenini
  birebir taklit eder (op başına stride, cutting/bending = 1 pas).
- `on_param_change` override'ı artık bu çevrilmiş indeksle anahtarlıyor.
- Doğrulandı: roughing(3)+geri, cutting, roughing(2) karışık düzeninde toolpath→fwd
  eşleme `[0,0,1,1,2,2,3,4,5]` (beklenenle birebir).

Sonuç: bir geri pas seçiliyken slider override'ı düzenlenirse, aynalandığı ileri pasa
uygulanır. (Property editor zaten doğrudan op paramlarına yazıyor; bu yol etkilenmez.)

**Geri almak için:** `on_param_change`'de `_active_fwd_pass_idx()` çağrısını
`active_editing_pass_idx` ile değiştir, helper'ı sil.

---

## 2026-06-16 — Back Pass Clearance: Yapısal Düzeltme (Çarpışma Bugfix)

**Semptom:** `linear_approach` modunda, geri paslar 5-6. pastan sonra clearance
kuralına uymuyor, mandrel tepesine yakın "kritik çizgiyi" geçip mandrele giriyordu.
İleri paslar güvenliydi.

**Kök neden (headless diagnostic ile kanıtlandı):** Geri pasın tek güvenlik ağı
`_clamp_radial_clearance` idi ve mandrel Z aralığı (`[min_z, top_z]`) dışındaki
**her noktayı atlıyordu** (`if sim_z > m_top_z: continue`). Geri pas yayı rutin olarak
`top_z`'nin üstüne taşıyor (P3 = contact_z + p3_z_offset; yüksek paslarda contact_z
zaten tepeye yakın). İçeri çeken `back_pass_arc_x` veya flaring/dışbükey profilde, bu
düzeltilmeyen üst noktalar mandrel içine giriyor; son düzeltilen nokta (z<top_z) ile
düzeltilmeyen üst nokta arasındaki düz G1 segmenti kenarın hemen altında yüzeyi kesiyordu.
Pas indeksi büyüdükçe yayın daha büyük kısmı kör noktaya düştüğü için "5-6. pastan sonra"
ortaya çıkıyordu.

**Düzeltme (`path_generator.py`):**
- `_clamp_radial_clearance` → **`_correct_clearance_uniform`** ile değiştirildi.
  İleri pasın kullandığı **uniform-radial-shift** prensibini tüm geri pas polyline'ına
  uygular: en kötü clearance'ı bulup bütün yolu rijit olarak dışarı öteler (bp_arc
  şekli korunur, sadece radyal konum düzeltilir — ileri pasın spline'ı dışarı kaydırması
  gibi). İki kör nokta kapatıldı:
  1. **Z-aralığı kör noktası yok:** radius lookup için Z `[min_z, top_z]`'ye clamp'lenir
     (atlanmaz) — kenarın hemen ötesi kenar yarıçapı gibi değerlendirilir, asla içine
     girilmez.
  2. **Segment-duyarlı:** clearance sadece köşe noktalarında değil, segment boyunca
     örneklenir — düz G1 kirişi dışbükey yüzeyi fark edilmeden kesemez.
  - Sadece dışarı (deficit > 0) düzeltir; güvenli yol asla içeri çekilmez → kasıtlı
    dışa bow korunur. Geri pas bloğunda (`if _fwd_splits is not None`) çağrılır;
    swap durumunda da düzeltme swap'tan önce uygulandığı için swapped-forward güvenli.

**Doğrulama:** Tüm geometri (dome/flare/cone/ogive/neck) × `back_pass_arc_x` 0…−25
kombinasyonlarında en kötü geri pas clearance = **0.499mm** (hedef 0.5; önceden flare/−15
→ **−1.545mm**). `bp_arc=0` iken geri pas hâlâ ileri pasın bire bir tersi (0.0mm fark).

**Geri almak için:** `_correct_clearance_uniform` çağrısını eski `_clamp_radial_clearance`
mantığıyla değiştir (Z-aralığı atlamalı per-point clamp). Not: bu kör noktayı geri getirir.

### Ek: Geri Pastan Düz Yaklaşım Kolu Çıkarıldı (`linear_approach`)

**İstek/Sorun:** Geri pasın sonunda, mandrel eksenine **paralel düz yaklaşım kolu**
(forward'ın P1→P2 yaklaşım kolu, ters çevrilmiş olarak P2→ap_start) yer alıyordu.
Bu kol istenmiyordu: (a) ironing/geri stroke yaklaşım kolunu geri izlememeli; (b) konik
(yukarı daralan) mandrelde kolun ALT ucu (daha büyük yarıçap bölgesi) bağlayıcı clearance
kısıtı olup tüm pası dışarı kaydırıyor, temas noktasını parçadan uzaklaştırıyordu
(ör. forward idx8 temas X=80.8, geometrik gereken ≈67 → ~13mm fazla).

**Düzeltme + p2_radius takibi (`calculate_paths`, geri pas bloğu):**
Geri pas artık ileri pasın **forming kısmını birebir tersine** kullanıyor
(`new_path[_line_end:]` = T1 → P2 fileto → çıkış → P3), yaklaşım kolu hariç:
```python
_line_end, _ = _fwd_splits
forming_part = np.array(new_path[_line_end:], dtype=float)  # P2 fileto + çıkış dahil
_bp_path = forming_part[::-1].copy()
# bp_arc_x/z: uçlarda (P3, T1) sıfır, ortada maksimum parabolik bombe
if (abs(bp_arc_x) > 1e-9 or abs(bp_arc_z) > 1e-9) and len(_bp_path) >= 3:
    _w = 4*_tt*(1-_tt);  _bp_path += np.outer(_w, [bp_arc_x, 0, bp_arc_z])
_bp_path = self._correct_clearance_uniform(_bp_path, ...)
```
- **p2_radius takibi:** Eski kod T1→P3 arası TEK bir quadratic Bézier yeniden kuruyordu,
  P2 filetosunu (p2_radius) yok sayıyordu. Artık forward forming noktaları aynen
  kullanıldığı için geri pas filetoyu ve çıkış eğrisini birebir izliyor.
  `bp_arc=0` → ileri forming'in tam aynası (doğrulandı: `max|bp − rev(fwd)| = 0.0000`;
  p2_radius=8'de fileto noktası dahil 15 vs 14 nokta).
- **bp_arc_x/z artık** kontrol-noktası kaydırması değil, eğriye parabolik bombe ekler.
- Yaklaşım kolu (`new_path[:_line_end]`) hâlâ hariç; clearance garantisi
  `_correct_clearance_uniform` ile aynı.

**Geri almak için:** `forming_part`/parabolik-bombe bloğunu, eski T1→P3 Bézier
yeniden-kurma koduyla değiştir (filetoyu tekrar yok sayar).

### Not: Ironing (Yüzey-Konformal) Geri Pas Modu — KALDIRILDI

Kısa süre prototiplenen `back_pass_mode = "ironing"` (yüzey-konformal dönüş stroku)
**kaldırıldı**: gerçek mandrelde mandrel'e girip çıkan "çöp" paslar üretiyordu (muhtemelen
ray-trace profilindeki normal gürültüsü + `[contact_z → P3.z]` span tanımı `pass_angle`'a
bağlı). `_build_ironing_back_pass`, `back_pass_mode`/`back_pass_allowance` paramları ve
UI (Mode combobox + Back Allowance) geri alındı. Fikir TODO #12'de saklı — ileride
düzeltilebilir (span'i `pass_angle`'dan bağımsız tanımla, profil normalini düzleştir).

Detay: **TODO #12** (ironing, ertelendi) + **TODO #13** (ileri pas P2→P3 mid-anchor).

**Geri almak için:** `back_pass_mode` dalını kaldır, `mirror` bloğunu eski girintisine al,
`_build_ironing_back_pass` metodunu sil.

---

## 2026-06-16 — Exit Curve Tension + Back Pass Unification

### 1. `exit_curve_tension` Parametresi (`path_generator.py`, `program_tab.py`)

**Yeni per-op parametre:** `exit_curve_tension` (float, default 0.4).

`linear_approach` modunda P2→P3 çıkış Bézier'inin kontrol noktası yüksekliğini P2→P3 mesafesinin oranı olarak belirler.

**Eski (hardcode):**
```python
ph_dist = max(corner_blend, p2p3_len * 0.4)
```

**Yeni:**
```python
exit_tension = float((op or {}).get("exit_curve_tension", 0.4))
ph_dist = max(corner_blend, p2p3_len * exit_tension)
```

- `0.1` → P3'e neredeyse düz çizgi
- `0.4` → eski davranış (varsayılan, geriye uyumlu)
- `1.0+` → çok kıvrımlı çıkış

**UI:** "Exit Tension" giriş alanı, Corner Blend'in hemen altına eklendi.

---

### 2. Geri Pas Bézier Tabanı Unifikasyonu (`path_generator.py:321–336`)

**Eski:** Geri pas kontrol noktası `midpoint(P3, P2) + [bp_arc_x, bp_arc_z]` idi.
`bp_arc_x=0, bp_arc_z=0` → P3→P2 düz çizgi (ileri çıkış eğrisiyle hiç ilgisi yoktu).

**Yeni:** Geri pas kontrol noktası tabanı, ileri çıkış eğrisinin kontrol noktasıyla aynı:
`ctrl_base = [p2.X, 0, p2.Z + exit_tension * p2p3_len]`
`ctrl = ctrl_base + [bp_arc_x, 0, bp_arc_z]`

`bp_arc_x=0, bp_arc_z=0` iken: geri pas, ileri çıkış eğrisinin tam tersini izler (aynı XZ yolu, ters yön).
`bp_arc_x/z ≠ 0` → asimetrik ayar için ileri tabanından offset.

**Geri almak için:** `ctrl_base_bp` satırını `mid = (p3_arr_bp + p2_arr_bp) / 2.0` ile değiştir,
`ctrl = mid + [bp_arc_x, 0, bp_arc_z]` yap. `bp_exit_ten` ve `p2p3_len_bp` satırlarını sil.

---

## 2026-06-16 — Pass Angle, Corner Blend, Rendering Smooth Fix

### 1. Pass Angle + Progressive Angle (`path_generator.py`, `program_tab.py`)

**Yeni per-op parametreler:** `pass_angle` (derece, float), `progressive_angle_enabled` (bool).

`pass_angle`: P2'deki açıyı tanımlar — P2→P1 vektörü ile P2→P3 vektörü arasındaki açı.
- 180° = düz geçiş (anti-parallel)
- Küçük açı = sivri dönüş
- **Option B:** P3 kol uzunluğu L3 = |P2→P3| sabit tutulur, sadece yön değişir.

`progressive_angle_enabled`: Aktifken birinci pas `pass_angle` kullanır, son pas 180°'ye lineer interpolasyon.

**Matematik (`path_generator.py` ~satır 227, `calculate_paths` loop içinde):**
```python
p3_z = abs(p3_z)  # normalizasyon — her zaman pozitif convention

_pa_deg = op.get("pass_angle", None)
if _pa_deg is not None:
    _eff_angle = float(_pa_deg)
    if op.get("progressive_angle_enabled", False) and count > 1:
        _eff_angle += i * (180.0 - _eff_angle) / (count - 1)
    _L3 = math.sqrt(p3_x**2 + abs(p3_z)**2)
    if _L3 > 0.001:
        _shape = op.get("pass_shape", "spline")
        if _shape in ("linear_approach", "linear_full"):
            _theta_A = -math.pi / 2   # sabit -90°
        else:
            _px, _pz = abs(p1_x), abs(p1_z)
            _theta_A = math.atan2(-_pz, _px) if _px > 0.001 else -math.pi / 2
        _theta_B = _theta_A + math.radians(_eff_angle)
        p3_x = _L3 * math.cos(_theta_B)
        p3_z = _L3 * math.sin(_theta_B)
```

**UI (`program_tab.py`):** "Path Shape" bölümüne `Pass Angle (deg)` entry + `Progressive` checkbox eklendi.

---

### 2. abs() Corruption Bugfix (`path_generator.py`)

**Semptom:** Pass angle ne kadar küçük veya negatif girilirse girilsin, P3 hep aynı yönde kalıyordu.

**Kök neden:** `_create_and_store_pass()` içinde `p3_z_offset` ve `p3_x_offset`'e `abs()` uygulanıyordu. Bu, pass_angle bloğunda hesaplanan işaretli değerleri imha ediyordu.

**Düzeltme:**
```python
# ÖNCE:
calc_p3_z = p2.Z() + abs(p3_z_offset)
p3 = gp_Pnt(p2.X() + abs(p3_x_offset), 0, calc_p3_z)

# SONRA:
calc_p3_z = p2.Z() + p3_z_offset
p3 = gp_Pnt(p2.X() + p3_x_offset, 0, calc_p3_z)
```

`calculate_paths` loop başında `p3_z = abs(p3_z)` normalizasyonu eklenerek pozitif convention garanti edildi; pass_angle bloğu ise signed değerleri gerektiği gibi üretir.

---

### 3. Corner Blend — P2 Köşesini Yumuşatma (`path_generator.py`, `program_tab.py`)

**Yeni per-op parametre:** `corner_blend` (mm, default 0).

`linear_approach` modunda yaklaşım kolu (düz Z) ile çıkış Bézier'i P2'de keskin bir köşe oluşturur. `corner_blend > 0.01` olduğunda P2 etrafına quadratic Bézier fileto eklenir.

**İleri pas (`_create_and_store_pass`, ~satır 615–660):**
```python
p_blend    = np.array([p2.X(), 0.0, p2.Z() - corner_blend])  # yaklaşım kolu üzerinde
# exit_portion: P2→P3 Bézier (ph_dist = max(corner_blend, p2p3_len * 0.4))
# p_exit: exit_portion üzerinde P2'den corner_blend uzaklığındaki nokta
fillet = quadratic_bezier(p_blend, p2_arr, p_exit, n=...)  # P2 kontrol noktası
```

**Geri pas** da benzer şekilde P2 etrafında aynı fillet'ı alır.

**UI (`program_tab.py`):** Shape mode combo'dan sonra `Corner Blend (mm)` entry eklendi. Tooltip: `linear_approach` modunda geçerli, 5–15mm tipik.

---

### 4. Forward Pass Exit Curve — Rendering Fix (`main.py`)

**Semptom:** P2→P3 arasındaki çıkış eğrisi render'da düz çizgi parçalarından oluşan poligon gibi görünüyordu. Back pass Bézier ise mükemmel düzgün görünüyordu.

**Kök neden (iki katmanlı sorun):**

**(a) `ph_dist = 1.0mm` hardcode:** Quadratic Bézier'deki kontrol noktası P2'ye çok yakın → `t`-uniform örnekleme P2 yakınında ~24× daha sıkı kümeleniyor → `gcode_res=2mm` downsampling bu kümenin neredeyse tamamını atıyor → P3 yakınında sadece birkaç nokta kalıyor.

Düzeltme: `ph_dist = max(corner_blend, p2p3_len * 0.4)` — P2→P3 mesafesinin %40'ı.

**(b) `pv.lines_from_points` düz segment render:** Stored path `gcode_res=2mm` ile örneklenmiş ~14 nokta içeriyor. `lines_from_points` bunları düz segmentlerle birleştiriyor → poligon görünümü.

Düzeltme: `main.py:447` — `pv.Spline` kullanarak görsel interpolasyon, ayrıca keskin köşede (P2) salınım sorununu önlemek için sharp corner detection ile path'i split edip her parçayı ayrı Spline/line olarak render et, sonra merge et.

**Final rendering kodu (`main.py:445–480`):**
```python
p_arr = np.array(p, dtype=float)
# Keskin köşe tespiti (P2 junction, dot < 0 → açı > 90°)
dirs = np.diff(p_arr, axis=0); dirs_n = dirs / norm(dirs)
dots = einsum(dirs_n[:-1], dirs_n[1:])
split_idx = argmin(dots) + 1 if dots.min() < 0.0 else None

def _seg_poly(pts):
    return lines_from_points(pts) if len(pts) <= 2 else pv.Spline(pts, n_points=max(50, min(200, len(pts)*10)))

poly = _seg_poly(p_arr[:split_idx+1]).merge(_seg_poly(p_arr[split_idx:])) if split_idx else _seg_poly(p_arr)
```

**G-code etkilenmedi:** Bu sadece görsel render değişikliği. Stored toolpath ve G-code üretimi aynı.

---

## 2026-06-14 — Back Pass Bézier Ark + Nokta Sayısı Düzeltmesi + P2 Z Extend

### 1. UI: P3 X Konumu Değiştirildi (`program_tab.py`)
Roughing Path Shape bölümündeki sıra: P1 X → P1 Z → **P3 X** → P3 Z → Step → Rotation.
Önceden P3 X en alttaydı; P1 Z ile birlikte düşünülmesi gerektiği için altına taşındı.

---

### 2. Back Pass Bézier Ark Özelleştirmesi (`path_generator.py`, `program_tab.py`)

**Arka plan:** Back pass başlangıçta `new_path[::-1]` (tam ters) olarak uygulandı. Sonra `linear_approach` için P3→P2 geçişi özelleştirilebilir hale getirildi.

**Son uygulama:** `linear_approach` modunda back pass, P3 ve P2 noktaları **ileri pasla aynı** tutularak quadratic Bézier eğrisi olarak üretiliyor.

```python
# path_generator.py — back pass bloğu
mid  = (p3_arr_bp + p2_arr_bp) / 2.0
ctrl = mid + np.array([bp_arc_x, 0.0, bp_arc_z])
t    = np.linspace(0, 1, num_exit_bp)
entry_arc_rev = (1-t)²·P3 + 2t(1-t)·ctrl + t²·P2   # P3→P2 yönü
```

- `back_pass_arc_x = 0, back_pass_arc_z = 0` → P3→P2 düz çizgi
- `back_pass_arc_x > 0` → ark mandrel'den uzaklaşır
- `back_pass_arc_z` → arkın Z'deki ağırlık merkezini kaydırır
- `spline` / `linear_full` modlarında: düz `new_path[::-1]` kullanılmaya devam eder

**Geri almak için:** back pass `if bp_pass_shape == "linear_approach":` bloğunu kaldır, `bp_path = np.array(new_path)[::-1]` bırak.

---

### 3. Nokta Sayısı Düzeltmesi (`path_generator.py`)

**Sorun:** Back pass çok fazla nokta içeriyordu; ileri pasın yaklaşım kolu da gereksiz yere çok noktalıydı.

**Kök neden:** `_create_and_store_pass` içinde `gcode_resolution` downsampling uygulanıyordu ama back pass doğrudan `check_res` yoğunluğunda saklanıyordu (4× fazla nokta).

**Değişiklikler:**

**(a) İleri pas yaklaşım kolu — `_create_and_store_pass` (linear_approach)**
```python
# Collision loop öncesinde:
_ap_split = None
# linear_approach branch içinde:
_ap_split = n_ap - 1   # exit portion başlangıç indeksi

# Collision loop sonrası, gcode_resolution öncesinde:
if _ap_split is not None and _ap_split > 1 and len(final_points) > _ap_split + 1:
    final_points = np.vstack([
        final_points[[0, _ap_split]],   # yaklaşım: sadece başlangıç + P2
        final_points[_ap_split + 1:]    # exit spline tam çözünürlükte
    ])
```

**(b) Back pass Bézier ark — `calculate_paths`**
```python
gcode_res_bp = float(params.get("gcode_resolution", 2.0))
# ... distance-based downsampling ile entry_arc_rev nokta sayısı azaltılıyor ...
approach_rev = np.array([p2_arr_bp, ap_start_bp])  # 2 nokta, düz çizgi
```

---

### 4. P2 Z Extend — Roughing Boşluk Doldurma (`path_generator.py`, `program_tab.py`)

**Sorun:** `count` az seçilirse paslar arasında Z yönünde kapsanmayan bölgeler oluşuyordu.

**Çözüm:** `p2_z_extend` parametresi — yaklaşım kolunun başlangıcı sabit kalır, sonu uzar.

```python
# calculate_paths — roughing loop içinde
p2_z_extend  = float(op.get("p2_z_extend", 0.0)) if not is_finish else 0.0
contact_z    = target_z + p2_z_extend          # P2 bu Z'de
effective_p1_z = p1_z + p2_z_extend            # yaklaşım kolu uzadı

# _create_and_store_pass çağrısı:
self._create_and_store_pass(p1_x, effective_p1_z, ...)
# Sonuç: ap_start = contact_z − effective_p1_z = target_z − p1_z  (değişmedi)
#         P2      = contact_z = target_z + p2_z_extend             (uzadı)
```

**Boşluk doldurma formülü:** `p2_z_extend = spacing − p1_z`
`spacing = (Zone End − Zone Start) / (Pass Count − 1)`

**Geri almak için:** `p2_z_extend = 0` bırak veya parametreyi sil.

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
