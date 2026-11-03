"""Zero-network checks for the per-match prediction archive and baseline analysis."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import baseline_analysis as ba
import match_prediction_archive as mpa
import reconstruct_png_predictions as recon
from config import DATA_DIR, SEASON
from performance_engine import SCORING_RULE, build_weekly_stats, grade_record

COH, GPT = "Cohere Command A+", "Groq GPT-OSS 120B"
FULL = {"winner_consensus": True, "score_consensus": True, "outcome": "HOME", "score": "2-1"}
SPLIT = {"winner_consensus": True, "score_consensus": False, "outcome": "HOME", "score": None}


def vote(model, score, ok=True):
    if not ok:
        return {"model": model, "success": False, "result": None}
    h, a = map(int, score.split("-"))
    return {"model": model, "success": True,
            "result": {"score": score, "outcome": "HOME" if h > a else "AWAY" if h < a else "DRAW"}}


def graded_week():
    """3 matches: full consensus, split consensus, failed Cohere vote."""
    specs = [("1", (2, 1), FULL, [vote(COH, "2-1"), vote(GPT, "1-0")]),
             ("2", (2, 0), SPLIT, [vote(COH, "3-0"), vote(GPT, "0-1")]),
             ("3", (1, 1), {"winner_consensus": False}, [vote(COH, "", ok=False), vote(GPT, "2-1")])]
    graded, matches = {}, []
    for mid, actual, cons, votes in specs:
        graded[mid] = grade_record({"match_id": mid, "matchday": 4, "ai_votes": votes, "consensus": cons}, *actual)
        matches.append({"match_id": mid, "home": "A" + mid, "away": "B" + mid, "utcDate": "2026-11-03T19:00:00Z",
                        "status": "EVALUATED", "verified_score": {"home": actual[0], "away": actual[1]}})
    snapshot = {"season": SEASON, "matches": matches, "stats": build_weekly_stats(graded, 4)}
    return snapshot, graded


class EntryAndIntegrityTests(unittest.TestCase):
    def test_entries_store_valid_scores_and_null_for_failures(self):
        snap, graded = graded_week()
        entry = mpa.match_entry(snap["matches"][2], graded["3"])
        self.assertIsNone(entry["models"][COH])
        self.assertEqual(entry["models"][GPT], {"score": "2-1", "points": 0})
        self.assertIsNone(entry["consensus"])
        split = mpa.match_entry(snap["matches"][1], graded["2"])
        self.assertEqual(split["consensus"], {"outcome": "HOME", "score": None, "points": 4})

    def test_native_week_passes_integrity_and_matches_official_totals(self):
        snap, graded = graded_week()
        week = mpa.build_native_week(4, snap, graded)
        self.assertEqual(week["source"], mpa.SOURCE_NATIVE)
        self.assertEqual(mpa.week_integrity_problems(week["matches"], snap["stats"]), [])
        self.assertEqual(sum(m["models"][GPT]["points"] for m in week["matches"]), snap["stats"]["models"][GPT]["points"])

    def test_tampered_points_or_drifted_scores_are_refused(self):
        snap, graded = graded_week()
        bad = copy.deepcopy(snap)
        bad["stats"]["models"][COH]["points"] += 2
        self.assertIsNone(mpa.build_native_week(4, bad, graded))
        drift = copy.deepcopy(snap)
        drift["matches"][0]["verified_score"] = {"home": 9, "away": 9}
        self.assertIsNone(mpa.build_native_week(4, drift, graded))

    def test_inputs_are_not_mutated(self):
        snap, graded = graded_week()
        before = copy.deepcopy((snap, graded))
        mpa.build_native_week(4, snap, graded)
        self.assertEqual((snap, graded), before)

    def test_reconstruction_diff_reports_score_changes(self):
        snap, graded = graded_week()
        native = mpa.build_native_week(4, snap, graded)
        old = copy.deepcopy(native)
        self.assertEqual(mpa.reconstruction_diff(old, native), [])
        old["matches"][0]["models"][COH]["score"] = "3-1"
        self.assertEqual(len(mpa.reconstruction_diff(old, native)), 1)


class PrepareFlowTests(unittest.TestCase):
    def _env(self, root, stored, official):
        (root / "stored.json").write_text(json.dumps(stored), encoding="utf-8")
        (root / "official.json").write_text(json.dumps(official), encoding="utf-8")
        return (patch.object(mpa, "MATCH_PREDICTIONS_FILE", root / "stored.json"),
                patch.object(mpa, "WEEKLY_REPORTS_FILE", root / "official.json"))

    def test_up_to_date_archive_makes_no_calls(self):
        snap, graded = graded_week()
        week = mpa.build_native_week(4, snap, graded)
        official = {"4": {**snap, "status": "FINAL", "season": SEASON}}
        with tempfile.TemporaryDirectory() as tmp:
            p1, p2 = self._env(Path(tmp), {"4": week}, official)
            with p1, p2, patch("source_loader.load_prediction_archive") as load:
                self.assertEqual(mpa.prepare_match_predictions(), 0)
                load.assert_not_called()

    def test_reconstructed_week_is_upgraded_only_with_consistent_native_data(self):
        snap, graded = graded_week()
        native = mpa.build_native_week(4, snap, graded)
        recon_week = copy.deepcopy(native)
        recon_week["source"] = mpa.SOURCE_RECONSTRUCTED
        official = {"4": {**snap, "status": "FINAL", "season": SEASON}}
        fixtures = {4: [{"id": int(mid), "matchday": 4, "status": "FINISHED", "utcDate": "2026-11-03T19:00:00Z",
                         "score": {"duration": "REGULAR", "regularTime": {"home": g["actual"]["home"], "away": g["actual"]["away"]}}}
                        for mid, g in graded.items()]}
        predictions = {mid: {k: v for k, v in g.items() if k not in ("actual",)} for mid, g in graded.items()}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p1, p2 = self._env(root, {"4": recon_week}, official)
            with p1, p2, patch("source_loader.load_prediction_archive", return_value=predictions), \
                    patch("result_provider.FootballDataResultProvider") as provider:
                provider.return_value.get_matches_by_matchday.return_value = fixtures
                self.assertEqual(mpa.prepare_match_predictions(), 0)
            saved = json.loads((root / "stored.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["4"]["source"], mpa.SOURCE_NATIVE)
            self.assertEqual(saved["4"]["upgraded_from"], mpa.SOURCE_RECONSTRUCTED)
            self.assertEqual(saved["4"]["reconstruction_differences"], 0)
            # native data unavailable (empty source) -> reconstruction is kept
            p1, p2 = self._env(root, {"4": recon_week}, official)
            with p1, p2, patch("source_loader.load_prediction_archive", return_value={}), \
                    patch("result_provider.FootballDataResultProvider") as provider:
                provider.return_value.get_matches_by_matchday.return_value = fixtures
                mpa.prepare_match_predictions()
            kept = json.loads((root / "stored.json").read_text(encoding="utf-8"))
            self.assertEqual(kept["4"]["source"], mpa.SOURCE_RECONSTRUCTED)


class BaselineTests(unittest.TestCase):
    def week(self, md, scores):
        """scores: list of (actual, {model: (score, points)}, consensus_points)"""
        matches = []
        for i, (actual, models, cons) in enumerate(scores):
            matches.append({"match_id": f"{md}{i}", "actual": {"home": actual[0], "away": actual[1]},
                            "models": {m: ({"score": s, "points": p} if s else None) for m, (s, p) in models.items()},
                            "consensus": None if cons is None else {"outcome": None, "score": None, "points": cons}})
        return {"scoring_rule": SCORING_RULE, "source": mpa.SOURCE_NATIVE, "matches": matches}

    def test_reference_points_follow_the_kicktipp_rule(self):
        self.assertEqual(ba.reference_points("home_1_0", None, {"home": 1, "away": 0}), 8)
        self.assertEqual(ba.reference_points("home_1_0", None, {"home": 3, "away": 2}), 6)
        self.assertEqual(ba.reference_points("home_2_1", None, {"home": 4, "away": 0}), 4)
        self.assertEqual(ba.reference_points("home_1_0", None, {"home": 0, "away": 1}), 0)
        self.assertEqual(ba.reference_points(ba.FIXED_MARGIN, "0-3", {"home": 1, "away": 2}), 8)  # 0-3 -> 1-2 exact
        self.assertEqual(ba.reference_points(ba.FIXED_MARGIN, "0-1", {"home": 0, "away": 3}), 4)  # outcome only
        self.assertEqual(ba.reference_points(ba.FIXED_MARGIN, "2-2", {"home": 1, "away": 1}), 8)
        self.assertIsNone(ba.reference_points(ba.FIXED_MARGIN, None, {"home": 1, "away": 1}))

    def test_paired_statistics_are_deterministic(self):
        d = [4, 0, -4, 6, 0, 4, -4, 4]
        a, b = ba.paired(d), ba.paired(d)
        self.assertEqual(a, b)
        self.assertEqual(a["matches"], 8)
        self.assertAlmostEqual(a["mean"], 1.25)
        self.assertEqual((a["better"], a["equal"], a["worse"]), (4, 2, 2))
        self.assertLessEqual(a["ci95"][0], a["mean"])
        self.assertGreaterEqual(a["ci95"][1], a["mean"])
        self.assertEqual(ba.paired([]), {"matches": 0})
        self.assertNotIn("ci95", ba.paired([3]))

    def test_like_for_like_matches_and_split_by_lock_matchday(self):
        weeks = {
            "3": self.week(3, [((2, 1), {COH: ("2-1", 8), GPT: (None, 0)}, 8), ((0, 1), {COH: ("2-1", 0), GPT: ("1-2", 6)}, None)]),
            "4": self.week(4, [((1, 0), {COH: ("2-1", 6), GPT: ("1-0", 8)}, 4)]),
        }
        out = ba.analyze(weeks)
        self.assertEqual((out["all"]["matches"], out["observed"]["matches"], out["out_of_sample"]["matches"]), (3, 2, 1))
        gpt_all = out["all"]["models"][GPT]
        self.assertEqual(gpt_all["matches"], 2)  # the null (failed) prediction is skipped, never a 0
        self.assertEqual(gpt_all["points"], 14)
        coh = out["observed"]["models"][COH]
        self.assertEqual(coh["matches"], 2)
        # home_1_0 on (2-1)=6 and (0-1)=0 -> avg 3.0
        self.assertEqual(coh["vs"]["home_1_0"]["reference_avg"], 3.0)
        self.assertEqual(out["out_of_sample"]["models"][COH]["vs"]["home_1_0"]["reference_avg"], 8.0)
        self.assertEqual(out["all"]["consensus"]["matches"], 2)
        self.assertEqual(out["baseline_lock_matchday"], 3)
        self.assertIn("Dış-örnek", ba.overview(out))

    def test_wrong_scoring_rule_is_rejected(self):
        week = self.week(3, [((1, 0), {COH: ("1-0", 8)}, 8)])
        week["scoring_rule"] = "other"
        with self.assertRaises(ValueError):
            ba.analyze({"3": week})

    def test_analysis_output_is_reproducible(self):
        weeks = {"3": self.week(3, [((2, 1), {COH: ("2-1", 8)}, 8), ((0, 2), {COH: ("1-0", 0)}, 0)])}
        self.assertEqual(json.dumps(ba.analyze(weeks), sort_keys=True), json.dumps(ba.analyze(copy.deepcopy(weeks)), sort_keys=True))


class ShippedDataTests(unittest.TestCase):
    def setUp(self):
        self.official = json.loads((DATA_DIR / "kicktipp_weekly_reports.json").read_text(encoding="utf-8"))
        self.stored = json.loads((DATA_DIR / "kicktipp_match_predictions.json").read_text(encoding="utf-8"))

    def test_backfilled_weeks_match_every_official_statistic(self):
        self.assertEqual(sorted(self.stored, key=int)[:3], ["1", "2", "3"])
        for md, week in self.stored.items():
            skip = set(week.get("unreconstructed_models") or [])
            self.assertEqual(mpa.week_integrity_problems(week["matches"], self.official[md]["stats"], skip), [], md)
            self.assertEqual(week["scoring_rule"], SCORING_RULE)

    def test_reconstruction_script_reproduces_the_shipped_file(self):
        for md, rows in recon.WEEKS.items():
            week, problems = recon.build_week(md, rows, self.official[str(md)])
            self.assertEqual(problems, [])
            self.assertEqual(week["matches"], self.stored[str(md)]["matches"])

    def test_matchday_one_documents_what_could_not_be_reconstructed(self):
        self.assertEqual(self.stored["1"]["unreconstructed_models"], ["Groq Qwen 3.6 27B", "Mistral Small Latest"])
        self.assertEqual(self.stored["2"]["unreconstructed_models"], [])


if __name__ == "__main__":
    unittest.main()
