# Performance Bot entegrasyon yaması

Temel kaynak mevcut yerel Champions-League-Performance-Bot-main kopyasıdır.
GitHub yapayforzeka1/Champions-League-Performance-Bot erişimi 404 döndüğünden
canlı deponun aynı sürümde olduğu doğrulanamadı. Canlı sürüm farklıysa bu yamayı
üzerine yazmadan güncel kaynakla karşılaştırın.

Kendi puanlama kuralı aynen korunur: tam skor 5; farklı skorla doğru beraberlik 5;
diğer doğru sonuç 3; yanlış 0. Yanıtsız model puanı None, kapsama ayrı hesaplanır.
Tahmin deposunun 6/5/3/2/0 puanları rapora karıştırılmaz; özel kopyada yeniden hesaplanır.
Kaynak tahminler ve puanlar değiştirilmez, AI çağrısı yapılmaz.
Yeni Qwen 3.8 verisi mevcut QWEN sütununa dahil edilir; kaynak model kimliği korunur.
weekly_report.py görsel dosyası birebir korunmuştur.

Haftalık/season görselleri ayrı gönderim durumlarıyla izlenir. Önceden FINAL olan
eski raporlar otomatik yeniden gönderilmez. Gönderim sonucu belirsizse UNCERTAIN
olarak durur; kullanıcı incelemesi olmadan tekrar gönderilmez. Kesin gönderildiği
doğrulanırsa ilgili delivery alanı SENT, gönderilmediği doğrulanırsa PENDING olarak
arşiv yedeği alındıktan sonra düzeltilebilir. Yanlışlıkla çift rapor riskine karşı
otomatik tekrar yerine bu kontrol tercih edildi. Recovery artifact hata durumunda alınır.

Mevcut ertelenmiş/iptal/askıya alınmış maçlar terminal sayılır, raporda ayrı gösterilir.
Böyle FINAL raporlar sonraki sonuç düzeltmelerinde kendiliğinden yenilenmez.
Bu eski davranış korunmuştur; ek maç sonradan oynanırsa kontrollü rapor revizyonu gerekir.
Rapor hazır oluşunu kontrol etmek için günlük 01:30 UTC (04:30 TSİ) schedule kullanılır;
AI çağrısı yoktur. Aynı haftanın raporu yeniden gönderilmez.
Sezon değişiminde eski arşiv üzerine yazmak yerine hata verir; eski sezonu yedekleyip
farklı DATA_DIR ile yeni sezona geçin. JSON bozulmasında boş arşive dönülmez.

Secrets: ANALYSIS_TELEGRAM_BOT_TOKEN, ANALYSIS_TELEGRAM_CHAT_ID,
FOOTBALL_DATA_API_KEY, PREDICTION_REPO_TOKEN (tahmin deposuna Contents: Read).
Variable: PREDICTION_REPO=gerçek-sahip/Haftalik-Mac-Tahmini.
main dalı kullanılır; farklıysa mevcut workflow'daki PREDICTION_BRANCH güncellenmelidir.
Mevcut bot ve yeni Telegram Bağlantı Kontrolü yalnızca bu projenin bot secrets'ını kullanır.

Yeni testler: kaynağı değiştirmeden bağımsız puanlama, Qwen eşleme, uzatmayı 90 dakika
saymama, haftalık/sezon gönderimi, ikinci çalışmada tekrar etmeme ve bozuk arşivi koruma.
