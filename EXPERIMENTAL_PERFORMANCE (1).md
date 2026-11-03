# Deneysel Performans — 3. maç haftasından itibaren

Bu modül iki **kayıtlı** deneysel tahmini yalnızca okur:

- `al_score_average_v1` — AL Skor Ortalaması
- `al_most_frequent_score_v1` — En Sık AL Skoru

Kaynak `match_predictions.json` içindeki `experimental_predictions` alanıdır. Beklenen biçim:

```json
{
  "schema_version": 1,
  "classification": "PROSPECTIVE",
  "methods": {
    "al_score_average_v1": {
      "match_id": "12345",
      "method": "al_score_average_v1",
      "version": 1,
      "classification": "PROSPECTIVE",
      "predicted_score": "2-1",
      "predicted_outcome": "HOME",
      "created_at": "2030-10-20T16:40:00+00:00",
      "valid_ai_count": 3,
      "models_used": [{"model": "AL-model", "model_id": "stable/model"}],
      "failure_reason": null,
      "source_votes_sha256": "..."
    },
    "al_most_frequent_score_v1": {"...": "same method-specific fields"}
  }
}
```

Yalnızca resmî **90 dakika** sonucu tamamlanan maç haftaları değerlendirilir.

## Kanıt ve sınıflandırma

1. `PROSPECTIVE` kaydının `created_at` zamanı gerçek başlangıçtan önce olmalı; `match_utc` fikstür zamanı ile uyuşmalı.
2. Kaynak AL oylarının SHA-256 özeti, kayıtlı yöntem özetiyle uyuşmalı.
3. Tahmin, **maçtan önce tarihli bir GitHub commit'inin `match_predictions.json` kopyasında aynı şekilde** bulunmalı. Commit SHA, tarih ve deneysel kayıt SHA-256'sı sonuçta saklanır.
4. Başlangıçtan sonraki kayıt, BACKTEST, hiç tahmin üretmeyen yöntem veya ispatlanamayan tarihsel kayıt **puan alamaz** ve `failure_reasons` içinde izlenir. Başarısızlık **yanlış skor/0 puan** sayılmaz.
5. Git commit tarihleri kullanıcı tarafından belirlenebildiğinden bu kontrol mutlak/kriptografik push-time kanıtı değildir. Tam kanıt gerektiğinde sunucu zamanlı Actions kaydı veya imzalı, değişmez bir zaman damgası ayrıca istenmelidir. Şüpheli kayıtlar insan incelemesine yönlendirilmelidir.

## Raporlama

Ayrı dosyalar (mevcut FINAL ve Telegram akışından **bağımsız**):

- `data/experimental_weekly_reports.json` — yöntem/sürüm ve maç bazında saklanan değişmez haftalık değerlendirme.
- `data/experimental_season_performance.json` — yalnızca yeni deneysel haftaların toplamı.
- `reports/experimental_performance.md` — resmî modeller ve iki deneysel yöntem için **ortak maçlar üzerinden** karşılaştırma.

Aktif puanlama yalnızca Kicktipp **8/6/4/0**. Eski haftalar (2026/27 1–2) deneysel ileriye dönük başarıya dahil edilmez. Deneysel yöntemlerin sonucu **resmî 3/5 ortak kararını, model sıralamasını veya Telegram tahmin görsellerini değiştirmez**. Eski FINAL/Telegram raporlarına yazma işlemi yoktur.

GitHub Actions sırasında bağımsız deneysel değerlendirme başarısız olursa resmî rapor/Telegram akışını durdurmaz; ancak deneysel kaydetme adımı atlanır ve hata logda görünür. AI/API token kullanan model tahmini çalıştırılmaz; kaynak GitHub ve skor API'si **yalnızca okunur**.

Çevrimdışı test: `python -m unittest discover -s tests -v`.
