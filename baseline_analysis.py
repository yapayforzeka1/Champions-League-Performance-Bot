"""Internal, read-only comparison of every model against fixed reference predictions.

Question answered: does a model add value over trivial rules? Nothing here
changes official points, FINAL reports or Telegram output, and the report is NOT
sent anywhere (publishing it is a separate, manual decision).

Reference predictions are LOCKED (version 1):
  home_1_0           always predict 1-0 for the home team
  home_2_1           always predict 2-1 for the home team
  fixed_margin_2_1   keep the model's own outcome, replace its score with
                     2-1 / 1-2 / 1-1 (tests whether the model's margin helps)

They were chosen AFTER seeing matchdays 1-3. Those matchdays are therefore
reported as "observed" (in-sample); only matchdays after BASELINE_LOCK_MATCHDAY
are an honest out-of-sample test. The comparison is like-for-like: a model is
compared with the references on exactly the matches where it gave a valid
prediction. Uncertainty is shown as a paired difference with a seeded bootstrap.
"""
from __future__ import annotations

import random
from typing import Any

from config import DATA_DIR, MODEL_ORDER, REPORT_DIR, SEASON
from match_prediction_archive import MATCH_PREDICTIONS_FILE, SOURCE_RECONSTRUCTED
from performance_engine import SCORING_RULE, score_points

BASELINE_VERSION = 1
BASELINE_LOCK_MATCHDAY = 3
BASELINES = {"home_1_0": (1, 0), "home_2_1": (2, 1)}
FIXED_MARGIN = "fixed_margin_2_1"
REFERENCES = [*BASELINES, FIXED_MARGIN]
BASELINE_FILE = DATA_DIR / "baseline_comparison.json"
BASELINE_OVERVIEW = REPORT_DIR / "baseline_comparison.md"
BOOTSTRAP_RESAMPLES = 4000
BOOTSTRAP_SEED = 20261103


def _pts(score: str, actual: dict[str, int]) -> int:
    return score_points(score, None, actual["home"], actual["away"])[0]


def reference_points(name: str, model_score: str | None, actual: dict[str, int]) -> int | None:
    """Points of a locked reference on one match (None if not computable)."""
    if name in BASELINES:
        home, away = BASELINES[name]
        return _pts(f"{home}-{away}", actual)
    if name == FIXED_MARGIN and model_score:
        h, a = map(int, model_score.split("-"))
        return _pts("2-1" if h > a else "1-2" if h < a else "1-1", actual)
    return None


def paired(diffs: list[int | float]) -> dict[str, Any]:
    n = len(diffs)
    if not n:
        return {"matches": 0}
    mean = sum(diffs) / n
    out: dict[str, Any] = {"matches": n, "mean": round(mean, 2),
                           "better": sum(1 for d in diffs if d > 0),
                           "equal": sum(1 for d in diffs if d == 0),
                           "worse": sum(1 for d in diffs if d < 0)}
    if n >= 2:
        var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
        out["se"] = round((var / n) ** 0.5, 2)
        rng = random.Random(BOOTSTRAP_SEED)
        means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(BOOTSTRAP_RESAMPLES))
        out["ci95"] = [round(means[int(0.025 * BOOTSTRAP_RESAMPLES)], 2),
                       round(means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1], 2)]
    return out


def _avg(values: list[int | float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0


def _group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"matches": len(rows), "models": {}}
    result["baselines_on_all_matches"] = {
        name: _avg([reference_points(name, None, r["actual"]) for r in rows]) for name in BASELINES}
    names = [m for m in MODEL_ORDER if any((r["models"].get(m) or None) for r in rows)]
    for model in names:
        mine = [r for r in rows if r["models"].get(model)]
        pts = [r["models"][model]["points"] for r in mine]
        block: dict[str, Any] = {"matches": len(mine), "points": sum(pts), "avg": _avg(pts), "vs": {}}
        for ref in REFERENCES:
            ref_pts = [reference_points(ref, r["models"][model]["score"], r["actual"]) for r in mine]
            block["vs"][ref] = {"reference_avg": _avg(ref_pts),
                                "model_minus_reference": paired([a - b for a, b in zip(pts, ref_pts)])}
        result["models"][model] = block
    cons = [r for r in rows if r.get("consensus")]
    if cons:
        pts = [r["consensus"]["points"] for r in cons]
        block = {"matches": len(cons), "points": sum(pts), "avg": _avg(pts), "vs": {}}
        for ref in BASELINES:
            ref_pts = [reference_points(ref, None, r["actual"]) for r in cons]
            block["vs"][ref] = {"reference_avg": _avg(ref_pts),
                                "model_minus_reference": paired([a - b for a, b in zip(pts, ref_pts)])}
        result["consensus"] = block
    return result


def flatten(weeks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for md, week in sorted(weeks.items(), key=lambda kv: int(kv[0])):
        if week.get("scoring_rule") != SCORING_RULE:
            raise ValueError(f"Matchday {md}: scoring rule mismatch")
        for m in week["matches"]:
            rows.append({"matchday": int(md), "match_id": m["match_id"], "actual": m["actual"],
                         "models": m["models"], "consensus": m.get("consensus")})
    return rows


def analyze(weeks: dict[str, dict[str, Any]], lock_matchday: int = BASELINE_LOCK_MATCHDAY) -> dict[str, Any]:
    rows = flatten(weeks)
    sources = {md: w.get("source") for md, w in weeks.items()}
    return {
        "season": SEASON, "scoring_rule": SCORING_RULE, "baseline_version": BASELINE_VERSION,
        "references": {**{k: f"{h}-{a}" for k, (h, a) in BASELINES.items()},
                       FIXED_MARGIN: "model outcome kept, score -> 2-1 / 1-2 / 1-1"},
        "baseline_lock_matchday": lock_matchday,
        "note": ("References were chosen after seeing matchdays <= lock; only 'out_of_sample' "
                 "(matchday > lock) is an honest test."),
        "matchdays": sorted(weeks, key=int), "sources": dict(sorted(sources.items(), key=lambda kv: int(kv[0]))),
        "all": _group(rows),
        "observed": _group([r for r in rows if r["matchday"] <= lock_matchday]),
        "out_of_sample": _group([r for r in rows if r["matchday"] > lock_matchday]),
    }


def _fmt(block: dict[str, Any], ref: str) -> str:
    d = block["vs"][ref]
    p = d["model_minus_reference"]
    ci = f"[{p['ci95'][0]:+.2f}; {p['ci95'][1]:+.2f}]" if p.get("ci95") else "–"
    return f"{d['reference_avg']:.2f} | {p.get('mean', 0):+.2f} | {ci}"


def _table(group: dict[str, Any], ref: str) -> list[str]:
    lines = ["| Model | Maç | Ort. | Referans ort. | Fark | %95 aralık |", "|---|---:|---:|---:|---:|---:|"]
    entries = list(group["models"].items())
    if group.get("consensus") and ref in BASELINES:
        entries.append(("Konsensüs", group["consensus"]))
    for name, block in entries:
        lines.append(f"| {name} | {block['matches']} | {block['avg']:.2f} | " + _fmt(block, ref) + " |")
    return lines


def overview(analysis: dict[str, Any]) -> str:
    lines = [f"# Taban çizgisi karşılaştırması ({analysis['season']}) — İÇ ANALİZ, Telegram'a gönderilmez", "",
             f"Kilitli referanslar (sürüm {analysis['baseline_version']}): `home_1_0` (hep ev 1-0), `home_2_1` (hep ev 2-1), "
             "`fixed_margin_2_1` (modelin sonucu korunur, skoru 2-1 / 1-2 / 1-1 yapılır).", "",
             f"**Önemli:** Referanslar {analysis['baseline_lock_matchday']}. haftaya kadar olan veriye bakılarak seçildi. "
             "Bu haftalar 'gözlenen' (iç-örnek) sayılır; adil test yalnızca sonraki haftalardır.", "",
             "Karşılaştırma aynı maçlarda yapılır: model, yalnızca geçerli tahmin verdiği maçlarda referansla kıyaslanır. "
             "Fark = model ortalaması − referans ortalaması.", ""]
    for key, title in (("observed", "Gözlenen haftalar (iç-örnek)"), ("out_of_sample", "Dış-örnek (adil test)")):
        group = analysis[key]
        lines += [f"## {title} — {group['matches']} maç", ""]
        if not group["matches"]:
            lines += ["Henüz veri yok.", ""]
            continue
        lines += ["Tüm maçlarda sabit tahmin ortalamaları: " +
                  ", ".join(f"{k} {v:.2f}" for k, v in group["baselines_on_all_matches"].items()), ""]
        for ref in REFERENCES:
            lines += [f"### Referans: `{ref}`", "", *_table(group, ref), ""]
    sources = {s for s in analysis["sources"].values()}
    if SOURCE_RECONSTRUCTED in sources:
        lines += ["> Not: Bazı haftalar yayınlanmış görsellerden geri kurulmuştur "
                  "(1. haftada Qwen 3.6 ve Mistral görselde yoktur); resmî istatistiklerle birebir doğrulanmıştır.", ""]
    return "\n".join(lines)


def prepare_baseline_report() -> int:
    from performance_bot import _load_json, _save_json

    weeks = _load_json(MATCH_PREDICTIONS_FILE, {})
    if not weeks:
        print("ℹ️ No per-match prediction archive yet; baseline comparison skipped")
        return 0
    analysis = analyze(weeks)
    _save_json(BASELINE_FILE, analysis)
    BASELINE_OVERVIEW.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_OVERVIEW.write_text(overview(analysis), encoding="utf-8")
    print(f"✅ Baseline comparison written for matchdays {', '.join(analysis['matchdays'])}; internal only")
    return 0


if __name__ == "__main__":
    raise SystemExit(prepare_baseline_report())
