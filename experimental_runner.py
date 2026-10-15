"""Read-only experimental performance job, independent from official FINAL delivery.

No AI calls, historical backfill, consensus changes, or Telegram sends. Future
PROSPECTIVE experiments require a matching source GitHub pre-kickoff commit.
"""
from __future__ import annotations

from pathlib import Path

from config import DATA_DIR, REPORT_DIR, SEASON, WEEKLY_REPORTS_FILE
from experimental_performance import METHODS, build_experimental_season, build_experimental_week
from github_provenance import GitHubPreKickoffEvidence
from performance_bot import _load_json, _save_json
from performance_engine import matchday_resolution, merge_latest_results
from result_provider import FootballDataResultProvider, ResultProviderError
from source_loader import load_prediction_archive, SourceLoadError

EXPERIMENTAL_WEEKLY = DATA_DIR / 'experimental_weekly_reports.json'
EXPERIMENTAL_SEASON = DATA_DIR / 'experimental_season_performance.json'
EXPERIMENTAL_OVERVIEW = REPORT_DIR / 'experimental_performance.md'
OFFICIAL_WEEKLY = WEEKLY_REPORTS_FILE


def _summary(season: dict) -> str:
    lines = [f'# Şampiyonlar Ligi — Deneysel Performans ({season["season"]})', '',
             '**Yalnızca doğrulanmış maç öncesi PROSPECTIVE tahminler.** '
             'Bu rapor resmî ortak kararı veya Kicktipp turnuva puanını değiştirmez.', '',
             'Kicktipp 8/6/4/0 · Maç sonuçları: doğrulanmış 90 dakika.', '',
             '| Yöntem | Maç fırsatı | Geçerli tahmin | Kapsam | Doğru 1-X-2 | Tam skor | Puan | Ort. puan |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key in METHODS:
        v = season['methods'][key]
        lines.append(f'| {v["label"]} v{v["version"]} | {v["opportunities"]} | '
                     f'{v["valid_predictions"]} | %{v["coverage_pct"]} | '
                     f'{v["outcome"]} (%{v["outcome_pct"]}) | {v["exact"]} | '
                     f'{v["points"]} | {v["avg"]} |')
    lines.extend(['', '## Aynı maçlar üzerinden karşılaştırma', '',
                  'Puanlar yalnızca her iki yöntemin de geçerli tahmininin bulunduğu '
                  'ortak maçlarda hesaplanmıştır.', ''])
    for key in METHODS:
        v = season['methods'][key]
        lines.extend([f'### {v["label"]} v{v["version"]}', '',
                      '| Karşılaştırılan | Ortak maç | Deneysel puan | Karşılaştırılan puan | Daha iyi / eşit / geride |',
                      '|---|---:|---:|---:|---:|'])
        for label, comp in sorted(v['head_to_head'].items()):
            lines.append(f'| {label} | {comp["common_matches"]} | {comp["experimental_points"]} | '
                         f'{comp["comparison_points"]} | {comp["experimental_better"]} / '
                         f'{comp["equal"]} / {comp["comparison_better"]} |')
        lines.extend(['', '**Tahmin yok / doğrulanamadı:** ' + (
            ', '.join(f'{k}={n}' for k, n in sorted(v['failure_reasons'].items())) or 'Yok'), ''])
    lines.extend(['Bu gözlemler küçük örneklemde başarı üstünlüğü kanıtlamaz. '
                  'BACKTEST ve doğrulanamayan kaynak kayıtları başarı puanına dahil edilmemiştir.', ''])
    return '\n'.join(lines)


def prepare_experimental_reports() -> int:
    existing = _load_json(EXPERIMENTAL_WEEKLY, {})
    if not isinstance(existing, dict) or any(v.get('season') != SEASON for v in existing.values()):
        raise RuntimeError('Experimental archive season/schema mismatch; manual review required')
    official = _load_json(OFFICIAL_WEEKLY, {})
    # The official bot already establishes 90-minute results and FINAL. Do not
    # spend another GitHub/provider request on idle days or old weeks.
    due = {str(md) for md, r in official.items()
           if isinstance(r, dict) and r.get('status') == 'FINAL'
           and r.get('season') == SEASON and int(md) > (2 if SEASON == '2026/27' else 0)
           and str(md) not in existing}
    if not due:
        print('ℹ️ No new official FINAL eligible for experiment; zero provider/GitHub calls')
        return 0
    try:
        predictions = load_prediction_archive()
        fixtures_by_week = FootballDataResultProvider().get_matches_by_matchday()
    except (SourceLoadError, ResultProviderError) as exc:
        print(f'⚠️ Experimental evaluation source unavailable: {exc}')
        return 1
    # Identical, trusted fixture completion logic as the official report.
    status_map = {str(f['id']): f for fixtures in fixtures_by_week.values() for f in fixtures if f.get('id') is not None}
    graded = merge_latest_results(predictions, status_map)
    checker = GitHubPreKickoffEvidence()
    new = 0
    for md, fixtures in sorted(fixtures_by_week.items()):
        key = str(md)
        if key not in due or key in existing:
            # First FINAL is immutable. Never rerun/backfill pre-match predictions
            # or rewrite a delivered historical evaluation.
            continue
        state = matchday_resolution(fixtures, graded)
        if not state['final']:
            continue
        report = build_experimental_week(md, fixtures, predictions, checker)
        if report is None:
            continue
        existing[key] = report
        new += 1
        counts = ', '.join(f'{method}: {report["methods"][method]["valid_predictions"]}' for method in METHODS)
        print(f'🧪 Experimental matchday {md} FINAL staged ({counts}); no Telegram.')
    if not new:
        print('ℹ️ No NEW experimental FINAL; existing experimental archive preserved')
        return 0
    season = build_experimental_season(existing)
    _save_json(EXPERIMENTAL_WEEKLY, existing)
    _save_json(EXPERIMENTAL_SEASON, season)
    EXPERIMENTAL_OVERVIEW.parent.mkdir(parents=True, exist_ok=True)
    EXPERIMENTAL_OVERVIEW.write_text(_summary(season), encoding='utf-8')
    print(f'✅ {new} new experimental FINAL; no official FINAL or Telegram modified')
    return 0


if __name__ == '__main__':
    raise SystemExit(prepare_experimental_reports())
