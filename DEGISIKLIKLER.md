# Düzeltme turu 1 — değişiklik özeti

| # | Düzeltme | Dosyalar |
|---|---|---|
| 1 | TARİH sütunu boştu: kickoff artık doğrulanmış fikstürden (`utcDate`) alınıyor, `match_utc` yedeği eklendi | `performance_bot.py`, `weekly_report.py` |
| 1a | Saat UTC basılıyordu: Türkiye saatine (UTC+3) çevriliyor | `weekly_report.py` |
| 2 | Düşük kapsama (%50 altı) için Actions uyarısı; puanlara dokunmaz | `performance_engine.py`, `performance_bot.py`, `config.py` |
| 3 | Kanıt commit'i ile vuruş arası süre (`lead_minutes`) saklanıyor, 20 dk altı için uyarı | `github_provenance.py`, `experimental_performance.py`, `experimental_runner.py`, `config.py` |
| 4 | Konsensüs vs model "aynı maçlar" karşılaştırması (yalnızca okuma, FINAL'lere dokunmaz) | `common_match_report.py` (yeni), `.github/workflows/performance_bot.yml` |
| 5a | Eski `kicktipp_delivery_batch.json` silindi | `data/` |
| 5b | Kullanılmayan `REPORT_DELAY_MINUTES`, `PERFORMANCE_STATE_FILE` (+ `performance_state.json`), `MODES`, `import os` kaldırıldı | `config.py`, `consensus_engine.py`, `telegram_report.py` |
| 5c | README "FINAl" yazım hatası | `README.md` |
| 5d | Model renkleri model adına sabitlendi | `weekly_report.py` |
| 6 | Eleme turu maçları lig matchday'ine karışmıyor (`stage` filtresi) | `result_provider.py`, `config.py` |

Testler: 70 mevcut + 17 yeni = 87, hepsi geçiyor. Eski FINAL arşivleri ve PNG'ler değiştirilmedi.
Not: 2 ve 3'ün asıl kaynağı tahmin reposundadır; burada yalnızca tespit/uyarı eklendi.
