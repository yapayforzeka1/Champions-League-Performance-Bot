# Champions League Performance Bot

UEFA Champions League 2026/27 haftalık maç tahmin sisteminin ürettiği AI tahminlerini **bağımsız ve yeniden hesaplanabilir** biçimde değerlendiren performans sistemi.

## Mimari

```text
Prediction Repo
    │
    └── match_predictions.json  (salt okunur kaynak)
              │
              ▼
Champions-League-Performance-Bot
    ├── source_loader.py        → tahmin arşivini GitHub'dan okur
    ├── result_provider.py      → güncel CL maç durumlarını alır
    ├── consensus_engine.py     → strict-majority consensus
    ├── performance_engine.py   → 5/3/0 puanlama + Matchday finalizasyonu
    ├── weekly_report.py        → haftalık/sezon görselleri
    ├── telegram_report.py      → Telegram gönderimi
    └── performance_bot.py      → ana orkestrasyon
```

## Önemli kurallar

- Winner consensus yalnızca **benzersiz strict majority** ile oluşur.
- Exact-score consensus da bağımsız olarak **strict majority** ister.
- Tam skor = **5 puan**.
- Doğru sonuç, yanlış skor = **3 puan**.
- Doğru beraberlik tahmini = **5 puan**.
- Yanlış = **0 puan**.
- Consensus yoksa consensus puanı verilmez.
- Tahmin arşivinde kaydı olmayan maç **0 puan değildir**; `UNAVAILABLE` olarak raporlanır.
- Matchday raporu ilk uygun saatte kilitlenmez. Tüm planlanan maçlar `EVALUATED`, `UNAVAILABLE` veya terminal ertelenme/iptal durumuna geldiğinde **FINAL** olur.
- Final rapor bir Matchday için yalnızca bir kez Telegram'a gönderilir.
- Model puanı yanında `coverage_pct` ve başarısız çağrı sayısı da tutulur; API 429 yaşayan modelin düşük puanı tek başına performans sonucu sayılmaz.

## GitHub Secrets

Performance repo'da aşağıdaki Actions secrets tanımlanmalıdır:

- `FOOTBALL_DATA_API_KEY`
- `ANALYSIS_TELEGRAM_BOT_TOKEN`
- `ANALYSIS_TELEGRAM_CHAT_ID`
- `PREDICTION_REPO_TOKEN` — yalnızca prediction repo private ise gerekli. Token'ın prediction repo için en az Contents: Read erişimi olmalıdır.

İsterseniz repository variable olarak `PREDICTION_REPO` değerini değiştirebilirsiniz. Varsayılan:

`yapayforzeka1/Haftalik-Mac-Tahmini`

## Çalışma döngüsü

GitHub Actions her 5 dakikada bir çalışır:

1. Prediction repo'daki ham `match_predictions.json` okunur.
2. football-data.org üzerinden güncel CL maç durumları alınır.
3. Arşivlenmiş tahminler yeniden puanlanır.
4. Her Matchday için `PENDING` / `FINAL` durumu belirlenir.
5. FINAL Matchday için haftalık rapor oluşturulur.
6. Sezon toplamı yeniden hesaplanır.
7. Haftalık ve sezon görselleri Telegram'a gönderilir.
8. JSON arşivleri Performance repo'ya commit edilir.

## Test

```bash
python -m unittest discover -s tests -v
```

## Not

Bu repo prediction botunun `weekly_reports.json` dosyasına güvenmez. Böylece önceki sistemde görülen, ilk rapor snapshot'ının erken oluşturulup sonradan gelen maç sonuçlarını içermemesi problemi burada tekrar oluşmaz.
