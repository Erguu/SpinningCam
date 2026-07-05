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

The divider between the control panel and the 3D view can be
dragged to resize both — widen the panel if buttons or fields are
cut off. The chosen width is remembered.


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

Contact Zone     Draws a faded translucent red band around the
Band             mandrel marking the contact zone — where the roller
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

Kontrol paneli ile 3D görünüm arasındaki ayırıcı sürüklenerek
ikisi de yeniden boyutlandırılabilir — düğmeler veya alanlar
kesiliyorsa paneli genişletin. Seçilen genişlik hatırlanır.


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

Temas Bölgesi      Mandrel etrafında soluk yarı saydam kırmızı bir
Bandı              bant çizer — rulonun temas beslemesine (contact
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


PROGRESSIVE ANGLE & REACH (per-pass P3 exit shaping)
════════════════════════════════════════════════════════════════
The exit point P3 is defined as a length (reach) in a direction
(angle) out from the contact point. When Pass Angle is set, two
independent per-pass sweeps are available:

  • Progressive Angle — swings the exit DIRECTION across passes,
    from the first pass's Pass Angle toward the Fan End Angle.

  • Progressive Reach — changes the exit LENGTH across passes,
    from the current P3 reach toward the Reach End (mm). Set a
    smaller Reach End to shorten the stroke on later passes.

They are orthogonal and can run together: angle steers the
direction, reach sets the length. As the passes climb the mandrel
the unformed flange gets smaller, so shortening the reach per pass
keeps the exit near the blank edge without any material model.
Both fields only appear when Pass Angle is set and count > 1.


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


ADDING AND ORGANIZING OPERATIONS
════════════════════════════════════════════════════════════════
The "+ Add ▾" dropdown adds a new operation of the chosen type
(roughing, finishing, cutting, bending).

Each operation can be turned ON or OFF without deleting it: select
it and press On/Off, or simply double-click the row. Disabled
operations show "—" in the On column and appear gray; they are
skipped by Calculate and never reach the G-code. Use this to keep
several alternative strategies in the list and compare them by
switching which ones are active.

The "Real End Z" column shows where each operation's LAST pass
actually reaches in Z — its deepest contact point (P2), taken from
the path generator when the toolpaths are calculated. This differs
from "Zone End Z": the
p2_z_extend parameter pushes the last pass PAST the planned zone
end, so Real End Z = Zone End Z + p2_z_extend (for roughing). It is
in the same Z reference as Zone Start/End Z, so you can chain the
next operation from it directly. It shows "—" until the toolpaths
are calculated.

The planned "Zone Start Z" / "Zone End Z" columns (the Start Z /
End Z you set on each operation) can be added via Customize… (tick
them as Column). If the table has many columns, use the horizontal
scrollbar under it to reach the ones on the right.


CUSTOMIZE VIEW (Customize… BUTTON + Advanced CHECKBOX)
════════════════════════════════════════════════════════════════
Large programs expose dozens of parameters per operation, most of
which you rarely touch. Two controls tame this:

  - "Customize…" opens a window with one tab per operation type
    (Roughing / Finishing / Cutting / Bending). For each parameter
    the type can use, tick "Column" to add it as a column in the
    operations table (so you can compare operations at a glance),
    and/or "Advanced" to hide it from the property editor. A
    parameter can be basic for one type and advanced for another.

  - The "Advanced" checkbox in the toolbar is a global view switch.
    Off: the editor shows only the parameters NOT marked advanced —
    a short, clean form. On: every parameter is shown (the classic
    behaviour). It affects the view only.

Column choices and basic/advanced tags are saved WITH the program
(.ssp), so each program remembers its own layout; the Advanced
switch is a single app-wide setting. IMPORTANT: hiding a parameter
never changes its value and never changes the toolpath — a hidden
field still feeds path generation exactly as before. This is only
about what you see, not what the machine does. A cell that shows
"—" in the table means that parameter does not apply to that
operation type. New programs start from sensible defaults.


OPERATION SUGGESTER (✨Suggest BUTTON)
════════════════════════════════════════════════════════════════
The Suggest button proposes a roughing + finishing sequence from
the loaded mandrel profile and a material table. It estimates:
  - roughing pass count from the part's total wall angle,
  - the pass-angle fan (first pass angle, spreading to 180°),
  - spindle RPM from the material surface speed,
  - feeds (mm/min) from the material's mm/rev values,
  - back pass on/off (ironing stroke when the wall is steep
    enough that flange wrinkling is a risk),
  - a blank diameter estimate by surface-area equivalence.

The preview includes a "WHY THESE VALUES" section explaining each
number in one line, plus warnings (spinning ratio, RPM/feed
clamps, workspace). Nothing is inserted until you press
"Insert as new operations" — the proposal is appended to the
operation list, where you can edit or disable it like any other
operation. Suggestions come from generic cold-spinning
heuristics: treat them as a starting point, then Calculate,
check clearances and simulate as usual. The numbers (angle per
pass, speeds, feeds, ratio limits) live in materials.json next
to the program and can be tuned per machine and material.


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


KADEMELİ AÇI VE UZUNLUK (pas başına P3 çıkış şekli)
════════════════════════════════════════════════════════════════
Çıkış noktası P3, temas noktasından bir yönde (açı) uzanan bir
uzunluk (reach) olarak tanımlanır. Pas Açısı tanımlıysa, pas başına
iki bağımsız yelpaze kullanılabilir:

  • Kademeli Açı — çıkış YÖNÜNÜ paslar boyunca ilk pasın Pas
    Açısından Yelpaze Bitiş Açısına doğru çevirir.

  • Kademeli Uzunluk — çıkış UZUNLUĞUNU paslar boyunca mevcut P3
    uzunluğundan Uzunluk Bitiş (mm) değerine değiştirir. Daha
    küçük bir bitiş değeri sonraki pasların strokunu kısaltır.

İkisi diktir ve birlikte çalışır: açı yönü, uzunluk uzunluğu
ayarlar. Paslar mandrelde yukarı çıktıkça şekillenmemiş flanş
küçülür; bu yüzden pas başına uzunluğu kısaltmak, hiçbir malzeme
modeli olmadan çıkışı blank kenarına yakın tutar. Her iki alan da
yalnızca Pas Açısı tanımlı ve paso sayısı > 1 iken görünür.


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


OPERASYON EKLEME VE DÜZENLEME
════════════════════════════════════════════════════════════════
"+ Ekle ▾" açılır menüsü seçilen tipte yeni operasyon ekler
(kaba, bitirme, kesme, kıvırma).

Her operasyon silinmeden AÇIK/KAPALI yapılabilir: seçip Aç/Kapat
düğmesine basın veya satıra çift tıklayın. Kapalı operasyonlar
Aktif sütununda "—" gösterir ve gri görünür; Hesapla bunları
atlar, G-code'a asla girmezler. Birden fazla alternatif stratejiyi
listede tutup hangilerinin aktif olduğunu değiştirerek
karşılaştırmak için kullanın.

"Gerçek Bitiş Z" sütunu her operasyonun SON pasının Z'de gerçekte
nereye ulaştığını gösterir — en derin temas noktası (P2), takım
yolları hesaplanırken yol üreticisinden alınır. Bu, "Bölge Bitiş
Z"den FARKLIDIR: p2_z_extend
parametresi son pası planlanan bölge bitişinin ÖTESİNE iter, yani
Gerçek Bitiş Z = Bölge Bitiş Z + p2_z_extend (kaba için). Bölge
Başlangıç/Bitiş Z ile aynı Z referansındadır, bu yüzden bir sonraki
operasyonu doğrudan buradan zincirleyebilirsiniz. Takım yolları
hesaplanana kadar "—" gösterir.

Planlanan "Bölge Başlangıç Z" / "Bölge Bitiş Z" sütunları (operasyona
verdiğiniz Start Z / End Z) Özelleştir… ile eklenebilir (Sütun
kutusunu işaretleyin). Tabloda çok sütun varsa, sağdakilere ulaşmak
için altındaki yatay kaydırma çubuğunu kullanın.


GÖRÜNÜMÜ ÖZELLEŞTİRME (Özelleştir… DÜĞMESİ + Gelişmiş KUTUSU)
════════════════════════════════════════════════════════════════
Büyük programlarda her operasyon onlarca parametre gösterir, çoğuna
nadiren dokunursunuz. İki kontrol bunu düzenler:

  - "Özelleştir…" her operasyon tipi için bir sekme içeren bir
    pencere açar (Kaba / Bitirme / Kesme / Kıvırma). Tipin
    kullanabildiği her parametre için "Sütun"u işaretleyerek onu
    operasyon tablosuna sütun olarak ekleyebilir (operasyonları bir
    bakışta karşılaştırmak için) ve/veya "Gelişmiş"i işaretleyerek
    özellik editöründen gizleyebilirsiniz. Bir parametre bir tip
    için temel, başka bir tip için gelişmiş olabilir.

  - Araç çubuğundaki "Gelişmiş" kutusu genel bir görünüm anahtarıdır.
    Kapalı: editör yalnızca gelişmiş işaretlenmemiş parametreleri
    gösterir — kısa, sade bir form. Açık: tüm parametreler görünür
    (klasik davranış). Yalnızca görünümü etkiler.

Sütun seçimleri ve temel/gelişmiş etiketleri programla (.ssp)
BİRLİKTE kaydedilir; her program kendi düzenini hatırlar. Gelişmiş
anahtarı ise uygulama genelinde tek bir ayardır. ÖNEMLİ: bir
parametreyi gizlemek değerini ASLA değiştirmez ve takım yolunu ASLA
değiştirmez — gizli bir alan yol üretimini eskisi gibi besler. Bu
yalnızca ne gördüğünüzle ilgilidir, makinenin ne yaptığıyla değil.
Tabloda "—" gösteren bir hücre, o parametrenin o operasyon tipine
uygulanmadığı anlamına gelir. Yeni programlar makul varsayılanlarla
başlar.


OPERASYON ÖNERİCİ (✨ÖNER DÜĞMESİ)
════════════════════════════════════════════════════════════════
Öner düğmesi, yüklü mandrel profilinden ve bir malzeme tablosundan
kaba + bitirme operasyon dizisi önerir. Tahmin ettikleri:
  - parçanın toplam duvar açısından kaba paso sayısı,
  - paso açısı yelpazesi (ilk paso açısı, 180°'ye yayılır),
  - malzeme yüzey hızından mil devri (RPM),
  - malzemenin mm/dev değerlerinden beslemeler (mm/dak),
  - geri pas açık/kapalı (duvar açısı flanşta kırışma riski
    yaratacak kadar dikse ütüleme hamlesi),
  - yüzey alanı eşdeğerliğiyle sac çapı tahmini.

Önizlemede her sayıyı tek satırda açıklayan "BU DEĞERLER NEDEN
BÖYLE" bölümü ve uyarılar (sıvama oranı, RPM/besleme sınırlamaları,
çalışma alanı) bulunur. "Yeni operasyon olarak ekle" düğmesine
basmadan hiçbir şey eklenmez — öneri operasyon listesine eklenir
ve diğer operasyonlar gibi düzenlenebilir veya kapatılabilir.
Öneriler genel soğuk sıvama kurallarından gelir: başlangıç noktası
olarak kullanın, ardından her zamanki gibi Hesapla'ya basın,
mesafeleri kontrol edin ve simüle edin. Değerler (paso başına açı,
hızlar, beslemeler, oran sınırları) programın yanındaki
materials.json dosyasındadır; makineye ve malzemeye göre
ayarlanabilir.


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

Clamp Zone Default (counter-press)
  The base region of the part is held between the counter-press
  and the mandrel and is never formed. Set the clamped depth here
  (mm, measured up from the mandrel base) as the machine default.
  Each program can override it on the Process tab ("Clamp Zone");
  0 there means "use this machine default". The excluded region is
  drawn as a translucent red band in the 3D view. For now this is
  advisory only: an operation that starts inside the band is logged
  as a warning but the path is still generated — so keep setting the
  first operation's Start Z above the band as you do today.

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
    lead/lag angle); "Start→End Angle" ties the angle to the
    surface position — "Tilt @ Start Z" applies at the
    operation's Start Z, "Tilt @ End Z" at its End Z, with a
    linear transition in Z between them. The same Z always
    yields the same angle, on every pass and in both travel
    directions. Tilt is clamped to the B limits; violations
    are reported as kinematic warnings in the log.
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

Challenger Rr — a second way to measure the tool's reach:
"Rr" is how far the roller reaches from the machine reference to
the point that touches the part. Normally each tool's Rr is
measured one way. The problem: that measurement can come out a
little different for each tool, so calibrating with one tool and
then running another can leave a small gap.

Example: you calibrate with tool 1 and it is correct. You switch
to tool 2, and it stops about 1 mm short of the part. The tool is
fine — the two tools were just measured slightly differently.

The dialog now shows a "Challenger Rr" for the selected tool. It
measures every tool the SAME way (from the tool's STEP file), so
the tools stay consistent with each other. To test it:

  1. Pick tool 1, click "Use ▸", do the touch, and Apply.
  2. Pick tool 2, click "Use ▸", and do its touch.
  3. If the gap is gone, this way of measuring is better.

Important: "Use ▸" only fills the Rr box for this calibration. It
does NOT change the tool library and saves no tool value.


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
    Bitiş Açısı" açıyı yüzey konumuna bağlar — "Eğim @
    Başlangıç Z" operasyonun Başlangıç Z'sinde, "Eğim @ Bitiş
    Z" Bitiş Z'sinde geçerlidir, arada Z'ye göre doğrusal
    geçilir. Aynı Z her pasta ve her iki yönde de aynı açıyı
    verir. Eğim B limitlerine kırpılır; aşımlar günlükte
    kinematik uyarı olarak raporlanır.
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

Challenger Rr — takımın erişimini ölçmenin ikinci bir yolu:
"Rr", rulonun makine referansından parçaya değen noktaya kadar ne
kadar uzandığıdır. Normalde her takımın Rr'si tek bir yöntemle
ölçülür. Sorun: bu ölçüm her takım için biraz farklı çıkabilir; bu
yüzden bir takımla kalibre edip başka takımla çalışınca küçük bir
boşluk kalabilir.

Örnek: Takım 1 ile kalibre ediyorsun, doğru. Takım 2'ye geçiyorsun
ve parçaya ~1 mm kala duruyor. Takım kusurlu değil — iki takım
sadece biraz farklı ölçülmüş.

Diyalog artık seçili takım için bir "Challenger Rr" gösteriyor. Bu
değer HER takımı AYNI şekilde ölçer (takımın STEP dosyasından), böylece
takımlar birbiriyle tutarlı kalır. Test etmek için:

  1. Takım 1'i seç, "Use ▸"e bas, dokunuşu yap ve Apply'la.
  2. Takım 2'yi seç, "Use ▸"e bas ve onun dokunuşunu yap.
  3. Boşluk kaybolduysa bu ölçüm yöntemi daha iyidir.

Önemli: "Use ▸" yalnızca bu kalibrasyon için Rr kutusunu doldurur.
Takım kütüphanesini DEĞİŞTİRMEZ ve hiçbir takım değerini KAYDETMEZ.


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


"CLEARANCE ADVISORY — ANGLED SURFACES" WARNING APPEARS
════════════════════════════════════════════════════════════════
This warning is informational only — toolpaths are never changed
by it. It appears when the mandrel has angled (conical or curved)
surfaces inside an operation's Z range. On such slopes the
clearance model is less accurate, because the roller is a tilted
disc rather than a sphere:

• A positive (+) deviation means the roller will stay farther
  from the part than the commanded clearance (safe, but the
  gap on the part will be larger than expected).

• A negative (−) deviation means the roller can come CLOSER
  to the part than commanded — treat this as a gouge risk and
  verify the first run with a dry pass or extra clearance.

On cylindrical (straight) mandrel sections the model is exact
and this warning does not appear. The popup is shown once per
recipe; the same details are always written to the log.
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


"BOŞLUK UYARISI — AÇILI YÜZEYLER" UYARISI GÖRÜNÜYOR
════════════════════════════════════════════════════════════════
Bu uyarı yalnızca bilgilendirme amaçlıdır — takım yolları asla
değiştirilmez. Mandrelin, bir operasyonun Z aralığı içinde açılı
(konik veya eğri) yüzeyleri olduğunda görünür. Bu tür eğimlerde
boşluk modeli daha az hassastır, çünkü rulo bir küre değil,
eğik bir disktir:

• Pozitif (+) sapma, rulonun parçadan komut verilen boşluktan
  daha uzak kalacağı anlamına gelir (güvenli, ancak parçadaki
  boşluk beklenenden büyük olur).

• Negatif (−) sapma, rulonun parçaya komut verilenden daha çok
  YAKLAŞABİLECEĞİ anlamına gelir — bunu dalma (gouge) riski
  olarak değerlendirin ve ilk çalıştırmayı kuru paso veya ek
  boşlukla doğrulayın.

Silindirik (düz) mandrel bölümlerinde model tamdır ve bu uyarı
görünmez. Açılır pencere reçete başına bir kez gösterilir; aynı
ayrıntılar her zaman log'a yazılır.
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
