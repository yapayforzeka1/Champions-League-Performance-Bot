from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

from config import SEASON, TELEGRAM_ENABLED, DATA_DIR, SEASON_PERFORMANCE_FILE, WEEKLY_REPORTS_FILE
from performance_engine import _provider_regular_score, archived_consensus, build_season_snapshot, build_weekly_snapshot, matchday_resolution, merge_latest_results
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
            # Render the original published pre-match decision, never a post-hoc vote.
            display_record["consensus"] = copy.deepcopy(archived_consensus(record))
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


# An explicit, committed user-approved lock for 2026/27 reports already delivered
# via Telegram before the GitHub archive save failed. Never infer a new send
# from a missing new-format archive when this receipt exists.
DELIVERY_LOCK_FILE_NAME = "kicktipp_delivery_locks.json"
DELIVERY_BATCH_FILE_NAME = "kicktipp_delivery_batch.json"
DELIVERY_PARTS = ("weekly", "season")


def _run_key() -> str:
    """Unique per GitHub run *attempt*. A re-run must not reuse a send intent."""
    return os.getenv("PERFORMANCE_RUN_KEY") or "local-only"


def prepare_reports() -> int:
    """Read official scores and frozen predictions, render + stage, NEVER send."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    weekly_reports = _load_json(WEEKLY_REPORTS_FILE, {})
    legacy_reports = _load_json(DATA_DIR / "weekly_reports.json", {})
    lock_path = DATA_DIR / DELIVERY_LOCK_FILE_NAME
    locks = _load_json(lock_path, {})
    if os.getenv("REQUIRE_DELIVERY_LOCKS", "").lower() == "true":
        if not lock_path.is_file() or not all(
            isinstance(locks.get(str(md)), dict) and all(locks[str(md)].get(part) == "SENT" for part in DELIVERY_PARTS)
            for md in (1, 2)
        ):
            raise RuntimeError("Historical 1/2 matchday Telegram delivery locks missing; refusing unsafe run")
    if any(v.get("season") not in {None, SEASON} for v in weekly_reports.values()):
        raise RuntimeError("Season mismatch: archive existing data before a new season; no overwrite")

    try:
        predictions = load_prediction_archive()
        by_matchday = FootballDataResultProvider().get_matches_by_matchday()
    except (SourceLoadError, ResultProviderError) as exc:
        print(f"❌ Performans botu veri hazırlığı başarısız: {exc}")
        return 1

    status_map = {str(m.get("id")): m for rows in by_matchday.values() for m in rows if m.get("id") is not None}
    graded = merge_latest_results(predictions, status_map)
    created = 0

    for matchday, fixtures in sorted(by_matchday.items()):
        if not fixtures:
            continue
        resolution = matchday_resolution(fixtures, graded)
        key = str(matchday)
        previous = weekly_reports.get(key)
        legacy_final = legacy_reports.get(key) if legacy_reports.get(key, {}).get("status") == "FINAL" else None
        if previous:
            from performance_engine import SCORING_RULE
            if previous.get("status") != "FINAL" or previous.get("scoring_rule") != SCORING_RULE:
                raise RuntimeError(f"Matchday {matchday}: existing archive needs manual review; untouched")
            _warn_if_final_changed(previous, fixtures, resolution)
            if any((previous.get("delivery") or {}).get(part) != "SENT" for part in DELIVERY_PARTS):
                print(f"⚠️ Matchday {matchday}: saved FINAL delivery is pending/uncertain; "
                      "manual review required, no automatic retry")
            continue
        if not resolution["final"]:
            print(f"⏳ Matchday {matchday}: PENDING ({resolution['pending_matches']} unresolved, "
                  f"{resolution['postponed_matches']} postponed/cancelled).")
            continue

        if legacy_final:
            _warn_if_final_changed(legacy_final, fixtures, resolution)
            old_scores = {str(m.get('match_id')): m.get('verified_score')
                          for m in legacy_final.get('matches', []) if m.get('verified_score') is not None}
            new_scores = {str(m.get('match_id')): m.get('verified_score')
                          for m in resolution.get('matches', [])}
            if any(new_scores.get(mid) != score for mid, score in old_scores.items()):
                print(f"⚠️ Matchday {matchday}: legacy FINAL scores differ; skipped for manual review")
                continue

        snapshot = build_weekly_snapshot(graded, matchday, resolution)
        if legacy_final:
            snapshot["migrated_from_legacy_final"] = True
        # A confirmed historic Telegram receipt is authoritative even if
        # earlier archive writes failed. Never deliver the same report twice.
        lock = locks.get(key, {})
        if legacy_final or (isinstance(lock, dict) and all(lock.get(p) == "SENT" for p in DELIVERY_PARTS)):
            snapshot["delivery"] = {p: "SENT" for p in DELIVERY_PARTS}
            snapshot["delivery_source"] = "legacy_final" if legacy_final else "confirmed_telegram_receipt"
        else:
            snapshot["delivery"] = {p: "PENDING" for p in DELIVERY_PARTS}
            snapshot["prepared_run_key"] = _run_key()

        render_snapshot = _prepare_render_records(snapshot, graded)
        render_weekly_image(render_snapshot)
        weekly_reports[key] = snapshot
        _save_json(WEEKLY_REPORTS_FILE, weekly_reports)
        created += 1
        print(f"✅ Matchday {matchday}: Kicktipp FINAL prepared (delivery {snapshot['delivery']}).")

    if not created:
        print("ℹ️ No NEW final reports to archive")
        return 0
    season = build_season_snapshot(weekly_reports)
    for model in season["models"]:
        season["models"][model]["week_points"] = {
            str(md): int(weekly_reports[str(md)]["stats"]["models"].get(model, {}).get("points", 0))
            for md in season["finalized_matchdays"]
        }
    season["consensus"]["week_points"] = {
        str(md): int(weekly_reports[str(md)]["stats"]["consensus"].get("points", 0))
        for md in season["finalized_matchdays"]
    }
    _save_json(SEASON_PERFORMANCE_FILE, season)
    render_season_image(season)
    print("🏁 Evaluation ready; no Telegram calls in preparation phase.")
    return 0


def reserve_deliveries() -> int:
    """Persist UNCERTAIN before any Telegram API call is allowed.

    Reserve ONLY reports created in the current run, so a prior partial run
    can never be silently retried. The workflow must push both files before
    calling deliver_reserved().
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    reports = _load_json(WEEKLY_REPORTS_FILE, {})
    locks = _load_json(DATA_DIR / DELIVERY_LOCK_FILE_NAME, {})
    key = _run_key()
    batch = {"run_key": key, "items": []}
    for md, report in reports.items():
        if report.get("status") != "FINAL" or report.get("prepared_run_key") != key:
            continue
        if md in locks:
            continue
        for part in DELIVERY_PARTS:
            if report.get("delivery", {}).get(part) != "PENDING":
                continue
            report["delivery"][part] = "UNCERTAIN"
            batch["items"].append({"matchday": md, "part": part})
    if not batch["items"]:
        print("ℹ️ No NEW delivery reservations; previous UNCERTAIN receipts remain untouched")
        return 0
    # First write batch, then frozen delivery state. No Telegram calls until
    # BOTH are successfully pushed by GitHub Actions.
    _save_json(DATA_DIR / DELIVERY_BATCH_FILE_NAME, batch)
    _save_json(WEEKLY_REPORTS_FILE, reports)
    print(f"📌 Reserved {len(batch['items'])} delivery parts; persist to GitHub BEFORE Telegram.")
    return 0


def deliver_reserved() -> int:
    """Send only the current persisted reservation; never retry UNCERTAIN."""
    reports = _load_json(WEEKLY_REPORTS_FILE, {})
    batch = _load_json(DATA_DIR / DELIVERY_BATCH_FILE_NAME, {})
    if batch.get("run_key") != _run_key():
        print("ℹ️ No delivery batch for this run; no send")
        return 0
    items = batch.get("items", [])
    if not items:
        print("ℹ️ No new Telegram report to send")
        return 0
    if not TELEGRAM_ENABLED:
        raise RuntimeError("Telegram disabled: reserved delivery remains UNCERTAIN for manual review")
    lock = _load_json(DATA_DIR / DELIVERY_LOCK_FILE_NAME, {})
    # Check the entire batch before the first external side effect.
    for item in items:
        md, part = str(item["matchday"]), item["part"]
        if part not in DELIVERY_PARTS or md in lock or md not in reports:
            raise RuntimeError("Invalid/previously delivered batch; refusing Telegram send")
        report = reports[md]
        if report.get("prepared_run_key") != _run_key() or report.get("delivery", {}).get(part) != "UNCERTAIN":
            raise RuntimeError("Batch receipt does not match saved UNCERTAIN reservation")
    from config import REPORT_DIR
    for item in items:
        md, part = str(item["matchday"]), item["part"]
        image = REPORT_DIR / f"kicktipp_matchday_{md}_weekly.png" if part == "weekly" else REPORT_DIR / "kicktipp_season_performance.png"
        if not image.is_file():
            raise RuntimeError(f"Reserved report image missing: {image}; no send for this part")
        caption = (f"🏆 Şampiyonlar Ligi — Matchday {md} FINAL Performans · 8/6/4/0"
                   if part == "weekly" else "📊 Şampiyonlar Ligi — Sezon Genel Performans · 8/6/4/0")
        # Status is already UNCERTAIN in *remote GitHub*, so an exception or a
        # failed Git push after send never causes another automatic delivery.
        send_photo(image, caption)
        reports[md]["delivery"][part] = "SENT"
        _save_json(WEEKLY_REPORTS_FILE, reports)
        print(f"✅ Matchday {md} {part}: Telegram sent; receipt ready to persist")
    return 0


def main() -> int:
    # Deliberately safe default: invoking the bot without arguments cannot
    # accidentally transmit an uncommitted historical FINAL.
    return prepare_reports()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kicktipp performance report with durable delivery barrier")
    parser.add_argument("mode", nargs="?", default="prepare", choices=("prepare", "reserve", "deliver"))
    args = parser.parse_args()
    raise SystemExit({"prepare": prepare_reports, "reserve": reserve_deliveries,
                      "deliver": deliver_reserved}[args.mode]())
