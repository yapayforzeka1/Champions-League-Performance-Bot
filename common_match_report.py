"""Read-only like-for-like comparison of consensus vs individual AI models.

Why this exists: the official report averages consensus points only over the
matches where a consensus formed (selection effect), while a score-split
consensus can earn at most 4 points. This module compares each model with the
consensus on the SAME matches. It never changes official points, FINAL
reports, Telegram delivery or source predictions, and makes no AI calls.

Weeks already present in the output file are immutable and never recomputed.
"""
from __future__ import annotations

from typing import Any

from config import DATA_DIR, MODEL_ORDER, REPORT_DIR, SEASON, WEEKLY_REPORTS_FILE
from performance_engine import SCORING_RULE, _model_identity, archived_consensus

COMMON_WEEKLY = DATA_DIR / "common_match_comparison.json"
COMMON_OVERVIEW = REPORT_DIR / "common_match_comparison.md"
SCHEMA_VERSION = 1


def _block(points: list[int]) -> dict[str, Any]:
    n = len(points)
    return {"matches": n, "points": sum(points), "avg": round(sum(points) / n, 2) if n else 0}


def match_row(match_id: str, record: dict[str, Any]) -> dict[str, Any]:
    """One graded match: consensus points and each model's valid points (else None)."""
    consensus = archived_consensus(record)
    cons_points = record.get("consensus_points") if consensus.get("winner_consensus") else None
    models: dict[str, int | None] = {}
    for model in MODEL_ORDER:
        points = None
        for vote in record.get("ai_votes") or []:
            if _model_identity(vote) == model and vote.get("success") and vote.get("points") is not None:
                points = int(vote["points"])
                break
        models[model] = points
    return {
        "match_id": str(match_id),
        "consensus": None if cons_points is None else int(cons_points),
        "consensus_has_score": bool(consensus.get("score_consensus")) and cons_points is not None,
        "models": models,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cons_rows = [r for r in rows if r["consensus"] is not None]
    consensus = {
        **_block([r["consensus"] for r in cons_rows]),
        "with_score": _block([r["consensus"] for r in cons_rows if r["consensus_has_score"]]),
        "outcome_only_max4": _block([r["consensus"] for r in cons_rows if not r["consensus_has_score"]]),
        "no_consensus_matches": len(rows) - len(cons_rows),
    }
    models: dict[str, Any] = {}
    for model in MODEL_ORDER:
        mine = [r for r in rows if r["models"].get(model) is not None]
        if not mine:
            continue
        both = [r for r in mine if r["consensus"] is not None]
        without = [r for r in mine if r["consensus"] is None]
        m_pts = [r["models"][model] for r in both]
        c_pts = [r["consensus"] for r in both]
        models[model] = {
            "own": _block([r["models"][model] for r in mine]),
            "on_no_consensus_matches": _block([r["models"][model] for r in without]),
            "pairwise_vs_consensus": {
                "common_matches": len(both),
                "model_points": sum(m_pts),
                "consensus_points": sum(c_pts),
                "model_avg": round(sum(m_pts) / len(both), 2) if both else 0,
                "consensus_avg": round(sum(c_pts) / len(both), 2) if both else 0,
                "model_better": sum(1 for a, b in zip(m_pts, c_pts) if a > b),
                "equal": sum(1 for a, b in zip(m_pts, c_pts) if a == b),
                "consensus_better": sum(1 for a, b in zip(m_pts, c_pts) if a < b),
            },
        }
    return {"matches": len(rows), "consensus": consensus, "models": models}


def build_common_week(matchday: int, snapshot: dict[str, Any], graded: dict[str, Any],
                      *, season: str = SEASON) -> dict[str, Any] | None:
    """Immutable per-week comparison from a FINAL snapshot and re-graded records.

    Returns None if a graded official score differs from the FINAL snapshot
    (data drift): such a week needs manual review, not silent recomputation.
    """
    rows = []
    for item in snapshot.get("matches") or []:
        if item.get("status") != "EVALUATED":
            continue
        record = graded.get(str(item["match_id"]))
        actual = (record or {}).get("actual") or {}
        saved = item.get("verified_score")
        if not record or not actual or (saved and (saved.get("home"), saved.get("away"))
                                        != (actual.get("home"), actual.get("away"))):
            return None
        rows.append(match_row(item["match_id"], record))
    return {"season": season, "matchday": int(matchday), "status": "FINAL",
            "scoring_rule": SCORING_RULE, "schema_version": SCHEMA_VERSION,
            "rows": rows, **summarize(rows)}


def build_common_season(weeks: dict[str, dict], *, season: str = SEASON) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for md, week in sorted(weeks.items(), key=lambda kv: int(kv[0])):
        if week.get("scoring_rule") != SCORING_RULE or week.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Mixed/incompatible common-match archive at matchday {md}")
        rows.extend(week["rows"])
    return {"season": season, "scoring_rule": SCORING_RULE, "schema_version": SCHEMA_VERSION,
            "finalized_matchdays": sorted(weeks, key=int), **summarize(rows)}


def _overview(season: dict[str, Any]) -> str:
    c = season["consensus"]
    lines = [f"# Konsensüs ve modeller — aynı maçlar üzerinden ({season['season']})", "",
             "Resmî puanları değiştirmez. Her model, konsensüsün oluştuğu **aynı maçlarda** konsensüsle kıyaslanır.", "",
             f"Konsensüs: {c['matches']} maç, {c['points']} puan, ort. {c['avg']}; "
             f"skor uzlaşmalı {c['with_score']['matches']} maç (ort. {c['with_score']['avg']}), "
             f"yalnız sonuç uzlaşmalı {c['outcome_only_max4']['matches']} maç (en çok 4 puan, ort. "
             f"{c['outcome_only_max4']['avg']}); konsensüssüz {c['no_consensus_matches']} maç.", "",
             "| Model | Ortak maç | Model puanı | Konsensüs puanı | Model ort. | Konsensüs ort. | Model iyi / eşit / geri |"
             , "|---|---:|---:|---:|---:|---:|---:|"]
    for model, data in season["models"].items():
        p = data["pairwise_vs_consensus"]
        lines.append(f"| {model} | {p['common_matches']} | {p['model_points']} | {p['consensus_points']} | "
                     f"{p['model_avg']} | {p['consensus_avg']} | "
                     f"{p['model_better']} / {p['equal']} / {p['consensus_better']} |")
    lines.extend(["", "## Seçilim etkisi: konsensüs oluşmayan maçlarda model ortalaması", "",
                  "| Model | Konsensüssüz maç | Ort. puan |", "|---|---:|---:|"])
    for model, data in season["models"].items():
        b = data["on_no_consensus_matches"]
        lines.append(f"| {model} | {b['matches']} | {b['avg']} |")
    lines.extend(["", "Küçük örneklemde fark, üstünlük kanıtı değildir.", ""])
    return "\n".join(lines)


def prepare_common_reports() -> int:
    from performance_bot import _load_json, _save_json
    from performance_engine import merge_latest_results
    from result_provider import FootballDataResultProvider, ResultProviderError
    from source_loader import SourceLoadError, load_prediction_archive

    existing = _load_json(COMMON_WEEKLY, {})
    official = _load_json(WEEKLY_REPORTS_FILE, {})
    if not isinstance(existing, dict) or any(v.get("season") != SEASON for v in existing.values()):
        raise RuntimeError("Common-match archive season/schema mismatch; manual review required")
    due = {str(md) for md, r in official.items()
           if isinstance(r, dict) and r.get("status") == "FINAL" and r.get("season") == SEASON
           and str(md) not in existing}
    if not due:
        print("ℹ️ No new official FINAL for common-match comparison; zero provider/GitHub calls")
        return 0
    try:
        predictions = load_prediction_archive()
        by_matchday = FootballDataResultProvider().get_matches_by_matchday()
    except (SourceLoadError, ResultProviderError) as exc:
        print(f"⚠️ Common-match comparison source unavailable: {exc}")
        return 1
    status_map = {str(m["id"]): m for rows in by_matchday.values() for m in rows if m.get("id") is not None}
    graded = merge_latest_results(predictions, status_map)
    new = 0
    for key in sorted(due, key=int):
        week = build_common_week(int(key), official[key], graded)
        if week is None:
            print(f"::warning title=Common-match drift::Matchday {key}: graded score differs from FINAL "
                  "or is missing; skipped for manual review.")
            continue
        existing[key] = week
        new += 1
        print(f"📐 Common-match comparison matchday {key} staged ({week['matches']} matches); no Telegram.")
    if not new:
        return 1
    season = build_common_season(existing)
    _save_json(COMMON_WEEKLY, existing)
    _save_json(DATA_DIR / "common_match_season.json", season)
    COMMON_OVERVIEW.parent.mkdir(parents=True, exist_ok=True)
    COMMON_OVERVIEW.write_text(_overview(season), encoding="utf-8")
    print(f"✅ {new} common-match week(s) saved; official FINAL/Telegram untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(prepare_common_reports())
