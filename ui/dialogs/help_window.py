import tkinter as tk
from tkinter import ttk
from i18n import t, get_language

# ── Help content ──────────────────────────────────────────────────────────────
# Stored here (not in i18n.py) because it's long prose, not short UI labels.
# Each section key maps to {"EN": "...", "TR": "..."}.

_C = {
    "start": {
        "EN": """\
WHAT THIS SOFTWARE DOES
════════════════════════════════════════════════════════════════
EMS SoftSpinner is a CAM tool for 2-axis CNC metal spinning. It
generates roller toolpaths that a spinning lathe will follow to
form a blank sheet over a mandrel into the desired shape.


GENERAL WORKFLOW — first time through
════════════════════════════════════════════════════════════════
1.  Load a mandrel model (STEP/STP file)
    The software analyses the profile automatically. You should
    see the mandrel shape appear in the 3D view.

2.  Configure machine settings  (do this once per machine)
    Set the coordinate system, home position, workspace limits,
    and G-code header/footer for your controller.

3.  Perform touch-point calibration
    Tell the software the exact position of the roller tip in
    machine coordinates. This is the most critical step —
    everything else depends on it being correct.

4.  Set blank and material dimensions
    Enter the blank radius and the target wall thickness of the
    finished part.

5.  Add operations
    Build a sequence of passes: roughing to move material,
    finishing to reach final dimensions, cutting or bending
    as needed.

6.  Calculate and inspect
    Press Calculate. Review toolpaths in the 3D view. Use the
    heatmap and distance indicators to check for collisions.

7.  Export
    Save G-code for your controller, or export SCL for TIA
    Portal, or a CSV recipe for documentation.


TIP
════════════════════════════════════════════════════════════════
Hover over any field or button to see a tooltip describing what
it does and what values are typical.
""",
        "TR": """\
BU YAZILIM NE YAPAR
════════════════════════════════════════════════════════════════
EMS SoftSpinner, 2 eksenli CNC metal sıvama için bir CAM
aracıdır. CNC sıvama tezgahının bir mandrel üzerinde blank sacı
istenilen şekle getirmek için izleyeceği rulo yollarını üretir.


GENEL İŞ AKIŞI — ilk kullanım
════════════════════════════════════════════════════════════════
1.  Mandrel modelini yükle (STEP/STP dosyası)
    Yazılım profili otomatik olarak analiz eder. 3D görünümde
    mandrel şeklinin belirmesini görmelisiniz.

2.  Makine ayarlarını yapılandır  (her makine için bir kez yap)
    Koordinat sistemini, home pozisyonunu, çalışma alanı
    sınırlarını ve denetleyiciniz için G-code başlık/altbilgisini
    ayarlayın.

3.  Touch-point kalibrasyonu yap
    Yazılıma rulo ucunun makine koordinatlarındaki tam konumunu
    bildirin. Bu en kritik adımdır — geri kalan her şey bunun
    doğru olmasına bağlıdır.

4.  Blank ve malzeme boyutlarını gir
    Blank yarıçapını ve bitmiş parçanın hedef duvar kalınlığını
    girin.

5.  Operasyon ekle
    Paso dizisi oluştur: malzemeyi hareket ettirmek için kaba,
    son boyutlara ulaşmak için bitirme, gerekirse kesme veya bükme.

6.  Hesapla ve incele
    Hesapla düğmesine bas. 3D görünümde takım yollarını incele.
    Çarpışmaları kontrol etmek için ısı haritasını ve mesafe
    göstergelerini kullan.

7.  Dışa aktar
    Denetleyicin için G-code kaydet, TIA Portal için SCL aktar
    ya da dokümantasyon için CSV reçetesi oluştur.


İPUCU
════════════════════════════════════════════════════════════════
Herhangi bir alan veya düğmenin üzerine gelin; ne yaptığını ve
hangi değerlerin tipik olduğunu açıklayan bir ipucu görünür.
""",
    },

    "view": {
        "EN": """\
NAVIGATING THE 3D VIEW
════════════════════════════════════════════════════════════════
  Rotate       Left-click and drag
  Pan          Middle-click and drag  (or Shift + left-click)
  Zoom         Scroll wheel
  Reset view   Use the preset buttons (Front, ISO, etc.)

If the geometry disappears or gets clipped, use the Fix View
button — it resets the camera clipping range.


WHAT YOU SEE
════════════════════════════════════════════════════════════════
Grey mesh          The mandrel — the form your part is shaped over.

Flat disc          The blank — the starting sheet before forming.

Coloured lines     Toolpaths. Colour = operation type:
                     Blue   = roughing
                     Orange = finishing
                     Green  = cutting
                     Purple = bending
                     Teal   = back pass (return stroke)

Roller shape       The roller at its current position.
                   A small green dot marks the exact tip point.

Transparent box    The machine workspace boundary.


VISUAL ANALYSIS OVERLAYS
════════════════════════════════════════════════════════════════
Heatmap          Colours each path point by distance to the
                 mandrel surface.
                   Blue  = safe clearance
                   Red   = collision or dangerously close

Analysis lines   Short lines from each path point to the mandrel.
                 Useful for spotting where clearance is tight.

Distance labels  The minimum distance from each pass to the mandrel
                 shown as a number. Cyan lines connect to the
                 closest point.

Tip distance     The real-time gap between roller tip and mandrel
                 at the current roller position. Use this to verify
                 calibration looks sensible before running.

Velocity Colors  Draws a faded translucent red band around the
                 mandrel marking the contact zone — where the roller
                 slows to its contact feed. Path segments inside the
                 band run slow; segments outside run fast. It follows
                 the mandrel profile and does not alter the toolpaths.
                 Only appears for operations with a contact zone set.


TIP
════════════════════════════════════════════════════════════════
Turn overlays on selectively — having all of them on at once
makes the view cluttered. Heatmap alone is usually enough for a
quick collision check.
""",
        "TR": """\
3D GÖRÜNÜMDE GEZİNME
════════════════════════════════════════════════════════════════
  Döndür        Sol tıklayıp sürükle
  Kaydır        Orta tıklayıp sürükle  (veya Shift + sol tık)
  Yakınlaştır   Fare tekerleği
  Görünüm sıfırla   Hazır görünüm düğmeleri (Önden, İzometrik vb.)

Geometri kaybolur veya kırpılırsa Görünümü Düzelt düğmesini
kullanın — kamera kırpma aralığını sıfırlar.


NE GÖRÜRSÜNÜZ
════════════════════════════════════════════════════════════════
Gri mesh            Mandrel — parçanın şekillendirildiği form.

Düz disk            Blank — şekillendirmeden önceki başlangıç sacı.

Renkli çizgiler     Takım yolları. Renk = operasyon türü:
                      Mavi        = kaba
                      Turuncu     = bitirme
                      Yeşil       = kesme
                      Mor         = bükme
                      Camgöbeği   = geri pas (dönüş hamlesi)

Rulo şekli          Rulonun mevcut konumu.
                    Küçük yeşil nokta tam uç noktasını gösterir.

Şeffaf kutu         Makinenin çalışma alanı sınırı.


GÖRSEL ANALİZ KATMANLARI
════════════════════════════════════════════════════════════════
Isı haritası       Her yol noktasını mandrel yüzeyine olan
                   mesafeye göre renklendirir.
                     Mavi  = güvenli boşluk
                     Kırmızı = çarpışma veya tehlikeli yakınlık

Analiz çizgileri   Her yol noktasından mandrel'e kısa çizgiler.
                   Boşluğun dar olduğu yerleri tespit etmek için
                   kullanışlıdır.

Mesafe etiketleri  Her pasın mandrele olan minimum mesafesi sayı
                   olarak gösterilir. Camgöbeği çizgiler en yakın
                   noktaya bağlanır.

Uç mesafesi        Mevcut rulo konumunda rulo ucu ile mandrel
                   arasındaki anlık boşluk. Çalıştırmadan önce
                   kalibrasyonun mantıklı göründüğünü doğrulamak
                   için kullanın.

Hız Renkleri       Mandrel etrafında soluk yarı saydam kırmızı bir
                   bant çizer — rulonun temas beslemesine (contact
                   feed) yavaşladığı temas bölgesini işaretler. Bandın
                   içindeki yol kısımları yavaş, dışındakiler hızlı
                   çalışır. Mandrel profilini takip eder ve takım
                   yollarını değiştirmez. Yalnızca temas bölgesi
                   tanımlı operasyonlar için görünür.


İPUCU
════════════════════════════════════════════════════════════════
Katmanları seçerek açın — hepsini aynı anda açmak görünümü
karıştırır. Hızlı bir çarpışma kontrolü için ısı haritası
genellikle yeterlidir.
""",
    },

    "ops": {
        "EN": """\
OPERATION TYPES
════════════════════════════════════════════════════════════════
Roughing       The main forming passes. The roller pushes material
               progressively toward the mandrel over multiple passes.
               Each pass steps slightly closer to the final shape.
               Roughing handles the bulk of material movement.

Finishing      Final surface passes. The roller follows the mandrel
               profile closely, removing the last gap and smoothing
               the surface. Use after roughing is complete.

Cutting        A single pass that scores or cuts the material at a
               fixed radial position.

Bending        A single pass that bends the flange or rim at the
               edge of the part.


HOW MULTIPLE PASSES WORK
════════════════════════════════════════════════════════════════
For roughing: the total approach depth is divided equally among
the pass count. Pass 1 makes the lightest contact; the last pass
reaches the target depth. Increasing the count means smaller
steps — less force per pass, better surface quality, slower cycle.

For finishing: each pass traces the mandrel profile at a defined
standoff. Multiple finishing passes step down that standoff to
zero (the actual part thickness). Use 1–3 finishing passes
depending on the surface quality required.


PASS DIRECTION (FORWARD / REVERSE)
════════════════════════════════════════════════════════════════
Each roughing or finishing operation has a Direction setting.
Forward (default) cuts in the normal direction. Reverse flips the
cut direction of every pass so the roller travels the inverse way
(e.g. tip→root). The path geometry is identical — only the
traversal direction changes. In a multi-pass operation the order
the passes are laid down stays the same; just the cut direction of
each pass is reversed. Reverse and Back Pass can be combined.


BACK PASS (RETURN STROKE)
════════════════════════════════════════════════════════════════
After each forward pass, an optional back pass returns the roller
toward the flange end. This irons out material, improves surface
finish, and reduces wrinkling.

The back pass follows the forward exit curve in reverse. Its
shape can be adjusted independently — a slight outward bow helps
the roller clear material on the return without catching.

Back passes double the number of toolpath lines and increase
cycle time. Use them where surface finish or material control
is critical.


CALCULATE
════════════════════════════════════════════════════════════════
After any change to operations or parameters, press Calculate to
rebuild all toolpaths. The 3D view does not update automatically
(unless Auto-Calculate is on). Always calculate before exporting.
""",
        "TR": """\
OPERASYOn TÜRLERİ
════════════════════════════════════════════════════════════════
Kaba (Roughing)      Ana şekillendirme pasaları. Rulo, malzemeyi
                     birden fazla paso boyunca mandrel'e doğru
                     kademeli olarak iter. Her paso biraz daha yaklaşır.
                     Kaba pasolar malzeme hareketinin büyük bölümünü
                     gerçekleştirir.

Bitirme (Finishing)  Son yüzey pasaları. Rulo, mandrel profilini
                     yakından takip eder, kalan boşluğu kaldırır ve
                     yüzeyi düzeltir. Kaba işlem tamamlandıktan sonra
                     kullanılır.

Kesme (Cutting)      Malzemeyi sabit bir radyal konumda çizen veya
                     kesen tek bir paso.

Bükme (Bending)      Parçanın kenarındaki flanş veya kenarı büken
                     tek bir paso.


ÇOKLU PASOLAR NASIL ÇALIŞIR
════════════════════════════════════════════════════════════════
Kaba için: toplam yaklaşma derinliği paso sayısına eşit bölünür.
1. paso en hafif temaşı yapar; son paso hedef derinliğe ulaşır.
Sayıyı artırmak daha küçük adımlar demektir — paso başına daha az
kuvvet, daha iyi yüzey kalitesi, daha uzun çevrim.

Bitirme için: her paso mandrel profilini belirli bir boşlukta takip
eder. Birden fazla bitirme pasası bu boşluğu sıfıra (gerçek parça
kalınlığına) indirir. Gereken yüzey kalitesine göre 1–3 bitirme
pasası kullanın.


PAS YÖNÜ (İLERİ / TERS)
════════════════════════════════════════════════════════════════
Her kaba veya bitirme operasyonunun bir Yön ayarı vardır. İleri
(varsayılan) normal yönde keser. Ters, her pasın kesim yönünü
çevirir; rulo ters yönde ilerler (örn. uç→kök). Yol geometrisi
aynıdır — yalnızca ilerleme yönü değişir. Çok paslı operasyonda
pasların oluşturulma sırası aynı kalır; sadece her pasın kesim yönü
ters döner. Ters yön ve Geri Pas birlikte kullanılabilir.


GERİ PAS (DÖNÜŞ HAMLESİ)
════════════════════════════════════════════════════════════════
Her ileri pasosundan sonra, isteğe bağlı bir geri pas rulonun
flanş ucuna doğru geri dönmesini sağlar. Bu malzemeyi ütüler,
yüzey kalitesini iyileştirir ve kırışıklığı azaltır.

Geri pas, ileri pasosunun çıkış eğrisini ters yönde takip eder.
Şekli bağımsız olarak ayarlanabilir — hafif dışa doğru bir yay,
rulonun geri dönüşte malzemeye takılmadan geçmesine yardımcı olur.

Geri paslar takım yolu çizgilerini iki katına çıkarır ve çevrim
süresini artırır. Yüzey kalitesi veya malzeme kontrolünün kritik
olduğu yerlerde kullanın.


HESAPLA
════════════════════════════════════════════════════════════════
Operasyonlarda veya parametrelerde herhangi bir değişiklikten sonra
tüm takım yollarını yeniden oluşturmak için Hesapla'ya basın. 3D
görünüm otomatik olarak güncellenmez (Otomatik Hesaplama açık
değilse). Dışa aktarmadan önce her zaman hesaplayın.
""",
    },

    "machine": {
        "EN": """\
MACHINE SETUP — KEY CONCEPTS
════════════════════════════════════════════════════════════════
Coordinate system
  The software works in its own CAM coordinate space. You define
  how that maps to machine coordinates: where the origin is,
  which direction each axis points, and whether to output radius
  or diameter values.

  Get this right first. All exported coordinates depend on it.

Home / Program Start position
  Where the roller goes at the start of the program and returns
  to after each pass. Set this to a position that is safely
  clear of the workpiece, chuck, and tailstock on all axes.
  Too close = crash risk. Too far = wasted cycle time.

Retract distances
  After each pass, the roller steps back by the retract amount
  before returning home. This prevents the roller from dragging
  across the part on the repositioning move.

Workspace limits
  Define the physical travel range of your machine. These are
  used to draw the workspace box in the 3D view as a visual
  reference. The software does not currently enforce hard limits
  — it is your responsibility to check that paths stay inside.

Roller approach side
  Whether the roller approaches from the positive or negative X
  side of the mandrel axis. Changing this mirrors all path
  coordinates. Set it to match your machine's physical layout.

Saving machine settings
  All fields on this tab (home, retract, offsets, workspace,
  G-code output, …) belong to the active machine profile. They
  are auto-saved to that profile as soon as you change them, so
  your edits survive a restart. The "Save Machine Profile" button
  at the top-right does the same thing on demand.


MACHINE TYPES
════════════════════════════════════════════════════════════════
The machine you selected at startup (license window) decides what
this software shows:

ID111 — Spinning Lathe (cold, two-axis)
  Full feature set including the Siemens PLC sections (PLC mode,
  custom commands, M-code table) and SCL / Recipe CSV export.

ID112 — Hot Spinning Lathe (tilt-arm)
  Hot spinning machine with the X slide on a rotary arm and a
  CODESYS-based controller. The Siemens-specific sections and
  SCL export are hidden for this machine.

  Tilt-arm (B axis) kinematics:
  - Machine tab gains a "Tilt Arm (B Axis)" section: pivot X/Z,
    B min/max limits, B home and B sign. These are placeholder
    values until the machine drawings arrive.
  - Each roughing/finishing operation gains a "Tilt Mode (B)"
    selector: "Surface Normal" makes the roller follow the
    mandrel surface normal (plus an optional Tilt Offset
    lead/lag angle); "Start→End Angle" interpolates linearly
    between an operator-entered start and end angle over the
    pass. Tilt is clamped to the B limits; violations are
    reported as kinematic warnings in the log.
  - B = 0° means the slide is purely radial (same posture as
    machine ID111); positive B leans the tool toward +Z.
  - G-code output carries a B word on every cutting move; the
    pass info panel and the PDF operation sheet show each
    pass's B start → end angles as an operator reference.
  - The 3D simulation tilts the roller live and the position
    monitor shows the current B angle.
  Heating control and the CODESYS controller export are added
  in upcoming versions.

Each physical machine has its own profile file and settings; the
license file controls which machines you can open.


CALIBRATION — the most important step
════════════════════════════════════════════════════════════════
Calibration defines where the roller tip is in machine
coordinates. Without correct calibration, all paths will be
offset by a fixed amount — correct shape, wrong position.

Procedure:
1. Manually jog the roller until the tip just touches the
   mandrel surface (or blank surface, depending on the
   calibration reference you are using).
2. Read the X and Z coordinates from the machine's DRO.
3. Enter those values in the calibration dialog.
4. Apply to the appropriate parameters (the dialog shows
   which apply buttons affect which parameters).

Repeat the calibration whenever you change the roller, re-home
the machine, or suspect the position has drifted.


EXPORT FORMATS
════════════════════════════════════════════════════════════════
G-code (.nc)     Standard CNC moves. Use for most controllers.
                 Contains G0 (rapid) and G1 (feed) moves with
                 feed rates, spindle speed commands, and your
                 custom header/footer.

SCL (.scl)       Siemens TIA Portal format. Use when the machine
                 runs a Siemens S7 PLC. The paths are written as
                 structured data arrays for the PLC program.

Recipe CSV       A simplified pass-by-pass parameter table.
                 Useful for documentation, setup sheets, and
                 importing into other tools.

PDF report       A printable sheet with the operation list, pass
                 summary, and a 2D XZ diagram of the toolpaths.
                 Use as a machine-side setup reference.
""",
        "TR": """\
MAKİNE KURULUMU — TEMEL KAVRAMLAR
════════════════════════════════════════════════════════════════
Koordinat sistemi
  Yazılım kendi CAM koordinat uzayında çalışır. Bunun makine
  koordinatlarıyla nasıl eşleştiğini tanımlarsınız: orijin nerede,
  her eksen hangi yönde, çıkışta yarıçap mı çap mı kullanılsın.

  Önce bunu doğru ayarlayın. Dışa aktarılan tüm koordinatlar
  buna bağlıdır.

Home / Program Başlangıç Pozisyonu
  Rulonun program başında gittiği ve her pasosundan sonra döndüğü
  konum. Bunu tüm eksenlerde iş parçasından, bağlama aparatından
  ve puntadan güvenli şekilde uzakta bir konuma ayarlayın.
  Çok yakın = çarpışma riski. Çok uzak = gereksiz çevrim süresi.

Geri çekilme mesafeleri
  Her pasosundan sonra, rulo home'a dönmeden önce geri çekilme
  miktarı kadar geri adım atar. Bu, yeniden konumlandırma
  hareketinde rulonun parça üzerinden sürünmesini önler.

Çalışma alanı sınırları
  Makinenizin fiziksel hareket aralığını tanımlar. Bunlar 3D
  görünümde görsel referans olarak çalışma alanı kutusunu çizmek
  için kullanılır. Yazılım şu anda sert sınırları zorlamaz —
  yolların içinde kalmasını kontrol etmek sizin sorumluluğunuzdadır.

Rulo yaklaşım tarafı
  Rulonun mandrel eksenine pozitif mi yoksa negatif X tarafından
  mı yaklaştığı. Bunu değiştirmek tüm yol koordinatlarını
  yansıtır. Makinenizin fiziksel düzenine uyacak şekilde ayarlayın.

Makine ayarlarını kaydetme
  Bu sekmedeki tüm alanlar (home, geri çekilme, ofsetler, çalışma
  alanı, G-code çıkışı, …) aktif makine profiline aittir.
  Değiştirdiğiniz anda profile otomatik kaydedilir, böylece
  düzenlemeleriniz yeniden başlatmadan sonra da korunur. Sağ
  üstteki "Makine Profilini Kaydet" düğmesi de aynı işi elle yapar.


MAKİNE TİPLERİ
════════════════════════════════════════════════════════════════
Başlangıçta (lisans penceresinde) seçtiğiniz makine, yazılımın
neleri göstereceğini belirler:

ID111 — Sıvama Tezgahı (soğuk, iki eksen)
  Siemens PLC bölümleri (PLC modu, özel komutlar, M-code tablosu)
  ve SCL / Reçete CSV dışa aktarımı dahil tüm özellik seti.

ID112 — Sıcak Sıvama Tezgahı (döner kollu)
  X kızağı döner bir kol üzerinde olan, CODESYS tabanlı
  denetleyicili sıcak sıvama makinesi. Bu makinede Siemens'e özgü
  bölümler ve SCL dışa aktarımı gizlidir.

  Döner kol (B ekseni) kinematiği:
  - Makine sekmesine "Döner Kol (B Ekseni)" bölümü eklenir:
    pivot X/Z, B min/maks limitleri, B ev konumu ve B işareti.
    Makine çizimleri gelene kadar bunlar geçici değerlerdir.
  - Her kaba/bitirme operasyonuna "Eğim Modu (B)" seçici gelir:
    "Yüzey Normali" ruloyu mandrel yüzey normalini izletir
    (istenirse Eğim Ofseti ile öne/arkaya yatırma); "Başlangıç→
    Bitiş Açısı" operatörün girdiği başlangıç ve bitiş açısı
    arasında pas boyunca doğrusal geçiş yapar. Eğim B
    limitlerine kırpılır; aşımlar günlükte kinematik uyarı
    olarak raporlanır.
  - B = 0° kızağın tamamen radyal olduğu anlamına gelir (ID111
    makinesiyle aynı duruş); pozitif B takımı +Z yönüne eğer.
  - G-code çıktısında her kesme hareketi B kelimesi taşır; pas
    bilgi paneli ve PDF operasyon sayfası her pasın B başlangıç
    → bitiş açısını operatör referansı olarak gösterir.
  - 3D simülasyon ruloyu canlı olarak eğer ve konum monitörü
    anlık B açısını gösterir.
  Isıtma kontrolü ve CODESYS denetleyici çıktısı sonraki
  sürümlerde eklenecektir.

Her fiziksel makinenin kendi profil dosyası ve ayarları vardır;
hangi makineleri açabileceğinizi lisans dosyası belirler.


KALİBRASYON — en önemli adım
════════════════════════════════════════════════════════════════
Kalibrasyon, rulo ucunun makine koordinatlarında nerede olduğunu
tanımlar. Doğru kalibrasyon olmadan tüm yollar sabit bir miktar
kadar ofsetlenecektir — doğru şekil, yanlış konum.

Prosedür:
1. Rulo ucunu tam olarak mandrel yüzeyine (veya kullandığınız
   kalibrasyon referansına bağlı olarak blank yüzeyine) temas
   edene kadar manuel olarak hareket ettirin.
2. X ve Z koordinatlarını makinenin DRO'sundan okuyun.
3. Bu değerleri kalibrasyon diyaloğuna girin.
4. Uygun parametrelere uygulayın (diyalog hangi uygula düğmelerinin
   hangi parametreleri etkilediğini gösterir).

Ruloyu değiştirdiğinizde, makinenin home'unu sıfırladığınızda
veya konumun kaymış olabileceğinden şüphelendiğinizde kalibrasyonu
tekrarlayın.


DIŞA AKTARMA FORMATLARI
════════════════════════════════════════════════════════════════
G-code (.nc)      Standart CNC hareketleri. Çoğu denetleyici için
                  kullanın. Besleme hızları, mil hızı komutları ve
                  özel başlık/altbilginizle G0/G1 hareketlerini içerir.

SCL (.scl)        Siemens TIA Portal formatı. Makine bir Siemens S7
                  PLC ile çalışıyorsa kullanın. Yollar PLC programı
                  için yapılandırılmış veri dizileri olarak yazılır.

Reçete CSV        Basitleştirilmiş paso-paso parametre tablosu.
                  Dokümantasyon, kurulum sayfaları ve diğer araçlara
                  aktarım için kullanışlıdır.

PDF raporu        Operasyon listesi, paso özeti ve takım yollarının
                  2D XZ diyagramını içeren yazdırılabilir sayfa.
                  Makinede kurulum referansı olarak kullanın.
""",
    },

    "trouble": {
        "EN": """\
PATHS DON'T APPEAR AFTER A CHANGE
════════════════════════════════════════════════════════════════
Press Calculate. Some parameters do not trigger an automatic
recalculation to avoid slowing down the interface during editing.
Always press Calculate after making operation changes, and
always calculate before exporting.


ROLLER APPEARS TOO FAR FROM THE MANDREL
════════════════════════════════════════════════════════════════
The roller standoff is the sum of several stacked values: roller
tip radius + part thickness + clearance (the per-operation gap). If
the roller looks too far away in the 3D view:

1. Check calibration first. An incorrect roller tip position
   is the most common cause. Re-run the touch calibration from
   scratch and verify the tip radius in the tool library.

2. Check that the part thickness matches your actual blank
   material thickness — not the mandrel shell offset, which
   is a separate visual parameter.

3. Verify the roller radius value in the tool library is the
   calibrated effective reach distance, not the geometric
   disc radius from the STEP file (these are different things).


RED HEATMAP AREAS (collision or near-collision)
════════════════════════════════════════════════════════════════
Red means the roller is calculated to pass too close to or
through the mandrel. The collision correction pushes it out,
but if large areas are red it means the correction is working
hard and the geometry may not be reliable:

• Reduce pass depth — more passes for the same total depth
  means smaller steps and less chance of collision.

• Increase the number of roughing passes rather than going
  deep in one step.

• For curved or conical surfaces, enable conformal clearance
  mode — this makes the collision correction follow the
  mandrel surface normal rather than pushing in a fixed
  radial direction.

• Check that the part thickness is not set too low — a value
  of zero would put the path on the mandrel surface itself.


SIMULATION ROLLER JUMPS OR MOVES UNEXPECTEDLY
════════════════════════════════════════════════════════════════
The simulation plays back the actual stored toolpath. Unexpected
movement in simulation is unexpected movement on the machine.
Do not dismiss it. Likely causes:

• Home position is inside the mandrel or blank volume.
• Retract distance is too small — the roller doesn't clear
  the part before moving home.
• Calibration is off and the coordinate offset makes a rapid
  move pass through the workpiece.

Re-check the home position, retract distances, and calibration.


EXPORTED G-CODE IS EMPTY OR HAS NO MOVES
════════════════════════════════════════════════════════════════
You exported before calculating. The path list was empty, so the
file contains only the header. Press Calculate first, confirm
toolpaths appear in the 3D view, then export.


MACHINE MOVES IN THE WRONG DIRECTION
════════════════════════════════════════════════════════════════
Check the axis inversion settings and the roller approach side
setting. These are the only two controls that flip output
coordinate directions. Change one at a time and recalculate
after each change so you can isolate which axis is the problem.


PATHS LOOK CORRECT IN 3D BUT ARE WRONG ON THE MACHINE
════════════════════════════════════════════════════════════════
This is almost always a calibration problem. The 3D view shows
CAM-space coordinates; the machine uses its own coordinate
system. If the mapping between them is wrong by any amount,
every path will be shifted by that amount.

Re-run the full touch calibration procedure. Pay attention to
which surface you are touching (mandrel vs. blank) and which
reference point the calibration dialog is applying to.
""",
        "TR": """\
DEĞİŞİKLİKTEN SONRA YOLLAR GÖRÜNMEDİ
════════════════════════════════════════════════════════════════
Hesapla düğmesine basın. Bazı parametreler, düzenleme sırasında
arayüzü yavaşlatmamak için otomatik yeniden hesaplamayı tetiklemez.
Operasyon değişikliklerinden sonra her zaman Hesapla'ya basın,
dışa aktarmadan önce de her zaman hesaplayın.


RULO MANDRELDEN ÇOK UZAKTA GÖRÜNüYOR
════════════════════════════════════════════════════════════════
Rulo boşluğu, üst üste gelen birkaç değerin toplamıdır: rulo ucu
yarıçapı + parça kalınlığı + güvenlik boşluğu + pay. 3D görünümde
rulo çok uzakta görünüyorsa:

1. Önce kalibrasyonu kontrol edin. Yanlış rulo ucu konumu en
   yaygın nedendir. Touch kalibrasyonunu sıfırdan yeniden çalıştırın
   ve takım kütüphanesindeki uç yarıçapını doğrulayın.

2. Parça kalınlığının gerçek blank malzeme kalınlığıyla eşleştiğini
   kontrol edin — ayrı bir görsel parametre olan mandrel kabuk
   ofsetiyle değil.

3. Takım kütüphanesindeki rulo yarıçapı değerinin, STEP dosyasından
   gelen geometrik disk yarıçapı değil (bunlar farklı şeylerdir),
   kalibre edilmiş efektif erişim mesafesi olduğunu doğrulayın.


KIRMIZI ISI HARİTASI ALANLARI (çarpışma veya yakın çarpışma)
════════════════════════════════════════════════════════════════
Kırmızı, rulonun mandrel'e çok yakın geçmek veya içinden geçmek
üzere hesaplandığı anlamına gelir. Çarpışma düzeltmesi onu dışarı
iter, ancak geniş alanlar kırmızıysa düzeltme çok zorlanıyor
demektir ve geometri güvenilir olmayabilir:

• Paso derinliğini azaltın — aynı toplam derinlik için daha fazla
  paso, daha küçük adımlar ve daha az çarpışma şansı demektir.

• Tek bir adımda derin gitmek yerine kaba paso sayısını artırın.

• Eğri veya konik yüzeyler için konformal boşluk modunu etkinleştirin
  — bu, çarpışma düzeltmesinin sabit bir radyal yönde itmek yerine
  mandrel yüzey normalini takip etmesini sağlar.

• Parça kalınlığının çok düşük ayarlanmadığını kontrol edin —
  sıfır değeri yolu mandrel yüzeyinin kendisine koyar.


SİMÜLASYON RULOSU BEKLENMEDIK ŞEKILDE ATLIYOR VEYA HAREKETedİYOR
════════════════════════════════════════════════════════════════
Simülasyon, depolanan gerçek takım yolunu oynatır. Simülasyonda
beklenmedik hareket, makinede de beklenmedik harekettir.
Göz ardı etmeyin. Olası nedenler:

• Home pozisyonu mandrel veya blank hacminin içinde.
• Geri çekilme mesafesi çok küçük — rulo home'a gitmeden önce
  parçayı temizlemiyor.
• Kalibrasyon hatalı ve koordinat ofseti hızlı hareketi iş
  parçasından geçiriyor.

Home pozisyonunu, geri çekilme mesafelerini ve kalibrasyonu
yeniden kontrol edin.


DIŞA AKTARILAN G-CODE BOŞ VEYA HAREKET İÇERMİYOR
════════════════════════════════════════════════════════════════
Hesaplamadan önce dışa aktardınız. Yol listesi boştu, dolayısıyla
dosya yalnızca başlığı içeriyor. Önce Hesapla'ya basın, 3D görünümde
takım yollarının göründüğünü doğrulayın, ardından dışa aktarın.


MAKİNE YANLIŞ YÖNDE GİDİYOR
════════════════════════════════════════════════════════════════
Eksen ters çevirme ayarlarını ve rulo yaklaşım tarafı ayarını
kontrol edin. Bunlar çıkış koordinat yönlerini değiştiren tek iki
kontroldür. Bir seferde birini değiştirin ve hangi eksenin sorun
olduğunu izole edebilmek için her değişiklikten sonra yeniden
hesaplayın.


PASOLAR 3D'DE DOĞRU GÖRÜNÜYOR AMA MAKİNEDE YANLIŞ
════════════════════════════════════════════════════════════════
Bu neredeyse her zaman bir kalibrasyon sorunudur. 3D görünüm
CAM uzay koordinatlarını gösterir; makine kendi koordinat sistemini
kullanır. Aralarındaki eşleme herhangi bir miktarda yanlışsa,
her yol o miktar kadar kaymış olacaktır.

Tam touch kalibrasyon prosedürünü yeniden çalıştırın. Hangi yüzeye
temas ettiğinize (mandrel ve blank) ve kalibrasyon diyaloğunun
hangi referans noktasına uyguladığına dikkat edin.
""",
    },
}


class HelpWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title(t("help_win_title"))
        self.geometry("720x580")
        self.minsize(560, 400)
        self.resizable(True, True)

        lang = get_language()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        sections = [
            ("help_tab_start",   "start"),
            ("help_tab_view",    "view"),
            ("help_tab_ops",     "ops"),
            ("help_tab_machine", "machine"),
            ("help_tab_trouble", "trouble"),
        ]

        for label_key, content_key in sections:
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=t(label_key))

            sb = ttk.Scrollbar(frame, orient="vertical")
            sb.pack(side="right", fill="y")

            txt = tk.Text(
                frame,
                wrap="word",
                font=("Consolas", 9),
                relief="flat",
                bg="#fafafa",
                padx=10,
                pady=8,
                yscrollcommand=sb.set,
                state="normal",
            )
            txt.pack(side="left", fill="both", expand=True)
            sb.config(command=txt.yview)

            content = _C.get(content_key, {}).get(lang) or _C.get(content_key, {}).get("EN", "")
            txt.insert("1.0", content)
            txt.config(state="disabled")

        btn_close = ttk.Button(self, text=t("help_btn_close"), command=self.destroy)
        btn_close.pack(pady=(4, 8))

        self.transient(parent)
        self.focus_force()
