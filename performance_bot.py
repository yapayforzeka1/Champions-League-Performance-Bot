from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from config import SEASON, TELEGRAM_ENABLED, DATA_DIR, SEASON_PERFORMANCE_FILE, WEEKLY_REPORTS_FILE
from performance_engine import _provider_regular_score, build_season_snapshot, build_weekly_snapshot, matchday_resolution, merge_latest_results
from result_provider import FootballDataResultProvider, ResultProviderError
from source_loader import SourceLoadError, load_prediction_archive
from telegram_report import send_photo
from weekly_report import render_season_image, render_weekly_image


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise RuntimeError(f"Archive unreadable; preserved: {path}") from exc


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _prepare_render_records(snapshot: dict, predictions: dict) -> dict:
    snapshot = dict(snapshot)
    rows = []
    for row in snapshot.get("matches", []):
        if row.get("status") != "EVALUATED":
            continue
        record = predictions.get(str(row["match_id"]))
        if record:
            display_record = copy.deepcopy(record)
            rows.append(display_record)
    snapshot["render_records"] = rows
    return snapshot


def _warn_if_final_changed(previous: dict, fixtures: list[dict], resolution: dict) -> None:
    """Diagnose changes without modifying or re-sending any FINAL report.

    Old snapshots did not store match scores, so score changes in those
    snapshots cannot be reliably reconstructed. Their status changes can
    still be reported. New snapshots store `verified_score` per graded match.
    """
    current_rows = {str(row["match_id"]): row for row in resolution.get("matches", [])}
    provider_rows = {str(match.get("id")): match for match in fixtures}
    differences = []
    for old in previous.get("matches") or []:
        mid = str(old.get("match_id"))
        latest = current_rows.get(mid)
        if latest is None:
            differences.append(f"{mid}: fixture missing")
            continue
        if old.get("status") != latest.get("status"):
            differences.append(f"{mid}: status {old.get('status')} -> {latest.get('status')}")
        saved_score = old.get("verified_score")
        if saved_score is not None:
            current_score = _provider_regular_score(provider_rows[mid])
            if current_score is None or (
                saved_score.get("home"), saved_score.get("away")
            ) != current_score:
                differences.append(f"{mid}: official 90-minute score changed or missing")
    old_ids = {str(row.get("match_id")) for row in previous.get("matches") or []}
    for mid in current_rows.keys() - old_ids:
        differences.append(f"{mid}: new fixture")
    if differences:
        md = previous.get("matchday", "?")
        print(f"⚠️ Matchday {md}: existing FINAL differs from current provider data; "
              f"manual review required ({'; '.join(sorted(set(differences)))}). "
              "Archive preserved; Telegram not resent.")


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    weekly_reports = _load_json(WEEKLY_REPORTS_FILE, {})
    if any(v.get('season') not in {None, SEASON} for v in weekly_reports.values()):
        raise RuntimeError('Season mismatch: archive existing data and use a new DATA_DIR; no history overwritten.')

    try:
        predictions = load_prediction_archive()
        provider = FootballDataResultProvider()
        by_matchday = provider.get_matches_by_matchday()
    except (SourceLoadError, ResultProviderError) as exc:
        print(f"❌ Performans botu veri hazırlığı başarısız: {exc}")
        return 1

    status_map = {str(m.get("id")): m for rows in by_matchday.values() for m in rows if m.get("id") is not None}
    graded = merge_latest_results(predictions, status_map)

    for matchday, fixtures in sorted(by_matchday.items()):
        if not fixtures:
            continue
        resolution = matchday_resolution(fixtures, graded)
        key = str(matchday)
        previous = weekly_reports.get(key)
        if previous and previous.get("status") == "FINAL":
            # Never revise historic FINAL receipts, scores, or delivery state.
            # Diagnostics are read-only and cannot trigger a second Telegram.
            _warn_if_final_changed(previous, fixtures, resolution)
            delivery = previous.get("delivery")
            if isinstance(delivery, dict) and any(
                delivery.get(part) != "SENT" for part in ("weekly", "season")
            ):
                print(f"⚠️ Matchday {matchday}: incomplete/uncertain prior FINAL delivery; "
                      "manual review required; no automatic resend.")
            continue
        if not resolution["final"]:
            print(f"⏳ Matchday {matchday}: PENDING ({resolution['pending_matches']} maç çözülmedi).")
            continue

        snapshot = previous or build_weekly_snapshot(graded, matchday, resolution)
        snapshot.setdefault('delivery', {'weekly':'PENDING','season':'PENDING'})
        render_snapshot = _prepare_render_records(snapshot, graded)
        weekly_image = render_weekly_image(render_snapshot)
        weekly_reports[key] = snapshot
        _save_json(WEEKLY_REPORTS_FILE, weekly_reports)

        season = build_season_snapshot(weekly_reports)
        # Keep per-matchday points in season image data for visual weekly columns.
        for model in season["models"]:
            season["models"][model]["week_points"] = {
                str(md): int(weekly_reports[str(md)]["stats"]["models"].get(model, {}).get("points", 0))
                for md in season["finalized_matchdays"]
            }
        season["consensus"]["week_points"] = {
            str(md): int(weekly_reports[str(md)]["stats"]["consensus"]["points"])
            for md in season["finalized_matchdays"]
        }
        _save_json(SEASON_PERFORMANCE_FILE, season)
        season_image = render_season_image(season)

        for part, image, caption in [
            ('weekly', weekly_image, f'🏆 Şampiyonlar Ligi — Matchday {matchday} FINAL Performans · 5/5/3/0'),
            ('season', season_image, '📊 Şampiyonlar Ligi — Sezon Genel Performans · 5/5/3/0')]:
            if snapshot['delivery'][part] == 'SENT' or not TELEGRAM_ENABLED:
                continue
            snapshot['delivery'][part] = 'UNCERTAIN'
            _save_json(WEEKLY_REPORTS_FILE, weekly_reports)
            send_photo(image, caption)
            snapshot['delivery'][part] = 'SENT'
            _save_json(WEEKLY_REPORTS_FILE, weekly_reports)
        print(f"✅ Matchday {matchday} FINAL raporu hazırlandı ve gönderildi.")

    print("🏁 Performance Bot tamamlandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
