from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


MODES = {"NORMAL", "OUTCOME_COMMON_SCORE_SPLIT", "NO_COMMON"}


def _strict_majority(counts: Counter[str], total: int) -> tuple[str | None, int]:
    if total <= 0 or not counts:
        return None, 0
    value, count = counts.most_common(1)[0]
    if sum(1 for n in counts.values() if n == count) != 1:
        return None, 0
    if count <= total / 2:
        return None, 0
    return value, count


def build_consensus(votes: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [v for v in votes if v.get("success") and isinstance(v.get("result"), dict)]
    if not successful:
        return {
            "successful_ai": 0,
            "total_ai": len(votes),
            "outcome": None,
            "score": None,
            "outcome_votes": 0,
            "score_votes": 0,
            "outcome_share": 0,
            "score_share": 0,
            "winner_consensus": False,
            "score_consensus": False,
            "consensus_mode": "NO_COMMON",
            "top_outcome": None,
            "top_outcome_votes": 0,
            "top_score": None,
            "top_score_votes": 0,
            "failed_ai": [{"model": v.get("model"), "error": v.get("error")} for v in votes],
            "reasons_by_outcome": {},
        }

    outcomes = Counter(str(v["result"].get("outcome", "")).upper() for v in successful)
    scores = Counter(str(v["result"].get("score", "")).replace(" ", "") for v in successful)
    outcome, outcome_votes = _strict_majority(outcomes, len(successful))
    score, score_votes = _strict_majority(scores, len(successful))

    if outcome is None:
        mode = "NO_COMMON"
        score = None
        score_votes = 0
    elif score is None:
        mode = "OUTCOME_COMMON_SCORE_SPLIT"
    else:
        mode = "NORMAL"

    reasons: dict[str, list[str]] = defaultdict(list)
    for vote in successful:
        result = vote["result"]
        key = str(result.get("outcome", "")).upper()
        for reason in result.get("reasons", []) or []:
            reason = str(reason)
            if reason not in reasons[key]:
                reasons[key].append(reason)

    return {
        "successful_ai": len(successful),
        "total_ai": len(votes),
        "outcome": outcome,
        "score": score,
        "outcome_votes": outcome_votes,
        "score_votes": score_votes,
        "outcome_share": round(outcome_votes / len(successful) * 100) if outcome_votes else 0,
        "score_share": round(score_votes / len(successful) * 100) if score_votes else 0,
        "winner_consensus": outcome is not None,
        "score_consensus": score is not None,
        "consensus_mode": mode,
        "top_outcome": outcomes.most_common(1)[0][0],
        "top_outcome_votes": outcomes.most_common(1)[0][1],
        "top_score": scores.most_common(1)[0][0],
        "top_score_votes": scores.most_common(1)[0][1],
        "failed_ai": [{"model": v.get("model"), "error": v.get("error")} for v in votes if not v.get("success")],
        "reasons_by_outcome": {k: v[:5] for k, v in reasons.items()},
    }
