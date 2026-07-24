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

CAMERA BUTTONS (Process tab → Visual Settings)
Every angle you can reach with the mouse is also reachable with
buttons, and views you set with the buttons STICK (they no longer
snap back when the scene redraws):
  Presets        Front / Back / Left / Right / Top / Iso
  Horizontal     orbit left/right  (±5° fine, ±15° coarse)
  Vertical       tilt up/down      (±5° fine, ±15° coarse)
  Roll / Zoom    ⟲ ⟳ tilt the horizon;  🔍＋ / 🔍－ zoom
  Reset Camera   back to the default angle
  Saved Views    "＋ Save current view…" stores the current angle
                 under a name; each saved view has Go / ✕ (delete).
                 Saved views persist in settings.json. Number keys
                 1-9 jump straight to the matching saved view (they
                 are ignored while you type in a field).

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

Tip paths        Draws each pass at the roller TOUCH POINT instead of
                 the roller centre. The stored path is the roller
                 centre; this pulls the drawn line in by the tool
                 radius (r_tool) so you see where the sheet is actually
                 formed. Visual only — path generation, G-code and the
                 simulation are untouched, and it redraws from the last
                 result without recalculating. (Radial approximation;
                 on steep walls the true contact point can shift a
                 little along the surface normal.)

Rulers           Two placeable scale bars — a horizontal X ruler and
                 a vertical Z ruler — with mm tick marks. Placement:
                 the X ruler sits at the Z level you set ("X ruler at
                 Z"), the Z ruler at the X level you set ("Z ruler at
                 X"). Direction & zero: each ruler runs from its Start
                 to its End; the Start is the zero mark and labels read
                 distance from it, so set Start at a feature to measure
                 from there, and swap Start/End to flip direction.
                 Leave End equal to Start to auto-fit the scene (with
                 Start = 0 the labels then read true machine X / Z).
                 Visual only — never affects toolpaths or G-code.

Contact Zone     Draws a faded translucent red band around the
Band             mandrel marking the contact zone — where the roller
                 slows to its contact feed. Path segments inside the
                 band run slow; segments outside run fast. It follows
                 the mandrel profile and does not alter the toolpaths.
                 Only appears for operations with a contact zone set.

Bent-Sheet       A faded-blue surface showing how the SELECTED pass
Overlay          bends the blank, updated as you click operations or
                 step passes. Visual only — never affects toolpaths or
                 G-code. Toggle it under "Show Bent-Sheet Overlay".
                 NOTE: rebuilding this surface is the main cost of
                 clicking an operation, so turning it OFF makes op
                 selection noticeably snappier on large programs.


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

KAMERA DÜĞMELERİ (Proses sekmesi → Görsel Ayarlar)
Fareyle ulaşabildiğin her açıya düğmelerle de ulaşabilirsin ve
düğmelerle ayarladığın görünüm SABİT KALIR (sahne yeniden
çizilince artık geri sıçramaz):
  Önayarlar     Ön / Arka / Sol / Sağ / Üst / İzo
  Yatay         sola/sağa döndür  (±5° ince, ±15° kaba)
  Dikey         yukarı/aşağı eğ   (±5° ince, ±15° kaba)
  Eksen/Zoom    ⟲ ⟳ ufku eğ;  🔍＋ / 🔍－ yakınlık
  Kamerayı Sıfırla   varsayılan açıya döner
  Kayıtlı Görünümler   "＋ Mevcut görünümü kaydet…" o anki açıyı
                 bir adla saklar; her görünümün Git / ✕ (sil)
                 düğmesi var. Kayıtlı görünümler settings.json'da tutulur.
                 1-9 rakam tuşları ilgili kayıtlı görünüme anında
                 geçer (bir alana yazı yazarken yoksayılır).

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

Uç yolları         Her pası rulo MERKEZİ yerine rulo TEMAS
                   NOKTASINDA çizer. Saklanan yol rulo merkezidir;
                   bu seçenek çizilen çizgiyi takım yarıçapı (r_tool)
                   kadar içeri çeker, böylece sacın gerçekte nerede
                   şekillendiğini görürsünüz. Yalnızca görseldir — yol
                   üretimi, G-code ve simülasyon değişmez; son
                   sonuçtan yeniden çizilir, tekrar hesaplama yapılmaz.
                   (Radyal yaklaşım; dik duvarlarda gerçek temas
                   noktası yüzey normali boyunca biraz kayabilir.)

Cetveller          Yerleştirilebilir iki ölçek çubuğu — yatay X
                   cetveli ve dikey Z cetveli — mm taksimatlı. Konum:
                   X cetveli belirlediğiniz Z seviyesine ("X cetveli Z
                   konumu"), Z cetveli belirlediğiniz X seviyesine ("Z
                   cetveli X konumu") oturur. Yön ve sıfır: her cetvel
                   Başlangıç'tan Bitiş'e uzanır; Başlangıç sıfır
                   işaretidir ve etiketler oradan itibaren mesafeyi
                   okur — yani Başlangıç'ı bir özelliğe koyarak oradan
                   ölçün, yönü çevirmek için Başlangıç/Bitiş'i
                   değiştirin. Bitiş'i Başlangıç'a eşit bırakırsanız
                   uzunluk sahneye göre otomatik ayarlanır (Başlangıç=0
                   iken etiketler gerçek makine X / Z değerini okur).
                   Yalnızca görseldir — takım yollarını veya G-code'u
                   etkilemez.

Temas Bölgesi      Mandrel etrafında soluk yarı saydam kırmızı bir
Bandı              bant çizer — rulonun temas beslemesine (contact
                   feed) yavaşladığı temas bölgesini işaretler. Bandın
                   içindeki yol kısımları yavaş, dışındakiler hızlı
                   çalışır. Mandrel profilini takip eder ve takım
                   yollarını değiştirmez. Yalnızca temas bölgesi
                   tanımlı operasyonlar için görünür.

Bükülmüş Sac      SEÇİLİ pasın sacı nasıl büktüğünü gösteren soluk
Kaplaması         mavi bir yüzey; operasyona tıkladıkça veya pas
                   değiştirdikçe güncellenir. SADECE görsel — takım
                   yolunu veya G-code'u etkilemez. "Bükülmüş Sac
                   Kaplamasını Göster" ile aç/kapat. NOT: bu yüzeyin
                   yeniden hesaplanması bir operasyona tıklamanın ana
                   maliyetidir; KAPATMAK çok operasyonlu programlarda
                   operasyon seçimini belirgin şekilde hızlandırır.


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

Anchored sweep (build it in the Pass Table): normally each roughing
pass's contact steps UP the mandrel — pass 1 near Start Z, the last
near End Z, each a separate slice. To make the passes instead grow
from a FIXED start, open the Pass Table (right-click the op) and use
the fill helpers: "Set all → Anchor Z" pins every pass's start to the
same Z, then "Progressive → Extend" ramps each pass a bit further out
than the last. The result is a fixed-start, growing sweep — and you
can then hand-tune any single pass. (These are per-pass pins, so a
pinned op becomes a summary under Split/Unite — see the Pass Table.)

For finishing: each pass traces the mandrel profile at a defined
standoff. Multiple finishing passes step down that standoff to
zero (the actual part thickness). Use 1–3 finishing passes
depending on the surface quality required.

Straight-line finishing (2-point line): for a constant-angle
(conical or cylindrical) wall you can reduce a finishing pass to a
single straight line between its Start Z and End Z — far fewer
G-code points. This is only correct while that span really is
straight: the line is offset parallel to the surface, so on a
constant angle the clearance stays even the whole way. If the
surface between Start Z and End Z is curved or changes slope, the
line drifts off it and the clearance is no longer held mid-pass.
The software checks this and shows a warning (amber status bar, and
a pop-up if the surface bulges toward the tool, which risks a
gouge). If you see it, split the operation at the slope change or
switch it to sweeping/adaptive finishing. Tune the trigger with
the flatness tolerance parameter (default 0.15 mm).

Straighten start fillet (opt-in): a cylinder/cone mandrel often has
a small rounded radius where the wall meets the end face. Normally
the passes follow that fillet, so the first passes climb the little
radius. Turn on "Straighten Start Fillet" and any pass machining
below the fillet→wall transition instead follows the EXTRAPOLATED
straight wall, ignoring the small radius. The transition is found
automatically (same detector as the "flat start" hint); a mandrel
with no straight section is never straightened. For roughing, the
whole pass follows the wall (contact point AND the approach angle),
while the collision/gouge check still uses the REAL mandrel — so on
an outward (convex) lip the tool is still pushed out to clear it; it
can never be driven into the mandrel. This applies to STRAIGHT-LINE
finishing and ROUGHING only — sweeping/adaptive finishing
intentionally keeps hugging the real surface.

When straightening is on and a pass starts low (behind the radius),
the clamp-zone advisory softens to a calm note instead of the amber
alarm — but still reminds you to verify the roller clears the
counter-press.


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


REACH SOURCE & EXIT MODE (the editor's Path Shape section)
════════════════════════════════════════════════════════════════
A status line shows which EXIT MODE the operation is in:
  • ANGULAR (Pass Angle set): direction comes from Pass Angle,
    length from Reach. P3 X/Z are greyed ONLY when an explicit
    length source is active (Reach set, or Follow-blank on) —
    with Reach EMPTY the length still comes from |P3|, so the
    fields stay editable there.
  • RAW X/Z (Pass Angle empty): P3 X/Z are the actual exit
    offsets; entering a Reach rescales that vector to the given
    length while keeping its direction.

"Reach source" selects where the Reach value comes from:
  • Manual — you type it.
  • Follow blank — the ENGINE recomputes the reach for EVERY
    PASS from the remaining blank flange at that pass's own Z,
    so each exit kisses the blank edge. Your own values are
    NEVER overwritten: the Reach field shows the auto range
    ("oto first→last") readonly, and switching back to Manual
    reveals your numbers exactly as you left them. Two
    modifiers are yours: Blank factor (×) and Blank offset
    (mm, e.g. −5 = stop 5 mm before the edge); the result is
    flange × factor + offset. The Progressive-Reach fan is
    greyed here (the per-pass follow supersedes it) but its
    checkbox is never flipped for you. Enabling Follow is
    refused honestly if the flange model can't be computed
    (needs Sheet Radius). The switch itself is undoable.
  • "Fill ⟲" (Manual mode) — estimates the reach from the blank
    ONCE and fills the field; undo with Ctrl+Z.

Setting a Reach (or following the blank / pinning a pass) also
anchors the exit ENDPOINT to be clearance-independent (same reach
+ different clearance = same absolute end position). The Pass
Diagram window (formula panel) shows this whole chain with the
selected operation's live values.


EXIT CURVE SHAPE (bowing the P2→P3 leg) — linear shapes
════════════════════════════════════════════════════════════════
Reach and Pass Angle decide WHERE the exit ends (P3). Two knobs
decide the SHAPE of the curve between P2 and P3 — both leave P3
exactly where the reach/angle put it, so they never fight
Follow-blank or the Progressive-Angle fan:

  • Exit Arc Angle (°) — a tangent-chord circular arc. Positive
    bows outward, negative inward, 0 = straight. Simple, but it is
    parameterized by ANGLE: the arc sweep is TWICE the angle, so
    past ~90° it swings beyond a semicircle and folds back on
    itself. On steep near-vertical last passes (high Pass Angle /
    reach-follow) that fold is the "funny movement" where the tail
    curls over.

  • Exit Bow (mm) — the stable alternative. Parameterized by bow
    HEIGHT in millimetres, using a Bézier that reproduces P2 and P3
    exactly and grows monotonically — it CANNOT fold no matter how
    far you push it. Positive bows toward the mandrel top (+Z),
    negative toward the base, 0/empty = off. The side uses a fixed
    handedness, so EVERY pass in a progressive-angle fan bows the
    same way even as the exit tilts across the radial direction —
    no first-pass flip. Best when P2 and P3 sit at nearly the same
    Z and you want the exit to bow out and come back cleanly. When
    set, Exit Bow takes over from Exit Arc Angle. Typical 5–30 mm.
    (Replaces the old, non-functional "Exit Tension" field.)

  • Bow Bias (0–1) — where the bow's fullest point sits along the
    P2→P3 leg. 0.5 (default) centres it; lower pulls the peak toward
    P2, higher toward P3. The peak HEIGHT stays exactly Exit Bow mm
    and the endpoints stay pinned — only the peak's along-leg
    position moves. Only active while Exit Bow is set. Clamped to
    0.05–0.95.

  A bow never violates clearance — it is kept at the operation's own
  clearance (never below the hard safety floor), and P3 and the
  P1→P2 arm always stay where reach and angle put them. The "Bow
  Trim to Clr" toggle chooses HOW:
    • ON (default) — TRIM: the full bow is built, and only the part
      that would come too close is pushed back out to ride the
      clearance contour; the rest keeps the full bow. So a large bow
      survives even on a short, steep last pass (small tangent kink
      where it meets/leaves the contour).
    • OFF — CLAMP: the bow amplitude is shrunk until it just fits —
      a smaller but perfectly smooth bow (no kink).


PASS TABLE (Paslar ▦ — see every pass before you run)
════════════════════════════════════════════════════════════════
The Pass Table action (operation right-click menu) opens one row per
pass of the selected operation: contact Z, the EFFECTIVE angle
and reach the engine will really use, the exit endpoint, the
value SOURCE (manual / fan / follow / ⭑pin / legacy override)
and warnings:
  ⚠ clearance guard — this pass's endpoint sits ~clearance
    further out than its anchored neighbors (near-180° exits);
  ⚠ ~same as previous pass — endpoints closer than 2.5 mm do no
    distinguishable extra work;
  ⚠ reach≈0 — the pass falls back to the RAW default exit;
  ⚠ exit beyond blank edge — the commanded reach overshoots the
    ESTIMATED unformed flange at that Z: the tail of the pass is
    an air move (needs Sheet Radius; fix: shorten reach, pin the
    pass, or switch reach source to follow).
Selecting a row highlights that pass in the 3D view.
NOTE: warnings are recomputed from the CURRENT geometry — they
legitimately appear/disappear when blank size, reach or angles
change. The endpoint column ignores the iterative safety-floor
push, so the 3D path can sit a few mm further out in X.

EDITING: double-click a cell to stage a per-pass value (✎). You can
pin P1_Z (the pass's start), Extend (how far its P2 contact reaches
past the start), Clearance, Angle and Reach individually. P2_Z is the
resulting contact (P1_Z + Extend) and P3_Z the exit — both read-only.
(P1_Z, Extend and Clearance are for roughing operations.) To change
many passes at once use the Fill bar: pick a field, then "Set all"
(same value everywhere) or "Progressive" (smooth ramp first→last) —
e.g. Set all P1_Z + Progressive Extend = an anchored sweep. The 2D
preview at the bottom shows the passes as you edit.
Staged edits touch NOTHING until [Apply], which writes them as ONE
undo step; [Cancel] discards them. A pinned pass (⭑) keeps its values
against fans and follow mode — the highest-priority source. "Unpin"
removes pins AND any legacy hidden per-pass overrides on the selected
rows (also undoable). Pins live inside the operation, so they survive
copy, move and split (split remaps them to the right chunk). NOTE: a
pass carrying pins can't be reproduced by a single parametric
operation, so Split/Unite of a pinned op is a summary — review it.


PASS DIRECTION (FORWARD / REVERSE)
════════════════════════════════════════════════════════════════
Each roughing or finishing operation has a Direction setting.
Forward (default) cuts in the normal direction. Reverse makes the
roller travel the inverse way (e.g. tip→root). For linear-shape
passes the geometry now swaps its leg roles (2026-07-08 default):
the leg ENTERING the mandrel-near contact point is always the
STRAIGHT arm, and the exit-arc curve moves to the outgoing leg —
previously the roller entered along the curve, which is not what
a reverse pass should do. With Exit Arc Angle = 0 nothing
changes at all. The old behavior is available per op via the
advanced key reverse_legacy_flip. In a multi-pass operation the
order the passes are laid down stays the same; just each pass's
travel is reversed. Reverse and Back Pass can be combined.


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

The toolbar itself is intentionally small — it holds only Undo/Redo
(↶ ↷, at the far left), + Add ▾, Suggest, Tools…, Customize… and the
Advanced switch, plus the time readout. Every PER-ROW action
(Continue ⤵, Split, Unite, Reach⟲, Angle⟲, Pass Table, On/Off, Copy,
Delete, Batch, Library, Move ▲▼) lives on the RIGHT-CLICK menu of a
row. The bar automatically wraps onto a second line when the sidebar
is narrow or the screen is small, so Undo/Redo are never pushed out
of view.

Each operation can be turned ON or OFF without deleting it: select
it and press On/Off, or simply double-click the row. Disabled
operations show "—" in the On column and appear gray; they are
skipped by Calculate and never reach the G-code. Use this to keep
several alternative strategies in the list and compare them by
switching which ones are active.

"Copy" duplicates the targeted operations (the ☑ ticks if any are
set, otherwise the selected rows — same rule as Batch) and inserts
the copies right below the last target, selected and ready to
edit. One Ctrl+Z removes them. Use this instead of abusing "Save
as Default" for copying.

Operations can be given a NAME ("Name" field at the top of the
property editor, or right-click → Rename…). The name replaces the
type text in the list; leave it empty to show the type again.
Names are labels only — they never affect the toolpath.

RIGHT-CLICK on any row opens a context menu with the row actions:
Rename, Copy, On/Off, Reset to factory defaults, Continue ⤵,
Split, Unite, Reach⟲, Angle⟲, Pass Table, Batch, Move up/down,
Move to #…, Delete and the operation Library. This menu is now the
primary place for these actions — they were removed from the toolbar
to keep it compact and always fit on screen.

REORDERING operations: besides Move up/down (one row at a time), you
can DRAG A ROW and drop it where you want — a blue line shows where it
will land. To reach a position that is off-screen (e.g. move row 20 up
to row 2), keep holding the drag and SCROLL with the mouse wheel to
bring the target into view, then drop. If several rows are targeted
(☑ ticks or a multi-row selection) and you grab one of them, the whole
block moves together. For an exact spot, use right-click → Move to #…
and type the target line number. All of these are one Ctrl+Z to undo.

UNITE is the opposite of Split: select two or more operations and it
combines them into one, taking the first pick's slot. They do NOT
have to be next to each other — if you pick operations with others
between them, those in-between operations are kept and slide to AFTER
the united operation. It only unites operations of the SAME type and
SAME tool. When the selection is the adjacent chunks of an earlier
Split, the union reproduces the original operation EXACTLY and applies
silently.

When the operations DIFFER, a resolver dialog opens so YOU decide how
each conflicting field is combined — one row per conflict with a
drop-down:
  • Start / End Z — the united operation spans the whole range; a Z
    choice only appears if your picks are out of Z order (then Min /
    Max recover the true extent).
  • Pass Angle / Reach / Tilt (values that change across passes) — keep
    a Ramp (first → last) or collapse to First / Last / Average.
  • Clearance and every other differing setting — First / Last /
    Average.
The default for every row reproduces the automatic merge, so just
press OK to accept it. Remember a single operation holds ONE clearance,
shape and tool and ramps the rest linearly, so uniting genuinely
different operations is a summary, not a lossless join — review the
result. One Ctrl+Z undoes a unite.

ESCAPE HATCH — factory defaults: "+ Add ▾" normally copies your
last "Save as Default" preset, so a preset polluted by experiments
produces polluted "new" operations. The dropdown's lower section
("— factory clean") adds an operation with CLEAN built-in defaults,
ignoring the preset. Right-click → "Reset to factory defaults"
does the same to an EXISTING stuck operation: all parameters are
replaced (pins, follow mode, fans dropped), while type, name and
on/off state are kept. Both are one Ctrl+Z step. Your saved preset
itself is untouched — overwrite it with "Save as Default" on a
clean operation when you want new defaults.

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


UNDO / REDO (↶ / ↷ BUTTONS, Ctrl+Z / Ctrl+Y)
════════════════════════════════════════════════════════════════
Every operation-LIST action can be undone: Split, Unite, Delete,
Move ▲▼, + Add, Continue ⤵, Reach⟲, Angle⟲, On/Off and inserting
suggested operations. Undo (↶, Ctrl+Z) restores the operation
list exactly as it was before the last such action; Redo (↷,
Ctrl+Y) re-applies an undone action. Up to 50 steps are kept —
when full, the oldest is dropped silently.

What is NOT tracked: values typed into the parameter fields of
the property editor. Those are quick to correct by hand, and
Ctrl+Z pressed while typing in a field is deliberately ignored so
it never reverts the operation list under you.

Doing any new list action clears the Redo history (the standard
editor rule). The history is per session and per project: loading
a project clears it. After an undo/redo the toolpaths recalculate
automatically only if Auto-Calculate is on — otherwise press
Calculate as usual.


BATCH EDIT (right-click → Batch… + ☑ COLUMN)
════════════════════════════════════════════════════════════════
Change ONE parameter on MANY operations in a single step — e.g.
add 2 mm to the Start Z of five operations at once, instead of
selecting and editing each one.

Choosing the target operations, two ways:
  - Click the ☑ cells in the table's first column to tick
    operations (clicking the cell only toggles the tick — it does
    not change the row selection or fire On/Off). Click the ☑
    COLUMN HEADER to tick every row at once (click again to clear).
  - Or simply select several rows with Shift/Ctrl+click, or press
    Ctrl+A to highlight all of them.
Ticks win when any are set; otherwise the selection is used. The
right-click → Batch… item enables at 2+ targets and shows the count.

This same target rule now drives Delete and Move ▲▼ too: the
right-click → Delete (or the Delete key while the list is focused)
removes EVERY targeted operation (it asks for confirmation when 2 or
more are targeted), and Move up/down shifts the whole target set
together as one block. Both are one undo step.

In the dialog: pick the parameter, the mode — "+= add" (add a
constant), "= set" (assign a value), "×= scale" (multiply) — and
type the value. The preview table shows every target operation's
old → new value LIVE as you type; nothing is written until Apply.
Rows where the parameter doesn't apply (wrong operation type, or
no base value for +=/×=) are greyed out and skipped.

The whole batch is ONE undo step: a single Ctrl+Z reverts all of
it. Which parameters appear in the dropdown is chosen per program
in Customize… (the third "Batch" checkbox; numeric parameters
only). Pass count is rounded to a whole number and never drops
below 1.


OPERATION LIBRARY (right-click → operation Library)
════════════════════════════════════════════════════════════════
Save operations under NAMES and reuse them in any program — e.g.
three different roughing strategies, each with its own name.
Unlike "Save as Default" (one unnamed slot per type, used by
+ Add), the library holds any number of named entries.

In the dialog: "+ Save selected op" snapshots the operation
selected in the Program tab under a name you choose (same name =
overwrite after confirmation). "Insert ▸" (or double-click an
entry) adds a copy into the current program right after the
selected row; the dialog stays open so you can insert several.
Entries can be renamed and deleted. Inserting is one undo step.

The library lives in ops_library.json NEXT TO the program (exe)
— it is app-level, so it survives across programs and projects.
To share it with another PC, copy that file.

SAFETY: when an entry is inserted, its tool reach (r_tool) is
RE-SYNCED from the current tool library — an entry saved months
ago can never reintroduce a stale calibrated reach value.


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
    A third "Batch" checkbox picks which parameters the Batch edit
    dialog offers (numeric parameters only; "—" means the
    parameter cannot be batch-edited). A "Border" dropdown draws a
    colored rectangle around that parameter's LABEL in the property
    editor (Red / Green / Blue / Orange / Purple / Yellow, or "—"
    for none) — a visual flag to point another user at the
    parameters that matter for this program. It borders only the
    label text, never the input box, and never changes any value.

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


TOOL LIBRARY — SHARING TOOLS BETWEEN PCs
════════════════════════════════════════════════════════════════
Each operation picks a roller from the Tool library (Tools…
button). A tool stores its calibrated reach (r_tool) AND its 3D
STEP geometry. Geometry now travels automatically: when you add a
tool and browse to its STEP file, the program copies it into a
tool_geometry/ folder next to the app and names it after the tool
ID (e.g. tool_geometry/T0103.STEP). It is then found by ID on any
machine — so a git pull, or a copied exe, brings the tools ready
to use, with no re-adding and no broken file paths.

To move tools between PCs outside git, use Export Library… /
Import Library… in the Tool window. Export writes one .zip holding
tools.json + every tool's STEP file; Import copies the geometry in
and merges the tools (asking before overwriting any that share an
ID). NOTE: r_tool is a calibrated, machine-specific number — after
importing tools from another machine, re-check calibration for
your own setup.


TOOL-CHANGE POSITION (per operation)
════════════════════════════════════════════════════════════════
When an operation needs a different tool than the one before it,
the machine retracts and M6 rotates the turret. Each operation has
a Tool Change setting that controls WHERE that retract goes:

  Global (home)        Retract to the machine home / Program Start.
                       This is the default and the safest choice.
  Absolute X/Z         Retract to an explicit point you type in.
  Relative to last     Retract to an offset (ΔX / ΔZ) from the
                       previous pass's FORMING end (its last cutting
                       point, before the automatic per-pass retract) —
                       handy for a quick change close to the work.

Axis directions: X is the RADIAL axis — a larger X moves the roller
further OUT, away from the part. Z is the AXIAL (lathe) axis — a
larger Z moves in the +Z machine direction (toward the mandrel top).
Note that increasing Z alone does NOT move away from the part; it
just slides along the axis, so mind the mandrel profile.

Move order: by default the retract goes Z first, then X — this
clears the part axially before traversing radially. Tick
Simultaneous XZ to move both axes together in one diagonal rapid
(faster). A diagonal can cut across a convex corner, so use it only
where the straight line to the point is clear.

It only matters on an operation whose tool differs from the one
before it; the first operation always homes.

Simulation cue: during playback the sim pauses briefly at every
tool change and shows a yellow banner (outgoing → incoming tool)
with a pulsing marker at the change point, so a fast run doesn't
hide where the swap happens.

SIMULATION TIMING
Playback is timed by the program's real rates, not by point count:
each cutting pass plays at that operation's own feed, so a slow
contact-feed finish looks slow next to a fast rough and a short
(2-point) straight-line finish no longer whips through. Rapids play
at the machine's rapid-traverse rate — set it in Machine ▸ Program
Start / Retract ▸ 'Rapid Rate (mm/min)'. That value only times the
simulation; it is never written into the exported program.

Sim Speed is a typed × multiplier — enter any value (0.25, 5, 50…)
or step it with the arrows. 1× plays in the real process time; 2×
takes half. The 'Process time' line shows the real machining time
(at 1×) and the scaled playback time at your chosen multiplier.

HOW THE COLLISION CHECK WORKS
After Calculate, a custom tool-change point is checked two ways:
  1. Clearance AT the point — the radial distance from the roller
     (plus its radius) to the outermost part/blank surface at that
     Z. M6 rotates the turret here, so a small value means a tool
     could strike the part as it swings in.
  2. Clearance ALONG the move — the retract path is sampled and the
     closest approach to the part is measured. The move starts at
     the part, so only a NEGATIVE value matters: it means the path
     (typically a Simultaneous-XZ diagonal) dips into the part.
Either one trips a warning. It is a geometric radial check against
the mandrel/blank profile — it does NOT model the exact shape of
the OTHER tools on the turret, so treat it as an aid, not a
guarantee, and keep generous clearance. The warning is advisory
only; the toolpath is never changed. Move the point further OUT in
X, clear of the blank in Z, or turn Simultaneous XZ off to clear it.


PASS RETRACT (per operation)
════════════════════════════════════════════════════════════════
After each pass the roller retracts by an X/Z offset before the next
move. This is set PER OPERATION — every operation (roughing,
finishing, cutting, bending) has its own Retract X / Retract Z field.
There is no global retract any more: each operation owns its value,
so different operations can retract differently. New operations
default to 50 mm; leaving a field empty also means 50 mm. Existing
programs are migrated automatically, so every operation keeps the
retract it had before. The 3D simulation and the exported G-code use
the same value, so what you see is what the machine runs.


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

Sabit başlangıç süpürme (Pas Tablosunda oluştur): normalde her kaba
pasın temas noktası mandrelde YUKARI adımlar — 1. paso Başlangıç Z,
son paso Bitiş Z yakınında, her biri ayrı bir dilim. Pasların
SABİT bir başlangıçtan büyümesi için Pas Tablosunu açın (op'a sağ
tık) ve doldurma yardımcılarını kullanın: "Hepsine ata → Kök Z" her
pasın başlangıcını aynı Z'ye sabitler, sonra "Kademeli → Uzatma" her
pası bir öncekinden biraz daha uzağa çıkarır. Sonuç: sabit başlangıç,
büyüyen süpürme — ve istediğiniz tek pası elle ince ayarlayabilirsiniz.
(Bunlar pas-başına pinlerdir; pinli op Böl/Birleştir'de bir özet olur —
Pas Tablosuna bakın.)

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


REACH KAYNAĞI VE ÇIKIŞ MODU (editörün Yol Şekli bölümü)
════════════════════════════════════════════════════════════════
Bir durum satırı operasyonun hangi ÇIKIŞ MODUNDA olduğunu gösterir:
  • AÇISAL (Pass Angle dolu): yön Pass Angle'dan, uzunluk
    Reach'ten gelir. P3 X/Z alanları YALNIZCA açık bir uzunluk
    kaynağı etkinken grileşir (Reach dolu veya Sacı-takip açık) —
    Reach BOŞKEN uzunluk hâlâ |P3|'ten gelir, alanlar
    düzenlenebilir kalır.
  • HAM X/Z (Pass Angle boş): P3 X/Z gerçek çıkış ofsetleridir;
    Reach girilirse bu vektörün boyunu, yönünü koruyarak verilen
    uzunluğa ölçekler.

"Reach kaynağı" Reach değerinin nereden geldiğini seçer:
  • Elle — kendin yazarsın.
  • Sacı takip et — MOTOR, HER PASIN reach'ini o pasın kendi
    Z'sindeki kalan sac flanşından hesaplar; her çıkış sacın
    ucunu öper. Senin değerlerin ASLA üzerine yazılmaz: Reach
    alanı salt-okunur "oto ilk→son" aralığını gösterir; Elle'ye
    dönünce kendi sayıların aynen ortaya çıkar. İki değiştirici
    senindir: Sac çarpanı (×) ve Sac kaydırma (mm; örn. −5 =
    kenardan 5 mm önce dur); sonuç = flanş × çarpan + kaydırma.
    Progressive-Reach yelpazesi bu modda gridir (pas-başına
    takip onu zaten kapsar) ama işaretin ASLA değiştirilmez.
    Flanş modeli hesaplanamıyorsa (Sac Yarıçapı yok) mod
    açılmaz ve dürüstçe söylenir. Geçişin kendisi Ctrl+Z ile
    geri alınır.
  • "Doldur ⟲" (Elle modunda) — reach'i sactan BİR KEZ tahmin
    edip alana doldurur; Ctrl+Z ile geri alınır.

Reach girmek (veya sacı takip / pas pinlemek) ayrıca çıkış BİTİŞ
noktasını clearance'tan bağımsız kılar (aynı reach + farklı
clearance = aynı mutlak bitiş konumu). Pass Diagram penceresi
(formül paneli) bu zinciri seçili operasyonun canlı değerleriyle
gösterir.


PAS TABLOSU (Paslar ▦ — çalıştırmadan önce her pası gör)
════════════════════════════════════════════════════════════════
Pas Tablosu işlemi (operasyon sağ-tık menüsü) seçili operasyonun her
pası için bir satır açar: temas Z'si, motorun GERÇEKTE
kullanacağı açı ve reach, çıkış uç noktası, değerin KAYNAĞI
(elle / yelpaze / takip / ⭑pin / eski override) ve uyarılar:
  ⚠ klerens koruması — bu pasın ucu, demirli komşularından
    ~klerens kadar dışarıda kalır (180°'ye yakın çıkışlar);
  ⚠ öncekiyle ~aynı — uçlar 2.5 mm'den yakınsa pas ayırt
    edilir iş yapmaz;
  ⚠ reach≈0 — pas HAM varsayılan çıkışa düşer;
  ⚠ sac ucu aşımı — komut edilen reach, o Z'deki TAHMİNİ
    şekilsiz flanşı aşıyor: pasın kuyruğu boşta harekettir
    (Sac Yarıçapı gerekir; çözüm: reach'i kısalt, pası pinle
    veya reach kaynağını takibe al).
Satır seçmek o pası 3B görünümde vurgular.
NOT: uyarılar GÜNCEL geometriden yeniden hesaplanır — sac boyu,
reach veya açılar değişince görünüp kaybolmaları normaldir. Uç
noktası sütunu yinelemeli güvenlik-tabanı itmesini içermez; 3B
yol X'te birkaç mm daha dışarıda olabilir.

DÜZENLEME: bir hücreye çift tıkla → pas-başına değer BEKLEMEYE alınır
(✎). P1_Z (pasın başlangıcı), Uzatma (P2 temasının başlangıçtan ne
kadar uzağa ulaştığı), Klerens, Açı ve Reach ayrı ayrı pinlenebilir.
P2_Z sonuçtaki temastır (P1_Z + Uzatma), P3_Z çıkıştır — ikisi de
salt-okunur. (P1_Z, Uzatma ve Klerens kaba operasyonlar içindir.)
Birçok pası birden değiştirmek için Doldur çubuğunu kullan: alan seç,
sonra "Hepsine ata" veya "Kademeli" — örn. Hepsine ata P1_Z + Kademeli
Uzatma = sabit başlangıç süpürme. Alttaki 2B önizleme pasları gösterir. Beklemedekiler
[Uygula]'ya kadar HİÇBİR
ŞEYE dokunmaz; Uygula hepsini TEK Ctrl+Z adımı olarak yazar,
[İptal] atar. Pinli pas (⭑) değerlerini yelpazeye ve sac takibine
karşı korur — en yüksek öncelikli kaynaktır. "Pin temizle"
seçili satırlardaki pinleri VE eski tip gizli override'ları
kaldırır (o da geri alınabilir). Pinler operasyonun içinde
yaşar: kopyala, taşı ve böl'de korunurlar (böl, pinleri doğru
parçaya yeniden eşler). NOT: pin taşıyan bir pas tek bir parametrik
operasyonla üretilemez → pinli op'un Böl/Birleştir'i bir özettir,
sonucu gözden geçir.


PAS YÖNÜ (İLERİ / TERS)
════════════════════════════════════════════════════════════════
Her kaba veya bitirme operasyonunun bir Yön ayarı vardır. İleri
(varsayılan) normal yönde keser. Ters'te rulo ters yönde ilerler
(örn. uç→kök). Lineer şekilli paslarda geometri artık bacak
rollerini değiştirir (2026-07-08 varsayılanı): mandrele yakın
temas noktasına GİREN bacak her zaman DÜZ koldur; çıkış yayı
(Exit Arc) çıkan bacağa taşınır — eskiden rulo mandrele eğri
üzerinden giriyordu, ters pasın istediği bu değildir. Exit Arc
Angle = 0 ise hiçbir şey değişmez. Eski davranış op başına
reverse_legacy_flip anahtarıyla geri gelir. Çok paslı
operasyonda pasların oluşturulma sırası aynı kalır; sadece her
pasın ilerleyişi ters döner. Ters yön ve Geri Pas birlikte
kullanılabilir.


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

Araç çubuğu bilinçli olarak küçük tutuldu — yalnızca Geri Al/Yinele
(↶ ↷, en solda), + Ekle ▾, Öner, Takımlar…, Özelleştir… ve Gelişmiş
anahtarı ile süre göstergesini taşır. HER SATIR-BAŞINA işlem
(Devam ⤵, Böl, Birleştir, Reach⟲, Açı⟲, Pas Tablosu, Aç/Kapat, Kopyala, Sil,
Toplu, Kütüphane, Yukarı/Aşağı ▲▼) artık satırın SAĞ-TIK menüsünde.
Kenar çubuğu dar ya da ekran küçük olduğunda araç çubuğu otomatik
olarak ikinci satıra kayar; böylece Geri Al/Yinele hiçbir zaman
görünmez olmaz.

Her operasyon silinmeden AÇIK/KAPALI yapılabilir: seçip Aç/Kapat
düğmesine basın veya satıra çift tıklayın. Kapalı operasyonlar
Aktif sütununda "—" gösterir ve gri görünür; Hesapla bunları
atlar, G-code'a asla girmezler. Birden fazla alternatif stratejiyi
listede tutup hangilerinin aktif olduğunu değiştirerek
karşılaştırmak için kullanın.

"Kopyala" hedef operasyonları çoğaltır (☑ işaretleri varsa onlar,
yoksa seçili satırlar — Toplu ile aynı kural) ve kopyaları son
hedefin hemen altına, seçili ve düzenlemeye hazır ekler. Tek
Ctrl+Z hepsini kaldırır. Kopyalama için "Varsayılan Kaydet"i
kullanmaya artık gerek yok.

Operasyonlara AD verilebilir (özellik editörünün üstündeki "Ad"
alanı veya sağ-tık → Yeniden adlandır…). Ad, listede tip yazısının
yerine görünür; boş bırakılırsa tekrar tip gösterilir. Ad yalnızca
bir etikettir — takım yolunu asla etkilemez.

Herhangi bir satıra SAĞ TIKLAMAK satır işlemlerini içeren menüyü
açar: Yeniden adlandır, Kopyala, Aç/Kapat, Fabrika varsayılanına
sıfırla, Devam ⤵, Böl, Birleştir, Reach⟲, Açı⟲, Pas Tablosu, Toplu,
Yukarı/Aşağı taşı, # konumuna taşı…, Sil ve operasyon Kütüphanesi. Bu
menü artık bu işlemlerin ASIL yeri — araç çubuğunu derli toplu tutmak
ve her ekranda sığdırmak için araç çubuğundan kaldırıldılar.

OPERASYON SIRALAMA: Yukarı/Aşağı taşı (tek tek) dışında, bir satırı
SÜRÜKLEYİP istediğiniz yere bırakabilirsiniz — mavi bir çizgi nereye
düşeceğini gösterir. Ekran dışı bir konuma ulaşmak için (örn. 20.
satırı 2. satıra taşımak) sürüklemeyi bırakmadan FARE TEKERİYLE kaydırıp
hedefi görünür yapın, sonra bırakın. Birden çok satır hedefliyse (☑
işaretleri veya çoklu seçim) ve içlerinden birini tutarsanız, blok
birlikte taşınır. Kesin bir konum için sağ-tık → # konumuna taşı… ile
hedef satır numarasını yazın. Bunların hepsi tek Ctrl+Z ile geri alınır.

BİRLEŞTİR, Böl'ün tersidir: iki veya daha fazla operasyon seçin, tek
operasyonda birleştirir (ilk seçimin yerine yerleşir). YAN YANA olmak
ZORUNDA DEĞİLLER — aralarında başka operasyonlar olanları seçerseniz,
o aradaki operasyonlar korunur ve birleşik operasyonun ARKASINA kayar.
Yalnızca AYNI tip ve AYNI takıma sahip operasyonları birleştirir.
Seçim daha önce Böl ile üretilmiş BİTİŞİK parçalarsa, birleşim orijinal
operasyonu BİREBİR ve sessizce uygular.

Operasyonlar FARKLIYSA, çakışan her alanı NASIL birleştireceğinize
KARAR vermeniz için bir çözüm penceresi açılır — her çakışma için bir
satır ve açılır liste:
  • Başlangıç / Bitiş Z — birleşik operasyon tüm aralığı kapsar; Z
    seçeneği yalnızca seçimleriniz Z sırasında değilse çıkar (o zaman
    En düşük / En yüksek gerçek kapsamı geri getirir).
  • Pas Açısı / Reach / Eğim (paslar arasında değişen değerler) —
    Yelpaze (ilk → son) tut ya da İlk / Son / Ortalama tek değere indir.
  • Clearance ve farklı olan diğer her ayar — İlk / Son / Ortalama.
Her satırın varsayılanı otomatik birleşimi yeniden üretir, yani kabul
etmek için TAMAM'a basın. Unutmayın: tek bir operasyon TEK clearance,
şekil ve takım tutar, gerisini doğrusal yelpazeler — bu yüzden
gerçekten farklı operasyonları birleştirmek kayıpsız bir birleşim değil,
bir ÖZETtir; sonucu gözden geçirin. Bir Ctrl+Z birleştirmeyi geri alır.

KAÇIŞ KAPISI — fabrika varsayılanları: "+ Ekle ▾" normalde son
"Varsayılan Kaydet" ön ayarınızı kopyalar; deneylerle kirlenmiş bir
ön ayar, kirli "yeni" operasyonlar üretir. Menünün alt bölümü
("— fabrika temiz") ön ayarı YOK SAYARAK yerleşik temiz
varsayılanlarla operasyon ekler. Sağ-tık → "Fabrika varsayılanına
sıfırla" aynısını MEVCUT sıkışmış bir operasyona yapar: tüm
parametreler değiştirilir (pinler, takip modu, yelpazeler silinir);
tip, ad ve açık/kapalı durumu korunur. İkisi de tek Ctrl+Z adımıdır.
Kayıtlı ön ayarınıza dokunulmaz — yeni varsayılan istediğinizde
temiz bir operasyonda "Varsayılan Kaydet"e basın.

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


GERİ AL / YİNELE (↶ / ↷ DÜĞMELERİ, Ctrl+Z / Ctrl+Y)
════════════════════════════════════════════════════════════════
Operasyon LİSTESİNİ değiştiren her işlem geri alınabilir: Böl,
Birleştir, Sil, Taşı ▲▼, + Ekle, Devam ⤵, Reach⟲, Açı⟲, Aç/Kapat ve öneri
operasyonlarının eklenmesi. Geri Al (↶, Ctrl+Z) listeyi son
işlemden önceki haline birebir döndürür; Yinele (↷, Ctrl+Y) geri
alınan işlemi tekrar uygular. En fazla 50 adım tutulur — dolunca
en eski adım sessizce düşer.

Takip EDİLMEYEN: özellik düzenleyicideki parametre alanlarına
yazılan değerler. Bunlar elle kolayca düzeltilir; ayrıca bir alana
yazı yazarken basılan Ctrl+Z bilinçli olarak yok sayılır — yazı
yazarken operasyon listesi asla geri sarılmaz.

Yeni bir liste işlemi yapmak Yinele geçmişini temizler (standart
editör kuralı). Geçmiş oturuma ve projeye özeldir: proje yüklemek
geçmişi sıfırlar. Geri al/yinele sonrası takım yolları yalnızca
Otomatik Hesapla açıksa kendiliğinden yeniden hesaplanır — değilse
her zamanki gibi Hesapla'ya basın.


TOPLU DÜZENLEME (sağ-tık → Toplu… + ☑ SÜTUNU)
════════════════════════════════════════════════════════════════
TEK adımda BİRÇOK operasyonun BİR parametresini değiştirin — örn.
beş operasyonun Başlangıç Z'sine tek seferde 2 mm ekleyin, her
birini tek tek seçip düzenlemek yerine.

Hedef operasyonları seçmenin iki yolu:
  - Tablonun ilk sütunundaki ☑ hücrelerine tıklayarak operasyonları
    işaretleyin (hücreye tıklamak yalnız işareti değiştirir — satır
    seçimini bozmaz, Aç/Kapat'ı tetiklemez). ☑ SÜTUN BAŞLIĞINA
    tıklamak hepsini birden işaretler (tekrar tıklamak temizler).
  - Veya satırları Shift/Ctrl+tık ile çoklu seçin, ya da Ctrl+A ile
    hepsini birden vurgulayın.
İşaret varsa işaretler geçerlidir; yoksa seçim kullanılır. Sağ-tık →
Toplu… ögesi 2+ hedefte aktifleşir ve sayıyı gösterir.

Aynı hedef kuralı artık Sil ve Taşı ▲▼ için de geçerli: sağ-tık →
Sil (veya liste odaktayken Delete tuşu), hedeflenen TÜM operasyonları
kaldırır (2+ hedefte onay sorar) ve Yukarı/Aşağı taşı, hedef kümesini
tek blok olarak birlikte kaydırır. İkisi de tek geri-al adımıdır.

Pencerede: parametreyi, modu — "+= ekle" (sabit ekle), "= ata"
(değer ata), "×= ölçekle" (çarp) — ve değeri seçin. Önizleme
tablosu siz yazdıkça her hedef operasyonun eski → yeni değerini
CANLI gösterir; Uygula'ya basana kadar hiçbir şey yazılmaz.
Parametrenin geçerli olmadığı satırlar (yanlış operasyon tipi veya
+=/×= için taban değer yok) gri gösterilir ve atlanır.

Tüm toplu işlem TEK geri-al adımıdır: tek Ctrl+Z hepsini geri
alır. Açılır listede hangi parametrelerin sunulacağı programa özel
olarak Özelleştir… penceresinde seçilir (üçüncü "Toplu" kutusu;
yalnız sayısal parametreler). Pas sayısı tam sayıya yuvarlanır ve
1'in altına düşmez.


OPERASYON KÜTÜPHANESİ (sağ-tık → operasyon Kütüphanesi)
════════════════════════════════════════════════════════════════
Operasyonları AD vererek kaydedin ve herhangi bir programda tekrar
kullanın — örn. her biri kendi adıyla üç farklı kaba strateji.
"Varsayılan Kaydet"ten (tip başına tek adsız yuva, + Ekle bunu
kullanır) farklı olarak kütüphane istediğiniz kadar adlı kayıt tutar.

Pencerede: "+ Seçili op'u kaydet", Program sekmesinde seçili
operasyonu vereceğiniz adla kaydeder (aynı ad = onay sonrası
üzerine yazar). "Ekle ▸" (veya kayda çift tık) bir kopyayı mevcut
programa, seçili satırın hemen altına ekler; pencere açık kalır —
arka arkaya birkaç kayıt ekleyebilirsiniz. Kayıtlar yeniden
adlandırılabilir ve silinebilir. Ekleme tek geri-al adımıdır.

Kütüphane exe'nin YANINDAKİ ops_library.json dosyasında yaşar —
uygulama genelindedir, programlar ve projeler arasında kalıcıdır.
Başka bir bilgisayarla paylaşmak için o dosyayı kopyalayın.

GÜVENLİK: bir kayıt eklenirken takım erişimi (r_tool) güncel takım
kütüphanesinden TAZELENİR — aylar önce kaydedilmiş bir kayıt bayat
kalibre reach değerini asla geri getiremez.


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
    için temel, başka bir tip için gelişmiş olabilir. Üçüncü
    "Toplu" kutusu, Toplu düzenleme penceresinin hangi
    parametreleri sunacağını seçer (yalnız sayısal parametreler;
    "—" = o parametre toplu düzenlenemez).

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


TAKIM KÜTÜPHANESİ — TAKIMLARI PC'LER ARASI PAYLAŞMA
════════════════════════════════════════════════════════════════
Her operasyon, Takım kütüphanesinden (Takımlar… düğmesi) bir rulo
seçer. Bir takım hem kalibre erişimini (r_tool) HEM de 3B STEP
geometrisini saklar. Geometri artık otomatik taşınır: bir takım
ekleyip STEP dosyasına göz attığınızda, program onu uygulamanın
yanındaki tool_geometry/ klasörüne kopyalar ve takım ID'siyle
adlandırır (örn. tool_geometry/T0103.STEP). Böylece her makinede
ID ile bulunur — git pull veya kopyalanan bir exe, takımları
kullanıma hazır getirir; yeniden ekleme yok, bozuk dosya yolu yok.

Takımları git dışında PC'ler arasında taşımak için Takım
penceresindeki Kütüphaneyi Dışa Aktar… / İçe Aktar… kullanın. Dışa
aktarma tek bir .zip yazar (tools.json + her takımın STEP dosyası);
İçe aktarma geometriyi kopyalar ve takımları birleştirir (aynı
ID'lileri değiştirmeden önce sorar). NOT: r_tool kalibre, makineye
özel bir değerdir — başka bir makineden takım içe aktardıktan sonra
kendi kurulumunuz için kalibrasyonu yeniden kontrol edin.


TAKIM DEĞİŞİM KONUMU (operasyon başına)
════════════════════════════════════════════════════════════════
Bir operasyon bir öncekinden farklı bir takım gerektirdiğinde makine
geri çekilir ve M6 tareti döndürür. Her operasyonun, bu geri çekilmenin
NEREYE gideceğini belirleyen bir Takım Değişim ayarı vardır:

  Global (home)        Makine home / Program Start'a geri çekilir.
                       Varsayılan ve en güvenli seçenek budur.
  Mutlak X/Z           Girdiğiniz açık bir noktaya geri çekilir.
  Son pasa göre        Önceki pasın ŞEKİLLENDİRME bitişine (otomatik
                       pas-sonu geri çekilmeden önceki son kesme
                       noktası) göre bir ofsete (ΔX / ΔZ) geri çekilir
                       — işe yakın hızlı bir değişim için kullanışlı.

Eksen yönleri: X RADYAL eksendir — daha büyük X rulonu daha DIŞARI,
parçadan uzağa taşır. Z EKSENEL (torna) eksenidir — daha büyük Z,
+Z makine yönünde (mandrel üstüne doğru) hareket eder. Yalnızca Z'yi
artırmak parçadan UZAKLAŞMAZ; sadece eksen boyunca kayar, bu yüzden
mandrel profiline dikkat edin.

Hareket sırası: varsayılan olarak geri çekilme önce Z, sonra X gider
— traverse öncesi parçadan eksenel uzaklaşır. Her iki ekseni tek bir
çapraz rapid'de birlikte hareket ettirmek için Eşzamanlı XZ'yi
işaretleyin (daha hızlı). Çapraz hareket dışbükey bir köşeyi
kesebilir, bu yüzden yalnızca noktaya giden düz çizgi açıksa kullanın.

Yalnızca takımı bir öncekinden farklı olan operasyonda etkilidir;
ilk operasyon her zaman home'a gider.

Simülasyon ipucu: oynatma sırasında sim her takım değişiminde kısa
süre duraklar ve sarı bir başlık (giden → gelen takım) ile değişim
noktasında nabız gibi atan bir işaret gösterir; böylece hızlı bir
oynatmada değişimin nerede olduğu kaçmaz.

SİMÜLASYON ZAMANLAMASI
Oynatma, nokta sayısına değil programın gerçek hızlarına göre
zamanlanır: her kesme pası o operasyonun kendi feed'iyle oynar, bu
yüzden yavaş bir contact-feed finish hızlı bir rough'un yanında yavaş
görünür ve kısa (2 noktalı) düz-çizgi finish artık akıp geçmez.
Rapid'ler makinenin hızlı-ilerleme hızıyla oynar — bunu Makine ▸
Program Start / Retract ▸ 'Rapid Rate (mm/min)' altında ayarlayın. Bu
değer YALNIZCA simülasyonu zamanlar; dışa aktarılan programa asla
yazılmaz.

Sim Hızı bir × çarpan alanıdır — istediğiniz değeri yazın (0.25, 5,
50…) veya okçuklarla adımlayın. 1× gerçek işlem süresinde oynar; 2×
yarı sürede. 'İşlem süresi' satırı gerçek işlem süresini (1×) ve
seçtiğiniz çarpandaki ölçekli oynatma süresini gösterir.

ÇARPIŞMA KONTROLÜ NASIL ÇALIŞIR
Hesapla sonrası özel bir takım-değişim noktası iki şekilde kontrol
edilir:
  1. Noktadaki BOŞLUK — rulodan (artı yarıçapı) o Z'deki en dıştaki
     parça/taslak yüzeyine radyal mesafe. M6 tareti burada döndürür,
     bu yüzden küçük değer takımın dönerken parçaya çarpabileceği
     anlamına gelir.
  2. Hareket BOYUNCA boşluk — geri çekilme yolu örneklenir ve parçaya
     en yakın yaklaşım ölçülür. Hareket parçadan başladığı için
     yalnızca NEGATİF değer önemlidir: yol (genellikle Eşzamanlı-XZ
     çaprazı) parçaya dalıyor demektir.
Herhangi biri uyarı verir. Bu, mandrel/taslak profiline karşı
geometrik radyal bir kontroldür — taretteki DİĞER takımların tam
şeklini modellemez, bu yüzden garanti değil yardımcı olarak görün ve
bol boşluk bırakın. Uyarı yalnızca tavsiyedir; takım yolu değişmez.
Gidermek için noktayı X'te daha DIŞARI, Z'de taslaktan uzağa taşıyın
veya Eşzamanlı XZ'yi kapatın.


PAS GERİ ÇEKİLMESİ (operasyon başına)
════════════════════════════════════════════════════════════════
Her pastan sonra rulo, bir sonraki harekete geçmeden önce bir X/Z
ofseti kadar geri çekilir. Bu, OPERASYON BAŞINA ayarlanır — her
operasyonun (kaba, bitirme, kesme, bükme) kendi Geri Çekilme X /
Geri Çekilme Z alanı vardır. Artık genel bir geri çekilme değeri
YOKTUR: her operasyon kendi değerini taşır, böylece farklı
operasyonlar farklı geri çekilebilir. Yeni operasyonlar varsayılan
50 mm'dir; alanı boş bırakmak da 50 mm demektir. Mevcut programlar
otomatik taşınır, böylece her operasyon önceki geri çekilme değerini
korur. 3D simülasyon ile dışa aktarılan G-code aynı değeri kullanır.


HESAPLA
════════════════════════════════════════════════════════════════
Operasyonlarda veya parametrelerde herhangi bir değişiklikten sonra
tüm takım yollarını yeniden oluşturmak için Hesapla'ya basın. 3D
görünüm otomatik olarak güncellenmez (Otomatik Hesaplama açık
değilse). Dışa aktarmadan önce her zaman hesaplayın.
""",
    },

    "tools": {
        "EN": """\
TOOL SETUP & CALIBRATION
════════════════════════════════════════════════════════════════
Every operation forms metal with a ROLLER, chosen from the Tool
library (Program tab -> Tools...). Getting a tool right has two
independent parts: its GEOMETRY (the 3D shape) and its CALIBRATED
REACH (where its contact point sits in machine coordinates).


1. ADD A TOOL
----------------------------------------------------------------
Program tab -> Tools... -> fill in:
  - ID    - a unique code, e.g. T0104. This ALSO names the tool's
            geometry file.
  - Name / Type / Color - labels only.
Then click Browse and pick the roller's STEP file. On Add/Save the
program COPIES that file into a tool_geometry/ folder next to the
app and renames it after the ID (tool_geometry/T0104.STEP), so the
tool is portable: it travels on a git pull or a copied exe and is
found automatically on any machine. You never manage the path by
hand.


2. RADIUS vs Rr (r_tool) - READ THIS
----------------------------------------------------------------
These are two DIFFERENT numbers:

  - Radius - pure geometry: the disc radius measured from the STEP
    file (centre to rim). The "Calculate radius from STEP" button
    fills this.

  - Rr / r_tool - the CALIBRATED distance from the machine's X
    reference (the disc centre) to the point that actually touches
    the part. This is what the toolpath USES. If you leave Rr
    empty, the path falls back to Radius.

THE RULE: Rr must be GREATER THAN OR EQUAL TO Radius. Rr is the
distance to the contact rim; set it SMALLER than the disc radius
and the machine drives the roller centre too close, so the rim
GOUGES the part. Whenever you change a tool's STEP/geometry,
recalculate Radius AND update Rr - a stale Rr from the old shape
is the classic gouge trap.

Safe options when you have no calibrated number yet:
  - set Rr = the calculated Radius (a correct starting point), or
  - clear Rr so it falls back to Radius automatically.


3. CALIBRATE (touch-point)
----------------------------------------------------------------
Radius from the STEP is only geometry. The TRUE Rr comes from
touch-point calibration, because the machine's zero may not sit
exactly at the disc centre. Open the touch-point calibration
dialog, jog the roller until it just touches a known surface, read
the DRO, enter the values and apply. See "Calibration - the most
important step" in the Machine tab for the full procedure and the
Challenger Rr helper. Re-calibrate whenever you change the roller
or re-home the machine.


4. CHANGE A TOOL'S STEP LATER
----------------------------------------------------------------
Tools... -> click the tool in the list -> Browse a new STEP ->
Save changes (keep the ID the same). The new file replaces
tool_geometry/<id>.STEP automatically. Recalculate Radius and
re-check Rr afterwards (see the rule in step 2).


5. SHARE TOOLS WITH ANOTHER PC
----------------------------------------------------------------
In the Tool window: Export Library... writes one .zip (all tools +
their STEP files); Import Library... reads it back, copies the
geometry in and merges (asking before overwriting same-ID tools).
Geometry travels by ID, so nothing has to be re-added - but Rr is
machine-specific, so re-check calibration after importing.


QUICK CHECKLIST FOR A NEW TOOL
----------------------------------------------------------------
  [ ] ID set, STEP browsed, Add/Save (auto-copied by ID)
  [ ] Calculate radius from STEP  -> Radius filled
  [ ] Rr set (calibrated, or = Radius as a start; never < Radius)
  [ ] Select the tool -> 3D roller looks right
  [ ] Touch-point calibration done for this machine
""",
        "TR": """\
TAKIM KURULUMU & KALİBRASYON
════════════════════════════════════════════════════════════════
Her operasyon metali bir RULO ile şekillendirir; rulo Takım
kütüphanesinden seçilir (Program sekmesi -> Takımlar...). Bir
takımı doğru ayarlamanın iki bağımsız parçası vardır: GEOMETRİSİ
(3B şekil) ve KALİBRE ERİŞİMİ (temas noktasının makine
koordinatlarındaki yeri).


1. TAKIM EKLEME
----------------------------------------------------------------
Program sekmesi -> Takımlar... -> doldurun:
  - ID    - benzersiz bir kod, örn. T0104. Bu AYNI ZAMANDA takımın
            geometri dosyasını adlandırır.
  - Ad / Tip / Renk - yalnızca etiket.
Sonra Gözat'a tıklayıp rulonun STEP dosyasını seçin. Ekle/Kaydet'te
program bu dosyayı uygulamanın yanındaki tool_geometry/ klasörüne
KOPYALAR ve ID ile adlandırır (tool_geometry/T0104.STEP); böylece
takım taşınabilir olur: git pull veya kopyalanan bir exe ile gelir
ve her makinede otomatik bulunur. Yolu asla elle yönetmezsiniz.


2. RADIUS ile Rr (r_tool) FARKI - MUTLAKA OKUYUN
----------------------------------------------------------------
Bunlar İKİ FARKLI sayıdır:

  - Radius - salt geometri: STEP dosyasından ölçülen disk yarıçapı
    (merkezden kenara). "STEP'ten yarıçap hesapla" düğmesi bunu
    doldurur.

  - Rr / r_tool - makinenin X referansından (disk merkezi) parçaya
    gerçekten TEMAS eden noktaya kadar olan KALİBRE mesafe. Takım
    yolu BUNU kullanır. Rr boş bırakılırsa yol Radius'a düşer.

KURAL: Rr, Radius'tan BÜYÜK VEYA EŞİT olmalıdır. Rr temas kenarına
olan mesafedir; disk yarıçapından KÜÇÜK ayarlarsanız makine rulo
merkezini fazla yaklaştırır ve kenar parçayı DALAR (gouge). Bir
takımın STEP/geometrisini her değiştirdiğinizde Radius'u yeniden
hesaplayın VE Rr'yi güncelleyin - eski şekilden kalan bayat Rr,
klasik dalma tuzağıdır.

Henüz kalibre değeriniz yoksa güvenli seçenekler:
  - Rr = hesaplanan Radius yapın (doğru bir başlangıç), veya
  - Rr'yi boşaltın; otomatik olarak Radius'a düşer.


3. KALİBRASYON (touch-point)
----------------------------------------------------------------
STEP'ten gelen Radius yalnızca geometridir. GERÇEK Rr, touch-point
kalibrasyonundan gelir, çünkü makinenin sıfırı tam olarak disk
merkezinde olmayabilir. Touch-point kalibrasyon diyaloğunu açın,
ruloyu bilinen bir yüzeye tam değecek şekilde ilerletin, DRO'yu
okuyun, değerleri girip uygulayın. Tam prosedür ve Challenger Rr
yardımcısı için Makine sekmesindeki "Kalibrasyon - en önemli adım"
bölümüne bakın. Ruloyu değiştirdiğinizde veya makineyi yeniden
home'ladığınızda yeniden kalibre edin.


4. BİR TAKIMIN STEP DOSYASINI SONRADAN DEĞİŞTİRME
----------------------------------------------------------------
Takımlar... -> listeden takıma tıklayın -> yeni STEP'e Gözat ->
Değişiklikleri Kaydet (ID'yi aynı tutun). Yeni dosya
tool_geometry/<id>.STEP'i otomatik değiştirir. Sonrasında Radius'u
yeniden hesaplayın ve Rr'yi yeniden kontrol edin (2. adımdaki
kural).


5. TAKIMLARI BAŞKA BİR PC İLE PAYLAŞMA
----------------------------------------------------------------
Takım penceresinde: Kütüphaneyi Dışa Aktar... tek bir .zip yazar
(tüm takımlar + STEP dosyaları); Kütüphaneyi İçe Aktar... geri
okur, geometriyi kopyalar ve birleştirir (aynı ID'lileri
değiştirmeden önce sorar). Geometri ID ile taşınır, yani hiçbir şey
yeniden eklenmez - ama Rr makineye özeldir, içe aktardıktan sonra
kalibrasyonu yeniden kontrol edin.


YENİ BİR TAKIM İÇİN HIZLI KONTROL LİSTESİ
----------------------------------------------------------------
  [ ] ID girildi, STEP seçildi, Ekle/Kaydet (ID ile otomatik kopya)
  [ ] STEP'ten yarıçap hesapla  -> Radius doldu
  [ ] Rr ayarlandı (kalibre, ya da başlangıç için = Radius; asla < Radius)
  [ ] Takımı seç -> 3B rulo doğru görünüyor
  [ ] Bu makine için touch-point kalibrasyonu yapıldı
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
                 PLC memory is limited (max lines per program), so
                 enable PLC Mode (Machine tab) to reduce points.
                 Tick "Auto-tune tolerance to line limit" and set a
                 Target Max Lines to have the tolerance fitted to
                 your budget automatically on export — it never
                 lowers clearance below the normal G-code path
                 (it warns if the target can't be met safely).

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
                  PLC belleği kısıtlıdır (program başına azami satır),
                  bu yüzden nokta azaltmak için PLC Modunu (Makine
                  sekmesi) açın. "Toleransı satır limitine otomatik
                  ayarla" kutusunu işaretleyip Hedef Azami Satır girin;
                  tolerans dışa aktarımda bütçenize otomatik oturtulur —
                  clearance normal G-code yolunun altına asla düşürülmez
                  (hedef güvenle karşılanamazsa uyarır).

                  TARET / TAKIM TABLOSU: Her SCL reçetesinin başlığına
                  taret düzeni (yuva→takım-kodu, yuva sayısı, açılar)
                  yazılır — PLC takım eşlemesini artık HMI'dan değil
                  REÇETEDEN alır. Makine sekmesindeki "Taret / Takım
                  Tablosu" bölümünde 4 yuvayı ayarlayın (kod 0 = boş);
                  "Takım kütüphanesinden doldur" ID'lerden kodları çeker
                  (T0103 → 103). "Açıları otomatik" işaretliyse açıları
                  PLC eşit aralıkla hesaplar, değilse ölçülen açıları
                  elle girin. Programda kullanılan bir takım hiçbir yuvaya
                  eşlenmemişse dışa aktarma ENGELLENİR (yanlış takıma
                  dönmeyi önler). Bu değişiklikten ÖNCE üretilmiş eski
                  reçeteler geçersizdir → yeniden üretin.

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
            ("help_tab_tools",   "tools"),
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
