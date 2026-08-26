# Açık sorular — TODO #99 (P2 köşe noktaları) + #100 (çıkış yolu noktaları)

**Tarih:** 2026-08-26
**Neden var:** İki yeni madde planlandı ama şu sorular cevaplanmadan kod yazılamaz.
Detay: `TODO.md` → #99 ve #100.
**Not:** 1. ve 2. sorular #99 içindir; 2. soruya "PLC tarafı çözüyor" cevabı gelirse
#99 tamamen gereksiz hale gelebilir — önce PLC ekibine sormak mantıklı.

---

## BÖLÜM 1 — OPERATÖRE SORULACAKLAR

### Soru 1 — P2 köşesi tam olarak nasıl kötü çalışıyor? (#99)*A, dolayısıyla bazen nokta sayısını azaltabilmek istiyorum. şuanki yapıda nokta sayısını azaltabilmenin tek yolu daha fazla pasoya sahip olup paso başına düşen nokta sayısını düşürmek*

P2'deki yuvarlatma (fillet) bölgesinde ne görüyorsun:

- (a) Makine her noktada duraklıyor / yavaşlıyor, hareket kesik kesik mi?
- (b) Parçanın yüzeyinde iz mi kalıyor?
- (c) Sadece yavaş mı, süre mi uzuyor?

Ayrıca: **köşe kaç noktayla düzgün çalışıyor?** (Bugün mesafeye göre otomatik
hesaplanıyor, tipik olarak onlarca nokta oluyor.)

> **Ne değiştirir:** Cevap (a) ise nokta sayısını azaltmak doğru çözüm. Cevap (b) ise
> sorun nokta sayısı değil, ilerleme hızının sürekliliği — bambaşka bir iş. Ayrıca
> PLC ekibine soracağımız soru (Bölüm 2, Soru 1) bunu CAM tarafında hiçbir şey
> değiştirmeden çözebilir.

### Soru 2 — Nokta azaltma güvenliği (#99)*C şıkkı: bunun nokta sayısıyla alakası yok. parçaya dalma tamamen x değeriyle alakalı noktanın. oluşan noktalar hiçbir zaman clearence değerinden daha az olucak şekilde bir x eksen mesafesine sahip olmamalı kalıpla. Bu da şuanki güvenlik önlemlerimizle sağlanıyor olması lazım. araştırmanı öneririm*

P2 köşesindeki nokta sayısını çok azaltırsan, noktalar arasındaki düz çizgi köşeyi
kesip parçaya dalabilir (gouge). Böyle bir durumda program ne yapsın: 

- (a) Reddetsin, güvenli olan nokta sayısını korusun mu?
- (b) Güvenli olabildiği kadar azaltıp "şu kadarına indirebildim" diye sana mı söylesin?

> **Ne değiştirir:** Varsayılan davranış. Bu maddenin tek gerçek riski bu — az nokta
> = uzun kiriş = köşeyi kesme.

---

### Soru 3 — Noktalara ayrı ayrı HIZ da vermek istiyor musun? (#100)*plc tarafı bunu destekleyebiliyosa aslında bu özelliğe de sahip olmak isterim. şuan contact zone yapımız var ve seviyoruz. dolayısıyla farklı hızlardaki konumları da kullanırdık*

Pasın P2'den sonraki (çıkış) kısmındaki noktaları elle koyacağız. Her nokta için
**ayrı ilerleme hızı (feed)** da vermek ister misin — örneğin sac kenarına
yaklaşırken yavaşlasın — yoksa tüm çıkış için tek hız yeterli mi? 

> **Ne değiştirir:** Tabloya bir sütun daha eklenir ve verinin saklanma şekli
> değişir. Reçete formatı her satırda ayrı hız taşıyabiliyor, yani mümkün. Ama
> sonradan eklemek zor — baştan bilmek gerek.

### Soru 4 — Kaç nokta yeter? (#100) *Bunun için bi üst sınır belirlemek zorunda mıyız. büyük ihtimal 10 nokta kullanırlar ama daha fazla kullanmak isterlerse tekrardan arttırmaya çalışmakla uğraşmak da istemem*

P2 ile pasın bitiş noktası arasında şekli istediğin gibi vermek için kaç noktaya
ihtiyacın var? **5 nokta yeter mi, daha fazlası mı lazım?** 

> **Ne değiştirir:** Üst sınırı belirler. Çok fazla nokta hem elle yönetilemez hem de
> makineye zaten gitmez (sadeleştirme siliyor). Az olursa şekli veremezsin.

### Soru 5 — Elle nokta koyunca otomatik hesaplar kapanacak — nasıl olsun? (#100)*B şıkkı. yani manual'e almaktan bahsediyoruz aslında. *

Bir operasyona elle nokta koyduğunda, o operasyon için **otomatik reach (sacı takip
et) ve progressive açı** hesabı artık çalışamaz — ikisi aynı geometriyi çekiştirir.
(Bunu sen zaten söylemiştin, doğrusu bu.) Program bunu nasıl yapsın:

- (a) Kendisi kapatsın ve sana haber versin mi?
- (b) Sen kapatana kadar nokta koymana izin vermesin mi?
- (c) Kapatmasın, sadece uyarsın mı?

> **Ne değiştirir:** Hâlihazırda çalışan bir programın şeklinin elinde değişebileceği
> an tam olarak burası. Sessiz olmaması şart.

### Soru 6 — Ters (reverse) paslarda ne olsun? (#100) *Bunu henüz düşünmemiştim. diğerini implament ederken back pass ve ya reverse passler için de makul bi şeyler düşünür müsün*

Ters yönlü paslarda takım mandrele diğer taraftan giriyor ve o **giriş bacağını
bilerek DÜZ tutuyoruz** (TODO #82 kararı). Ters bir operasyona elle nokta koyarsan:

- (a) Bu noktalar yok mu sayılsın?
- (b) Şekil çıkış tarafına mı taşınsın?

> **Ne değiştirir:** #82'deki kararla çakışmasın. Şimdi karar verilmezse sonradan
> sürpriz olarak çıkar.

---

## BÖLÜM 2 — PLC EKİBİNE SORULACAKLAR (İngilizce, doğrudan gönderilebilir)

> Bunlar bilgi sorusu — bir değişiklik talebi değil. Özellikle Soru 1 önemli:
> cevabı "evet, harmanlıyoruz" ise #99'u hiç yapmamıza gerek kalmayabilir.

### Q1 — Velocity blending across short LINEAR segments: *axis decelerate to a stop at every point*

The corner at P2 (the fillet) is emitted as a run of short consecutive `CMD=1`
LINEAR moves. Our operator reports that this region runs slow and rough.

**Does your motion package blend velocity between consecutive short linear moves
(look-ahead / cornering tolerance), or does the axis decelerate to a stop at every
point? If blending exists, is it configurable, and what is the current setting?**

Why we ask: if blending is available, we do not need to change the CAM output at
all. If it is not, our only lever is to emit fewer points on the corner — which
costs corner accuracy. We would rather not pay that if the controller can solve it.

### Q2 — Circular interpolation: *linear point-to-point is the permanent contract*

Section 5 of `CAM_INTERFACE_SPEC.md` lists the command set as RAPID(0) / LINEAR(1) /
TOOL_CHANGE(10) / SPINDLE_ON(20) / SPINDLE_OFF(21) / DWELL(30) / PROGRAM_END(99) —
every motion is a linear point-to-point move.

**Is there any prospect of a circular-interpolation command (a G2/G3 equivalent,
e.g. `CMD=2/3` with centre or radius carried in `Param`), or is linear
point-to-point the permanent contract?**

Why we ask: a single arc line would replace 10–40 chord lines at every pass corner —
smoother motion and a much smaller recipe at the same time. We are not asking you to
build it now; we want to know whether to design around it or design it out.

### Q3 — Recipe capacity above 1000 lines : *1000 is a hard ceiling for PLC memory and its not dynamic*

Our exporter declares `capacity = max(line_count, 1000)`, rounded up to a whole
number of chunk arrays, and writes only `LineCount` lines. The remaining elements
are declared but never assigned (the padding), `CMD=99` marks the end, and the
header checksum deliberately covers emitted lines only — never the padding.

**Can the recipe DB be declared LARGER than 1000 lines on your side (e.g. 2000 as
20 × 100), or is 1000 a hard ceiling for PLC memory?**

Why we ask: we have it recorded both ways — as "array size is dynamic, the user
decides" and as a hard 1000-line limit — and we would like to settle it before it
bites someone.

---

## Cevaplar geldikten sonra

- Soru 1 + Bölüm 2 Q1 → #99 yapılacak mı, yoksa PLC tarafında mı çözülüyor, belli olur.
- Soru 2 → #99'un varsayılan güvenlik davranışı.
- Soru 3 → #100'ün veri modeli (nokta başına hız sütunu var mı yok mu).
- Soru 4, 5, 6 → #100'ün UI ve mod kuralları.
- Bölüm 2 Q2 → uzun vadeli: köşe pürüzlülüğünün gerçek çözümü.
- Bölüm 2 Q3 → `TODO.md` #99 içindeki açık not kapanır.

Cevaplar gelince `TODO.md` #99/#100 maddelerindeki "Open questions" bölümleri
"DECIDED (user, tarih)" olarak güncellenmeli.
