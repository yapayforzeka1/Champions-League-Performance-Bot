from __future__ import annotations

import copy
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from config import MODEL_ORDER, SEASON, TERMINAL_STATUSES
from consensus_engine import build_consensus


def actual_outcome(home: int, away: int) -> str:
    if home > away:
        return "HOME"
    if home < away:
        return "AWAY"
    return "DRAW"


def score_points(predicted_score: str | None, predicted_outcome: str | None, actual_home: int, actual_away: int) -> tuple[int, bool, bool]:
    actual = actual_outcome(actual_home, actual_away)
    score = str(predicted_score or "").replace(" ", "")
    exact = score == f"{actual_home}-{actual_away}"
    if exact:
        return 5, True, True
    outcome = str(predicted_outcome or "").upper()
    if outcome == "DRAW" and actual == "DRAW":
        return 5, False, True
    if outcome == actual:
        return 3, False, True
    return 0, False, False


def grade_record(record: dict[str, Any], actual_home: int, actual_away: int, actual_status: str = "FINISHED") -> dict[str, Any]:
    record = copy.deepcopy(record)
    actual = {"home": actual_home, "away": actual_away, "status": actual_status}
    votes = record.get("ai_votes", []) or []
    consensus = build_consensus(votes)

    for vote in votes:
        vote["points"] = None
        vote["exact_score_correct"] = False
        vote["outcome_correct"] = False
        if not vote.get("success") or not isinstance(vote.get("result"), dict):
            continue
        points, exact, outcome_correct = score_points(
            vote["result"].get("score"),
            vote["result"].get("outcome"),
            actual_home,
            actual_away,
        )
        vote["points"] = points
        vote["exact_score_correct"] = exact
        vote["outcome_correct"] = outcome_correct

    c_points = None
    c_exact = False
    c_outcome = False
    if consensus.get("winner_consensus"):
        c_points, c_exact, c_outcome = score_points(
            consensus.get("score") if consensus.get("score_consensus") else None,
            consensus.get("outcome"),
            actual_home,
            actual_away,
        )

    evaluated = dict(record)
    evaluated["actual"] = actual
    evaluated["consensus"] = consensus
    evaluated["consensus_points"] = c_points
    evaluated["consensus_exact_score_correct"] = c_exact
    evaluated["consensus_outcome_correct"] = c_outcome
    evaluated["outcome_correct"] = c_outcome
    evaluated["exact_score_correct"] = c_exact
    return evaluated


def _provider_regular_score(match: dict[str, Any]) -> tuple[int, int] | None:
    """Use only an available, verified 90-minute score from the result provider."""
    if str(match.get("status", "")).upper() != "FINISHED":
        return None
    raw = match.get("score") or {}
    if not isinstance(raw, dict):
        return None
    score = raw.get("regularTime") or {}
    if not score and str(raw.get("duration", "")).upper() == "REGULAR":
        score = raw.get("fullTime") or {}
    if not isinstance(score, dict):
        return None
    home, away = score.get("home"), score.get("away")
    if home is None or away is None:
        return None
    try:
        home, away = int(home), int(away)
    except (TypeError, ValueError):
        return None
    if home < 0 or away < 0:
        return None
    return home, away


def _has_usable_prediction(record: dict[str, Any] | None) -> bool:
    """A missing/failed AL vote is not a result still waiting to be graded."""
    if not isinstance(record, dict):
        return False
    for vote in record.get("ai_votes") or []:
        if not isinstance(vote, dict) or not vote.get("success"):
            continue
        result = vote.get("result")
        if isinstance(result, dict) and (result.get("score") or result.get("outcome")):
            return True
    return False


def merge_latest_results(predictions: dict[str, Any], status_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Grade every archived prediction that has a terminal real result."""
    result: dict[str, Any] = {}
    for key, record in predictions.items():
        item = copy.deepcopy(record)
        match = status_map.get(str(key))
        graded_from_provider = False
        if match:
            official_score = _provider_regular_score(match)
            if official_score is not None:
                item = grade_record(item, *official_score, "FINISHED")
                graded_from_provider = True
        # Re-evaluate a private copy under this project's unchanged 5/5/3/0 rules.
        # Never mix source 6/5/3/2/0 grades into a Performance report.
        if not graded_from_provider and item.get('actual'):
            actual = item['actual']
            if actual.get('scope') == 'REGULAR_90' and actual.get('home') is not None and actual.get('away') is not None:
                item = grade_record(item, int(actual['home']), int(actual['away']), 'FINISHED')
        result[str(key)] = item
    return result


def _resolved_fixture_status(match: dict[str, Any], prediction: dict[str, Any] | None) -> str:
    status = str(match.get("status", "")).upper()
    if status == "FINISHED":
        if not _has_usable_prediction(prediction):
            return "UNAVAILABLE"
        # An archived `actual` may come from the prediction repository. It is
        # not proof that the result provider has supplied a 90-minute score.
        if _provider_regular_score(match) is None or not prediction.get("actual"):
            return "PENDING"
        return "EVALUATED"
    if status in TERMINAL_STATUSES:
        return status
    return "PENDING"


def matchday_resolution(fixtures: list[dict[str, Any]], predictions: dict[str, Any]) -> dict[str, Any]:
    rows = []
    counts = defaultdict(int)
    for match in fixtures:
        mid = str(match.get("id"))
        prediction = predictions.get(mid)
        status = _resolved_fixture_status(match, prediction)
        counts[status] += 1
        row = {
            "match_id": mid,
            "home": (match.get("homeTeam") or {}).get("name", "?"),
            "away": (match.get("awayTeam") or {}).get("name", "?"),
            "utcDate": match.get("utcDate"),
            "status": status,
            "provider_status": match.get("status"),
        }
        # New snapshots retain official scores for *future* read-only drift
        # checks. Previously finalized reports are never backfilled or edited.
        if status == "EVALUATED":
            home, away = _provider_regular_score(match)
            row["verified_score"] = {"home": home, "away": away}
        rows.append(row)
    pending = counts["PENDING"]
    return {
        "final": pending == 0,
        "planned_matches": len(fixtures),
        "evaluated_matches": counts["EVALUATED"],
        "unavailable_matches": counts["UNAVAILABLE"],
        "postponed_matches": sum(counts[s] for s in ("POSTPONED", "CANCELLED", "SUSPENDED", "ABANDONED")),
        "pending_matches": pending,
        "matches": rows,
    }


def _model_identity(vote: dict[str, Any]) -> str | None:
    """Keep Qwen API versions distinct, even if a display label is stale.

    Older archived votes lack model_id, so their historical display name is
    deliberately retained instead of inferring a newer version.
    """
    result = vote.get("result")
    model_id = str(result.get("model_id") or "") if isinstance(result, dict) else ""
    if model_id == "qwen/qwen3.8-27b":
        return "Groq Qwen 3.8 27B"
    if model_id == "qwen/qwen3.6-27b":
        return "Groq Qwen 3.6 27B"
    return vote.get("model")


def build_weekly_stats(predictions: dict[str, Any], matchday: int) -> dict[str, Any]:
    model_stats = {
        model: {
            "prediction_opportunities": 0,
            "successful_predictions": 0,
            "failed_predictions": 0,
            "points": 0,
            "exact": 0,
            "outcome": 0,
            "avg": 0,
            "coverage_pct": 0,
            "point_distribution": {"5": 0, "3": 0, "0": 0},
        }
        for model in MODEL_ORDER
    }
    consensus = {
        "evaluated_matches": 0,
        "matches": 0,
        "points": 0,
        "exact": 0,
        "outcome": 0,
        "no_consensus": 0,
        "score_split": 0,
        "avg": 0,
    }

    records = [r for r in predictions.values() if int(r.get("matchday") or 0) == int(matchday) and r.get("actual")]
    for record in records:
        consensus["evaluated_matches"] += 1
        c = record.get("consensus") or build_consensus(record.get("ai_votes", []))
        if c.get("winner_consensus"):
            consensus["matches"] += 1
            if record.get("consensus_points") is not None:
                consensus["points"] += int(record["consensus_points"])
            consensus["outcome"] += int(bool(record.get("consensus_outcome_correct")))
            if c.get("score_consensus"):
                consensus["exact"] += int(bool(record.get("consensus_exact_score_correct")))
            else:
                consensus["score_split"] += 1
        else:
            consensus["no_consensus"] += 1

        for model in MODEL_ORDER:
            item = model_stats[model]
            votes = [v for v in record.get("ai_votes", []) if _model_identity(v) == model]
            # A model absent from this matchday's active pool had no opportunity.
            # A recorded unsuccessful vote still counts as a failed attempt.
            if not votes:
                continue
            item["prediction_opportunities"] += 1
            vote = votes[0]
            if not vote.get("success") or vote.get("points") is None:
                item["failed_predictions"] += 1
                continue
            item["successful_predictions"] += 1
            item["points"] += int(vote.get("points") or 0)
            item["point_distribution"][str(int(vote.get("points") or 0))] += 1
            item["exact"] += int(bool(vote.get("exact_score_correct")))
            item["outcome"] += int(bool(vote.get("outcome_correct")))

    for item in model_stats.values():
        n = int(item["successful_predictions"])
        item["avg"] = round(item["points"] / n, 2) if n else 0
        opportunities = int(item["prediction_opportunities"])
        item["coverage_pct"] = round(n / opportunities * 100, 1) if opportunities else 0
    if consensus["matches"]:
        consensus["avg"] = round(consensus["points"] / consensus["matches"], 2)

    return {"models": model_stats, "consensus": consensus}


def build_weekly_snapshot(predictions: dict[str, Any], matchday: int, resolution: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "scoring_rule": "performance:5-5-3-0",
        "season": SEASON,
        "matchday": int(matchday),
        "status": "FINAL",
        "finalized_at": now,
        "planned_matches": int(resolution["planned_matches"]),
        "evaluated_matches": int(resolution["evaluated_matches"]),
        "unavailable_matches": int(resolution["unavailable_matches"]),
        "postponed_matches": int(resolution["postponed_matches"]),
        "pending_matches": int(resolution["pending_matches"]),
        "matches": resolution["matches"],
        "stats": build_weekly_stats(predictions, matchday),
    }


def build_season_snapshot(weekly_reports: dict[str, Any]) -> dict[str, Any]:
    totals = {
        model: {
            "matchdays": 0,
            "points": 0,
            "successful_predictions": 0,
            "failed_predictions": 0,
            "exact": 0,
            "outcome": 0,
            "avg": 0,
            "point_distribution": {"5": 0, "3": 0, "0": 0},
        }
        for model in MODEL_ORDER
    }
    consensus = {"matchdays": 0, "matches": 0, "points": 0, "exact": 0, "outcome": 0, "no_consensus": 0, "score_split": 0, "avg": 0}

    for key, report in sorted(weekly_reports.items(), key=lambda kv: int(kv[0])):
        if report.get("status") != "FINAL":
            continue
        stats = report.get("stats", {})
        for model in MODEL_ORDER:
            src = stats.get("models", {}).get(model, {})
            dst = totals[model]
            if src and (int(src.get("successful_predictions") or 0) + int(src.get("failed_predictions") or 0)) > 0:
                dst["matchdays"] += 1
            for field in ("points", "successful_predictions", "failed_predictions", "exact", "outcome"):
                dst[field] += int(src.get(field, 0))
            for points in ("5", "3", "0"):
                dst["point_distribution"][points] += int(src.get("point_distribution", {}).get(points, 0))
        c = stats.get("consensus", {})
        consensus["matchdays"] += 1
        for field in ("matches", "points", "exact", "outcome", "no_consensus", "score_split"):
            consensus[field] += int(c.get(field, 0))

    for item in totals.values():
        n = item["successful_predictions"]
        item["avg"] = round(item["points"] / n, 2) if n else 0
    consensus["avg"] = round(consensus["points"] / consensus["matches"], 2) if consensus["matches"] else 0
    return {"season": SEASON, "finalized_matchdays": sorted(weekly_reports.keys(), key=int), "models": totals, "consensus": consensus}
