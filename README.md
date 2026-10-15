# Champions League Performance Bot

UEFA Champions League 2026/27 tahmin arşivini bağımsız biçimde değerlendirir, haftalık ve sezon geneli performans görsellerini Telegram'a gönderir.

## Temel kurallar

- Puanlama: tam skor **8P**, doğru 1-X-2 ve doğru gol farkı (farklı beraberlik dahil) **6P**, yalnız doğru 1-X-2 **4P**, yanlış sonuç **0P**.
- Başarılı her AI tahmini consensus oluşup oluşmamasından bağımsız puanlanır.
- API/model hatası veya üretilemeyen tahmin **0 puan değildir**; yalnızca coverage oranını düşürür.
- Consensus için en az **3 başarılı AI tahmini** gerekir. Ardından benzersiz strict-majority kuralı uygulanır.
- Consensus performansı bireysel AI performansından ayrı tutulur ve aynı 8/6/4/0 sistemiyle değerlendirilir.
- Tahmin kaydı olmayan bitmiş maç `UNAVAILABLE` olarak tutulur; AI başarısızlığına 0 puan yazılmaz.
- Ertelenen/iptal edilen veya doğrulanmış 90 dakika skoru bulunmayan maçlar, manuel inceleme olmadan FINAL kabul edilmez.
- FINAL rapor bir Matchday için yalnızca bir kez Telegram'a gönderilir.

## Rapor zamanı ve gönderim güvenliği

GitHub Actions her gün 01:30 UTC (Türkiye 04:30) zamanlanmış kontrol yapar ve elle tetiklenebilir. Yapay zekâ tahmin API'leri yeniden çağrılmaz; kaynak tahminler okunur, football-data.org üzerinden resmi 90 dakika sonuçları kontrol edilir. Şampiyonlar Ligi'nin ilk sekiz lig maç haftası için üretim workflow'u **18 maçlık fikstürü** bekler.

Telegram gönderimi üç ayrı komuta ayrılmıştır:

1. `python performance_bot.py prepare` — puanları, haftalık/sezon arşivini ve görselleri hazırlar; **Telegram göndermez**. Workflow bu değişiklikleri önce GitHub'a kaydeder.
2. `python performance_bot.py reserve` — **yalnız o çalışmada yeni hazırlanmış** raporlar için `UNCERTAIN` teslim durumunu kalıcılaştırır. Workflow bu durumu Telegram'dan **önce** GitHub'a kaydeder.
3. `python performance_bot.py deliver` — yalnız geçerli çalışmanın kalıcı rezervasyonlarını gönderir; başarılı gönderimlerin `SENT` durumunu kaydeder.

GitHub'a rezervasyon kaydı yazılamazsa Telegram gönderimine geçilmez. Telegram veya son GitHub kaydı hata verirse `UNCERTAIN` durumundaki raporlar **otomatik yeniden gönderilmez**, manuel inceleme gerekir. Bu, bazı iletilerin teknik hata nedeniyle hiç gitmemiş olmasına rağmen otomatik yeniden gönderilememesi anlamına gelebilir; mükerrer gönderimi önlemek için bilinçli güvenlik tercihidir.

`data/kicktipp_delivery_locks.json` dosyası, kullanıcının daha önce Telegram'da aldığını doğruladığı **1. ve 2. hafta raporları** için tek seferlik tekrar-gönderim kilididir. Bu dosya mutlaka kodla birlikte GitHub'a yüklenmelidir. Geçmiş FINAl'ler, yayımlanmış ortak kararlar, AI tahminleri ve önceki PNG raporları değişmez. Yeni rapor için ayrıca açık onay ve veri doğrulaması gerekir.

## Görsellerin kaydı

`.gitignore` eski genel rapor görsellerini yok sayar. Workflow yalnızca `reports/kicktipp_*.png` dosyalarını `git add -f` ile arşive ekler; geçmiş `reports/matchday_1_weekly.png` gibi görsellere dokunmaz.

## Telegram çıktısı

FINAL Matchday'de iki PNG gönderilir:

1. Haftalık AI performansı: toplam puan, ortalama /8, 8P/6P/4P/0P dağılımı ve coverage; ayrıca consensus performansı.
2. Sezon geneli AI performansı: aynı metriklerin tüm FINAL Matchday'ler üzerinden toplamı.

## Mistral

Bu repo Mistral dahil modelleri çağırmaz; prediction repo'nun ürettiği `match_predictions.json` verisini değerlendirir. Mistral API/entegrasyon hatası burada 0 puan sayılmaz ve coverage ile görünür hale gelir. Mistral çağrısının düzeltilmesi veya alternatif modelle değiştirilmesi prediction repo tarafında yapılmalıdır.

## Secrets

- `FOOTBALL_DATA_API_KEY`
- `ANALYSIS_TELEGRAM_BOT_TOKEN`
- `ANALYSIS_TELEGRAM_CHAT_ID`
- `PREDICTION_REPO_TOKEN` — prediction repo private ise Contents: Read erişimi gerekir.

Varsayılan prediction repo: `yapayforzeka1/Haftalik-Mac-Tahmini`.

## Test

```bash
python -m unittest discover -s tests -v
```

## Tek aktif puanlama ve tarihî FINAL güvenliği

Aktif puanlar `data/kicktipp_weekly_reports.json` ve `data/kicktipp_season_performance.json` içinde 8/6/4/0 olarak tutulur. Eski `data/weekly_reports.json`, `data/season_performance.json` ve önceki rapor görselleri tarihî delil olarak değiştirilmez. Birinci maç haftası eski FINAL ise 90 dakika skoru güncel sağlayıcıdan teyit edildikten sonra yeni standarda göre hesaplanır, Telegram'a tekrar gönderilmez. İkinci hafta ve sonrası ancak maç günü tüm sonuçları netleşince FINAL olur. Eksik maçlardan sahte FINAL üretilmez; kaynak tahminlere dokunulmaz.
