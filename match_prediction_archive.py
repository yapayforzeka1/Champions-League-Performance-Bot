"""Per-match model prediction archive for official FINAL weeks.

Why: the official weekly archive keeps only aggregate statistics, so a
model's per-match scores could only be recovered from the published PNG.
This module stores, for every FINAL matchday, each model's valid score and
points per match plus the frozen consensus.

Safety rules:
- Read-only with respect to official FINAL reports, scoring and Telegram.
- A week is stored only if re-derived per-model points and valid-prediction
  counts match the official FINAL statistics exactly (integrity check).
- Weeks with source RECONSTRUCTED_FROM_PUBLISHED_PNG (a documented one-off
  backfill) are replaced by native data once it passes the same integrity
  check; native weeks are immutable.
"""
from __future__ import annotations

import re
from typing import Any

from config import DATA_DIR, SEASON, WEEKLY_REPORTS_FILE
from performance_engine import SCORING_RULE, _model_identity, archived_consensus

MATCH_PREDICTIONS_FILE = DATA_DIR / "kicktipp_match_predictions.json"
SCHEMA_VERSION = 1
SOURCE_NATIVE = "NATIVE_PREDICTION_ARCHIVE"
SOURCE_RECONSTRUCTED = "RECONSTRUCTED_FROM_PUBLISHED_PNG"
_SCORE = re.compile(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*")


def _norm_score(value: Any) -> str | None:
    found = _SCORE.fullmatch(str(value or ""))
    return f"{int(found.group(1))}-{int(found.group(2))}" if found else None


def match_entry(item: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """One graded match -> compact entry. Failed/absent votes are stored as null."""
    models: dict[str, Any] = {}
    for vote in record.get("ai_votes") or []:
        name = _model_identity(vote)
        if not name:
            continue
        score = _norm_score((vote.get("result") or {}).get("score")) if vote.get("success") else None
        if score is not None and vote.get("points") is not None:
            models[name] = {"score": score, "points": int(vote["points"])}
        else:
            models.setdefault(name, None)
    consensus = archived_consensus(record)
    cons_points = record.get("consensus_points") if consensus.get("winner_consensus") else None
    return {
        "match_id": str(item["match_id"]),
        "home": item.get("home"),
        "away": item.get("away"),
        "utcDate": item.get("utcDate"),
        "actual": {"home": int(record["actual"]["home"]), "away": int(record["actual"]["away"])},
        "models": models,
        "consensus": None if cons_points is None else {
            "outcome": consensus.get("outcome"),
            "score": _norm_score(consensus.get("score")) if consensus.get("score_consensus") else None,
            "points": int(cons_points),
        },
    }


def week_integrity_problems(matches: list[dict[str, Any]], official_stats: dict[str, Any],
                            skip_models: set[str] | None = None) -> list[str]:
    """Compare per-match sums with the official FINAL statistics; [] means consistent."""
    skip = skip_models or set()
    problems: list[str] = []
    for model, stats in (official_stats.get("models") or {}).items():
        if model in skip or not stats.get("prediction_opportunities"):
            continue
        valid = [m["models"][model]["points"] for m in matches if m["models"].get(model)]
        if sum(valid) != stats.get("points"):
            problems.append(f"{model}: points {sum(valid)} != official {stats.get('points')}")
        if len(valid) != stats.get("successful_predictions"):
            problems.append(f"{model}: valid {len(valid)} != official {stats.get('successful_predictions')}")
    cons = official_stats.get("consensus") or {}
    cons_points = [m["consensus"]["points"] for m in matches if m.get("consensus")]
    if sum(cons_points) != cons.get("points"):
        problems.append(f"consensus: points {sum(cons_points)} != official {cons.get('points')}")
    if len(cons_points) != cons.get("matches"):
        problems.append(f"consensus: matches {len(cons_points)} != official {cons.get('matches')}")
    return problems


def build_native_week(matchday: int, snapshot: dict[str, Any], graded: dict[str, Any]) -> dict[str, Any] | None:
    """Per-match archive for one FINAL week, or None if data drifted from the FINAL report."""
    matches = []
    for item in snapshot.get("matches") or []:
        if item.get("status") != "EVALUATED":
            continue
        record = graded.get(str(item["match_id"]))
        actual = (record or {}).get("actual") or {}
        saved = item.get("verified_score") or {}
        if not record or not actual or (saved.get("home"), saved.get("away")) != (actual.get("home"), actual.get("away")):
            return None
        matches.append(match_entry(item, record))
    if week_integrity_problems(matches, snapshot.get("stats") or {}):
        return None
    return {"season": snapshot.get("season", SEASON), "matchday": int(matchday), "status": "FINAL",
            "scoring_rule": SCORING_RULE, "schema_version": SCHEMA_VERSION,
            "source": SOURCE_NATIVE, "matches": matches}


def reconstruction_diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Differences between a reconstructed week and its native replacement."""
    old_by = {m["match_id"]: m for m in old.get("matches", [])}
    diffs: list[str] = []
    for match in new.get("matches", []):
        before = old_by.get(match["match_id"])
        if before is None:
            diffs.append(f"{match['match_id']}: missing in reconstruction")
            continue
        for model, entry in (before.get("models") or {}).items():
            current = (match["models"] or {}).get(model)
            if (entry or {}).get("score") != (current or {}).get("score"):
                diffs.append(f"{match['match_id']} {model}: {entry} != {current}")
        if (before.get("consensus") or {}).get("points") != (match.get("consensus") or {}).get("points"):
            diffs.append(f"{match['match_id']} consensus points differ")
    return diffs


def prepare_match_predictions() -> int:
    from performance_bot import _load_json, _save_json
    from performance_engine import merge_latest_results
    from result_provider import FootballDataResultProvider, ResultProviderError
    from source_loader import SourceLoadError, load_prediction_archive

    stored = _load_json(MATCH_PREDICTIONS_FILE, {})
    official = _load_json(WEEKLY_REPORTS_FILE, {})
    if not isinstance(stored, dict) or any(v.get("season") != SEASON for v in stored.values()):
        raise RuntimeError("Match-prediction archive season/schema mismatch; manual review required")
    finals = {str(md): r for md, r in official.items()
              if isinstance(r, dict) and r.get("status") == "FINAL" and r.get("season") == SEASON}
    due = sorted((md for md in finals
                  if md not in stored or stored[md].get("source") == SOURCE_RECONSTRUCTED), key=int)
    if not due:
        print("ℹ️ Match-prediction archive up to date; zero provider/GitHub calls")
        return 0
    try:
        predictions = load_prediction_archive()
        by_matchday = FootballDataResultProvider().get_matches_by_matchday()
    except (SourceLoadError, ResultProviderError) as exc:
        print(f"⚠️ Match-prediction archive source unavailable: {exc}")
        return 1 if any(md not in stored for md in due) else 0
    status_map = {str(m["id"]): m for rows in by_matchday.values() for m in rows if m.get("id") is not None}
    graded = merge_latest_results(predictions, status_map)
    changed = 0
    for md in due:
        week = build_native_week(int(md), finals[md], graded)
        was_reconstructed = md in stored
        if week is None:
            if was_reconstructed:
                print(f"ℹ️ Matchday {md}: native data unavailable/inconsistent; keeping PNG reconstruction")
            else:
                print(f"::warning title=Match-prediction drift::Matchday {md}: per-match sums differ from the "
                      "FINAL report or scores drifted; not stored, manual review required.")
            continue
        if was_reconstructed:
            diffs = reconstruction_diff(stored[md], week)
            week["upgraded_from"] = SOURCE_RECONSTRUCTED
            week["reconstruction_differences"] = len(diffs)
            print(f"🔁 Matchday {md}: PNG reconstruction replaced by native data "
                  f"({len(diffs)} differences){': ' + '; '.join(diffs[:3]) if diffs else ''}")
        else:
            print(f"🗂️ Matchday {md}: per-match predictions archived ({len(week['matches'])} matches); no Telegram.")
        stored[md] = week
        changed += 1
    if changed:
        _save_json(MATCH_PREDICTIONS_FILE, dict(sorted(stored.items(), key=lambda kv: int(kv[0]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(prepare_match_predictions())
