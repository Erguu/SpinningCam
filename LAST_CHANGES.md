# Son Değişiklikler

Bu dosya önemli düzeltme ve geliştirmeleri kronolojik sırayla tutar.
Sorun çıkarsa buraya bak — hangi satır değişti, neden, ne bekleniyor.

---

## 2026-07-10 — settings.json git'ten çıkarıldı (pull çakışması fix) — FAZ 1

Kullanıcı: biri pull edince değiştirilmiş dosyalar (özellikle settings) yüzünden
git çakışma hatası veriyor. KÖK NEDEN: uygulamanın çalışırken SÜREKLİ yazdığı
dosyalar git'te İZLENİYOR → her kullanıcının kopyası repodan ayrışıyor → `git
pull` yerel değişikliklerin üzerine yazmayı reddediyor.

**Analiz (kod doğrulandı):** SADECE `settings.json` gerçekten çakışıyor
(`save_settings_json` her etkileşimde yazar). `layout.json` yalnızca OKUNUR
(gui_manager, yazma yok) → drift yok. `materials.json` yalnızca YOKSA yazılır
(`save_default_materials` `if exists: return`) → drift yok. Bu ikisi İZLENMEYE
DEVAM (çakışmıyorlar). `tools.json` + `machines/*.json` düzenlenince/kalibre
edilince çakışır → FAZ 2'ye ertelendi.

**Yapılan (FAZ 1, commit b13e502, PUSH'lu):**
- `.gitignore`: `settings.json` eklendi. Uygulama yoksa kod varsayılanlarından
  yeniden kurar (main.py load_settings `if os.path.exists` → yoksa default_params).
- `packaging_manifest.py`: SHIP_NEXT_TO_EXE'den ÇIKARILDI, NOT_SHIPPED'e eklendi.
  YAN FAYDA: exe artık dev'in kamera/`_admin:true`/lisans yolu durumunu tohum
  olarak SHIPLEMİYOR (müşteri temiz kod varsayılanıyla, admin DEĞİL başlıyor).
- `git rm --cached settings.json` (yerel dosya korundu, artık ignore'lu).
- `check_packaging` statik GEÇTİ (kaynak tarayıcı NOT_SHIPPED'de bulunca flag'lemez).
- **Mevcut klonlar için TEK SEFERLİK geçiş adımı** `PULL_MIGRATION_settings.md`'ye
  yazıldı (yedekle → `git checkout -- settings.json` → pull → geri yükle).

**FAZ 2 (GELECEK OTURUM):** `tools.json` + `machines/*.json` → izlenen `.default`
tohum + gitignore'lu canlı dosya + ilk-çalıştırmada tohumlama. Takımlar zaten
Export/Import zip ile paylaşılıyor; makine kalibrasyonu yerel kalır. Not: bazı
dosyalar zaten kendini-yaratıyor (materials, ID111-1); ID112-1 YARATMIYOR →
tohum şart.

---

## 2026-07-10 — Taşınabilir takım kütüphanesi: ID-adlı STEP geometrisi + zip dışa/içe aktarma

Kullanıcı: programı push edip başka biri pull edince (veya exe elden verilince)
her seferinde takımları elle yeniden eklemek gerekiyordu. KÖK NEDEN: her takım
STEP dosyasını MUTLAK yol ile saklıyordu (`C:/Users/PC/Documents/CAD_Files/
meksika/Spinning tool 1.STEP`) ve STEP dosyaları repoda YOKTU → başka makinede
yol ölü, geometri gelmiyor. (r_tool/radius zaten tools.json ile taşınıyordu.)
Kullanıcı fikri: STEP dosyalarını takım ID'siyle adlandır → otomatik bulunsun.

**Yapılan (onaylı A+B: hem git hem exe; ID-adlandırma):**
- **`tool_step_loader.py`:** modül sabiti `TOOL_GEOMETRY_DIR = "tool_geometry"` +
  `_STEP_EXTS`. `_resolve_step_path` yeniden yazıldı — ÖNCE konvansiyon
  (`tool_geometry/<id>.<ext>`, base_dir=get_base_path() yanında, ID'den bulunur,
  makine-bağımsız), SONRA eski `step_file` (relatif→cwd→mutlak) GERİYE-UYUM
  fallback'i. Konvansiyon dosyası varsa bayat mutlak yolu EZER.
- **`tool_library_io.py` (YENİ):** `sync_tool_geometry(base, tool, old_id)` —
  eklenen/düzenlenen takımın harici STEP'ini `tool_geometry/<id>.<ext>`e kopyalar,
  ID değişince yeniden adlandırır, `step_file`i taşınabilir relatif yola normalize
  eder. `export_library`/`import_library` — tools.json + her takımın STEP'ini tek
  `.zip`e paketler / geri okur (git dışı paylaşım). `find_geometry_file`,
  `geometry_dir`. Ağır bağımlılık yok (os/json/shutil/zipfile + tool_step_loader
  sabitleri).
- **`ui/dialogs/tool_manager.py`:** Add/Save artık `_sync_geometry` çağırıyor
  (kopya/rename + normalize, hata SAVE'i bloklamaz). Yeni "Kütüphaneyi Dışa/İçe
  Aktar…" düğmeleri (ağaç altında f_io) + `export_library`/`import_library`
  metotları; içe aktarmada ID çakışması TEK sefer sorulur (Evet=ez / Hayır=atla).
- **MİGRASYON (tek sefer, yapıldı):** `tool_geometry/` oluşturuldu; T0101←Spinning
  tool 1, T0102/T0103←Spinning tool 2 kopyalandı (ID-adlı); tools.json 3 mutlak
  yol → relatif konvansiyon yoluna güncellendi.
- **Paketleme:** `packaging_manifest.SHIP_NEXT_TO_EXE`e `("tool_geometry", True)`
  eklendi (build_exe zaten dizinleri copytree ile kopyalıyor; check_packaging
  _DATA_RE STEP'i flag'lemez; statik kontrol GEÇTİ).
- **`i18n.py`:** 18 yeni `tm_*` anahtarı (EN/TR/ES) — dışa/içe aktar düğme+mesajları,
  geometri-sync notu, çakışma diyaloğu.
- **`ui/dialogs/help_window.py` (EN+TR):** "ops" sekmesine "TOOL LIBRARY — SHARING
  TOOLS BETWEEN PCs" bölümü (r_tool makine-özel uyarısı dâhil). AYRICA yeni
  ADANMIŞ yardım sekmesi **"Tools & Calibration"** (`_C["tools"]` EN+TR;
  sections listesine `("help_tab_tools","tools")` ops↔machine arası; i18n
  `help_tab_tools` EN/TR/ES) — takım ekleme, Radius↔Rr farkı ve **Rr ≥ Radius
  gouge kuralı**, kalibrasyon, STEP değiştirme, dışa/içe aktarma + hızlı kontrol
  listesi tek yerde. (Kullanıcı T0102 STEP'ini değiştirince Radius 77.53 oldu ama
  r_tool 74.31 kaldı → r_tool < radius uyarısı bu sekmeyi tetikledi.)

**Doğrulama:** yeni `_test_tool_io.py` 4/4 GEÇTİ (konvansiyon çözümü, bayat
mutlak yolu ezme, export→import round-trip, sync kopya+ID-rename); tüm modüller
conda env'de import oldu; AST temiz; `check_packaging` statik GEÇTİ.
**GUI SMOKE BEKLİYOR** (Takımlar penceresinde dışa/içe aktar düğmeleri, ekleyince
otomatik kopya, 3B ruloların doğru yüklenmesi). Commit EDİLMEDİ.
**Geri alma:** `tool_geometry/` sil + tools.json'u mutlak yollara döndür +
bu tarihli değişiklikleri geri al; `_resolve_step_path` fallback zaten eski
davranışı koruyor.

---

## 2026-07-10 — Her monitöre sığan çözünürlük + Program araç çubuğu sadeleştirme/kaydırma

Kullanıcı: başka bir dizüstünde pencere ekrandan taşıyordu ve kenar çubuğu en
geniş haline sürüklense bile Program sekmesindeki araç çubuğunun Geri Al/Yinele
düğmeleri görünmüyordu (tek satırda ~19 widget, sağdaki öğeler ekrandan taşıyor).
İstek: (1) çözünürlüğü her monitöre uydur, (2) sağ-tık menüsünde zaten olan
düğmeleri kaldır, (3) araç çubuğu taşmasın (kaydırma emniyeti). Üçü de yapıldı.

**Yapılan:**
- **`ui/main_window.py`:** yeni modül düzeyi `_enable_windows_dpi_awareness()`
  (`super().__init__()` ÖNCESİNDE çağrılır) → per-monitor DPI farkındalığı
  (shcore, yoksa legacy `SetProcessDPIAware`), yüksek-DPI dizüstülerde bulanık
  bitmap-germe yerine yerel çözünürlükte render. `__init__` içinde: (a) Tk
  ölçeği gerçek DPI'ye ayarlanır (`tk scaling = dpi/72`; 96-DPI'de ~1.333 =
  no-op → mevcut makinede değişiklik yok, yüksek-DPI'de yazı okunur kalır);
  (b) sabit `1400x900` yerine ekrana KENETLENMİŞ geometri (restore boyu, küçük
  ekranda taşmaz), sonra `state("zoomed")` çalışma alanını doldurur (görev
  çubuğuna saygılı); (c) `minsize(1000, 640)`. Hepsi try/except ile korumalı.
- **`ui/tabs/program_tab.py` — Program araç çubuğu:** AGRESİF sadeleştirme.
  Sağ-tık menüsünde zaten var olan tüm düğmeler kaldırıldı (Devam ⤵, Böl,
  Reach⟲, Açı⟲, Pas Tablosu, Aç/Kapat, Kopyala, Sil, Toplu, Kütüphane,
  Yukarı/Aşağı ▲▼). Kalan: Geri Al/Yinele (artık EN BAŞTA), + Ekle ▾, Öner,
  Takımlar…, Özelleştir…, Gelişmiş kutusu, süre etiketi. `self.btn_reach` ve
  `self.btn_batch` artık yok → onları güncelleyen `_update_batch_button` (1430)
  ve `on_op_select` reach-grileme (1690) zaten `hasattr` korumalı, sorunsuz
  atlanıyor. `t("btn_...")` i18n anahtarları (sağ-tık menüsü, geri-al etiketleri)
  DOKUNULMADI. Pas Tablosu sağ-tık menüsüne EKLENDİ (eksikti).
- **`ui/tabs/program_tab.py` — yeni `_reflow_toolbar()` (kaydırma emniyeti):**
  araç çubuğu widget'ları artık pack yerine `_toolbar_items` listesinde tutulup
  `place()` ile soldan-sağa yerleştirilir; sonraki widget genişliği taşacaksa
  yeni satıra kaydırılır. `place()` seçildi çünkü grid sütun genişliklerini
  eşler ve dar durumda widget'ı çerçeve kenarından taşırıp yeniden kırpabilirdi.
  `<Configure>`'a bağlı + `after_idle`/`after(200)` ile ilk çizim. Genişlik
  değişmezse erken döner (Configure gürültüsü yok). Frame yüksekliği kullanılan
  satır sayısına kilitlenir (`pack_propagate(False)`). Sonuç: Geri Al/Yinele
  HER çözünürlük/kenar-çubuğu genişliğinde görünür (en solda; en son kaybolacak).
- **`ui/dialogs/help_window.py` (EN+TR):** "BUTON" diyen bölüm başlıkları/gövde
  düzeltildi (Pas Tablosu, Toplu, Kütüphane artık sağ-tık); "OPERASYON EKLEME"
  bölümüne araç çubuğunun sadeleştiği + kaydırdığı notu eklendi; sağ-tık menü
  listesine Pas Tablosu eklendi.

**Kullanıcı geri bildirimi sonrası düzeltmeler (aynı gün):**
- **Maximized açılmıyordu:** `state("zoomed")` erken (plotter.show + Win32
  embed ÖNCESİ) ayarlanıyordu; reparent zoom'u düşürüyordu. `__init__` sonunda
  `after(250)` + `after(900)` ile `_reassert_zoom()` (zaten zoomed değilse tekrar
  zoomla) eklendi.
- **Sash sürükleme yavaştı:** toolbar `<Configure>` artık `_schedule_reflow`
  ile DEBOUNCE'lu (sürükleme dururken ~60ms sonra tek re-layout) — her piksel
  yeniden sarma yok. (Not: sürüklemedeki kalan maliyet PyVista yeniden-render'ı,
  bu değişikliğin dışında.)
- **Undo/Redo öncesi boşluk:** `_reflow_toolbar` başlangıç `x = left_inset (12px)`.

**Doğrulama:** `_test_undo.py` GEÇTİ; her iki modül `spinning_cam` conda env'de
import oldu; AST temiz. **GUI SMOKE TEST BEKLİYOR** (pencere maximized açılıyor
mu, araç çubuğu dar kenar çubuğunda 2. satıra kayıyor mu, Geri Al/Yinele hep
görünür mü, yüksek-DPI dizüstüde ölçek doğru mu). Commit EDİLMEDİ.
**Geri alma:** üç dosyadaki bu tarihli değişiklikleri geri al; davranış eski
tek-satır araç çubuğuna ve sabit `1400x900` pencereye döner.

---

## 2026-07-09 — Parametre etiketi renkli çerçeve vurgusu (#84, GÖRSEL, opt-in)

Kullanıcı: programı devralan başka bir kullanıcıya "şu parametrelere dikkat et"
diyebilmek için bazı parametrelerin ETİKETİNİ (input kutusunu değil) renkli bir
dikdörtgen çerçeveyle işaretlemek istedi. Görünümü Özelleştir (Program sekmesi)
üzerinden yapılandırılabilir.

**Yapılan (hepsi GÖRSEL — değer/yol/G-code'a dokunmaz):**
- **`ui/tabs/program_tab.py`:** modül düzeyinde `BORDER_COLORS` (red/green/blue/
  orange/purple/yellow → hex). `op_view_config[tip]["highlight"] = {key: renk_adı}`
  yeni alan; `_default_cfg` (boş {}) ve `_view_cfg` (stored'dan okur) genişletildi.
  Yeni `_apply_label_highlights(op_type)`: editör kurulduktan sonra `_pkey`'li her
  satırın İLK çocuğunu (metin etiketi; kontrol daima sağda) 1px `highlightthickness`
  renkli çerçeveli bir `tk.Frame` içine `pack(in_=...)` ile sarar → etiketin
  çevresinde İÇİ BOŞ ince renkli dikdörtgen (iç zemin sistem varsayılanı kalır,
  metin okunur; DOLGU DEĞİL). Widget yeniden oluşturulmaz, master değişmez →
  görünürlük/sıralama mantığı etkilenmez. Her iki `_apply_field_visibility`
  çağrısından sonra çağrılır (satır ~1841 cutting/bending erken dönüş + ~2487 ana
  dal). GERÇEK KÖK NEDEN (2 kez kaçırıldı): `pack(in_=border)` etiketin master'ını
  DEĞİŞTİRMEZ (hâlâ row'un çocuğu, border ile KARDEŞ). border sonradan
  oluşturulduğu için istifte etiketin ÜSTÜNDE kalıp metni örtüyordu (önce dolu
  renk = tamamen kapalı, sonra hollow = gri kutu + renkli kenar, metin yine yok)
  → çözüm `lbl.lift(border)` (etiketi border'ın üstüne kaldır; `winfo children`
  istif sırasıyla doğrulandı). Çerçeve 1px `highlightthickness` hollow ring
  (iç zemin sistem varsayılanı, metin okunur).
- **`ui/dialogs/view_customizer.py`:** her parametre satırına "Çerçeve" (Border)
  açılır menüsü (4. sütun, genişlik 96px; diyalog 620→720). Renk adları i18n ile
  çevrili; seçim `highlight` haritasına yazılır. `_vars` tuple 3→4 elemana çıktı
  (`+bdr_var`); `_reset_defaults` çerçeveleri "—"e sıfırlar; `_apply` boş-olmayan
  renkleri toplar. Ayrıca her parametre satırı arasına yatay ayraç (`ttk.Separator`,
  gridde parametre içeriği `2*r`, ayraç `2*r+1`, columnspan=5) eklendi → hangi
  etiketin hangi kutuya ait olduğu bir bakışta görünüyor (kullanıcı isteği).
- **`i18n.py`:** `vc_col_border` + `vc_border_none/red/green/blue/orange/purple/
  yellow` (EN/TR/ES); `vc_info` çerçeve özelliğini anlatacak şekilde güncellendi.
- **`ui/dialogs/help_window.py`:** Customize View bölümüne Border açıklaması eklendi.

**Kalıcılık:** `op_view_config` zaten program başına (.ssp) kaydediliyor →
`highlight` de otomatik rider. `after_view_config_changed` seçili op için
`on_op_select`'i zaten yeniden çağırdığından çerçeve Apply'dan hemen sonra görünür.

**Geri alma:** BORDER_COLORS + `_apply_label_highlights` + iki çağrı satırı
kaldırılır, view_customizer 4. sütun geri alınırsa özellik kalkar; `highlight`
alanı eski configlerde yoksayılır (geriye dönük uyumlu).

**Doğrulama:** py_compile OK; headless Tk testi (etiket renkli çerçeveye taşınıyor,
input kutusu/kontrol dokunulmuyor, ilk çocuk = etiket varsayımı entry+checkbox
satırlarında doğrulandı) GEÇTİ. **GUI smoke test + commit BEKLİYOR.**

---

## 2026-07-09 — Kamera: tam açı kontrolü + adlandırılmış görünümler (GÖRSEL)

Kullanıcı: bazı açılara sadece fareyle ulaşılıyordu (düğmelerle değil) ve tek bir
kayıt yuvası vardı. **Kök neden:** iki ayrı kamera sistemi çakışıyordu —
kanonik olan `cam_azimuth/cam_elevation/cam_roll` paramlarından her tam sahne
çiziminde kamerayı YENİDEN kuruyor (`main.py:1320`); eski düğmeler ise CANLI
kamerayı doğrudan itip paramları güncellemiyordu → bir sonraki `update_scene`'de
geri sıçrıyordu. Ayrıca döndürme düğmeleri SADECE azimuth'u değiştiriyordu; dikey
(elevation) ve roll yalnızca gizli/legacy UI'larda (`gui_manager.py`, `ui_sidebar.py`)
vardı.

**Yapılan (hepsi GÖRSEL — yol/G-code/sim'e dokunmaz):**
- **`main.py`:** yeni param `cam_distance` (vars. 800) + `camera_presets` (liste);
  orbit formülünde sabit `dist=800` → `params["cam_distance"]`.
- **`ui/tabs/process_tab.py`:** kamera bölümü tamamen yeniden yazıldı. Tüm düğmeler
  artık kanonik paramları `on_param_change(..., "camera")` ile sürüyor → görünüm
  KALICI. Yatay (±5/±15), Dikey (±5/±15), Roll (⟲⟳ ±15), Zoom (🔍±, ×0.85),
  6 önayar (paramlara yazacak şekilde düzeltildi → artık sıçramıyor), "Kamerayı
  Sıfırla" (0/0/90, 800). Adlandırılmış görünümler: "＋ Mevcut görünümü kaydet…"
  → ada göre `camera_presets`'e ekler; her satır Git/✕. settings.json'da saklanır.
- **`i18n.py`:** `lbl_cam_azimuth/elevation/roll_zoom`, `lbl_saved_views`,
  `btn_save_view`, `lbl_no_presets`, `btn_preset_go`, `dlg_save_view_title/prompt`
  (EN/TR/ES). **help_window:** "NAVIGATING THE 3D VIEW" / "3D GÖRÜNÜMDE GEZİNME"
  bölümüne kamera düğmeleri bloğu.

Eski tek-yuvalı `params["camera"]` (save_cam/reset_cam) kaldırıldı — zaten
başlangıçta OKUNMUYORDU (startup `cam_azimuth` vb. kullanıyor) yani işlevsizdi.
Elevation ±89°'ye kırpıldı (kutup gimbal'ı önlemek için; "Üst" önayarı 89° kullanır).

**GIMBAL FIX (aynı gün, kullanıcı geri bildirimi):** dikey (elevation) artırımları
belli bir noktadan sonra tepe taklak oluyor / takılıyordu. Kök neden: eski kamera
kurulumu `up=(0,0,1)` sonra `camera.roll=90` uyguluyordu; VTK kötü `up`'ı yeniden
diklemiyor → yüksek elevation'da `up·fwd ≈ -1` (up bakış yönüne neredeyse PARALEL)
→ görünüm çöküp ters dönüyordu. **Fix (`main.py` kamera bloğu):** kamera artık
azimuth/elevation/roll'dan SÜREKLİ ortonormal çerçeve olarak kuruluyor — konum +
analitik dik `up` (kutuplarda bile bozulmayan taban-up, sonra bakış yönü etrafında
Rodrigues roll). `camera.roll` artık HİÇ çağrılmıyor. Headless: tüm taramada
(az −180…180, el −90…90, roll 0…180) `up·fwd`=0 ve |up|=1. el=0'da eski ile birebir
aynı `up=(1,0,0)` → Ön/Arka/Sol/Sağ değişmedi; Üst/İzo artık geometrik doğru.
Üst önayarı tam 90°.

**SÜREKLİ DİKEY DÖNÜŞ (2. geri bildirim):** dikey artırımlar ±90'da DURUYORDU
(kelepçe), yatay/roll ise sürekli dönüyordu → tutarsız. Artık dikey de azimuth/roll
gibi −180…180 sarmalıyor (`nudge_el` → `_wrap180`), yani tepe noktasının üzerinden
geçip sürekli dönüyor (kutbun ötesinde kamera trackball gibi ters dönüyor).
Yeniden-kurulum her elevation için ortonormal kaldığından sıçrama/kilitlenme yok
(headless: el −180…180 taramasında up·fwd=0, 15°'lik adımlar birebir düzgün).

**YATAY/DİKEY TAKAS (3. geri bildirim):** düğmeler "tam tersi" çalışıyordu —
varsayılan `roll=90` parçayı yan yatırdığı için ekranın sağ yönü dünya-Z, yukarı
yönü dünya-X; dolayısıyla AZIMUTH ekranda DİKEY, ELEVATION ekranda YATAY hareket
üretiyor (view matrisinden ölçüldü: az+15 → dy=-2.04 dikey; el+15 → dx=-2.39 yatay).
Fix (`process_tab.py`): ◀/▶ satırı artık `nudge_el`, ▲/▼ satırı `nudge_az` sürüyor;
işaretler "içerik oku takip eder" (fare sürüklemesi gibi): ▶=sahne sağa=-el,
▲=sahne yukarı=-az. Etiketler işaretsiz büyüklük (◀◀ 15 vb.).

**KLAVYE 1-9 KISAYOLU (4. istek):** rakam tuşları kayıtlı görünümlere atlar.
Yeni `main.py` `apply_camera_preset(index)` (0-tabanlı; boş yuvada no-op; cam param'ları
yazıp `update_scene("camera")`). Bağlama `main_window.py` `_bind_camera_preset_keys()`
(plotter.show sonrası bir kez): HEM Tk toplevel (`<Key-1..9>`,`<KP_1..9>`; bir alana
yazarken yoksayılır — Entry/Combobox/Spinbox sınıf filtresi) HEM 3B görünüm (VTK).

**GOTCHA (ilk deneme ÇALIŞMADI):** pyvista `add_key_event` argümanı olan callback'i
REDDEDİYOR (`lambda *a:` → TypeError, try/except yuttu → hiç kaydolmadı) ve yalnız TEK
tam keysym eşliyor (numpad kaçar). Fix: `add_key_event` yerine tek `iren.add_observer
("KeyPressEvent", _on_vtk_key)`; `_on_vtk_key` basılan rakamı doğrudan `GetKeyCode()`'dan
okuyor ('1'..'9' hem üst sıra hem numpad/NumLock), `GetKeySym()` (KP_/rakam) yedeği ile.
Tk tarafı 3B pencere odaktayken olayı ALMIYOR (Win32 VTK penceresi Tk değil) — bu yüzden
VTK observer şart. Numpad NumLock AÇIK ister. Kayıtlı görünüm listesi artık "1. Ad" diye
numaralı; "Git" düğmeleri de `apply_camera_preset(i)` çağırıyor (eski `apply_preset`
kaldırıldı). i18n `lbl_preset_keys_hint` (EN/TR/ES) + help_window notu. Headless:
`add_observer` var, `GetKeyCode()` basınca char döndürüyor (SetKeyCode('3')→'3') doğrulandı.

**Geri alma:** düğme etkisi param'a yazıldığı için `cam_azimuth/elevation/roll/
distance`'ı 0/0/90/800 yap veya "Kamerayı Sıfırla"ya bas. Kayıtlı görünümleri
sil → ✕. **DURUM:** headless (syntax+import+i18n+gimbal sweep) OK; **GUI smoke test BEKLİYOR.**

## 2026-07-09 — Çıkış Kavisi tepe konumu (`exit_bow_bias`, 0–1) (opt-in)
exit_bow kavisinin en dolgun noktasının P2→P3 bacağı üzerinde NEREDE olacağını
ayarlar. Kuadratik Bézier kontrol noktası kiriş boyunca kaydırılır
(`ctrl = A + bias·(B−A) + 2·bow·perp`): tepe YÜKSEKLİĞİ tam `exit_bow` mm kalır,
uç noktalar (P2, P3) sabit kalır — yalnızca tepenin bacak-boyu konumu kayar.
- **`path_generator.py`:** `_bezier_bow` + `_make_bow_leg` `bias=0.5` parametresi
  aldı (0.05–0.95'e kırpılır); linear dal `exit_bow_bias`'ı okuyup 3 çağrı yerine
  `bias=_bow_bias` geçiriyor. Headless: bias 0.2/0.5/0.8 → tepe-konum 0.345/0.495/0.645,
  tepe-yükseklik 8.0 sabit, uçlar sabit; bias=0.5 varsayılanla BAYT-AYNI.
- **UI (`program_tab.py`):** exit_bow altına "Kavis Konumu (0-1)" alanı; OP_PARAM
  universe/labels/section/batch/defaults güncellendi. Pas Diyagramı ASCII cheat-sheet
  bias satırı + canvas `ebow_ctrl` bias'a göre `mx/my` konumlandırıyor.
- **i18n:** `lbl_exit_bow_bias` (EN/TR/ES). **help_window:** "EXIT CURVE SHAPE"
  bölümüne Bow Bias maddesi.

**Geri alma:** alanı 0.5 bırak (veya boş) → tam merkezli kavis, eski davranış.

## 2026-07-08f — 4 hata düzeltmesi (cetvel kamera, kaydırma-düzenleme, hız modu, reach çarpanı)

Kullanıcı 4 hata bildirdi:

**1. Cetvel (ruler) ayarı kamerayı uzaklaştırıyor + hesaplama tetikliyor.**
İKİ kök neden:
(a) `plotter.add_ruler()` içeride `add_actor(..., reset_camera=True)` sabit kodlu
→ cetvel her çizildiğinde (her cetvel ayarında VE cetvel açıkken her sahne
güncellemesinde) kamera tüm aktörlere "fit" olup uzaklaşıyor. Fix: `_update_rulers`
add_ruler çağrılarından önce `camera_position`'ı snapshot alıp sonra geri yükler →
cetveller artık gerçek statik overlay.
(b) cetvel spinbox'ları `on_param_change(..., "all")` → `update_scene("all")`
auto-calc açıksa yolları yeniden hesaplıyordu. Fix: cetvel denetimlerine hafif
`"rulers"` modu (`helpers_ui.add_spinbox/add_checkbox`'a `mode=` parametresi;
`process_tab` cetvel satırları `mode="rulers"`). `on_param_change` bu modda
yalnızca `_render_rulers_only()` çağırır (yeni, `main.py`) — hesaplama yapmaz.

**2. İmleç input kutusundayken kaydırma değeri değiştiriyor.**
Kök neden: ttk.Spinbox/Combobox tekerleği sınıf düzeyinde değeri artırır; sekme
sayfası da tekerlekle kaydırır → ikisi birden. Fix: yeni `helpers_ui.scroll_not_edit()`
widget düzeyinde `<MouseWheel>`'i en yakın Canvas ata yönlendirip `"break"` döner
(değeri asla değiştirmez). Tüm spinbox'lara + operasyon combobox'larına
(hız/besleme modu, takım, yön, şekil, tilt) uygulandı.

**3. "Fabrika temiz" roughing op'unda Hız Modu RPM'e değişmiyor (dropdown açılıyor,
seçim yok sayılıyor).** Kök neden: `_add_prop_combo.save` önce `_flush_entries()`
çağırıyordu; `rebuild=True` alanların (Pas Sayısı, Pass Angle) saver'ı
`on_op_select()` ile tüm paneli — combobox dâhil — YIKIP yeniden kuruyor, sonra
`cb.get()` ölü widget'tan okuyor → seçim kayboluyordu. (Yön combosu çalışıyordu
çünkü StringVar okuyor, flush etmiyor.) Fix: `cb.get()` flush'tan ÖNCE okunuyor.

**4. Follow modda reach çarpanı (reach_blank_factor) simülasyon sac gösterimini
etkilemiyor.** Motor + overlay matematiği çarpanı DOĞRU uyguluyor (headless
doğrulandı: 0.5 çarpanı flanş yarıçap uzanımını yarıya indiriyor). Sorun: overlay
`last_calculated_paths`'ten çiziliyor; manuel-calc modunda çarpanı değiştirmek
yeniden hesap tetiklemiyordu → overlay bayat reach ile kalıyor, çarpan yok
sayılmış gibi görünüyor. Fix: `reach_blank_factor`/`reach_blank_offset` alanları
artık `rebuild=True` ("oto a→b" okuması anında güncellenir) + `force_calc=True`
(yeni `_schedule_forced_calc`/`_fire_forced_calc` — auto-calc kapalı olsa bile
arka planda debounce'lı yeniden hesap → overlay/sim tazelenir).

**Doğrulama:** 4 dosya derlendi; `_test_reach_follow`, `_test_deformed_blank`,
`_test_program_tab_toolbar`, `_test_pass_table` GEÇTİ. GUI smoke testi + commit
BEKLİYOR. Geri alma: değişiklikler `helpers_ui.py`, `main.py`,
`ui/tabs/process_tab.py`, `ui/tabs/program_tab.py`'de izole.

---

## 2026-07-08e — Çıkış Kavisi (exit_bow, mm): kararlı P2→P3 eğri kontrolü (opt-in)

Kullanıcı: "Follow modda P3'ü bozamayız, doğru. Genel açı için progressive'li
pass_angle var, o iyi. `exit_arc_angle` gibi ama onu tatmin etmeyen bir şey
istiyorum — P2 ile P3 arasında ESNEK bir eğri; P3'ü (ve reach-follow / progressive
açıyı) BOZMASIN. `exit_arc_angle`'ı belli bir noktadan sonra artırınca son paslar
bozuluyor, komik hareketler yapıyor." → Seçenek (b): P2 ile P3 yakın Z'de, dışa
kavis yapıp geri dönen eğri.

**Kök neden (exit_arc_angle bozulması):** `_tangent_chord_arc` yayı AÇI ile
parametrize (`sweep = 2·α`), yani ~90°'den sonra yarım daireyi aşıp kendi üstüne
KATLANIYOR — dik/near-vertical son paslardaki "komik hareket" bu. Ayrıca yalnızca
linear şekillerde etkili; `spline` şeklinde hiç uygulanmıyordu.

- **`path_generator.py _bezier_bow(A, B, bow_mm, check_res)`** (yeni): P2→P3 (veya
  T2→P3) arasını AÇI yerine mm KAVİS YÜKSEKLİĞİ ile eğen kuadratik Bézier. Uç
  noktalar A/B birebir korunur (P3 asla oynamaz) ve monoton büyür → ne kadar
  artırılırsa artırılsın ASLA katlanmaz. + = tepe (+Z), − = taban (−Z), 0/boş = kapalı.
- **Bağlama (`_create_and_store_pass` linear dalı):** yeni `exit_bow` op alanı
  okunur; set ise çıkış (ve ters paslarda `_swap_legs` çıkış kolu, ayrıca
  `linear_full` düz çıkış) bow-Bézier ile üretilir; boş/0 ise ESKİ davranış
  (tangent-chord yay / düz) → varsayılan byte-aynı.
- **`exit_bow` reach/açıdan BAĞIMSIZ:** headless doğrulandı — bow=0 vs bow=25 ile
  son nokta (P3) BİREBİR aynı ([130,0,120]); bow sadece eğrinin şeklini değiştiriyor
  (max X 130 → 149.5). Yani follow mode + progressive angle'a dokunmuyor.
- **ÖLÜ ALAN TEMİZLİĞİ:** `exit_curve_tension` (path gen'de zaten OKUNMUYORDU,
  hayalet alan) UI/universe/labels/section/batch listelerinden çıkarıldı; yerine
  `exit_bow` kondu. Op dict'te eski değer kalırsa zararsız (yok sayılır).
- **UI (`program_tab.py`):** `is_linear` bloğunda exit_arc_angle'ın hemen altında
  "Çıkış Kavisi (mm)" alanı (her iki linear şekilde). Pas Diyagramı hem ASCII
  cheat-sheet hem canvas artık exit_bow'u çiziyor (`ebow_ctrl` dik-Bézier ctrl,
  görsel ölçek 3px/mm, ±70px clamp).
- **i18n:** `lbl_exit_bow` (EN/TR/ES). **help_window:** yeni "EXIT CURVE SHAPE"
  bölümü (arc-fold sorununu ve bow farkını açıklıyor).

**2. TUR (kullanıcı geri bildirimi — yön + clearance):**
- **Yön hatası (#2 "ilk pas ters yöne kavisleniyor"):** Kök neden = bow yan-yön
  "global +X'e sabitle" kuralıydı; kademeli açı yelpazesi çıkış kirişini RADYAL
  yönden geçirince (pass_angle<90 → radyalin altı, >90 → üstü) dik bileşenin işareti
  TAM o geçişte dönüyordu → ilk pas ters. Yüzey-normali çapası da silindirde AYNI
  sonucu verir (kanıtlandı). Gerçek fix: `_bezier_bow` artık SABİT el-yönü kullanıyor
  (perp = kiriş +90°, işaret bow'dan), kiriş ile pürüzsüz döner, ASLA dönmez → tüm
  paslar aynı yöne. Doğrulandı: down-out ΔZ=+14, up-out ΔZ=+1.3 (ikisi de +Z).
- **Clearance ihlali (#3 "−20'de bazı paslar clearance'ı aşıyor + kolun clearance'ı
  artıyor"):** Kök neden = içe kavis tabanı deldiğinde mevcut ÜNİFORM shift TÜM pası
  (p1/p2/p3) dışarı ötelıyordu → P3 oynuyor + P1→P2 kolu fazla açılıyor. Fix: yeni
  `_make_bow_leg` + `_bow_penetration`; bow, op'un KENDİ clearance'ında (asla güvenlik
  tabanının altında değil) korunuyor:
  - **`exit_bow_trim` AÇIK (yeni op alanı, varsayılan True) = KIRP:** tam bow üretilir,
    yalnızca ihlal eden noktalar radyal olarak clearance yüzeyine itilir (o bölgede
    kontura biner), gerisi tam bow. Kısa/dik son pasta büyük bow korunur.
  - **KAPALI = KISALT:** bow genliği ihlal bitene kadar %15 adımlarla küçültülür
    (pürüzsüz, kırılmasız). Her iki modda da P3 + kol YERİNDE (üniform shift tetiklenmez).
  - `_create_and_store_pass`'e `op_clearance` parametresi eklendi (çağrı yerinde geçildi).
  Doğrulandı: −20 içe bow → trim & clamp min-clearance = 5.0 (op clr, ihlal yok), P3/kol
  birebir sabit.
- **UI:** exit_bow altına "Kavis Kırp (clr)" onay kutusu (`exit_bow_trim`, is_linear).
  universe/labels/section güncellendi; i18n `lbl_exit_bow_trim` (EN/TR/ES). Pas Diyagramı
  `ebow_ctrl` sabit el-yönüne çevrildi. help_window "EXIT CURVE SHAPE" + trim/clamp yazıldı.

**Geri alma:** exit_bow alanını boş bırak → tam eski davranış. `_bezier_bow`
ve tüm dallanmalar `abs(_exit_bow) > 1e-4` ile korumalı. Regresyon: `_test_reverse_linear`
GEÇTİ (exit_arc/ters-bacak bozulmadı).
**BEKLEYEN:** GUI smoke (alanı gir, kutuyu değiştir, diyagramı gör) + FİZİKSEL doğrulama
(dik son paslarda katlanma + ters-yön gitti mi, trim gouge yok mu). spline şeklinde
henüz YOK (sadece linear).

## 2026-07-08d — Pasları rulo TEMAS NOKTASINDA gösterme (opt-in, görsel)

Kullanıcı: "Yolları rulo merkezine göre çiziyoruz ama asıl işi rulo ucu yapıyor.
Yol üretimini hiç bozmadan, rulo boyutu kadar görsel kaydırma ile temas noktasını
görebilir miyiz? Bir onay kutusuyla."

- **`main.py _shift_path_to_tip(p_arr, r_tool)`** (yeni): bir yolun KOPYASINI
  mandrel ekseni X'ine doğru r_tool kadar radyal içeri çeker (merkez → temas
  noktası; `update_deformed_blank` ile aynı ilişki, eksen geçişine karşı 0.1 mm
  kısıtlı). Yalnızca ÇİZİLEN kopya kayar.
- **Render döngüsü:** ana pas tüpü (`p_arr`) çizilmeden önce `show_tip_paths`
  açıksa `_shift_path_to_tip(..., _rtool_for_pass(i))` uygulanır. Projeksiyon/
  analiz/rapid/approach katmanları DEĞİŞMEZ.
- **Yeniden çizim recalc'SIZ:** `_update_scene_impl` artık son render demetini
  `self._last_render_tuple` içinde tutuyor; yeni `redraw_paths_cached()` bunu
  `_pending_paths`'e koyup `update_scene("all", use_cached_paths=True)` çağırıyor.
  Onay kutusu handler'ı bunu kullanır → auto-calc KAPALI olsa bile (varsayılan)
  anında yeniden çizer, yol hesaplaması ÇALIŞMAZ.
- **UI (`process_tab.py`):** "Yolları Rulo Ucunda Göster (temas noktası)" özel
  onay kutusu (görsel bölümü, Pas Mesafe Çizgileri'nin altında).
- **i18n:** `cb_show_tip_paths` (EN/TR/ES). **help_window:** "Tip paths /
  Uç yolları" (EN+TR). **param:** `show_tip_paths` (varsayılan False).

GERİ ALMA: tamamen görsel — path/G-code/simülasyona DOKUNMAZ (yalnızca çizilen
tüpün X'i kayar). Kapatmak için onay kutusunu kaldır. Radyal yaklaşım (eğik
yüzeylerde normal boyunca küçük sapma). Headless smoke: 200→170 (r_tool=30),
Z korunuyor, aç/kapat cache'ten yeniden çiziyor. GUI smoke BEKLİYOR.

---

## 2026-07-08c — 3D görünüme yerleştirilebilir X/Z cetvelleri (opt-in)

Kullanıcı isteği: "3D görünümde her iki eksen için, yerleştirilebilir ve
mesafeleri doğrudan gösteren bir cetvel." Seçilen tasarım: sabit X ve Z ölçek
çubukları (interaktif tıkla-ölç değil).

- **Yeni param'lar (`main.py load_settings`):** `show_rulers` (bool, varsayılan
  False), `ruler_x_at_z` (yatay X cetvelinin oturduğu Z seviyesi),
  `ruler_z_at_x` (dikey Z cetvelinin oturduğu X seviyesi). Hepsi görsel-only.
- **`main.py _update_rulers()`** (yeni; `_update_scene_impl` sonunda
  `_update_grid_dynamic`'ten hemen sonra çağrılır). PyVista `add_ruler` ile iki
  `vtkAxisActor2D` çizer/kaldırır. Her cetvel koordinat sıfırında sabitlenir →
  taksimat etiketleri GERÇEK makine X/Z değerini (mm) okur. Span görünür
  aktörlerden (mandrel/roller/shell/blank) otomatik, 50 mm'lik temiz uca
  yuvarlanır; her 50 mm'de bir majör, 4 minör (=10 mm) taksimat.
- **UI (`ui/tabs/process_tab.py`):** Görsel Ayarlar'da "Cetvelleri Göster"
  onay kutusu + "X cetveli Z konumu" / "Z cetveli X konumu" spinbox'ları.
- **i18n:** `cb_show_rulers`, `sp_ruler_x_at_z`, `sp_ruler_z_at_x` (EN/TR/ES).
- **help_window.py:** VISUAL/GÖRSEL katmanlar bölümüne "Rulers/Cetveller".

GERİ ALMA: tamamen görsel katman — takım yolu/G-code'a DOKUNMAZ. Kapatmak için
onay kutusunu kaldır (varsayılan zaten kapalı). Headless smoke geçti (aç→2
aktör, kapat→None). GUI smoke BEKLİYOR.

**Ek (aynı gün):** Kullanıcı "cetvellerin yönünü ve başlangıç noktasını nasıl
değiştiririm?" → her cetvele **Başlangıç/Bitiş** kontrolü eklendi. Yeni param'lar
`ruler_x_start/ruler_x_end`, `ruler_z_start/ruler_z_end`. `_update_rulers` artık
`pointa=Başlangıç`, `pointb=Bitiş` çiziyor → etiketler Başlangıç'tan mesafeyi
okur (Başlangıç=sıfır işareti), Başlangıç→Bitiş yönü belirler. Bitiş==Başlangıç
ise ESKİ otomatik-sığdırma davranışı (Başlangıç'tan sahne kenarına, 50 mm'ye
yuvarlı) → varsayılan Başlangıç=0 ile etiketler hâlâ gerçek makine X/Z. UI'de
4 yeni spinbox (process_tab), i18n `sp_ruler_x_start/_end`, `sp_ruler_z_start/_end`
(EN/TR/ES), help_window EN+TR güncellendi.

---

## 2026-07-08b — Pas tablosu düzeltmeleri (GUI smoke geri bildirimi)

Kullanıcının ilk GUI smoke testi sonrası (`ui/dialogs/pass_table.py` +
i18n + help_window + `_test_pass_table.py`):

1. **`p2_z_extend` aynası:** tablo Z'si ve uç Z'si artık motorla aynı
   (`contact_z = target_z + p2_z_extend`; klerens normali de contact_z'den).
   Önceden 2 mm'lik extend tabloda görünmüyordu → uçlar motordan kayıktı.
2. **YENİ uyarı "sac ucu aşımı" (`pt_warn_beyond_blank`):** komut edilen
   reach o Z'deki tahmini flanşı >3 mm aşarsa "boşta hareket" uyarısı
   (flanş>0.5 mm iken; sacın tamamen şekillendiği Z'lerde susar — duvar
   üstünde kaymak normaldir). Kullanıcının "ilk pas çok uzakta ama uyarı
   yok" şikâyetinin cevabı: 93° + reach 40 + küçük sac → ~32 mm boşta.
3. **✎ hücre işareti:** beklemedeki düzenleme artık satır renginin yanında
   HÜCRENİN kendisinde "✎ değer" olarak görünür (çift-tık okuma ✎'yi soyar).
4. **Fabrika-temiz kaçış kapısı (`program_tab.py`):** "+ Ekle ▾" alt bölümü
   "— fabrika temiz" ön ayarı (op_presets) YOK SAYARAK temiz op ekler;
   sağ-tık → "Fabrika varsayılanına sıfırla" mevcut opun TÜM parametrelerini
   `_factory_op()` ile değiştirir (tip/ad/açık-kapalı korunur, onay popup'ı,
   tek undo). Kirlenmiş "Varsayılan Kaydet" ön ayarına dokunulmaz.
GERİ ALMA: 1–3 tablo/görselleştirme katmanında, 4 yeni UI girişleri — motor
değişmedi.

---

## 2026-07-08 — Reach/açı öncelik modeli P1–P4 (onaylı `PROPOSAL_REACH_ANGLE_PRIORITY.md`, TODO #72–#83)

Kullanıcı kararları: pas tablosu = POPUP; tablo düzenlemeleri = BEKLEMELİ
(Uygula/İptal); takip modu değiştiricileri = çarpan × + kaydırma mm (kullanıcıya
ait); ters-pas geometri düzeltmesi = **YENİ VARSAYILAN**.

### MOTOR (path_generator.py) — davranış değişiklikleri
1. **Takip modu (reach_follow_blank) MOTORA taşındı, PAS BAŞINA:** her pasın
   reach'i o pasın Z'sindeki flanştan = `flanş × reach_blank_factor +
   reach_blank_offset` (YENİ anahtar, mm). Op dict'i ASLA otomatik yazılmaz
   (R2) → #74/#75 ping-pong kökten öldü; UI'daki `_refresh_auto_reach`
   SİLİNDİ. ⚠ ESKİ takip-modlu .ssp'lerde yol İYİLEŞİR ama DEĞİŞİR (eskiden
   iki uç arası lineer yelpazeydi). GERİ ALMA: yok — Elle moda dönüp eski
   sayıları elle gir (op'taki değerler aynen duruyor).
2. **`pass_edits` (pas pinleri):** op-yerel `{pas_i: {pass_angle, reach}}` —
   EN YÜKSEK öncelik (pin > takip > yelpaze > reach > |p3|). Böl (#64)
   pinleri parça-yerel indekse yeniden eşler.
3. **#81 `exit_arc_angle` artık OP-BAŞINA** (boş = Process-tab genel değeri →
   eski programlar bit-aynı). Editör Yol Şekli bölümüne alan eklendi.
4. **#82 TERS PAS YENİ VARSAYILAN (lineer şekiller):** mandrele giren bacak
   DÜZ, exit-arc kavisi çıkan kola taşındı (`_tangent_chord_arc` helper; yay
   tanjant-kiriş açısı iki uçta simetrik → flip öncesi kurmak eşdeğer).
   exit_arc=0 → bit-aynı. GERİ ALMA: op'a `reverse_legacy_flip: true`.
   Takas modunda exit_mid ATLANIR (giriş bacağını eğerdi). ⚠ FİZİKSEL
   DOĞRULAMA GEREKLİ (kavisli ters paslar makinede yeniden kontrol).

### UI (program_tab / process_tab / main / helpers)
5. **PAS TABLOSU (`ui/dialogs/pass_table.py`, "Paslar ▦" + sağ-tık):** pas
   başına Z/etkin açı/etkin reach/uç nokta/KAYNAK (elle-yelpaze-takip-⭑pin-
   eski override)/uyarılar (klerens sıçraması, Δ<2.5mm yinelenen pas,
   reach≈0 ham çıkış). Çift-tık → beklemeli düzenleme (✎), [Uygula] = TEK
   undo adımı → `pass_edits`; [Pin temizle] pinleri + ESKİ gizli
   override'ları (gui_pass_overrides) kaldırır. Satır seçimi 3B vurgular.
   `compute_pass_rows` motor formüllerinin birebir aynası — motoru
   değiştirirken senkron tut!
6. **#76/#83 TEK HESAP YOLU:** program_tab'daki tüm senkron
   `update_scene("paths")` toggle çağrıları → `_schedule_auto_calc()`;
   Process-tab Hesapla → `_start_async_calc()`; `update_scene` canlı param
   düzenlemelerinde ağır hesabı arka plana devrediyor (`_delegate_async`,
   main.py) → sac yarıçapı değişince DONMA YOK. Startup/proje-yükleme
   (force_path_calc) senkron kaldı.
7. **#77 takip radyosu undo'lu + #73 korumalı** (flanş hesaplanamıyorsa mod
   açılmaz, `msg_follow_blocked`). **#72:** p3_x/p3_z SADECE açısal+uzunluk
   kaynağı etkinken kilitli (reach boşsa düzenlenebilir — legacy |p3| hâlâ
   uzunluk kaynağı). **#75:** yelpaze checkbox'ı kullanıcının — takip
   modunda gri ama ASLA çevrilmez. **#78:** çıkış-modu satırı `_section`
   etiketi aldı. **#79 undo:** `OpUndoStack` artık `extra` yan-durumu
   (gui_pass_overrides) saklıyor → 4'lü tuple (push/undo/redo İMZA DEĞİŞTİ).
8. Reach alanı takip modunda "oto ilk→son mm" gösterir (saver'sız salt-okunur).

### Testler
- YENİ: `_test_pass_edits.py`, `_test_reverse_linear.py`, `_test_pass_table.py`.
- YENİDEN YAZILDI (motor-taraflı takip): `_test_reach_follow.py`.
- GÜNCELLENDİ: `_test_undo.py` (4'lü tuple + sidecar senaryosu),
  `_test_program_tab_toolbar.py` (R2 + tablo + unpin senaryoları).
- DEĞİŞMEDEN GEÇİYOR: `_test_reach`, `_test_reach_foldback`,
  `_test_progressive_reach`, batch/split/continue/flange/surface/clamp/library.
- ÖNCEDEN BOZUK (bu oturumdan BAĞIMSIZ, commit'li kodda da düşüyor):
  `test_path_generator.py::test_empty_operations_list` (legacy op fallback),
  `_test_real_end_z.py` (bayat sütun-indeks assert'i, #67 Sel kayması),
  `_test_deformed_blank.py` (cp1254 konsol Δ karakteri).

### Paketleme
- `packaging_manifest.py` CRITICAL_MODULES += `ui.dialogs.pass_table`;
  `check_packaging.py` statik GEÇİYOR.

---

## 2026-07-07e — Reach/açı parametre sadeleştirme FAZ A (onaylı öneri) — TODO #68

`PROPOSAL_68_REACH_ANGLE_UX.md` kullanıcı ONAYIYLA uygulandı. **SADECE görünüm
katmanı: path_generator'a DOKUNULMADI (4 reach motor testi değişmeden GEÇİYOR),
hiçbir .ssp anahtarı eklenmedi/değişmedi.**

### Ne değişti (program_tab editörü)
- **Reach kaynağı radyosu** (Elle / Sacı takip et) eski `reach_follow_blank`
  checkbox'ının yerinde — AYNI anahtar, 1:1 eşleme. Yanında **"Doldur ⟲"**
  düğmesi (= toolbar Reach⟲; takip modunda İKİSİ DE gri — Q2 kararı,
  `self.btn_reach` state'i on_op_select'te).
- **Takip modunda Reach alanı salt-okunur gri + CANLI**: `_add_prop_entry`'ye
  `readonly` parametresi (saver YOK, binding YOK → bayat değer asla geri
  yazılamaz = **P1 bug fix'in yapısal yarısı**); `_refresh_auto_reach` artık
  taze değeri `_reach_live_var`'a basıyor (= gösterim yarısı; editör rebuild
  edilmez, odak bozulmaz).
- **GERİ BIRAKILABİLİRLİK GARANTİSİ (kullanıcı şartı):** Elle'ye dönüş her an
  serbest — yenileme durur, alan açılır, son hesaplanan değer düzenlenebilir
  başlangıç olarak kalır. Data-level test kanıtlıyor.
- **Çıkış modu satırı**: "AÇISAL — yön=Pass Angle, boy=Reach (P3 X/Z
  kullanılmaz)" / "HAM X/Z". AÇISAL modda **p3_x/p3_z salt-okunur gri**.
- **Sac çarpanı yalnızca takip modunda görünür** (P3 fix — genel çarpan sanılmasın).
- **Progressive Reach satırları Reach'in altına taşındı** (A4; SECTION_KEYS
  path_shape'e güncellendi; gating aynı: pass_angle + count>1).
- **Dürüst mesajlar (A3):** Reach⟲/Açı⟲ bir yelpaze checkbox'ını AÇTIĞINDA
  popup artık bunu söylüyor (`msg_reach_fan_note`/`msg_angle_fan_note`; Ctrl+Z notu).
- **Pass Diagram formül paneline "reach = |P2→P3|" bloğu (A5):** modu, öncelik
  zincirini, follow×factor'ı, clearance-bağımsızlık notunu ve yelpazeyi seçili
  op'un CANLI değerleriyle anlatır.
- **Etiketler (A6):** lbl_reach "Reach (mm)", lbl_reach_factor "Sac çarpanı (×)",
  lbl_reach_end "Son pas reach (mm)", lbl_progressive_end "Son pas açısı (°)"
  (EN/ES eşdeğer). Yeni anahtarlar: lbl_reach_source, rb_reach_manual/follow,
  btn_fill_reach_now, lbl_exit_mode_polar/raw, msg_*_fan_note.
- Help EN+TR: yeni "REACH KAYNAĞI VE ÇIKIŞ MODU" bölümleri.

### Doğrulama
- Motor DEĞİŞMEDİ: `_test_reach` / `_test_reach_foldback` / `_test_reach_follow` /
  `_test_progressive_reach` aynen GEÇİYOR.
- `_test_program_tab_toolbar.py` +1 bölüm: follow → reach ezilir; Elle'ye dönüş →
  yenileme durur, manuel edit hayatta kalır; `_reach_live_var` taze değeri alır.
- Diğer suite'ler (batch/undo/copy/library) GEÇİYOR.
- **GUI smoke test BEKLİYOR; commit BEKLİYOR.** Faz B (iki-yönlü reach↔p3 bind,
  toolbar sadeleştirme) ayrı onay bekliyor — yapılmadı.

## 2026-07-07d — Kopyala + Yeniden Adlandır + Sağ-tık Menü + Operasyon Kütüphanesi — TODO #69/#70/#71

Üç özellik tek oturumda (commit fad9809 SONRASI, henüz commit EDİLMEDİ):

### #69 Kopyala (çoklu)
- Toolbar "Kopyala" + sağ-tık menüsü. Hedef kuralı = Toplu ile AYNI (`_batch_targets`:
  ☑ işaretler varsa onlar, yoksa çoklu seçim; ≥1 yeter). Kopyalar deep-copy, son hedefin
  hemen altına BLOK halinde eklenir, eklenince seçili gelir. Adlı op'un kopyası
  " (kopya)" son eki alır. Undo-tracked (#66), ☑ işaretler temizlenir (indeks kayar).

### #70 Ad + sağ-tık context menüsü
- Opsiyonel `op["name"]` (motor YOK SAYAR; .ssp geri-uyumlu). Listede Tip sütununda
  ad varsa AD, yoksa tip gösterilir. Editörün üstünde "Ad" alanı (`_add_prop_entry`
  string modu; boş = anahtar silinir → tip görünür). Universe/labels/basic'e "name"
  eklendi (4 tip; Customize'da sütun/gelişmiş işaretlenebilir; Toplu'ya kapalı — string).
- **Sağ-tık menüsü** (`_on_tree_right_click`, `<Button-3>`): Yeniden adlandır…
  (simpledialog; önce `_flush_entries` — editördeki eski ad flush'ta ezmesin), Kopyala,
  Aç/Kapat, Devam ⤵, Böl…, Reach⟲, Açı⟲, Toplu (≥2 hedefte aktif), ▲/▼ taşı, Sil,
  Kütüphane…. Seçim dışı satıra sağ-tık önce o satırı seçer; seçim içine sağ-tık çoklu
  seçimi KORUR. Yeniden adlandırma alan-düzenlemesi sayılır → undo-TAKİPSİZ (#66 kuralı).

### #71 Operasyon Kütüphanesi
- YENİ `ops_library.py` (saf çekirdek, Tk'sız): `ops_library.json` exe'nin yanında
  (tools.json gibi app-level; bozuk dosya → [] asla çökmez). Entry: {name, type,
  params(deep-copy), created, machine}. Aynı ad = yerinde üzerine yazma.
  `make_op` = taze kopya + enabled + name.
- YENİ `ui/dialogs/op_library_dialog.py`: tip filtresi, Ad/Tip/Kayıt listesi,
  "+ Seçili op'u kaydet" (ad sorar, aynı adda onaylı üzerine yazma, kaydetmeden önce
  `_flush_entries`), "Ekle ▸" + çift-tık (pencere açık kalır — art arda ekleme),
  Yeniden adlandır, Sil (onaylı).
- `_insert_from_library`: anchor seçimin altına ekler (yoksa sona), undo-tracked,
  **r_tool takım kütüphanesinden TAZELENİR** (`app.sync_operation_r_tools()` —
  [[feedback-calibration-rtool]] bayat-reach gouge riskine karşı), status mesajı.
- `packaging_manifest`: `ops_library.json` → NOT_SHIPPED (runtime-üretilir);
  `ops_library` + `op_library_dialog` + `batch_edit_dialog` → CRITICAL_MODULES.
- "Varsayılan Kaydet" DURUYOR (+ Ekle şablonu olarak farklı iş görüyor).

### Doğrulama
- `_test_op_library.py` GEÇTİ (7: boş/round-trip/izolasyon/üzerine-yazma/
  find-rename-remove/make_op/bozuk-dosya).
- `_test_program_tab_toolbar.py` +3 bölüm GEÇTİ (çoklu kopya + son ek + undo;
  ad Tip sütununda; kütüphane ekleme konum/içerik/r_tool-sync/undo).
- i18n ×3 (~20 anahtar), help EN+TR (kopyala/ad/sağ-tık + OPERASYON KÜTÜPHANESİ bölümü).
- **GUI smoke test BEKLİYOR; commit BEKLİYOR.**

## 2026-07-07c — Özelleştir penceresi kutu hizası düzeltildi (kullanıcı: "kutular sağa sola kaymış")

`view_customizer._build_type_tab` satırları pack + karakter-genişlikli (width=10)
widget'larla diziyordu; Toplu sütununda Checkbutton/Label karışımı da eklenince her
satırın kutuları farklı x'e düşüyordu. FİX: başlık ve gövde artık GRID — kol 0 (parametre
adı) esner, kol 1-3 sabit 76 px (`_COLW`) ve ortalanmış; başlıkta scrollbar genişliği
kadar (18 px) boş kolon 4 telafisi. Gerçek-widget smoke (dialog kurulumu + Apply'ın
columns/advanced/batch yazması) GEÇTİ. Görsel hiza gerçek pencerede DOĞRULANACAK.

## 2026-07-07b — Toplu düzenleme: çoklu-seçim + tek parametre ayarı (Toplu… + ☑ sütunu) — TODO #67

Birçok operasyonun BİR parametresi tek adımda değişir (örn. 5 op'un start_z'sine +2 mm).
Kullanıcının tek tek seçip düzenleme derdini bitirir.

### Ne eklendi
- **Hedef seçimi (İKİSİ DE, kullanıcı kararı):** ops ağacına yeni **☑ ilk sütun**
  (`Sel`, tık = işaret; `<Button-1>` handler'ı "break" döndürür → satır seçimini bozmaz;
  çift-tık ☑ hücresinde Aç/Kapat'ı TETİKLEMEZ) + Treeview'ın yerleşik Shift/Ctrl çoklu
  seçimi. Kural: işaret varsa işaretler kazanır, yoksa seçim (`_batch_targets`).
- **"Toplu…" toolbar düğmesi:** ≥2 hedefte aktif, sayıyı gösterir ("Toplu… (3)").
  `_update_batch_button` → on_op_select + refresh_ops_tree + ☑ tık.
- **`BatchEditDialog`** (`ui/dialogs/batch_edit_dialog.py`): parametre combobox +
  mod radyoları (**+= ekle / = ata / ×= ölçekle**) + değer alanı + **CANLI önizleme
  tablosu** (# / Tip / Eski / Yeni; uygulanamayan satır gri "atlandı"). Uygula'ya
  kadar hiçbir şey yazılmaz; geçersiz değerde Uygula kapalı.
- **Saf çekirdek `ProgramTab._batch_compute`** (headless test edilir): tip evreninde
  olmayan parametre → "na" atla; +=/×= için taban yok (sayısal olmayan default) →
  "nobase" atla ama = ata çalışır; eksik değer sayısal OP_PARAM_DEFAULTS'a düşer;
  `count` tam sayıya yuvarlanır, taban 1.
- **Parametre listesi Özelleştir'den (#59 entegrasyonu, kullanıcı kararı):**
  view customizer'a ÜÇÜNCÜ **"Toplu"** kutusu (yalnız `_BATCH_ELIGIBLE` sayısal
  anahtarlarda; diğerlerinde "—"). `op_view_config[type]["batch"]` olarak .ssp ile
  kaydedilir. Eski config'de anahtar YOKSA küratörlü varsayılana düşer
  (`_DEFAULT_BATCH_KEYS`: speed/feed/count/start_z/end_z/clearance/reach/
  reach_blank_factor/pass_angle/rot/z_pos/plunge_x); açıkça boş [] saygı görür.
- **Undo entegrasyonu (#66):** tüm batch TEK snapshot (`_apply_batch` →
  `_push_undo`) → tek Ctrl+Z hepsini geri alır. Uygulama sonrası editör
  `on_op_select(_flush=False)` ile yeniden kurulur — bayat entry-saver'ın eski
  değeri geri yazması (#56 deseni) engellenir. `_schedule_auto_calc()` çağrılır.
- **☑ işaretleri yapısal değişimde temizlenir** (indeks bayatlar): del/move/split/
  undo-redo/proje yükleme (`_clear_batch_checks`).
- i18n: btn_batch, dlg_batch_title, lbl_batch_*, rb_batch_*, col_batch_old/new,
  msg_batch_noparams/done, vc_col_batch (EN/TR/ES) + vc_info güncellendi.
  Help (EN+TR): "TOPLU DÜZENLEME" bölümü + Özelleştir bölümüne üçüncü kutu notu.

### Doğrulama
- `_test_batch.py` GEÇTİ (9 senaryo: add/set/scale, na/nobase atlama, default
  fallback, count int+taban-1, bool guard, default cfg, _view_cfg geri-uyum, eligible seti).
- `_test_program_tab_toolbar.py` GENİŞLETİLDİ + GEÇTİ (☑ sütunu, undo/redo düğme
  durumları, batch düğme enable/disable + sayı, uçtan uca batch apply + tek-adım undo).
  NOT: On işareti values[1]→[2] kaydı (☑ öne eklendi) — test güncellendi.
- `_test_undo.py` / `_test_continue.py` / `_test_split.py` GEÇİYOR; 4 dosya derleniyor.
- **GUI smoke test BEKLİYOR** (☑ tıklama, canlı önizleme, gerçek pencerede).

### Geri alma
`program_tab.py`: _BATCH_* sabitleri, `_default_cfg`/`_view_cfg` "batch" anahtarı,
Sel sütunu (3 yer), `_on_tree_click`, batch metod bloğu, btn_batch, 5 adet
`_clear_batch_checks` çağrısı. `view_customizer.py`: üçüncü kutu. Dialog dosyası +
`_test_batch.py` sil. i18n anahtarları + help bölümleri.

## 2026-07-07 — Program sekmesi Geri Al / Yinele (↶/↷ + Ctrl+Z/Ctrl+Y) — TODO #66

Operasyon LİSTESİNİ değiştiren her düğme işlemi artık geri alınabilir (kullanıcının
asgari şartı: **Böl geri alınabilmeli**). Snapshot tabanlı: işlem ÖNCESİNDE
`operations` listesinin deep-copy'si yığına itilir — işlem başına özel ters-mantık yok.

### Ne eklendi
- `program_tab.py`: modül seviyesinde **`OpUndoStack`** (saf mantık, Tk'sız →
  headless test edilebilir). 50 derinlik; dolunca EN ESKİ sessizce düşer; yeni işlem
  redo yığınını temizler (standart editör kuralı). Girdiler `(etiket, ops deep-copy,
  seçili idx)`.
- İzlenen işlemler (9): `add_op`, `del_op`, `move_op` (▲▼), `toggle_op_enabled`
  (çift-tık dâhil), `continue_from_previous`, `compute_reach_from_blank` (Reach⟲),
  `compute_angle_from_surface` (Açı⟲), `open_split_op` (Böl), `_apply_suggested_ops`
  (✨Öner ekleme). Push, tüm doğrulamalardan/dialog onayından SONRA, mutasyondan
  HEMEN ÖNCE. Alan yazımı (property editor) BİLEREK izlenmiyor (kullanıcı kararı).
- Toolbar: **↶ / ↷** düğmeleri (zaman etiketinin solunda), yoksa disabled.
  Kısayollar toplevel'a bağlı: Ctrl+Z / Ctrl+Y (+Ctrl+Shift+Z). GUARD:
  Program sekmesi görünür değilse (`frame.winfo_ismapped()`) veya odak yazı
  girişindeyse (Entry/TEntry/Text/TCombobox/Spinbox) kısayol YOK SAYILIR —
  alana yazarken Ctrl+Z listeyi geri sarmaz.
- `_apply_history`: önce `_flush_entries()` (bekleyen düzenleme karşı-yığın
  snapshot'ına girsin), sonra saver'lar temizlenip editör widget'ları yıkılır
  (#56 bayat-saver deseni, del_op ile aynı), liste takas, tree yenile, seçim geri,
  `_schedule_auto_calc()` (auto-calc kapalıysa hesap YOK — mevcut davranışla uyumlu).
  Durum çubuğunda "Geri alındı: {işlem}".
- `main_window.open_project_action`: proje yüklenince `clear_undo_history()` —
  geçmiş oturuma/projeye özel.
- i18n: `act_move_op`, `msg_undo_done`, `msg_redo_done` (EN/TR/ES). Help (EN+TR):
  "GERİ AL / YİNELE" bölümü eklendi.

### Doğrulama
- `_test_undo.py` GEÇTİ (7 senaryo: restore, redo, deep-copy izolasyonu, redo-temizleme,
  50-derinlik + en-eski-düşer, boş yığın None + clear, iç içe undo/undo/redo).
- `_test_continue.py` + `_test_split.py` GEÇTİ (regresyon yok), 4 dosya derleniyor.
- **GUI smoke test BEKLİYOR** (düğme durumları, kısayol guard'ları gerçek pencerede).

### Geri alma (bu özelliği kaldırmak istersen)
`program_tab.py`: `OpUndoStack` sınıfı + "Undo / Redo for op-list actions (#66)"
metod bloğu + 9 adet `self._push_undo(...)` satırı + toolbar ↶/↷ bloğu + `__init__`
`self._op_undo` satırı. `main_window.py`: `clear_undo_history()` çağrısı.
i18n 3 anahtar, help 2 bölüm. `_test_undo.py` sil.

## 2026-07-05e — 3D sürükle-düzenle GERİ ÇEKİLDİ (kullanıcı: "hâlâ glitch, kaldıralım")

VTK sphere-widget sürükleme birkaç turdan sonra bile stabil çalışmadı (küçük kaydırma → büyük
açı/reach sıçraması, periyodik uzun/kısa salınım, çökme). Ortam GUI'siz olduğu için etkileşim
burada test edilemiyor. TAMAMEN KALDIRILDI:
- `program_tab`: Drag Edit + Revert⤺ butonları, `toggle_drag_edit`/`_refresh_drag_handle`/
  `_on_p3_drag`/`_on_drag_release`/`_active_forming_pass`/`revert_active_pass_override`,
  on_op_select + ◀/▶ kancaları. `var_drag_edit` kaldırıldı.
- `path_generator`: per-pass override motoru (`pass_overrides` bloğu, `_pass_overridden`,
  clearance-guard koşulu) GERİ ALINDI → orijinal davranış. ⚠ SONUÇ: sürükleyle bozulan op'lar
  KENDİLİĞİNDEN düzelir (op["pass_overrides"] verisi artık YOK SAYILIR).
- `main`: `self._last_cps` deposu kaldırıldı. `i18n`: btn_drag_edit/btn_revert_pass/msg_revert_*
  kaldırıldı. `_test_pass_override.py` silindi. NOT: `gui_pass_overrides` (ayrı, önceden var olan
  sistem) DOKUNULMADI.
Motor testleri (reach, foldback, progressive, real_end_z) GEÇİYOR = path_gen temiz.
Not: geri-çekilen tasarım git geçmişinde; ileride Customize-mode VTK sphere-widget YERİNE başka
yolla denenmeli.

## 2026-07-05d — 3D sürükle-düzenle: aktif pasın P3 tutamağı → per-pass override (TODO #61)

Kullanıcı seçti: **P3 (çıkış) tutamağı → reach+açı**, ve **SADECE O PAS** (per-pass override).

### Motor temeli (headless doğrulandı)
`path_generator` pas döngüsüne **per-pass override** eklendi: `op["pass_overrides"][i] =
{"angle":..,"reach":..}` (i = forming-pas indeksi, JSON string anahtar) fan'ı geçersiz kılıp O
PASIN `_eff_angle`/`_L3`'ünü sabitler. Yalnız pass-angle modunda. `_test_pass_override.py` GEÇTİ:
override'lı pas değişir, diğerleri AYNI, reach 25↔50 ucu tam 25 mm oynatır, boş override =
birebir eski davranış.

### Sürükle tutamağı (GUI — SMOKE TEST BEKLİYOR, VTK etkileşimi burada doğrulanamaz)
- `main.update_scene`: `self._last_cps = cps` (pas başına [P1,P2,P3], P3=cps[k][2]).
- `program_tab`: **"Drag Edit"** toolbar checkbox (opt-in, `toggle_drag_edit`). Açıkken aktif
  pasın P3'üne `plotter.add_sphere_widget` sarı tutamak. `_on_p3_drag`: yeni P3'ten
  exit=P3−P2 → reach=|exit|, θ_B=atan2, pass_angle=θ_B−θ_A → `pass_overrides[fi]`'ye yaz,
  350 ms debounce recalc (sürükleme akıcı kalsın). `_active_forming_pass` (back-pass/yanlış tip
  atlar), `_refresh_drag_handle` op-seçim + ◀/▶'te tutamağı taşır. i18n `btn_drag_edit`.
- ⚠ SONRAKİ: gerçek pencerede sürükleme, geri-hesap doğruluğu, recalc sonrası tutamak konumu.

### DÜZELTME (kullanıcı testi 1: "çılgın hareket, ayarlanamıyor")
Kök neden: override'lı pasa da clearance-bağımsız-reach çıkarması (`p3_x −= clearance`)
uygulanıyordu → sürüklenen P3 ile motorun yeniden ürettiği P3 uyuşmuyor → her recalc'ta pas
zıplıyor. Fix: `_pass_overridden` bayrağı; override'lı pas clearance kaydırmasını ATLAR →
P3 = P2 + reach·(cosθ_B,sinθ_B) TAM sürükleme noktası. Böylece bire-bir, açı/reach op fan'ıyla
SINIRLI DEĞİL. `_test_pass_override.py` + `_test_reach_foldback.py` GEÇTİ. **Revert⤺ butonu**
(`revert_active_pass_override`, kullanıcı seçti "düğme, düzenlemeler kalır"): aktif pasın
override'ını siler → fan varsayılanına döner, diğer paslar korunur. i18n `btn_revert_pass`.
Kullanıcı testi 2 + terminal kırmızı hataları BEKLİYOR.

## 2026-07-05c — Deforme-blank önizleme faz 1 (#63) + changelog penceresi + STEP oto-yükle + versiyon

### Deforme-blank overlay (TODO #63) — TOOLPATH-tabanlı, pasın açı+reach'ini birebir izler + SİMÜLASYON
**KULLANICI ONAYLADI (2026-07-05c): "actually you made it right."** Model son hâli: seçili pasın
GERÇEK toolpath'i (temas P2 → çıkış P3) alınır, tool yarıçapı kadar içeri çekilir, eksende
döndürülür → yüzey pasın AÇISINI (eğim) ve REACH'ini (boy) yapısı gereği izler. `_rtool_for_pass`,
`deformed_blank_offset` param (radyal ince ayar). Sığ pas→dışa yaslı, dik(~180°)→dik. Önceki
mandrel-profil/flanş-alan modelleri ÇÖP (kullanıcı "içeride/merkezden" dedi → toolpath'e geçildi).
**SİMÜLASYON (faz 3):** `SimulationController.current_pass_idx` (worker'da her cut/pass'te set,
finally'de -1); `check_sim_loop` bunu izler, değişince `active_editing_pass_idx`'i güncelleyip
`update_deformed_blank()` çağırır → sim oynarken sac pas-pas bükülür. `_sim_last_blank_pass` ile
sadece pas değişince çizer. `_test_deformed_blank.py` (toolpath-tabanlı) GEÇTİ. Gelecek: spring-back.
**MODEL YENİDEN KURULDU (kullanıcı 2026-07-05c): mandrel'e sarılan değil, PAS AÇISINA göre
bükülen sac.** Kullanıcı seçti: "flanş bu pasın açısı+reach'iyle yaslanır." Alt duvar mandrel'e
şekillenir (min-Z→pasın temas Z'si), oradan flanş **pasın kendi çıkış vektörü (P2→P3) boyunca
yaslanır** — yönü = pas açısı (θ_B), boyu = reach. Pas ilerledikçe açı yelpazelenince flanş
duvara doğru döner (sığ pas→dışa yaslı, ~180°→dikey). `main._active_pass_bend()` aktif pasın
toolpath'inden P2 (eksene en yakın) + P3 (uç) alır; `update_deformed_blank()` duvar + çıkış-
vektörü flanşı kurar, `extrude_rotate(angle=360)`; yarıçap eksene taşmaya karşı korunur; vis_off
ile mandrel/shell'den TAŞKIN çizilir (kalınlık ölçekli DEĞİL). `active_editing_pass_idx` sürer.
**Canlı yenileme düzeltmesi:** pas-nav ◀/▶ (`go_prev/go_next`) + slider (`cb_idx`) artık
`update_deformed_blank(render=True)` çağırır (eskiden sadece recolor_paths → Calculate gerekiyordu).
Toggle `show_deformed_blank`. SALT GÖRSEL. `_test_deformed_blank.py` (pas-tabanlı) GEÇTİ. Sıradaki:
simülasyon animasyonu; gelecekte spring-back. GUI smoke BEKLİYOR.

### Changelog penceresi + versiyon + STEP oto-yükle
- **version.py** `APP_VERSION="1.004"` = tek kaynak; ayarlardan yüklenen app_version bunun üstüne
  ZORLANIR (main.py) + tüm etiketler (title/gri bar/sidebar) doğrudan APP_VERSION okur (eski gri
  bar v1.003 gösteriyordu — müşteri-ayar yüklemesi params'ı geri yazıyordu; `app_version` artık
  `_load_machine_profile` clean-update'ten hariç). About metni hâlâ elle 1.002 (ayrı).
- **changelog.py** sürüm-anahtarlı; **ui/dialogs/changelog_window.py** açılışta yeni sürümde
  "Yenilikler" penceresi (Tekrar gösterme + OK). `changelog_seen_version` param; `entries_since`.
- **STEP oto-yükle**: açılışta `last_step_path` varsa sormadan yüklenir (yoksa/eksikse sorar).
  `main_window._auto_load_step`/`_startup_tasks`/`_maybe_show_changelog`.

## 2026-07-05b — Reach/açı oturumu: End Angle çerçeve düzeltmesi, çap-koruması, Angle⟲, fold-back clamp

Smoke-test sırasında bulunan 4 sorun (hepsi headless doğrulandı; **GUI smoke + commit BEKLİYOR**):

### 1. End Angle sütunu yanlış çerçevede (113° pas → 23° gösteriyordu)
`path_generator.py` ~373: son forming pasın end-angle'ı **mutlak +X'ten** kaydediliyordu
(`atan2(p3_z,p3_x)`), ama Pass Angle **yaklaşım yönüne göre** ölçülür (linear approach θ_A=−90°) →
113−90=23. Fix: pass-angle modunda `_eff_angle` (kullanıcının girdiği çerçeve, yelpaze bitişi
dahil) kaydediliyor; raw modda mutlak açı korunuyor. Sadece GÖSTERİM — toolpath değişmedi.

### 2. Reach⟲ çap-koruması (Sac Yarıçapı alanına ÇAP girilmesi)
Kök neden: `blank_radius` bir YARIÇAP alanı (i18n "Sheet Radius", main.py:676/1468). Kullanıcı
310 (çap) girmiş → reach ≈ 310−r_base ≈ 227 (gerçek ~72 olmalı). `compute_reach_from_blank`'e
uyarı eklendi: `R > br×2.5` ise "çap mı girdiniz?" (askyesno, yine de izin verir — warn-but-allow).
i18n `msg_reach_diam` (EN/TR/ES). br = `mandrel_mgr.props["br"]`.

### 3. Angle⟲ — progressive_angle_end'i mandrel yüzeyinden tahmin (opt-in, TODO #61)
Kullanıcı: "180 default yanlış — mandrel yüzey açısından hesaplansın." 180 sadece SİLİNDİR özel
hâli. `process_planner.estimate_surface_angle(mgr, z, forming_up)`: duvar teğet açısı = dış normal
`(dz,−dr)`'ye dik. `program_tab.compute_angle_from_surface()`: op end_z'de teğet → pass-angle
çerçevesine çevir (θ_end − θ_A), `progressive_angle_end`'i DOLDUR (count>1 ise fan aç). Araç çubuğu
`btn_compute_angle` (Reach⟲'dan sonra), i18n `btn_compute_angle`/`msg_angle_*`. Silindir→180 test
edildi. ⚠ Şekillendirme YÖNÜ (yukarı/aşağı) fiziksel doğrulama bekliyor (ters olursa çıkış ters döner).

### 4. Reach fold-back clamp (paslar 180°'yi geçip geri katlanıyordu) — KÖK NEDEN
Kullanıcının "paslar 180'den büyük görünüyor" sorunu. Log kanıtı: pas 30 komut açısı 179.8° ama
gerçek çıkış 182°. Kök neden = #61 clearance-bağımsız-reach: reach set iken `p3_x -= op_clearance`
(path_generator ~421). Fan ~180'e yaklaşınca p3_x→~0, tam clearance çıkarılınca NEGATİFE düşüyor →
çıkış dikeyi geçip geri katlanıyor. (Program kısaltmak / sac büyütmek ETKİLEMEZ — bu çıkarma yalnız
clearance+açıya bağlı.) Fix: clearance'ı SADECE bileşen >= 0 kaldığı sürece çıkar; aksi hâlde komut
çıkışını OLDUĞU GİBİ KORU (`if p3_x - op_clearance >= 0: p3_x -= op_clearance`, conformal'da her iki
bileşen). ⚠ ÖNEMLİ: bileşeni 0'a CLAMP ETME — o zaman clearance-altı tüm ~dikey paslar AYNI dikey
çizgiye çöker (paslar ÜST ÜSTE biner; kullanıcı bunu gördü). Komut çıkışını koruyunca her pas kendi
açısını (θ_B) korur → ne katlanma ne çakışma. Aşırı açıda uç HAFİF clearance-bağımlı olur (güvenlik/
ayrıklık > tam anchor). `_test_reach_foldback.py` GEÇTİ: (a) çıkış içe dönmüyor, (b) iki ~180° pas
AYRIK yön koruyor (dxa≠dxb), çökmüyor.

### 5. "Reach follows blank" — reach'i sac ucuna KİLİTLE (opt-in, TODO #61 option B)
Kullanıcı: "zone end z'yi artırabilmeliyim, reach otomatik sacın ucunu öpecek şekilde
hesaplansın." end_z ve reach ÇAKIŞMAZ (biri temas yüksekliği, diğeri çıkış stroju) ama reach'in
ucu ÖPMESİ için end_z'ye bağlı olması gerekir. Yeni per-op bayrak `reach_follow_blank`: açıkken
her recalc'tan önce reach flanş modelinden yeniden hesaplanır (start_z→reach, end_z→
progressive_reach_end), böylece end_z değişince çıkış otomatik yeni flanş ucuna oturur. end_z
sacın tükendiği yeri geçerse reach→0 (fold-back clamp near-flat pasları korur). Ortak yardımcılar
`_blank_reach_values`/`_apply_blank_reach` (Reach⟲ ile paylaşılır), `_refresh_auto_reach`
`_start_async_calc` başında çağrılır. Editörde checkbox (reach alanı altında), i18n
`lbl_reach_follow`, OP_PARAM_UNIVERSE/LABELS/path_shape kaydı. Manuel reach'i geçersiz kılar.

### 6. Pass Info'da reach satırı + reach payı (modifier)
- **Pass Info penceresi**: her pasta artık `Reach → |P2→P3|: xx.xx mm` satırı (gerçekleşen çıkış
  stroju = temas→uç mesafesi). `refresh_pass_info`, Contact satırından sonra.
- **Reach çarpanı** (`reach_blank_factor`, ×, opt-in, default 1.0): sactan hesaplanan reach'i
  ÖLÇEKLER. Reach⟲ ve 'Reach sacı takip etsin' değerine uygulanır (`_blank_reach_values`).
  1.00 = tam sac ucu, 0.90 = %90 (ucundan önce dur), 1.10 = %110 (geç); boş=1.0, negatife düşmez.
  Editörde alan (reach-follow altında, OP_PARAM_DEFAULTS'ta 1.0 ipucu), i18n `lbl_reach_factor`,
  OP_PARAM_UNIVERSE/LABELS/path_shape kaydı.

### Doğrulama
`spinning_cam` env'de: `_test_reach.py`, `_test_real_end_z.py`, `_test_progressive_reach.py`,
`_test_surface_angle.py` (yeni), `_test_reach_foldback.py` (yeni), `_test_reach_follow.py` (yeni,
gerçek ProgramTab yardımcılarını stub'a bağlayıp end_z↑→reach↓ doğrular) — HEPSİ GEÇTİ. Değişen
dosyalar: `path_generator.py`, `process_planner.py`, `ui/tabs/program_tab.py`, `i18n.py`.
COMMIT EDİLMEDİ.

---

## 2026-07-05 — Reach'i sactan tahmin (Reach⟲) — flanş alan-eşdeğerliği, opt-in (TODO #61 adım 4)

### Ne (kısa)
Opt-in **Reach⟲** düğmesi: seçili op'un reach'ini kalan sac FLANŞINDAN tahmin edip alanı
DOLDURUR (sessizce UYGULAMAZ — operatör değeri görür). Kullanıcı: "sac yarıçapı belli, kalan
flanşı hesapla, reach o olsun."

### Model (kullanıcı ile netleşti)
- Malzeme sayımı DAİMA kıskaç tabanından (min-Z, karşı baskının tuttuğu yer) başlar →
  yön-bağımsız ("parçaya göre değişir" cevabı). KAPALI düz taban → taban diski `r_base²`.
- `Rc(Z)² = r_base² + 2·Σ(taban..Z) r·ds` (alan-eşdeğerliği, analyze_profile ile aynı).
- Flanş dış yarıçapı `R_flanş = √(r(Z)² + R_sac² − Rc²)`; reach = RADYAL taşma `R_flanş − r(Z)`.
- RADYAL ölçüm (kullanıcı v1 için radyal seçti; tangent dik duvarlar için ertelendi).
- Tabanda büyük → tepede 0'a monoton azalır.

### Nasıl / nerede
- `process_planner.estimate_flange_reach(mandrel_mgr, blank_radius, contact_z)` — saf hesap.
- `ui/tabs/program_tab.py` `compute_reach_from_blank()`: seçili op'ta start_z'de reach,
  progressive-angle çok-paslı op'ta end_z'de `progressive_reach_end` (yelpaze) doldurur;
  refresh+recalc; "TAHMİN, doğrula" messagebox. Araç çubuğu `btn_compute_reach` (Split'ten
  sonra). i18n `btn_compute_reach`, `msg_reach_*` (EN/TR/ES). Sac Yarıçapı (blank_radius) şart.

### Doğrulama / durum
- Headless: `_test_flange_reach.py` GEÇTİ — tam sacla tepe taşması ~0, taban = R−r_base,
  monoton azalış, aşırı sac → tepede flanş kalır, bozuk girdi → 0. compile OK, i18n format OK.
- ⚠ İLK yanlış model (r_min² kapağı, nose-ucundan) test ile YAKALANDI ve düzeltildi
  (r_base, tabandan). **FİZİKSEL doğrulama + GUI smoke BEKLİYOR** (reach yanlışsa gouge riski).
- COMMIT EDİLMEDİ.

---

## 2026-07-05 — Operasyonu Parçalara Böl (Split…) — birebir üreten bitişik parçalar (TODO #64)

### Ne (kısa)
Çok-paslı bir parametrik operasyon (örn. 20 kaba pas, Z 10→60, açı 90→180) görsel bir
pencerede BİTİŞİK parçalara bölünebiliyor (örn. 1·1·5·5·4·2·2). Her parça, o pasları
BİREBİR üreten bağımsız bir operasyon olur. Sonra parçalar sıralanıp aralarına ters pas
operasyonları konabilir. Kullanıcı isteği: "20 pası ayır, aralarına ters pas koy, ama
op'u bozma." Parçalar first-class op olduğu için ayrı ayrı düzenlenebilir.

### Neden birebir çalışıyor (matematik)
Pas Z / pass_angle(→progressive_angle_end) / reach(→progressive_reach_end) / interp-tilt
hepsi pas indeksinde DOĞRUSAL ilerler. [a..b] parçası için alt-aralık uç değerleri (Z, açı,
reach, tilt) ayarlanınca parça, o dilimi aynen üretir. Tek-paslı parçalar yelpazeyi sabit
değere indirger. Diğer tüm alanlar kopyalanır. Güvenlik-düzeltmesi pas-başına deterministik
→ sıradan bağımsız → parçalarda da aynı.

### Nasıl / nerede
- `ui/tabs/program_tab.py` `_split_op(op, sizes, end_z_fallback)` — SAF (statik) dilimleme;
  `_pass_previews(op, end_z_fallback)` — diyalog için pas başına {z, angle}.
- `open_split_op()` — seçim/tip/count kontrolü, diyalog, onayda op yerine parçalar
  (`ops[idx:idx+1]=chunks`), #56 dersine göre editör-saver temizliği, refresh+recalc.
- `ui/dialogs/split_op_dialog.py` `SplitOpDialog` — kaydırmalı pas listesi, paslar arası
  tıklanabilir bölücü (✂), canlı "Parçalar (n): …" özeti, OK/İptal.
- Araç çubuğu `btn_split` (Continue'dan sonra). i18n `btn_split`, `msg_split_*`,
  `split_help`, `split_summary` (EN/TR/ES).

### Doğrulama / durum
- Headless: `_test_split.py` GEÇTİ — orijinal tek-op ile parça-op'lar BİREBİR aynı forming
  toolpath'leri üretiyor: progressive açı+reach [1,1,5,5,4,2,2] ve [10,10], sabit açı+reach,
  raw p3 modu, açık-uçlu (end_z=None→mandrel tepesi). count'a eşit olmayan sizes reddediliyor.
  compile OK, i18n format OK.
- Diyalog/düğme/akış **GUI smoke BEKLİYOR.** COMMIT EDİLMEDİ.

---

## 2026-07-05 — "Öncekinden Devam" (Continue ⤵) — tek-seferlik doldurma (TODO #61 adım 2)

### Ne (kısa)
Program tab'e **Devam ⤵** düğmesi: seçili operasyonu, ÜSTÜNDEKİ opun SON pasının bitiş
durumundan tek seferlik doldurur. Kopyalanan: Başlangıç Z (önceki bitiş), çıkış açısı
(pass_angle; yelpaze varsa `progressive_angle_end`; raw modda p3_x/p3_z oranı), reach ve
clearance. Takım KOPYALANMAZ. Doldurduktan sonra op bağımsızdır (ör. Yön=Ters yapılır).
Kullanıcı senaryosu: "önceki opun son pasıyla aynı konum/açıda ters pas" — artık elle
5. pasın değerini hesaplamak yok.

### Nasıl / nerede (ui/tabs/program_tab.py)
- `_continue_fill_values(prev, prev_end_z, prev_reach)` — SAF (statik) hesap: doldurulacak
  alan sözlüğü. Bağımsız test edilebilir. Motorun hesapladığı `last_op_end_z`/`last_op_reach`
  tercih edilir; hesap yoksa önceki opun parametrelerine düşer.
- `continue_from_previous()` — seçim/ilk-op kontrolü (messagebox uyarıları), fill uygular,
  tree+editör yeniler, `_start_async_calc` ile yeniden hesaplar, durum çubuğuna özet.
- Araç çubuğu düğmesi (toggle'dan önce). i18n `btn_continue_prev`, `msg_continue_*`.
- `messagebox` import edildi (program_tab).

### Doğrulama / durum
- Headless: `_test_continue.py` GEÇTİ — yelpaze bitiş açısı kopyalama, düz pass_angle,
  raw p3 oranı, hesap-yok fallback. program_tab/i18n compile OK, i18n format OK.
- GUI (düğme/messagebox/fill akışı) **GUI smoke BEKLİYOR.** COMMIT EDİLMEDİ.

---

## 2026-07-05 — Tek "Erişim" (reach) parametresi — pas çıkış uzunluğu (TODO #61 adım 1)

### Ne (kısa)
Pasın çıkış kolu (P2→P3) artık TEK bir "reach" (erişim) değeriyle ifade edilebilir:
büyüklük = reach, yön = (Pass Angle varsa ondan; yoksa p3_x/p3_z oranından). Operatör
açıyı bozmadan pası uzatıp kısaltabilir. `p3_x`/`p3_z` KALDIRILMADI — yön/oran onlardan
gelir, reach sadece uzunluğu ölçekler. Boş/0/geçersiz reach = ESKİ davranış (tam uyumlu).

### Motor (path_generator.py, geriye tam uyumlu)
- `_reach_v = op.get("reach")` parse (None/""/≤0 → None = legacy).
- Pass-angle modunda: `_L3 = _reach_v if set else sqrt(p3_x²+p3_z²)` — reach, _L3'ü
  (büyüklüğü) override eder; progressive_reach hâlâ paslar arası _L3'ü süpürür.
- Raw modda (Pass Angle yok): reach set ise `(p3_x, p3_z)` vektörü oranı korunarak
  reach uzunluğuna ölçeklenir.
- Okunabilir çıktı: `last_op_reach` + `last_op_end_angle` (son forming pasın büyüklüğü ve
  +X'ten açısı, derece) — RealEndZ ile aynı zamanlamada kaydedilir.

### Reach CLEARANCE'TEN BAĞIMSIZ (kullanıcı kararı 2026-07-05)
Kullanıcı: "aynı reach + farklı clearance → aynı MUTLAK bitiş noktası." Bu yüzden reach set
iken çıkış UCU (P3), sıfır-clearance temas referansına sabitlenir: P2 clearance standoff'unu
taşır (radyal / conformal'da normal boyunca), P3 offset'inden bu clearance bileşeni ÇIKARILIR
→ endpoint clearance'tan bağımsız. `path_generator.py` p2_x/p2_z bloğundan hemen sonra:
`if _reach_v: p3_x -= op_clearance*(nx conformal else 1); p3_z -= op_clearance*nz(conformal)`.
- **UYARILAR (test edildi):**
  1. **base_rot=0 için TAM** (linear approach / rotation kapalı). Auto-rotate spline'da P3,
     P2 etrafında döndüğü için YAKLAŞIK — gerekiyorsa vaka bazında doğrula.
  2. **DÜŞÜK clearance'ta güvenlik önceliklidir:** sabitlenmiş çıkış gouge yapacaksa
     safety-floor (collision) yolu dışarı iter ve ankraj geçersiz olur — bu DOĞRU/güvenli
     davranış. Test bunu düşük clearance'ta gözlemledi (P3 kontrol noktası yine de aynıydı).
- Readout (last_op_reach/end_angle) compensation ÖNCESİ yakalanır → End Reach = kullanıcının
  girdiği reach (niyet), End Angle = yön. Geometri compensation SONRASI (clearance-bağımsız uç).

### UI
- Program tab özellik editörü: yeni **reach** alanı (p3_z'den sonra), i18n `lbl_reach`.
  OP_PARAM_UNIVERSE["roughing"] + OP_PARAM_LABELS + SECTION_KEYS["path_shape"]'e eklendi
  (Customize View §21 senkron).
- İki yeni SABİT sütun (RealEndZ gibi): **End Reach** + **End Angle** — `last_op_reach`/
  `last_op_end_angle`'dan; i18n `col_end_reach`/`col_end_angle`. Finish/cut/bend → "—".

### Doğrulama / durum
- Headless: `_test_reach.py` GEÇTİ — reach unset/None/0/junk BİREBİR AYNI geometri
  (backward-compat), raw modda büyüklük ölçekleniyor + açı korunuyor (25→50 @36.87°),
  pass-angle modda reach _L3'ü override ediyor (25→40). `_test_planner_e2e.py` regresyon
  GEÇTİ (path sayıları/gcode/fan-end/passivate değişmedi). program_tab/i18n compile OK,
  UI wiring doğrulandı.
- **NOT yapıldı (sonraki rafinman):** iki-yönlü canlı bağ (reach yazınca p3_x/p3_z kutuları
  güncellensin ve tersi). Şu an reach alanı bağımsız yazılıyor; motor yön'ü p3'ten alıyor.
- 3B/GUI görünümü (alan + iki sütun) **GUI smoke BEKLİYOR.** COMMIT EDİLMEDİ.

---

## 2026-07-05 — Kıskaç/karşı-baskı bölgesi (counter-press) — Faz 1: UYARI + 3B bant (TODO #62)

### Ne (kısa)
Mandrel tabanındaki bölge karşı baskı (counter-press) ile mandrel arasında sıkışır ve
İŞLENMEZ. Şimdiye kadar operatör ilk operasyonun `start_z`'sini elle (örn. 10) girip bu
bölgeyi atlıyordu. Faz 1: bu bölge artık **parametreyle tanımlanıyor**, 3B sahnede
**yarı saydam kırmızı bant** olarak gösteriliyor ve bir operasyon bu bölgede başlarsa
**UYARI loglanıyor** (yol yine de üretilir — kırpma YOK, o Faz 2).

### Parametreler (iki katman — makine varsayılanı + program override)
- `clamp_zone_baseline` (MAKİNE profili anahtarı) — `machine_loader.MACHINE_PROFILE_KEYS`,
  `machines/ID111-1.json` + `ID112-1.json` (0.0), `config_schema.MachineProfileSchema`.
  Makine sekmesinde düzenlenir → `autosave_machine_profile` ile profile yazılır.
- `clamp_zone_length` (program/.ssp override) — `main.py load_settings` (0.0 = varsayılanı
  devral). Process sekmesi spinbox.
- **Etkin uzunluk** = `path_generator.effective_clamp_length(params)`: override > 0 ise o,
  değilse baseline. TABANDAN YUKARI mm. `clamp_top_z = mandrel min_z + etkin_uzunluk`.
  ⚠️ Bilinen tradeoff: override=0 "devral" demek → sıfır olmayan baseline'ı program bazında
  0'a çekip KAPATMAK Faz 1'de mümkün değil.

### Nasıl / nerede
- `path_generator.py`: modül düzeyi `effective_clamp_length()`; `calculate_paths` başında
  `self.last_clamp_warnings = []` + `clamp_top_z` hesabı; op döngüsünde `start_h < clamp_top_z`
  ise uyarı dict'i eklenir; sonda log. Sadece forming op'lar (roughing/finishing start_z);
  cutting/bending Faz 1'de kontrol edilmiyor.
- `main.py update_scene`: workspace bloğundan sonra `clamp_zone` aktörü — `pv.Cylinder`
  (kırmızı, opacity 0.18) min_z→clamp_top_z, yarıçap = mandrel taban yarıçapı + 5mm.
  `effective_clamp_length` main.py'ye import edildi.
- UI: Process `sp_clamp_zone`, Machine `lbl_clamp_baseline` (workspace frame'inde add_ws_entry).
  i18n EN/TR/ES. help_window "Clamp Zone Default" bölümü.
- **UYARININ GÖRÜNÜRLÜĞÜ (2026-07-05 düzeltme):** İlk sürümde uyarı SADECE log'a
  yazılıyordu → operatör görmüyordu. Eklendi: `main_window.refresh_clamp_status()` durum
  çubuğunu (`lbl_info`) amber renkte günceller. HER İKİ hesap yolundan çağrılır:
  program_tab `_poll_calc_queue` (async "⟳ Hesapla"/auto) VE process_tab `force_calc`
  ("GÜNCELLE/YOLLARI HESAPLA" düğmesi, senkron). i18n `status_clamp_warn`.
  ⚠ Uyarı SADECE bir op gerçekten bölge içinde başlarsa (start_z < min_z+len) tetiklenir;
  op'lar bandın üstünde başlıyorsa uyarı ÇIKMAZ (doğru davranış).
- **POP-UP + iki düğme (2026-07-05, kullanıcı isteği):** `refresh_clamp_status` durum
  çubuğuna EK olarak `_show_clamp_popup()` ile özel modal Toplevel gösterir. İki düğme:
  **Onayla** (kapatır; sonraki hesapta tekrar çıkabilir) ve **Tekrar gösterme**
  (`self._clamp_popup_suppressed=True` → oturum boyunca susturur; durum çubuğu kalıcı
  gösterge olarak kalır). Susturma SADECE oturumluk — güvenlik uyarısı bir sonraki açılışta
  tekrar uyarsın diye kalıcı DEĞİL (istenirse settings'e taşınabilir). Her ihlalli hesapta
  çıkar (susturulmadıysa). i18n `msg_clamp_warn_title/op/body`, `btn_confirm`,
  `btn_dont_show_again` (EN/TR/ES).

### Doğrulama / durum
- Headless: `_test_clamp_zone.py` GEÇTİ — effective_clamp_length çözümü (override/baseline/
  junk-safe), uyarı bölge içinde başlayınca tetikleniyor, üstünde/bölge yokken tetiklenmiyor,
  override=0 baseline'ı devralıyor, override baseline'ı yeniyor. 8 dosya py_compile OK
  (spinning_cam env).
- 3B bant görsel olarak headless test EDİLEMEDİ (plotter gerekir) → **GUI smoke BEKLİYOR.**
- **COMMIT EDİLMEDİ.** Geri alma: bu blokta adı geçen ekler kaldırılırsa özellik tamamen kalkar.

---

## 2026-07-04 — Operasyon tablosuna "Gerçek Bitiş Z" sütunu + yatay kaydırma

### Ne (kısa)
İki değişiklik:
1. **"Gerçek Bitiş Z" sütunu** (sabit) — her operasyonun SON ileri pasının Z'de
   gerçekte ulaştığı yeri (en derin temas P2) gösterir. Zone End Z'den farkı:
   `p2_z_extend` son pası planlanan bölge bitişinin ötesine iter → Gerçek Bitiş Z =
   Zone End Z + p2_z_extend. Değer, hesaplanan takım yolundan RAW CAM Z olarak okunur
   (makine dönüşümü YOK) → Zone Start/End Z ile AYNI referans, doğrudan zincirlenebilir.
2. **Yatay kaydırma çubuğu** — tabloda sadece dikey çubuk vardı; çok sütunda sağdakiler
   kırpılıp ulaşılamıyordu.

### Neden
Kullanıcı: "Zone Z, son pasın başlangıcı; ama p2_z_extend yüzünden gerçek Z daha ileride —
gerçek değeri görmek istiyorum." Zone End Z (op parametresi) bunu göstermiyor; asıl temas
`contact_z = target_z + p2_z_extend` (path_generator.py:300). Toolpath P2 (min-X) noktası
bunu otomatik yakalar (count==1, conformal, finishing dâhil). İLK deneme makine Z gösteriyordu
(yanlış referans) — RAW CAM Z'ye çevrildi.

### Nasıl / nerede — DEĞER PATH GENERATOR'DA HESAPLANIR (UI tahmin etmez)
- `path_generator.py` `calculate_paths`:
  - Yeni `self.last_op_end_z = {}` (op-index → son forming pasın ulaştığı CAM Z).
  - Döngü `for op_index, op in enumerate(operations):` (operations == params["operations"],
    aynı sıra/index → UI satır index'iyle birebir).
  - `end_h` belirlendikten sonra tek hesap: roughing `= (count<=1 ? start_h : end_h) +
    p2_z_extend` (satır ~294-300'deki target_z/contact_z ile birebir); finishing `= end_h`
    (tüm bölgeyi süpürür, extend=0); cutting/bending `= z_pos`.
- `ui/tabs/program_tab.py`:
  - `_compute_op_end_z()` artık SADECE `path_gen.last_op_end_z`'i okur (min-X sezgisi ÇÖPE).
  - `rebuild_tree_columns` + `_create_widgets` tree: base sütunlara `"RealEndZ"`.
  - `refresh_ops_tree`: değeri hücreye (yol yoksa "—").
  - `_create_widgets`: `tree_ops`'a `sb_x` yatay Scrollbar + `xscrollcommand`.
- `ui/main_window.py`: `update_scene` hook'u `refresh_pass_info` yanında `refresh_ops_tree`.
- `i18n.py`: `col_real_end_z` (EN "Real End Z" / TR "Gerçek Bitiş Z" / ES "Fin Real Z").

### Neden min-X sezgisi TERK EDİLDİ
İlk deneme UI'de yolun min-X (merkeze en yakın) noktasının Z'sini alıyordu = P2 sanılıyordu.
Ama `linear_approach` yaklaşım kolu, P2 ile AYNI X'te dikey bir çizgi (Z ≈ -37…+16 arası);
`argmin` kolun EN ALT-Z ucunu döndürüp op0 için ~10 gösteriyordu (kullanıcı bug'ı). Ayrıca
UI'nin `_get_pass_type_list` yol↔op eşlemesi otoriter değildi. Doğru kaynak: path generator'ın
zaten hesapladığı `contact_z` (satır 300). Headless PARAM_DEBUG doğruladı: op0 son pas
P2 Z=16.00 (=13+3), UI 16 gösteriyor.

### Not / doğrulama
SADECE görüntü — değer/takım yolu değişmez. Byte-compile OK; entegrasyon testi (gerçek
`calculate_paths`) op0=16 / op1=18.5 / finishing=30 GEÇTİ; toolbar smoke GEÇTİ; gerçek pencere
GUI smoke BEKLİYOR (kullanıcı uygulamayı yeniden başlatmalı).

---

## 2026-07-04 — Op Aç/Kapat artık UI'yi dondurmuyor (auto-calc arka plana alındı)

### Ne (kısa)
Bir operasyonu aktif/pasif yaptığında (veya bir op alanını düzenlediğinde) tetiklenen
otomatik yeniden hesap artık ARKA PLAN thread'inde çalışıyor — turuncu "Hızlı Hesapla"
düğmesiyle aynı yol. Eskiden bu, ana thread'de senkron `calculate_paths` çağırıp tüm
program yeniden hesaplanana kadar arayüzü donduruyordu.

### Neden
Kullanıcı gözlemi: "op'ları aç/kapat yapmak yavaş." Kök neden = `_fire_auto_calc`
→ `update_scene("paths")` → `path_generator.calculate_paths` ANA THREAD'de senkron
(main.py:775). "Hızlı Hesapla" düğmesi ise zaten `calculate_async` (arka plan) kullanıyordu.
NOT: pasif op'lar zaten HER YERDE atlanıyor (calculate_paths:137, generate_gcode:1461,
calculate_estimated_time:1888, main.update_scene:464) — çok sayıda pasif op hesaplamayı
yavaşlatmıyor; sorun tek bir toggle'ın senkron tam-hesap tetiklemesiydi.

### Nasıl / nerede
- `ui/tabs/program_tab.py`:
  - Yeni `_start_async_calc()` metodu — busy-state + roller_pos + `calculate_async` +
    `_poll_calc_queue` mantığı buraya taşındı (eskiden nested `_quick_calc` içindeydi).
  - `_quick_calc` artık sadece `self._start_async_calc()` çağırıyor (davranış aynı).
  - `_fire_auto_calc` artık senkron `update_scene("paths")` yerine `_start_async_calc()`
    kullanıyor + `auto_calculate_paths` kapalıysa erken dönüyor (toggle sadece listeyi
    tazeler, hesap yapmaz — ayarla tutarlı). Hızlı ardışık toggle'lar 300 ms debounce +
    `_calc_running` retry ile tek arka-plan hesaba birleşiyor.
  - Gereksiz property-editor yeniden-kurulumu kaldırıldı: `toggle_op_enabled` zaten
    seçili satırı tekrar `selection_set` ediyordu → `on_op_select` (tüm editör panelini
    baştan kurar) boşuna yeniden tetikleniyordu. `_on_tree_double_click` de aynı satırı
    yeniden seçiyordu. İkisi de artık seçim GERÇEKTEN değiştiyse set ediyor → çift-tık
    başına 1-2 tam panel yeniden-kurulumu tasarrufu.

### Beklenen / test
- Auto-calc AÇIK: op aç/kapat → arayüz donmaz, "Hesaplanıyor…" göstergesi, bitince render.
- Auto-calc KAPALI: op aç/kapat → yalnız liste güncellenir, hesap yok (Hesapla ile).
- Headless syntax doğrulandı; GERÇEK PENCERE GUI SMOKE TEST BEKLİYOR; commit EDİLMEDİ.
- Geri alma: `_fire_auto_calc` içinde `_start_async_calc()` yerine `self.app.update_scene("paths")`
  yaz ve auto-calc guard'ını kaldır.

---

## 2026-07-04 — Exe builder drift koruması: manifest + otomatik kontrol + exe öz-testi

### Ne (kısa)
Exe derleyicinin uygulamanın gerisinde SESSİZCE kalmasını önleyen bir doğrulama
katmanı eklendi. Artık tek bir build reçetesi (`build_exe.py`) var; ne paketleneceği
tek bir yerde tanımlı (`packaging_manifest.py`); ve her build sonunda otomatik bir
kontrol (`check_packaging.py --post-build`) exe'nin eksiksiz olduğunu kanıtlıyor.

### Neden
Üç ayrı build reçetesi (`build_exe.py` + `SpinningCam.spec` + `EMS_SoftSpinner.spec`)
birbirinden sapmıştı: sadece `.spec` `cryptography`'yi (lisans backend'i) paketliyordu,
asıl çalıştırılan reçete paketlemiyordu; yeni veri dosyaları (`materials.json`,
`machines/ID112-1.json`) hiç gönderilmiyordu; `--add-data` dosyaları uygulamanın hiç
okumadığı `_internal/`'e koyuyordu (`get_base_path()` == exe klasörü). Hatalar sessizdi.

### Nasıl / nerede
- **`packaging_manifest.py` (YENİ)** — tek doğruluk kaynağı:
  - `SHIP_NEXT_TO_EXE` — exe'nin YANINA konması gereken dosyalar (settings.json,
    tools.json, materials.json, machines/, logo.* opsiyonel).
  - `MUST_NOT_SHIP` — asla gönderilmemesi gerekenler (`license_private_key.pem`,
    `admin.lic`) → post-build sızıntı kontrolü.
  - `NOT_SHIPPED` — bilerek hariç tutulanlar (license.lic, layout.json, log, .nc).
  - `CRITICAL_MODULES` — frozen exe'de import edilebilmesi ZORUNLU modüller.
  - `run_selfcheck()` — GUI açmadan bütünlük kanıtı.
- **`main_tk.py`** — `--selfcheck` bayrağı eklendi: kritik modülleri import eder,
  lisans public key'ini kurar (cryptography backend'ini yüklemeye zorlar), veri
  dosyalarını exe yanında çözer, 0/1 döner.
- **`check_packaging.py` (YENİ)** — statik kontroller (kaynak var mı, modüller
  import oluyor mu, + KAYNAK TARAMASI: kodda okunan ama manifest'te olmayan veri
  dosyası için UYARI) ve `--post-build` (dosyalar exe yanında mı, sır sızmış mı,
  exe `--selfcheck` 0 mı).
- **`build_exe.py`** — artık TEK reçete. `--collect-all=cryptography` eklendi;
  kullanılmayan `images/` (uygulama okumuyor, dev ekran görüntüleri) çıkarıldı;
  build sonrası manifest exe yanına kopyalanıyor; sonra `check_packaging --post-build`
  çalışıp başarısızsa build'i düşürüyor.
- **`SpinningCam.spec` + `EMS_SoftSpinner.spec` SİLİNDİ** (git geçmişi koruyor).

### Geri alma / dikkat
- `spinning_cam` conda env'de çalıştır (OCC/fpdf/cryptography orada; sistem python'da
  import'lar başarısız olur — bkz HANDOVER_2026-07-01b).
- Yeni bir runtime veri dosyası eklersen `SHIP_NEXT_TO_EXE`'ye ekle; unutursan
  kaynak tarayıcı uyarır ama build'i düşürmez.
- Gerçek frozen rebuild (`build_exe.bat`, 2026-07-04) `BUILD SUCCESSFUL and VERIFIED`
  ile bitti: built exe'nin kendi `--selfcheck`'i tüm kritik modül + lisans crypto +
  veri dosyalarını exe yanında doğruladı. (Bütünlük/açılabilirlik doğrular; GUI
  render veya lisans mantığı doğruluğu DEĞİL.)

---

## 2026-07-04 — Program tab "Görünümü Özelleştir": yapılandırılabilir sütunlar + Temel/Gelişmiş

### Ne (kısa)
Program sekmesine iki kontrol eklendi: (1) **"Özelleştir…"** düğmesi → her operasyon
tipi için bir sekme içeren pencere; her parametre için **Sütun** (operasyon tablosuna
sütun ekle) ve **Gelişmiş** (editörden gizle) işaretlenebilir. (2) Araç çubuğunda
**Gelişmiş** kutusu → kapalıyken editör yalnızca temel (gelişmiş-olmayan) alanları
gösterir; açıkken hepsi görünür (klasik davranış). **Varsayılan: KAPALI = ilk açılışta Temel görünüm.**

### Neden
Çok parametreli programlarda editör çok uzun ve programlar arası fark takibi zor.
Sütunlar operasyonları bir bakışta karşılaştırmayı sağlar; Temel/Gelişmiş nadiren
dokunulan alanları gizler. Endüstri deseni: progressive disclosure + özelleştirilebilir
sütunlar (Fusion/Mastercam).

### Nasıl / nerede
- **Veri modeli** (`params`): `op_view_config` = {op_type: {columns:[...], advanced:[...]}}
  (program başına, .ssp içinde taşınır). `op_view_show_advanced` = global anahtar.
- **`ui/tabs/program_tab.py`:**
  - Modül tabloları: `OP_PARAM_UNIVERSE` (tip başına renderlanabilir tüm parametreler —
    `on_op_select` ile ELLE eşzamanlı tutulmalı), `OP_PARAM_LABELS`, `GROUP_DEPS`,
    `SECTION_KEYS`, `_DEFAULT_BASIC/_DEFAULT_COLUMNS`, `_default_cfg()`.
  - Çözücü/görünürlük: `_universe_for` (tilt-arm değilse tilt_* düşer), `_view_cfg`
    (yoksa default), `_hidden_keys` (grup bağımlılıklarını genişletir),
    `_apply_field_visibility` (ileri alanları + boş kalan bölüm başlıklarını gizler —
    değerlere dokunmaz), `_add_section_header`.
  - Sütunlar: `rebuild_tree_columns` (base + union), `refresh_ops_tree` genişletildi,
    `_cell_value` (uygulanamayan tip → "—"), `_column_union`.
  - Alan satırları `_pkey` ile etiketlendi (helper'lar + inline blok'lar), bölüm
    başlıkları `_section` ile.
  - Araç çubuğu: "Özelleştir…" + "Gelişmiş" kutusu.
- **`ui/dialogs/view_customizer.py`** (YENİ): sekmeli diyalog, Uygula/Sıfırla/Kapat.
- **`main.py` `load_project`:** global Gelişmiş anahtarı korunur; .ssp'de
  `op_view_config` yoksa bayat bellek temizlenir (default'a düşer).
- **`i18n.py`:** yeni EN/TR/ES anahtarları.
- **`help_window.py`:** Operasyonlar sekmesine "GÖRÜNÜMÜ ÖZELLEŞTİRME" bölümü (EN+TR).

### Güvenlik / geri alma
Tamamen görünüm-katmanı: gizli alanın değeri ve takım yolu DEĞİŞMEZ. Path generator'a
dokunulmadı. Geri almak için `params`'tan `op_view_config`/`op_view_show_advanced`
silinebilir; kod eski davranışa (hepsi görünür) düşer.

### Durum
Headless mantık testleri (9/9) GEÇTİ, tüm dosyalar derleniyor. GUI kullanıcı
tarafından ONAYLANDI (2026-07-04, "güzel görünüyor"). Commit HÂLÂ EDİLMEDİ
(kullanıcı onayı bekliyor). TODO #59.

---

## 2026-07-04 — Kalibrasyon "Challenger Rr" (eksen-fit erişim) — SADECE OPT-IN TEST

### Ne (kısa)
Kalibrasyon penceresine, mevcut hesabı DEĞİŞTİRMEDEN, alternatif bir takım erişim
değeri (`r_tool`) gösteren bir "challenger" eklendi. Amaç: farklı takımla kalibre
edip başka takımla çalışınca kalan ~1 mm boşluğun kaynağını FİZİKSEL test etmek.

### Neden (sorunun kökü)
Mevcut `get_contact_radius` = `max|XZ|/2` (kiriş/2). Disk eğik olduğu için "en uzak
nokta" ~45° sapıyor; bu ölçüm disk yarıçapı ile eğimi karıştırıyor ve takımdan
takıma ~0.5–1 mm farklı çıkıyor. Bir takımla kalibre edip diğerini çalıştırınca bu
tutarsızlık = gördüğün kalan boşluk. Challenger, diskin dönme eksenini fit edip o
eksene göre maks jant yarıçapını döndürür (eğimden bağımsız).

### Doğrulanan sayılar (headless, spinning_cam env)
| Takım | Mevcut (kiriş/2) | Challenger (eksen) |
|-------|------------------|--------------------|
| T0101 | 73.793 | 74.908 |
| T0102 | 77.528 | 77.528 |
| T0103 | 74.308 | 74.905 |

KRİTİK: göreli erişim. Mevcut: T0103−T0101 = **+0.52 mm** (103'e fazla erişim →
101 ile kalibre edilince 103 boşluk bırakıyor). Challenger: T0103−T0101 = **≈0.00 mm**
(iki disk aynı erişim). Hipotez: challenger ile boşluk ~0'a iner. FİZİKSEL TEST BEKLİYOR.

### Nerede (dosya:değişiklik)
1. **`tool_step_loader.py`** ~189: YENİ `get_contact_radius_axis()` metodu. Mevcut
   `get_contact_radius` BYTE-BYTE AYNI, hiç dokunulmadı. Yeni metot yalnızca
   diyalog ekranından çağrılıyor; path-gen / tool_manager hâlâ eskisini kullanıyor.
2. **`ui/dialogs/touch_calibration.py`**:
   - Rr satırının altına salt-okunur "Challenger Rr (axis)" etiketi + Δ + "Use ▸" düğmesi.
   - `_refresh_challenger(tool)`: seçili takım için challenger değerini hesaplar/gösterir.
   - `_use_challenger_rt()`: değeri SADECE diyalogdaki editable Rr alanına yazar.
   - `_on_tool_selected` ve `_load_last_session` bu etiketi tazeler.

### GÜVENLİK — DOĞRULANDI (kullanıcı bunu özellikle sordu)
- "Use ▸" düğmesi HİÇBİR takım değerini KAYDETMEZ. Yalnızca diyalogdaki Rr alanını
  doldurur. `tools.json` bu diyalogda ASLA yazılmaz (yalnızca satır 199'da okunur).
- Diyalogdaki iki `json.dump` da **settings.json**'a yazar (calibration_last_session
  ve calibration_view) — takım kütüphanesine değil.
- 5 Apply düğmesi yalnızca home_x / mandrel_pos_x_offset / final_part_thickness /
  home_z / machine_gcode_offset_z yazar. HİÇBİRİ r_tool'a dokunmaz. Yani challenger
  ile kalibre edip Apply'a bassan bile T0101/T0103 tools.json değerleri (73.79/74.31)
  DEĞİŞMEZ; sadece home_x gibi kalibrasyon çıktıları değişir.
- `get_contact_radius_axis` sadece okur (STEP mesh), hiçbir dosya/parametre yazmaz.

### Geri alma
Tek yaptığı ekleme; kaldırmak için `tool_step_loader.py`'deki yeni metodu ve
`touch_calibration.py`'deki challenger satır/metotlarını sil. Mevcut davranış aynen döner.

### Test prosedürü (yarın için)
1. T0101 seç → "Use ▸" (Rr→74.91) → gerçek dokunma DRO gir → Calculate → home_x Apply.
2. T0103 seç → "Use ▸" (Rr→74.91) → onun gerçek DRO'sunu gir → Calculate.
3. Delta X'e bak: ~0 → challenger kazandı (tools.json'a taşı). Hâlâ ~1 mm → eksen-fit
   yetmiyor, sıradaki adım eğim-projeksiyonlu erişim.

### Bekleyen
Fiziksel A/B testi (kullanıcı). Kazanırsa: `tools.json` r_tool'ları güncelle +
opsiyonel olarak path-gen'i bayrakla challenger'a çevir. Bkz. TODO #56.

---

## 2026-07-04 — Kademeli Uzunluk (progressive reach): pas başına P3 çıkış stroku

### Ne
Kaba operasyonlarda, mevcut **Kademeli Açı** yelpazesinin yanında yeni bir
opt-in **Kademeli Uzunluk** seçeneği. Açı P3 çıkışının *yönünü* paslar boyunca
çevirirken, uzunluk P3 çıkış kolunun *uzunluğunu* (L3 = √(P3x²+P3z²)) mevcut
değerden **Uzunluk Bitiş (mm)** değerine lineer interpolasyonla değiştirir.
İlk pas mevcut uzunluğu korur (interp ağırlığı 0), son pas bitiş değerine ulaşır.

İkisi diktir ve birlikte çalışır: P3 kutupsal formda (uzunluk × yön) üretildiği
için açı yönü, uzunluk uzunluğu ayarlar — çakışma yok. Mandrel yukarı çıktıkça
kalan flanş küçülür; uzunluğu kısaltmak çıkışı blank kenarına yakın tutar
(malzeme modeli gerekmez, gözle ayarla).

**Bağımlılık (kafa karışıklığı noktası):** Reach, **Pass Angle DEĞERİ girili** iken
çalışır — Progressive Angle *fan checkbox*'ına bağlı DEĞİL. Fan kapalı + reach açık
geçerli (yön sabit, uzunluk küçülür). Pass Angle BOŞ ise P3 ham (p3_x, p3_z) offset
olarak kullanılır ve `_L3` hiç hesaplanmaz → progress edecek "uzunluk" yok; bu yüzden
reach o modda devre dışıdır. Saf P3 X/Z modunda reach (Pass Angle kapalı) kullanıcı
kararıyla ERTELENDİ (2026-07-04) — gerekirse p3_x/p3_z orantılı küçültme ile eklenir.

### Nerede
1. **`path_generator.py`** ~265: `_L3` hesabından hemen sonra, `progressive_reach_enabled`
   açıksa ve `count > 1` iken `_L3 = max(_L3 + i*(reach_end - _L3)/(count-1), 0.0)`.
   Sadece `pass_angle` tanımlıysa çalışır (blok o koşulun içinde). Trig (cos/sin θ_B)
   bu güncellenmiş `_L3`'ü kullanır.
2. **`ui/tabs/program_tab.py`**: defaults sözlüğüne `progressive_reach_end: 30`;
   Kademeli Açı satırının altına (aynı `pass_angle is not None and count > 1` guard)
   `progressive_reach_enabled` checkbox + açıkken `progressive_reach_end` alanı.
3. **`i18n.py`**: `lbl_progressive_reach`, `lbl_reach_end` (EN/TR/ES).
4. **`ui/dialogs/help_window.py`**: `ops` bölümüne "PROGRESSIVE ANGLE & REACH" /
   "KADEMELİ AÇI VE UZUNLUK" paragrafı (EN+TR).

### Test
`_test_progressive_reach.py` — 3 kontrol GEÇTİ: (1) reach_end == mevcut reach → sıfır
değişim; (2) daha küçük reach_end sadece son pasları kısaltır, ilk pas dokunulmaz;
(3) reach, açı yelpazesinden bağımsız çalışır. Log doğrulaması: reach_end=10 ile
reach 44.7 → 33.2 → 21.6 → 10.0 lineer iniyor, yön θ_B=30° sabit.

### Geri alma
`path_generator.py` insert bloğunu, `program_tab.py` checkbox+alan bloğunu ve
defaults satırını, i18n 2 satırını, help paragraflarını sil. Eski reçeteler
etkilenmez (varsayılan `enabled=False` → sıfır davranış değişimi).

### Durum
Headless doğrulandı; derleme OK. Gerçek pencere GUI smoke test BEKLİYOR
(checkbox'ın Pas Açısı ayarlıyken göründüğü ve alanı açıp/kapadığı doğrulanmalı);
commit EDİLMEDİ.

---

## 2026-07-04 — Giriş alanlarında soluk "varsayılan + aralık" ipucu (tüm sekmeler)

### Ne
Her sayısal giriş alanının yanında, soluk gri küçük bir metin: alanın
**fabrika varsayılanı** ve (Process/Machine için) **değiştirilebilir aralığı**.
Kullanıcı boş bıraktığında hangi değerin geçerli olacağını ve hangi yöne
değiştirebileceğini kutuyu doldurmadan görebiliyor. Örn: `varsayılan 2  ·  0 - 20`.

### Ne değişti
1. **`main.py`** — `load_settings()`, kullanıcının `settings.json`'u ile birleşmeden
   ÖNCE saf varsayılanları `self.factory_defaults`'a kopyalıyor (ipucu buradan okur).
   Ayrıca `collision_resolution` (0.5) ve `exit_arc_angle` (0.0) defaults dict'e
   eklendi — önceden yoktular, bu yüzden Process sekmesinde sadece aralık görünüyordu.
2. **`ui/helpers_ui.py`** — `_fmt_num()` yardımcı + `_field_hint_text()` /
   `_add_field_hint()`. `add_spinbox` ve `add_scale` ipucu etiketini **başlık
   satırının sağına** yerleştiriyor (alta DEĞİL — düzeni aşağı kaydırmaz).
   Latin-5-güvenli karakterler (cp1254 konsol sorunu olmasın); egzotik glif yok.
   Stil sabitleri: `HINT_COLOR`, `HINT_FONT`.
3. **`i18n.py`** — `hint_default` anahtarı (EN "default" / TR "varsayılan" / ES "predet.").
4. **`ui/tabs/program_tab.py`** — op alanları paylaşılan helper'ı kullanmıyor;
   modül düzeyinde **`OP_PARAM_DEFAULTS`** tablosu (defaults `path_generator.py`
   fallback'lerinden BİREBİR alındı → davranışla asla çelişmez). `_add_prop_entry`
   ipucu etiketini **en sağa** koyar (entry genişliği korunur). Sabit defaults +
   değişken defaults (`= P1 X`, `= Feed`, `= mandrel top`, `= center + 50`),
   `pass_angle` → `off`. Op tipine bağlı `clearance` için `_add_prop_entry`'ye
   opsiyonel `default_hint` argümanı eklendi (roughing `= target clr`,
   finishing `= allow.+safety`).

### Kapsam
- Process/Machine spinbox+scale: 12/12 alan (default + aralık).
- Program op alanları: 30/31 alan. TEK istisna `exit_curve_tension` — path
  generation'dan KALDIRILMIŞ (ölü alan), dürüst bir varsayılanı yok → ipuçsuz.
  (İleride gizlenebilir; bu oturumun kapsamı dışında.)
- Machine sekmesindeki KENDİ entry widget'larıyla kurulan alanlar kapsam dışı
  (kullanıcı özellikle Program tab istedi).

### Doğrulama
`py_compile` OK (main.py, helpers_ui.py, i18n.py, program_tab.py). İpucu metin
üretimi headless doğrulandı + kapsam denetim script'i (kaynaktan tüm alan
anahtarlarını çıkarıp tablolarla diff — 2 eksik Process anahtarı böyle bulundu).
GERÇEK PENCERE GUI smoke testi BEKLİYOR: dar panelde en-sağ ipucunun sıkışıp
sıkışmadığını göz kontrolü. Commit EDİLMEDİ.

### Bekleyen
- `help_window.py` `_C` dict + (gerekirse) CODE_NAVIGATION.md bu özellik için
  GÜNCELLENMEDİ (help-window politikası gereği güncellenmeli).
- İsteğe bağlı: ipucu için Aç/Kapat ayarı (şimdilik daima açık).

### Geri alma
`main.py`: `self.factory_defaults` satırı + iki yeni default anahtarı sil.
`helpers_ui.py`: `_add_field_hint` çağrılarını ve yardımcıları kaldır.
`program_tab.py`: `OP_PARAM_DEFAULTS`, import, `_add_prop_entry` ipucu bloğu +
`default_hint` argümanı ve iki `clearance` çağrısındaki `default_hint=` sil.
`i18n.py`: `hint_default` anahtarı sil.

---

## 2026-07-04 — Operasyon silince ikinci set varsayılana dönüyor fix (Program tab)

### Sorun
İki (veya daha fazla) kaba/bitirme seti oluşturulup ikincisi varsayılandan
üretilip düzenlendikten sonra, **ilk set silinince ikinci set varsayılan
değerlere geri dönüyordu** (yaptığın düzenlemeler kayboluyordu).

### Kök neden
Özellik editöründeki her giriş alanının `save` closure'ı ve widget
`<FocusOut>`/`<Return>` binding'i, operasyona **pozisyonel index** ile yazar
(`operations[op_idx][key] = ...`, `program_tab.py:1194`). Bu closure'lar
`self._active_entry_savers` içinde toplanır ve bir sonraki etkileşimde
`_flush_entries()` ile tekrar oynatılır.

`del_op()` operasyonu `pop` ediyor ama **`_active_entry_savers`'ı temizlemiyor
ve editör widget'larını yok etmiyordu**. Silinen op0 (çoğu zaman hâlâ ekranda
duran varsayılan set) için kayıtlı bayat saver'lar index `0`'a bağlı kalıyor
ve op0'ın widget değerlerini tutuyordu. Sıradaki `_flush_entries()` (kalan op'a
tıklayınca ya da bir combobox değişince) bu bayat varsayılan değerleri
`operations[0]`'a — artık senin düzenlediğin ikinci set olan slota — yazıyordu.

### Ne değişti (`ui/tabs/program_tab.py`)
1. **`del_op()`** — `pop`'tan ÖNCE `_active_entry_savers` temizleniyor,
   `_active_op_idx=None`, ve `f_prop_editor` çocuk widget'ları yok ediliyor
   (bayat index binding'leri de ölür). Sonra `refresh_ops_tree` + o index'e
   gelen op için editör `on_op_select(None, _flush=False)` ile yeniden kuruluyor
   (liste boşsa editör temiz bırakılıyor).
2. **`move_op()`** — AYNI kök nedene sahip latent bozulma vardı (swap sonrası
   flush, taşınan op'un widget değerlerini yeni index'e gelen op'un üstüne
   yazardı). Artık önce `_flush_entries()` ile bekleyen düzenlemeler kaydedilir,
   sonra saver'lar temizlenip swap yapılır, yeni seçim için editör yeniden kurulur.

### Doğrulama
`program_tab.py` `ast.parse` ile derlendi (OK). Bu GUI-durum mantığı headless
test paketlerinde kapsanmıyor → GERÇEK PENCERE GUI smoke testi BEKLİYOR:
varsayılan kaba+bitirme oluştur → ikinci (düzenlenmiş) kaba ekle → ilkini sil →
ikinci set düzenlemelerini korumalı. Aynı şekilde ▲/▼ ile sıra değiştir.

### Geri alma
`del_op` ve `move_op`'u eski (kısa) hallerine döndür: saver temizleme /
widget yok etme / yeniden seçim satırlarını sil.

---

## 2026-07-03d — Durum çubuğu (info banner) zıplama/glitch fix

### Sorun
Sürüklenebilir panel (7-03c) sonrası: imleç yan panelde gezinirken alttaki
info çubuğu sürekli boyut değiştiriyor, tıklanmak istenen kontroller zıplıyordu.

### Kök neden
`frame_status` `height=30` ile oluşturulmuş ama **`pack_propagate(False)` YOK** →
gerçek yüksekliği içindeki `lbl_info` metnine bağlıydı. Çok satırlı tooltip'ler
(`\n` içeren) `<Enter>` ile banner'a yazılınca çubuk 2-3 satıra büyüyor, `<Leave>`
ile "Ready…" tek satıra dönünce küçülüyordu. 7-03c'de pack sırası değiştiği için
(status → paned) büyüyen çubuk artık **3D görünümden değil, paned alandan** (yani
yan panelden de) yer çalıyor → kontroller imlecin altında zıplıyor. Bug latent'ti;
yeni layout onu yan panele yönlendirdi.

### Ne değişti
1. `main_window.py` `_setup_layout`: `frame_status.pack_propagate(False)` eklendi —
   yükseklik 30px'e kilitlendi; tooltip metni artık çubuğu büyütemez.
2. `helpers_ui.py` `bind_tooltip`: `flat = " ".join(text.split())` — newline/boşluk
   dizileri tek boşluğa indirgeniyor, sabit yükseklikli çubuk temiz tek satır gösterir.

### Doğrulama
Her iki dosya `ast.parse` ile derlendi. GERÇEK PENCERE GUI smoke testi BEKLİYOR
(imleci yan panelde gezdir → banner sabit kalmalı, kontroller zıplamamalı).

### Bilinen ikincil konu (bu fix kapsamı DIŞINDA)
`program_tab.py:406` `txt_pass_info` (contact zone/pas bilgisi) `height=10` ister ama
`fill="both", expand=True` → dar pencerede istenen yüksekliğin altına sıkışabilir.
Banner artık şişmediği için daha az belirgin; gerekirse takip: Text'e minsize.

### Geri alma
`main_window.py`'den `frame_status.pack_propagate(False)` satırını sil;
`helpers_ui.py` `bind_tooltip` içinde `flat` yerine tekrar ham `text` kullan.

---

## 2026-07-03c — Sürüklenebilir panel ayırıcı + yelpaze bitiş açısı + TODO #54/#55

### Ne değişti (kullanıcı istekleri)
1. **Yan panel genişliği ayarlanabilir** — `main_window.py` `_setup_layout`:
   sabit `width=350` sidebar yerine `tk.PanedWindow` (yatay, 6px sash).
   Ayırıcı sürüklenince panel VE 3D görünüm yeniden boyutlanır; embedded
   PyVista zaten `plot_frame <Configure>` → `MoveWindow` ile takip ediyordu,
   yani mekanizma güvenli (programı bozmaz). Genişlik `params["sidebar_width"]`
   olarak sash bırakılınca settings.json'a kaydedilir; min panel 280px,
   min 3D 300px. NOT: durum çubuğu artık tam genişlik (pack sırası değişti).
   Bu, "▼ düğmesini göremiyorum" şikayetini kökten çözer.
2. **Yelpaze bitiş açısı (`progressive_angle_end`)** — `path_generator.py`
   ~255: kademeli açı artık sabit 180° yerine op'un
   `progressive_angle_end` değerine (varsayılan 180) doğru interpolasyon:
   `_eff_angle += i*(end−_eff_angle)/(count−1)`. Boş/None → 180 (eski davranış,
   mevcut reçeteler birebir aynı). Op editöründe "Yelpaze Bitiş Açısı" alanı
   (yalnızca Kademeli işaretliyken görünür; checkbox toggle artık editörü
   yeniden çizer). Önerici 180.0'ı açıkça yazar; öneri önizlemesi
   "X° → end°" gösterir. Doğrulama: end=120 ile son pas θ_B 128.7°→68.7°,
   ilk pas değişmedi (e2e assert).
3. **TODO.md #54/#55 eklendi** — önerici yol haritası: #54 daha fazla
   parametre önerisi (zones, contact feed, reverse, tilt, çok kademeli) +
   her birine WHY satırı; #55 daha isabetli öneri için ek girdiler
   (temper, tolerans, rijitlik, tavlama imkânı, rulo profili, adet).

### Doğrulama
Tüm 4 test paketi GEÇTİ (`_test_planner.py` 37 kontrol, dialog, e2e + yelpaze
bitiş açısı ve pasifleştirme, toolbar). `main_window.py` derlendi; PanedWindow
gerçek pencere GUI smoke testi BEKLİYOR.

### Geri alma
`main_window.py` `_setup_layout` sidebar/plot_frame packing'i eski haline
(sabit 350px); `path_generator.py` 180.0 sabitine; `program_tab.py`
`progressive_angle_end` alanı + `on_op_select` çağrısı; `i18n.py`
`lbl_progressive_end`; TODO #54/#55 blokları.

---

## 2026-07-03b — Önerici v2 (kullanıcı geri bildirimi): toolbar düzeni, On/Off, WHY bölümü

### Ne değişti (kullanıcı istekleri)
1. **Program sekmesi toolbar sadeleştirildi** — 4 ayrı "+ Kaba/+ Bitirme/+ Kes/+ Kıv"
   düğmesi yerine tek **"+ Ekle ▾" Menubutton** (op tipleri adapter'dan menüye).
   ✨Öner artık açık sarı `tk.Button` (görünürlük şikayeti üzerine).
2. **Operasyon pasifleştirme (silmeden karşılaştırma)** — tree'ye "Aktif" sütunu
   (✓/—), pasif satırlar gri (`op_disabled` tag). Yeni **Aç/Kapat** düğmesi +
   satıra **çift tıklama** toggle eder (`toggle_op_enabled`,
   `_on_tree_double_click`). `enabled=False` zaten calculate_paths/generate_gcode
   tarafından atlanıyordu — sadece UI eksikti. Toggle sonrası `_schedule_auto_calc()`.
3. **Öneri diyaloğu**: buton çubuğu `side="bottom"` ile ÖNCE pack ediliyor →
   pencere küçültülünce ekleme düğmesi asla kırpılmaz. Etiket netleştirildi:
   **"➕ Yeni operasyon olarak ekle"** (yeşilimsi tk.Button).
4. **Önerici daha fazla parametre öneriyor** — `direction: "forward"` (açık),
   `back_pass_enabled`: duvar açısı > 45° (BACK_PASS_BEND_THRESHOLD_DEG) ise
   AÇIK (kırışma riski, ütüleme), değilse açıkça False; `back_pass_feed` =
   kaba besleme, arc'lar 0.
5. **"BU DEĞERLER NEDEN BÖYLE" bölümü** — planner artık `notes` listesi döner
   (i18n `sug_note_*`, 8 satır): paso sayısı formülü, paso açısı yelpazesi,
   RPM hesabı, mm/dev→mm/dak, sac çapı alan korunumu, clearance mantığı,
   geri pas kararı (açık/kapalı gerekçesiyle), bitirme pası notu.
   Önizlemede gri (dim) satırlar olarak gösterilir.

### Doğrulama
- `_test_planner.py` 36 kontrol (yeni: back pass eşiği, direction, not anahtarları
  + EN/TR/ES template'lerin kwargs ile format edilebilirliği). GEÇTİ.
- `_test_suggester_dialog.py`: WHY bölümü render + buton çubuğu bottom-anchored. GEÇTİ.
- `_test_planner_e2e.py`: geri paslı 7 yol → 489 satır G-code (PLC<1000);
  op `enabled=False` yapılınca yolları düşüyor (karşılaştırma iş akışı). GEÇTİ.
- `_test_program_tab_toolbar.py` (YENİ): MagicMock app ile gerçek ProgramTab —
  Aktif sütunu, toggle, çift-tık, dropdown 4 tip, Öner düğmesi. GEÇTİ.
- Gerçek pencere GUI smoke test HÂLÂ BEKLİYOR.

### Geri alma
`program_tab.py`: `_create_widgets` toolbar bloğu + `toggle_op_enabled`/
`_on_tree_double_click` + tree cols eski haline; `process_planner.py`:
`BACK_PASS_BEND_THRESHOLD_DEG`, notes, direction/back_pass alanları çıkar;
`op_suggester.py`: pack sırası + WHY bölümü; `i18n.py`: `btn_add_op`,
`btn_toggle_op`, `col_on`, `sug_i_backpass/on/off`, `sug_h_why`, `sug_note_*`.

---

## 2026-07-03 — Operasyon Önerici (✨Öner): kural-tabanlı otomatik operasyon önerisi

### Ne değişti
Operatör know-how eksikliğinde başlangıç noktası vermek için Program sekmesine
tavsiye niteliğinde (advisory, opt-in) operasyon önerici eklendi. Hiçbir şey
otomatik uygulanmaz — öneri önizlenir, kullanıcı Uygula'ya basarsa eklenir.

1. **`process_planner.py` (YENİ)** — kural-tabanlı planlayıcı:
   - `analyze_profile(mandrel_mgr)`: profil önbelleğinden yükseklik, Ø maks/min,
     maks duvar açısı (radyal düzlemden; düz sac=0°, silindir=90°), yüzey
     uzunluğu, alan-eşdeğeri sac yarıçapı (`πR² = πr_min² + 2π∫r ds`).
   - `suggest_operations(...)`: 1 kaba op (count = ceil(bükme_açısı /
     malzeme_açı_per_paso), maks 12; `pass_angle` = −θ_A + açı_per_paso,
     `progressive_angle_enabled=True` → yelpaze 180°'ye yayılır) + 1 bitirme op.
     RPM = yüzey hızı / (π·Ø_maks), makine `max_spin_rpm` ve PLC 2550 ile
     kırpılır; besleme = mm/dev × RPM, PLC 3000 mm/dak ile kırpılır.
     Takım seçimi `add_op` ile aynı semantik (kalibre `r_tool` explicit-None,
     yoksa `radius`). Sıvama oranı β = Ø_sac / Ø_mandrel_MAJÖR (uç değil!).
   - Uyarılar (key, kwargs) çifti döner → i18n `sug_warn_*` anahtarları:
     oran aşımı, RPM/besleme kırpma, çalışma alanı X, STEP yok, >12 paso.
2. **`materials.json` (YENİ, ilk kullanımda otomatik oluşur)** — 6 malzemelik
   sezgisel tablo (Al yumuşak/5xxx, DC04, 304, bakır, pirinç): açı/paso,
   yüzey hızı, mm/dev kaba+bitirme, maks sıvama oranı, clearance'lar.
   TÜM sabitler burada — saha deneyimiyle kod değişikliği olmadan ayarlanır.
   Dosya yoksa `DEFAULT_MATERIALS` gömülü tablo kullanılır (tek-exe paketleme).
3. **`ui/dialogs/op_suggester.py` (YENİ)** — `OpSuggesterDialog`: malzeme
   combobox, sac kalınlığı (params'tan ön dolu) + sac çapı (alan-eşdeğeri
   tahminle ön dolu) girişleri, önizleme (analiz + op listesi + uyarılar),
   Uygula onay sorusu ile ekler. Kalınlık değiştirildiyse Uygula
   `on_param_change("final_part_thickness_on_mandrel", …)` üzerinden geçirir
   (önizlemede uyarı satırı gösterilir).
4. **`ui/tabs/program_tab.py`** — Tools düğmesinden sonra `✨Öner` düğmesi
   (adapter `roughing`+`finishing` destekliyorsa; her iki mevcut adapter de
   destekler). `open_op_suggester()` + `_apply_suggested_ops()` eklendi.
5. **`i18n.py`** — `btn_suggest_ops` + `sug_*` anahtarları (EN/TR/ES).
6. **`ui/dialogs/help_window.py`** — ops bölümüne "Operation Suggester"
   alt bölümü (EN+TR).

### Doğrulama
- `_test_planner.py`: 27 kontrol — profil analizi (koni: bend 63.4°, Ø tahmin),
  paso sayısı formülü, takım r_tool fallback'i, PLC/makine limit kırpmaları,
  oran/çalışma-alanı/RPM uyarı tetikleri. HEPSİ GEÇTİ.
- `_test_suggester_dialog.py`: widget smoke — önizleme render, malzeme
  değişince yeniden hesap, Apply callback. GEÇTİ.
- `_test_planner_e2e.py`: önerilen op'lar → `calculate_paths` → 4 yol →
  `generate_gcode` → 320 satır (PLC 1000 sınırı altında). GEÇTİ.
- GUI smoke test (gerçek pencerede düğme + diyalog) HENÜZ YAPILMADI.

### Geri alma
`process_planner.py`, `ui/dialogs/op_suggester.py`, `materials.json` sil;
`program_tab.py`'den `btn_suggest` bloğu + iki metodu, `i18n.py`'den `sug_*`
anahtarlarını, help_window'dan iki alt bölümü çıkar. Öneri mekanizması mevcut
hesaplama/yol üretim koduna hiç dokunmaz.

---

## 2026-07-03 — Açılı yüzey boşluk UYARISI (yalnızca bilgilendirme) + T0103 r_tool düzeltmesi

### Ne değişti
2026-07-02 araştırması: skaler r_tool boşluk modeli silindirik yüzeylerde tam,
eğimli yüzeylerde hatalı (radyal dal → dalma riski, normal dal → aşırı boşluk).
Kullanıcı kararı: şimdilik DÜZELTME YOK, sadece uyarı — mevcut mandrel
(18 konik kap) silindire yakın olduğundan uyarı sessiz kalmalı.

1. **`tools.json`** — T0103 `r_tool` 79.5 → **74.31** (saha kanıtı: T0101 ile
   kalibrasyon sonrası T0103 ~5 mm uzak kaldı; 79.5−74.31=5.19 mm birebir
   eşleşiyor; STEP mesh üç bağımsız ölçümle 74.31'i doğruladı).
2. **`tool_step_loader.py` `get_support_table()` (YENİ)** — takım STEP mesh'inden
   destek fonksiyonu δ(θ) tablosu: yüzey normali radyalden θ kadar eğildiğinde
   rulo gövdesinin uç teğet düzlemini ne kadar aştığı. [−89°,+89°], 179 nokta,
   taban düzeltmeli (δ(0)=0), mtime'lı cache, `side<0` açı işaretini aynalar.
3. **`main.py` `check_angled_clearance()` (YENİ)** — SADECE UYARI, yolu asla
   değiştirmez. Her etkin roughing/finishing op'un Z aralığını 120 noktada
   örnekler; model seçimi op'un gerçek dalıyla eşleşir (finishing + conformal
   → normal modeli `r_tool·(1−nx)−δ`; düz roughing → radyal `(blank+clr)·(nx−1)−δ`).
   |sapma| > `angled_clearance_warn_threshold` (varsayılan 0.5 mm) ise
   `logger.warning` + reçete imzası başına BİR popup (headless'ta popup yok).
   Tüm gövde try/except — advisory hesaplamayı asla bozamaz.
   Çağrı yeri: `update_scene`, `calculate_paths`/önbellek dalından hemen sonra.
4. **`i18n.py`** — `angled_clearance_warn_title/intro/legend` (EN/TR/ES).
5. **`help_window.py`** — Sorun Giderme'ye "Boşluk Uyarısı — Açılı Yüzeyler"
   bölümü (EN+TR): + = uzak kalır, − = yaklaşır (dalma riski).

### Geri alma
`update_scene`'deki `self.check_angled_clearance()` satırını sil — özellik
tamamen devre dışı kalır (metotlar ölü kod olarak zararsız). T0103 için eski
değere dönüş: `tools.json` r_tool = 79.5 (ÖNERİLMEZ — saha kanıtıyla yanlış).

### Doğrulama durumu
Headless doğrulandı: mevcut reçetede (silindirimsi mandrel) uyarı SESSİZ,
sentetik açılı senaryoda tetikleniyor. Commit EDİLMEDİ; GUI smoke test bekliyor.
İlk T0103 çalıştırması ~5.2 mm daha yakın gelecek — kuru paso veya geçici
0.5–1 mm clearance ile doğrula.

---

## 2026-07-03 — Interp eğim modu artık Z-bazlı (pas-bazlı değil)

### Ne değişti
"Başlangıç→Bitiş Açısı" (interp) eğim modu her pasın kendi içinde yay
uzunluğuna göre başlangıç→bitiş açısı tarıyordu. Kullanıcı tespiti: yüzey tek
pas içinde değişmez — açı pas ilerlemesine değil YÜZEY KONUMUNA bağlı olmalı.
Çok paslı kaba operasyonda eski model her pasta açıyı ileri-geri salındırıyordu.

1. **`path_generator.py` `_compute_tilt_for_path`** — interp artık Z-bazlı:
   `frac = clip((z − start_z)/(end_z − start_z), 0, 1)`,
   `tilt = tilt_start + frac·(tilt_end − tilt_start)`. `tilt_start` op'un
   Başlangıç Z'sinde, `tilt_end` Bitiş Z'sinde geçerli; bölge dışı kırpılır.
   `reverse` parametresi ve geri-pas uç-ters-çevirme mekanizması KALDIRILDI —
   Z-bazlı model yön-bağımsız (aynı Z her pasta/yönde aynı açı).
2. **`i18n.py`** — `lbl_tilt_start/end` → "Tilt @ Start Z (°)" / "Tilt @ End Z (°)"
   (TR "Eğim @ Başlangıç Z (°)" / "Eğim @ Bitiş Z (°)", ES karşılıkları).
3. **`program_tab.py`** — tilt mode combobox + tilt_start/end tooltip'leri
   yeni semantiğe göre; geri-pas cümlesi silindi.
4. **`help_window.py`** — ID112 interp maddesi EN+TR Z-bazlı anlatıma çevrildi.
5. **`CODE_NAVIGATION.md` §19** — yay-uzunluğu ve geri-pas cümleleri güncellendi.

Normal mod (yüzey normali) DEĞİŞMEDİ. ID111 etkilenmez (kin-gated).

### Geri alma
`_compute_tilt_for_path` interp dalını eski yay-uzunluğu koduna döndür +
`reverse` parametresini ve `generate_gcode` geri-pas çağrısındaki
`reverse=True`'yu geri koy (git: f48cd7e'deki hali).

### Doğrulama durumu
Headless doğrulandı (derleme + ID112 interp kontrol scripti + ID111 regresyon).
GUI smoke test bekliyor.

---

## 2026-07-02e — "Velocity Colors" artık temas bölgesi bandı gösteriyor

### Ne değişti
Eski "Velocity Colors" özelliği her pası nominal beslemeye göre TEK düz renkle
boyuyordu — zone/temas beslemesini yok sayıyor, üstelik hepsi tek besleme olunca
her şey sarı oluyordu (yanıltıcı). Kullanıcı isteği: pasların rengine DOKUNMADAN,
temas bölgesini 3D'de göstermek.

1. **`main.py` §2.5 (YENİ blok)** — `velocity_color_mode` açıkken mandrel
   etrafına soluk yarı saydam kırmızı bir "temas bölgesi bandı" çizilir.
   Bant yarıçapı = `yüzey + blank + shell + r_tool + contact_zone_mm` (rulo
   merkezinin temas bölgesine girdiği dış sınır). `generate_shell_mesh` yeniden
   kullanılır. Op başına bir bant (aynı kalınlıklar dedup). Yalnızca
   `contact_zone_mm > 0` olan etkin op'lar için. `actors["contact_bands"]`.
   Salt-görsel: yol üretimine/G-code'a DOKUNMAZ.
2. **`main.py` pas render** — eski düz `velocity_mode` renklendirme dalı
   KALDIRILDI; paslar artık her zaman tür renklerini korur (mavi/turuncu/teal).
   Ölü `op_feeds`/`min_feed`/`max_feed`/`velocity_mode` temizlendi (`op_types`
   korundu — hâlâ tür rengi için kullanılıyor).
3. **`main.py` `recolor_paths`** — velocity modunda erken `return` kaldırıldı
   (artık pas renkleri velocity modundan bağımsız normal boyanıyor).
4. **`process_tab.py`** — checkbox tooltip yeni davranışa göre güncellendi.
5. **`help_window.py`** — GÖRSEL ANALİZ KATMANLARI'na "Velocity Colors /
   Hız Renkleri" girişi (EN+TR).

### Geri alma
`main.py` §2.5 bloğunu ve tooltip/help girişlerini kaldır; eski velocity
renklendirme dalını geri koy. Temas bölgesi bandı tamamen `velocity_color_mode`
bayrağına bağlı — kapalıyken hiçbir aktör eklenmez.

### Doğrulama durumu
Kod düzenlendi; GUI smoke test bekliyor (checkbox aç/kapa → bant beliriyor/
kayboluyor, pas renkleri değişmiyor). Commit EDİLMEDİ.

---

## 2026-07-02d — Faz 1: ID112 döner kol (B ekseni) kinematiği

### Ne değişti
TODO #50 tamamlandı. ID112'nin X kızağı döner kol üzerinde — nokta başına eğim
(B) hesaplanıyor, görselleştiriliyor ve çıktıya yazılıyor. ID111 çıktısı
bayt-bayt AYNI (regresyonla doğrulandı).

1. **`kinematics.py` (YENİ)** — `TiltArmKinematics`: forward/inverse
   (uç XZ ⇄ B, X_kol, Z_araba), yan-farkında (`roller_positive_x_side`),
   `clamp_tilt`, `tilt_to_b`, `check_reachable` (B limit, cos≈0 tekilliği,
   x_arm<0). Fabrika: `get_kinematics(params)` → tilt_arm değilse None.
   Konvansiyon: θ=0° radyal kızak; `B = θ·sign + home`.
2. **Profil anahtarları** — `tilt_pivot_x/z`, `tilt_b_min/max/home/sign` →
   `MACHINE_PROFILE_KEYS` + `MachineProfileSchema` + `ID112-1.json`
   (çizim gelene kadar geçici değerler).
3. **`path_generator.py`** — `last_tilt_angles` (yol başına eğim dizisi;
   `_path_op_map` ile op eşlemesi; back pass'larda interp uçları ters).
   `_compute_tilt_for_path()`: `normal` modda yüzey normali + `tilt_offset`,
   `interp` modda yay-uzunluğu oranıyla `tilt_start`→`tilt_end`. Geometriden
   deterministik → PLC decimation alt kümesinde aynı sonuç. `generate_gcode`:
   her G1 + pas-başı G0'a ` B{deg}` kelimesi (konumlama rapidleri son B'yi
   tutar); `check_reachable` → `last_kinematic_warnings` + log.
4. **Görselleştirme** — `tool_step_loader._position_mesh(tilt_deg=)` (uçta
   rotate_y), `main.py` statik rulo eğimi + `update_roller_visual`
   SetOrientation (sıfır-alokasyon), `simulation_controller.current_tilt`,
   canlı monitörde ` B{deg}`.
5. **UI** — op editörde tilt_arm makinede "Eğim Modu (B)" combobox +
   `tilt_offset` / `tilt_start`+`tilt_end` alanları (moda göre);
   pas bilgisinde pas başına "Tilt → B: başlangıç → bitiş" satırı (operatör
   referansı); makine sekmesinde "Döner Kol (B Ekseni)" bölümü (`"tilt_arm"`
   section_frames'te, 111'de gizli); PDF'te pas başına B tablosu
   (`export_pdf(tilt_angles=)`); i18n EN/TR/ES; help window EN/TR.

### Bekleyen kararlar (TODO #50 açık sorular)
Kol yön işareti (pivotun dışına mı içine mi uzanıyor), gerçek pivot geometrisi,
Delta/Inovance IK sorusu ("user-defined kinematic transformation var mı?").
Ertelenen: temas noktası göçü, eğim-farkında kalibrasyon, gövde çarpışma testi.

### Geri alma
`get_kinematics()` tilt_arm dışında None döner → tüm tilt yolu atlanır; ID111
etkilenmez. Tek dosyayı geri almak için: kinematics.py'yi silme yetmez,
path_generator'daki `from kinematics import get_kinematics` importunu ve
`_b_word` çağrılarını da kaldırmak gerekir.

---

## 2026-07-02c — Makine #2 altyapısı: ID112 hot spinning + adapter katmanı aktif

### Ne değişti
İkinci makine (sıcak sıvama, döner kollu X, CODESYS IPC) için altyapı fazı.
Adapter katmanı artık STUB DEĞİL — UI gerçekten adapter'dan besleniyor:

1. **`machine_adapter.py`** — `HotTiltArmSpinningAdapter` (tip kodu `112`),
   `TYPE_DESCRIPTIONS["112"]`. Yeni yetenek kancaları: `get_export_formats()`,
   `get_kinematics()` ("xz" | "tilt_arm"), `supports_heating()`.
   112 şimdilik op tiplerini ve PathGenerator'ı 111'den miras alır (Faz 0).
2. **`machines/ID112-1.json`** — yeni profil (`kinematics: "tilt_arm"`, plc_mode 0,
   boş custom_commands/mcode_descriptions). ID111-1'e `kinematics: "xz"` eklendi.
3. **`machine_loader.py`** — `MACHINE_PROFILE_KEYS` başına `"kinematics"` eklendi
   (settings.json'a sızmaması için ŞART). `config_schema.py` → şemaya alan eklendi.
4. **`program_tab.py`** (~224) — op ekleme düğmeleri artık
   `active_adapter.get_available_op_types()`'tan geliyor (`_op_buttons` haritası).
   Adapter yoksa (headless) eski dört düğme.
5. **`machine_tab.py`** (`_create_widgets` sonu) — bölümler kurulduktan sonra
   `section_frames` haritası + `get_ui_sections()`'ta olmayanlara `pack_forget()`.
   112'de gizlenen: `plc`, `custom_cmds`, `mcode_desc` (Siemens'e özgü).
6. **`main_window.py`** — `_create_menu`: SCL / Recipe CSV menü öğeleri
   `get_export_formats()`'a bağlı (112'de yok). `_load_machine_profile`: adapter
   farklı PathGenerator sınıfı dönerse swap (şimdilik no-op; isinstance korumalı).
7. **`help_window.py`** — machine bölümüne "MACHINE TYPES / MAKİNE TİPLERİ" bloğu.

### Yol haritası
TODO.md #50 (tilt-arm kinematik), #51 (ısıtma/sıcak proses), #52 (CODESYS
post-processor). Bu fazda ID112 yolları hâlâ XZ düzleminde hesaplanır.

### Geri alma
4/5/6'daki adapter tüketimini kaldırmak yeterli (adapter None korumaları eski
davranışa döner); `machines/ID112-1.json` silinirse makine seçiciden kaybolur.
`"kinematics"`i MACHINE_PROFILE_KEYS'ten çıkarma — settings.json'a sızar.

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
