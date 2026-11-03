"""Zero-network regression checks for the round-1 review fixes (items 1-6)."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import common_match_report as cmr
import performance_bot as bot
import weekly_report as wr
from config import ACTIVE_MODEL_ORDER
from experimental_performance import thin_provenance_margins
from github_provenance import GitHubPreKickoffEvidence
from performance_engine import grade_record, low_coverage_models
from result_provider import FootballDataResultProvider
from test_experimental_performance import KICKOFF, _FakeSession, record as exp_record


def _vote(model, score, ok=True):
    if not ok:
        return {"model": model, "success": False, "result": None, "error": "X"}
    h, a = map(int, score.split("-"))
    return {"model": model, "success": True,
            "result": {"score": score, "outcome": "HOME" if h > a else "AWAY" if h < a else "DRAW"}}


class DateAndColourTests(unittest.TestCase):
    def test_match_utc_is_shown_in_turkey_time(self):
        # 19:00Z -> 22:00 Turkey (UTC+3); archive field is `match_utc`.
        self.assertEqual(wr._record_time({"match_utc": "2026-10-20T19:00:00Z"}), "20.10\n22:00")
        self.assertEqual(wr._record_time({"utcDate": "2026-10-20T16:45:00Z"}), "20.10\n19:45")

    def test_date_rolls_over_midnight_in_turkey_time(self):
        self.assertEqual(wr._record_time({"utcDate": "2026-10-20T22:30:00Z"}), "21.10\n01:30")

    def test_naive_and_missing_dates_are_safe(self):
        self.assertEqual(wr._record_time({"utcDate": "2026-10-20T19:00:00"}), "20.10\n22:00")
        self.assertEqual(wr._record_time({}), "—")

    def test_render_records_take_kickoff_from_verified_fixture(self):
        snap = {"matches": [{"match_id": "7", "status": "EVALUATED", "utcDate": "2026-10-20T19:00:00Z",
                             "home": "A", "away": "B"}]}
        out = bot._prepare_render_records(snap, {"7": {"match_id": "7", "ai_votes": []}})
        rec = out["render_records"][0]
        self.assertEqual(rec["utcDate"], "2026-10-20T19:00:00Z")
        self.assertEqual(wr._record_time(rec), "20.10\n22:00")
        self.assertEqual(rec["home"], "A")

    def test_model_colour_does_not_depend_on_roster_position(self):
        self.assertEqual(wr._model_color("Cohere Command A+", 0), wr._model_color("Cohere Command A+", 3))
        self.assertEqual(len({wr._model_color(m) for m in ACTIVE_MODEL_ORDER}), len(ACTIVE_MODEL_ORDER))

    def test_weekly_image_renders_with_dates(self):
        votes = [_vote(m, "2-1") for m in ACTIVE_MODEL_ORDER]
        rec = grade_record({"match_id": "1", "matchday": 3, "home": "A", "away": "B",
                            "match_utc": "2026-10-20T19:00:00Z", "ai_votes": votes}, 2, 1)
        from performance_engine import build_weekly_stats
        snap = {"season": "2026/27", "matchday": 3, "planned_matches": 1, "evaluated_matches": 1,
                "stats": build_weekly_stats({"1": rec}, 3), "render_records": [rec]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(wr, "REPORT_DIR", Path(tmp)):
            self.assertTrue(wr.render_weekly_image(snap).is_file())


class KnockoutGroupingTests(unittest.TestCase):
    def _provider(self, matches):
        provider = FootballDataResultProvider(api_key="x")
        provider.get_all_matches = lambda: matches
        return provider

    def test_knockout_matches_never_join_a_league_matchday(self):
        league = {"id": 1, "matchday": 1, "stage": "LEAGUE_STAGE", "utcDate": "2026-09-08T19:00:00Z"}
        playoff = {"id": 2, "matchday": 1, "stage": "PLAYOFFS", "utcDate": "2027-02-17T19:00:00Z"}
        last16 = {"id": 3, "matchday": 2, "stage": "LAST_16", "utcDate": "2027-03-10T19:00:00Z"}
        grouped = self._provider([league, playoff, last16]).get_matches_by_matchday()
        self.assertEqual(list(grouped), [1])
        self.assertEqual([m["id"] for m in grouped[1]], [1])

    def test_missing_stage_is_kept_for_backward_compatibility(self):
        grouped = self._provider([{"id": 1, "matchday": 3, "utcDate": "x"}]).get_matches_by_matchday()
        self.assertEqual(list(grouped), [3])


class DiagnosticWarningTests(unittest.TestCase):
    def test_low_coverage_models_are_listed_without_changing_stats(self):
        stats = {"models": {
            "Gemini 3.6 Flash": {"prediction_opportunities": 16, "successful_predictions": 5},
            "Cohere Command A+": {"prediction_opportunities": 16, "successful_predictions": 14},
            "Mistral Small Latest": {"prediction_opportunities": 16, "successful_predictions": 0},
        }}
        before = copy.deepcopy(stats)
        found = low_coverage_models(stats, 50)
        self.assertEqual([x["model"] for x in found], ["Gemini 3.6 Flash"])  # retired Mistral not flagged
        self.assertEqual(found[0]["coverage_pct"], 31.2)
        self.assertEqual(stats, before)

    def test_prepare_emits_warning_for_low_coverage_week(self):
        stats = {"models": {"Gemini 3.6 Flash": {"prediction_opportunities": 17, "successful_predictions": 0}}}
        self.assertEqual(low_coverage_models(stats)[0]["coverage_pct"], 0.0)

    def test_provenance_reports_lead_minutes(self):
        r = exp_record()
        out = GitHubPreKickoffEvidence(token="t", session=_FakeSession({"101": copy.deepcopy(r)})).verify(
            "101", KICKOFF, r["experimental_predictions"])
        self.assertTrue(out["verified"])
        self.assertEqual(out["lead_minutes"], 15.0)  # commit 16:45Z, kickoff 17:00Z

    def test_thin_margin_listing(self):
        report = {"methods": {"m": {"provenance": {"1": {"lead_minutes": 15.0}, "2": {"lead_minutes": 55.0},
                                                   "3": {"commit_sha": "legacy-without-lead"}}}}}
        self.assertEqual(thin_provenance_margins(report, 20), [{"method": "m", "match_id": "1", "lead_minutes": 15.0}])


def _graded(mid, consensus, votes, actual):
    rec = {"match_id": mid, "matchday": 3, "ai_votes": votes, "consensus": consensus}
    return grade_record(rec, *actual)


class CommonMatchTests(unittest.TestCase):
    def setUp(self):
        full = {"winner_consensus": True, "score_consensus": True, "outcome": "HOME", "score": "2-1"}
        split = {"winner_consensus": True, "score_consensus": False, "outcome": "HOME", "score": None}
        none = {"winner_consensus": False, "score_consensus": False}
        self.graded = {
            "1": _graded("1", full, [_vote("Cohere Command A+", "2-1"), _vote("Groq GPT-OSS 120B", "1-0")], (2, 1)),
            "2": _graded("2", split, [_vote("Cohere Command A+", "3-0"), _vote("Groq GPT-OSS 120B", "0-1")], (2, 0)),
            "3": _graded("3", none, [_vote("Cohere Command A+", "1-1"), _vote("Groq GPT-OSS 120B", "", ok=False)], (1, 1)),
        }
        self.snapshot = {"matches": [
            {"match_id": "1", "status": "EVALUATED", "verified_score": {"home": 2, "away": 1}},
            {"match_id": "2", "status": "EVALUATED", "verified_score": {"home": 2, "away": 0}},
            {"match_id": "3", "status": "EVALUATED", "verified_score": {"home": 1, "away": 1}},
            {"match_id": "4", "status": "UNAVAILABLE", "verified_score": {"home": 0, "away": 0}},
        ]}

    def test_pairwise_comparison_uses_only_common_matches(self):
        week = cmr.build_common_week(3, self.snapshot, self.graded)
        self.assertEqual(week["matches"], 3)
        c = week["consensus"]
        self.assertEqual((c["matches"], c["points"], c["no_consensus_matches"]), (2, 12, 1))  # 8 + 4
        self.assertEqual(c["with_score"]["points"], 8)
        self.assertEqual(c["outcome_only_max4"]["points"], 4)
        cohere = week["models"]["Cohere Command A+"]
        p = cohere["pairwise_vs_consensus"]
        self.assertEqual((p["common_matches"], p["model_points"], p["consensus_points"]), (2, 12, 12))
        self.assertEqual(cohere["on_no_consensus_matches"]["matches"], 1)  # match 3 only
        self.assertEqual(cohere["on_no_consensus_matches"]["points"], 8)
        gpt = week["models"]["Groq GPT-OSS 120B"]["pairwise_vs_consensus"]
        self.assertEqual(gpt["common_matches"], 2)  # failed vote on match 3 is not a 0
        self.assertEqual((gpt["model_points"], gpt["consensus_points"]), (6, 12))  # 1-0 vs 2-1 = same goal diff -> 6; 0-1 vs 2-0 = 0
        self.assertEqual(gpt["consensus_better"], 2)

    def test_unavailable_matches_are_ignored_and_drift_is_refused(self):
        self.assertEqual(len(cmr.build_common_week(3, self.snapshot, self.graded)["rows"]), 3)
        drift = copy.deepcopy(self.snapshot)
        drift["matches"][0]["verified_score"] = {"home": 9, "away": 9}
        self.assertIsNone(cmr.build_common_week(3, drift, self.graded))

    def test_season_is_the_sum_of_weeks_and_inputs_are_not_mutated(self):
        snap_before, graded_before = copy.deepcopy(self.snapshot), copy.deepcopy(self.graded)
        week = cmr.build_common_week(3, self.snapshot, self.graded)
        other = copy.deepcopy(week)
        other["matchday"] = 4
        season = cmr.build_common_season({"3": week, "4": other})
        self.assertEqual(season["matches"], 6)
        self.assertEqual(season["consensus"]["points"], 24)
        self.assertEqual(season["finalized_matchdays"], ["3", "4"])
        self.assertEqual((self.snapshot, self.graded), (snap_before, graded_before))
        self.assertIn("Konsensüs", cmr._overview(season))

    def test_existing_weeks_are_immutable_and_idle_runs_make_no_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            week = cmr.build_common_week(3, self.snapshot, self.graded)
            (root / "common.json").write_text(json.dumps({"3": week}), encoding="utf-8")
            official = {"3": {"status": "FINAL", "season": "2026/27"}}
            (root / "official.json").write_text(json.dumps(official), encoding="utf-8")
            with patch.object(cmr, "COMMON_WEEKLY", root / "common.json"), \
                    patch.object(cmr, "WEEKLY_REPORTS_FILE", root / "official.json"), \
                    patch("source_loader.load_prediction_archive") as load:
                self.assertEqual(cmr.prepare_common_reports(), 0)
                load.assert_not_called()


class DeadCodeRemovedTests(unittest.TestCase):
    def test_unused_settings_are_gone(self):
        import config
        for name in ("REPORT_DELAY_MINUTES", "PERFORMANCE_STATE_FILE"):
            self.assertFalse(hasattr(config, name))
        self.assertTrue(config.LEAGUE_STAGES)


if __name__ == "__main__":
    unittest.main()
