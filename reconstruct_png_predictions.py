"""One-off backfill of per-match model predictions from the PUBLISHED weekly PNGs.

Matchdays 1-3 were finalized before per-match predictions were archived. Their
scores were transcribed by reading the published images (`reports/*.png`) and
are stored with source RECONSTRUCTED_FROM_PUBLISHED_PNG. A week is written only
if EVERY check below passes against the official FINAL statistics:
per-model points and valid-prediction counts, consensus points / match count /
score-split count, and the actual-score column order.

Not run by the workflow. When the prediction repo still holds these weeks,
`match_prediction_archive.py` replaces the reconstruction with native data and
reports any difference. Matchday 1's PNG shows only Gemini, Cohere, GPT-OSS and
the consensus, so Groq Qwen 3.6 27B and Mistral are not reconstructible there.
"""
from __future__ import annotations

import json
import sys

from config import DATA_DIR, SEASON, WEEKLY_REPORTS_FILE
from match_prediction_archive import (MATCH_PREDICTIONS_FILE, SCHEMA_VERSION, SOURCE_RECONSTRUCTED,
                                      week_integrity_problems)
from performance_engine import SCORING_RULE, score_points

GEM, QWEN, COH, GPT, CLEF = ("Gemini 3.6 Flash", "Groq Qwen 3.8 27B", "Cohere Command A+",
                             "Groq GPT-OSS 120B", "Cloudflare Clef-omni")
N = None

# Row = (actual, {model: score}, consensus) ; consensus = None (no consensus) or (score|None, points)
MD1 = [
    ("2-1", {GEM: "2-1", COH: "2-1", GPT: "2-1"}, ("2-1", 8)),
    ("0-2", {GEM: "1-2", COH: "2-1", GPT: "2-1"}, N),
    ("3-2", {COH: "2-1", GPT: "2-1"}, ("2-1", 6)),
    ("2-3", {GEM: "2-1", COH: "2-1", GPT: "2-1"}, ("2-1", 0)),
    ("5-1", {COH: "2-1", GPT: "3-1"}, ("3-1", 4)),
    ("3-1", {GEM: "3-0", COH: "2-0", GPT: "2-1"}, (N, 4)),
    ("2-1", {GEM: "2-1", COH: "2-1", GPT: "2-1"}, ("2-1", 8)),
    ("6-1", {GEM: "3-0", COH: "2-1", GPT: "3-0"}, (N, 4)),
    ("0-1", {GPT: "2-1"}, N),
    ("3-1", {COH: "2-1", GPT: "2-0"}, ("2-1", 4)),
    ("1-1", {COH: "1-2", GPT: "2-1"}, ("2-1", 0)),
    ("1-1", {GEM: "3-1", COH: "2-1", GPT: "2-1"}, (N, 0)),
    ("5-0", {COH: "2-1", GPT: "3-0"}, (N, 4)),
    ("4-0", {GEM: "4-0", COH: "2-1", GPT: "2-0"}, (N, 4)),
    ("4-1", {GEM: "2-1", COH: "1-2", GPT: "2-1"}, N),
    ("2-3", {GEM: "2-1", COH: "2-1", GPT: "1-2"}, ("2-1", 0)),
]
MD2 = [
    ("0-2", {QWEN: "1-2", COH: "2-1", GPT: "1-1", CLEF: "1-2"}, N),
    ("2-0", {QWEN: "0-2", COH: "2-1", GPT: "1-1", CLEF: "0-2"}, N),
    ("3-4", {QWEN: "2-1", COH: "2-1", GPT: "2-0", CLEF: "3-1"}, (N, 0)),
    ("1-4", {QWEN: "1-3", GPT: "0-3", CLEF: "0-3"}, (N, 4)),
    ("2-0", {QWEN: "2-1", COH: "2-1", GPT: "2-1", CLEF: "1-1"}, ("2-1", 4)),
    ("3-0", {QWEN: "2-1", COH: "2-1", GPT: "2-0", CLEF: "1-1"}, (N, 4)),
    ("3-3", {QWEN: "0-3", CLEF: "0-3"}, N),
    ("1-0", {QWEN: "2-1", COH: "2-1", GPT: "3-1", CLEF: "2-1"}, ("2-1", 6)),
    ("3-1", {QWEN: "1-1", COH: "2-1", GPT: "1-1", CLEF: "1-1"}, ("1-1", 0)),
    ("3-6", {QWEN: "0-2", GPT: "0-2", CLEF: "0-2"}, ("0-2", 4)),
    ("3-2", {QWEN: "2-1", COH: "2-1", GPT: "4-1", CLEF: "4-1"}, (N, 4)),
    ("3-4", {QWEN: "1-2", COH: "2-1", GPT: "2-1", CLEF: "1-2"}, N),
    ("2-4", {QWEN: "2-1", COH: "2-1", GPT: "2-1", CLEF: "3-1"}, ("2-1", 0)),
    ("1-0", {QWEN: "0-3", GPT: "0-3", CLEF: "0-3"}, ("0-3", 0)),
    ("3-2", {QWEN: "2-1", COH: "2-1", GPT: "2-1", CLEF: "1-1"}, ("2-1", 6)),
    ("3-1", {QWEN: "1-1", COH: "2-1", GPT: "1-1", CLEF: "0-0"}, (N, 0)),
    ("0-3", {QWEN: "0-2", GPT: "0-2", CLEF: "0-2"}, ("0-2", 4)),
]
MD3 = [
    ("1-2", {GEM: "0-2", QWEN: "0-2", GPT: "1-2", CLEF: "0-3"}, (N, 4)),
    ("5-1", {GEM: "3-0", QWEN: "3-1", COH: "2-0", GPT: "2-0", CLEF: "4-1"}, (N, 4)),
    ("1-1", {QWEN: "0-2", GPT: "0-2", CLEF: "0-2"}, ("0-2", 0)),
    ("4-3", {GEM: "2-1", QWEN: "2-1", COH: "2-1", GPT: "1-1", CLEF: "3-1"}, ("2-1", 6)),
    ("4-0", {QWEN: "2-0", COH: "2-1", GPT: "2-0", CLEF: "4-1"}, (N, 4)),
    ("0-1", {QWEN: "2-1", COH: "2-1", GPT: "2-1", CLEF: "1-1"}, ("2-1", 0)),
    ("4-3", {GEM: "2-0", QWEN: "2-0", COH: "2-0", GPT: "2-0", CLEF: "3-1"}, ("2-0", 4)),
    ("4-2", {QWEN: "2-3", COH: "3-2", GPT: "3-2", CLEF: "1-3"}, N),
    ("4-1", {QWEN: "0-1", COH: "2-1", GPT: "2-1", CLEF: "0-2"}, N),
    ("4-1", {QWEN: "3-1", COH: "2-1", GPT: "2-0", CLEF: "3-1"}, (N, 4)),
    ("1-0", {QWEN: "2-1", COH: "2-1", GPT: "3-1", CLEF: "3-1"}, (N, 4)),
    ("2-2", {QWEN: "3-1", COH: "3-1", GPT: "3-1", CLEF: "3-1"}, ("3-1", 0)),
    ("3-0", {QWEN: "2-1", COH: "2-1", GPT: "3-1", CLEF: "1-1"}, (N, 4)),
    ("3-1", {QWEN: "3-1", COH: "3-1", GPT: "2-0", CLEF: "3-1"}, ("3-1", 8)),
    ("2-3", {GEM: "3-1", QWEN: "3-1", COH: "2-1", GPT: "2-1", CLEF: "3-1"}, ("3-1", 0)),
    ("1-0", {QWEN: "1-3", COH: "2-1", GPT: "2-3", CLEF: "0-3"}, (N, 0)),
]
WEEKS = {1: MD1, 2: MD2, 3: MD3}
UNRECONSTRUCTIBLE = {1: {"Mistral Small Latest", "Groq Qwen 3.6 27B"}}


def _outcome(h: int, a: int) -> str:
    return "HOME" if h > a else "AWAY" if h < a else "DRAW"


def build_week(md: int, rows: list, official: dict) -> tuple[dict, list[str]]:
    evaluated = [m for m in official["matches"] if m["status"] == "EVALUATED"]
    problems: list[str] = []
    if len(evaluated) != len(rows):
        problems.append(f"row count {len(rows)} != evaluated {len(evaluated)}")
        return {}, problems
    matches = []
    for item, (actual_txt, preds, cons) in zip(evaluated, rows):
        ah, aa = map(int, actual_txt.split("-"))
        saved = item["verified_score"]
        if (saved["home"], saved["away"]) != (ah, aa):
            problems.append(f"{item['match_id']}: actual column {actual_txt} != archive {saved}")
        models = {}
        for name, score in preds.items():
            points, _, _ = score_points(score, None, ah, aa)
            models[name] = {"score": score, "points": points}
        consensus = None
        if cons is not None:
            c_score, c_points = cons
            if c_score is not None:
                recomputed, _, _ = score_points(c_score, None, ah, aa)
                if recomputed != c_points:
                    problems.append(f"{item['match_id']}: consensus {c_score} -> {recomputed} != shown {c_points}")
                outcome = _outcome(*map(int, c_score.split("-")))
            else:
                outcome = _outcome(ah, aa) if c_points > 0 else None  # wrong outcome-only pick is not displayed
            consensus = {"outcome": outcome, "score": c_score, "points": c_points}
        matches.append({"match_id": str(item["match_id"]), "home": item["home"], "away": item["away"],
                        "utcDate": item["utcDate"], "actual": {"home": ah, "away": aa},
                        "models": models, "consensus": consensus})
    stats = official["stats"]
    problems += week_integrity_problems(matches, stats, UNRECONSTRUCTIBLE.get(md))
    split = sum(1 for m in matches if m["consensus"] and m["consensus"]["score"] is None)
    if split != stats["consensus"]["score_split"]:
        problems.append(f"consensus score_split {split} != official {stats['consensus']['score_split']}")
    for model, s in stats["models"].items():
        if model in UNRECONSTRUCTIBLE.get(md, set()) or not s["prediction_opportunities"]:
            continue
        dist = {"8": 0, "6": 0, "4": 0, "0": 0}
        for m in matches:
            if m["models"].get(model):
                dist[str(m["models"][model]["points"])] += 1
        if dist != s["point_distribution"]:
            problems.append(f"{model}: distribution {dist} != official {s['point_distribution']}")
    week = {"season": SEASON, "matchday": md, "status": "FINAL", "scoring_rule": SCORING_RULE,
            "schema_version": SCHEMA_VERSION, "source": SOURCE_RECONSTRUCTED,
            "unreconstructed_models": sorted(UNRECONSTRUCTIBLE.get(md, set())), "matches": matches}
    return week, problems


def main() -> int:
    official = json.loads(WEEKLY_REPORTS_FILE.read_text(encoding="utf-8"))
    out, failed = {}, False
    for md, rows in WEEKS.items():
        week, problems = build_week(md, rows, official[str(md)])
        if problems:
            failed = True
            print(f"❌ Matchday {md}: " + "; ".join(problems))
        else:
            out[str(md)] = week
            print(f"✅ Matchday {md}: {len(week['matches'])} matches match every official FINAL statistic")
    if failed:
        print("Nothing written.")
        return 1
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MATCH_PREDICTIONS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MATCH_PREDICTIONS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
