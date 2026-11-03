"""No AI, GitHub write, football network or real Telegram operations in these tests."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import performance_bot as bot
from performance_engine import (SCORING_RULE, build_season_snapshot,
                                build_weekly_stats, grade_record,
                                matchday_resolution, merge_latest_results)
from weekly_report import _consensus_row, _model_row, render_season_image, render_weekly_image


def fixture(mid, md=2, status="FINISHED", score=(2, 1)):
    return {"id": mid, "matchday": md, "status": status,
            "homeTeam": {"name": "Home"}, "awayTeam": {"name": "Away"},
            "score": ({"duration": "REGULAR", "fullTime": {"home": score[0], "away": score[1]}}
                      if score is not None else {})}


def prediction(mid, md=2, consensus=None):
    if consensus is None:
        consensus = {"winner_consensus": True, "score_consensus": False,
                     "outcome": "HOME", "score": None}
    return {"matchday": md, "match_id": str(mid), "final_sent": True,
            "prediction_mode": "NORMAL", "consensus": copy.deepcopy(consensus),
            "published_consensus": copy.deepcopy(consensus),
            "ai_votes": [
                {"model": "Groq Qwen 3.8 27B", "success": True,
                 "result": {"score": "2-1", "outcome": "HOME"}},
                {"model": "Cohere Command A+", "success": True,
                 "result": {"score": "3-2", "outcome": "HOME"}},
                {"model": "Groq GPT-OSS 120B", "success": True,
                 "result": {"score": "3-0", "outcome": "HOME"}},
            ]}


class StatisticsIntegrity(unittest.TestCase):
    def test_consensus_point_distribution_and_accuracy_are_distinct(self):
        c = {"winner_consensus": True, "score_consensus": False,
             "outcome": "HOME", "score": None}
        preds = {
            "1": grade_record(prediction(1, consensus=c), 2, 1),
            "2": grade_record(prediction(2, consensus=c), 0, 2),
        }
        original = copy.deepcopy(preds)
        weekly = build_weekly_stats(preds, 2)
        self.assertEqual(preds, original)
        self.assertEqual(weekly["consensus"]["point_distribution"], {"8": 0, "6": 0, "4": 1, "0": 1})
        self.assertEqual(weekly["consensus"]["points"], 4)
        self.assertEqual(weekly["consensus"]["outcome_pct"], 50)
        self.assertEqual(weekly["consensus"]["point_efficiency_pct"], 25)
        cview = _consensus_row(weekly)
        self.assertEqual(cview["outcome_pct"], 50)
        self.assertEqual(cview["pct"], 25)
        self.assertEqual(cview["avg"], 2)
        self.assertEqual(weekly["models"]["Groq Qwen 3.8 27B"]["points"], 8)
        self.assertEqual(weekly["models"]["Groq Qwen 3.8 27B"]["outcome_pct"], 50)

        md = {"status": "FINAL", "scoring_rule": SCORING_RULE, "stats": weekly}
        season = build_season_snapshot({"2": md})
        self.assertEqual(season["consensus"]["point_distribution"]["4"], 1)
        self.assertEqual(season["consensus"]["point_distribution"]["0"], 1)
        self.assertEqual(season["consensus"]["outcome_pct"], 50)
        self.assertEqual(season["consensus"]["point_efficiency_pct"], 25)
        self.assertEqual(season["consensus"]["coverage_pct"], 100)

    def test_empty_or_failed_model_is_not_declared_successful(self):
        row = _model_row("Gemini 3.6 Flash", {"failed_predictions": 3, "successful_predictions": 0})
        self.assertEqual(row["points"], 0)
        self.assertIsNone(row["outcome_pct"])
        self.assertIsNone(row["avg"])
        self.assertEqual(row["coverage_pct"], 0)

    def test_officially_finished_unavailable_attempt_counts_failure_not_zero_points(self):
        rec = prediction(50)
        rec["ai_votes"] = [{"model": "Groq Qwen 3.8 27B", "success": False, "result": None}]
        rec["consensus"] = {"winner_consensus": False}
        rec["published_consensus"] = {"winner_consensus": False}
        fixtures = [fixture(50)]
        graded = merge_latest_results({"50": rec}, {"50": fixtures[0]})
        resolution = matchday_resolution(fixtures, graded)
        self.assertTrue(resolution["final"])
        self.assertEqual(resolution["unavailable_matches"], 1)
        from performance_engine import build_weekly_snapshot
        snap = build_weekly_snapshot(graded, 2, resolution)
        qwen = snap["stats"]["models"]["Groq Qwen 3.8 27B"]
        self.assertEqual(qwen["failed_predictions"], 1)
        self.assertEqual(qwen["successful_predictions"], 0)
        self.assertEqual(qwen["point_distribution"], {"8": 0, "6": 0, "4": 0, "0": 0})
        self.assertEqual(snap["stats"]["consensus"]["evaluated_matches"], 1)
        self.assertEqual(snap["stats"]["consensus"]["no_consensus"], 1)

    def test_missing_official_score_never_final_even_without_prediction(self):
        res = matchday_resolution([fixture(1, score=None)], {})
        self.assertFalse(res["final"])
        self.assertEqual(res["unavailable_matches"], 0)
        self.assertEqual(res["pending_matches"], 1)

    def test_postponed_fixture_blocks_final(self):
        res = matchday_resolution([fixture(1, status="POSTPONED")], {})
        self.assertFalse(res["final"])
        self.assertEqual(res["postponed_matches"], 1)

    def test_league_phase_missing_fixture_blocks_final_only_in_configured_production(self):
        matches = [fixture(i) for i in range(17)]
        with patch.dict(os.environ, {"EXPECTED_UCL_LEAGUE_MATCHES": "18"}):
            res = matchday_resolution(matches, {})
        self.assertFalse(res["final"])
        self.assertEqual(res["provider_missing_fixtures"], 1)
        self.assertEqual(res["pending_matches"], 1)


class DurableDeliverySafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reports = self.root / "reports"
        self.reports.mkdir()
        self.data = self.root / "data"
        self.data.mkdir()
        self.records = {"100": prediction(100, 2)}
        self.orig_records = copy.deepcopy(self.records)
        self.fixtures = {2: [fixture(100, 2)]}
        self.sent = []
        self.patches = [
            patch.multiple(bot, DATA_DIR=self.data,
                           WEEKLY_REPORTS_FILE=self.data / "kicktipp_weekly_reports.json",
                           SEASON_PERFORMANCE_FILE=self.data / "kicktipp_season_performance.json",
                           TELEGRAM_ENABLED=True),
            patch.object(bot, "load_prediction_archive", return_value=self.records),
            patch.object(bot, "FootballDataResultProvider"),
            patch("weekly_report.REPORT_DIR", self.reports),
            patch("config.REPORT_DIR", self.reports),
            patch.object(bot, "send_photo", side_effect=lambda *args: self.sent.append(args)),
            patch.dict(os.environ, {"PERFORMANCE_RUN_KEY": "run-123"}),
        ]
        for m in self.patches:
            m.start()
            self.addCleanup(m.stop)
        bot.FootballDataResultProvider.return_value.get_matches_by_matchday.return_value = self.fixtures

    def _weekly(self):
        return json.loads((self.data / "kicktipp_weekly_reports.json").read_text())

    def test_prepare_then_reserve_then_deliver_once(self):
        self.assertEqual(bot.prepare_reports(), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(self._weekly()["2"]["delivery"], {"weekly": "PENDING", "season": "PENDING"})
        self.assertTrue((self.reports / "kicktipp_matchday_2_weekly.png").exists())
        self.assertTrue((self.reports / "kicktipp_season_performance.png").exists())
        self.assertEqual(bot.reserve_deliveries(), 0)
        self.assertEqual(self._weekly()["2"]["delivery"], {"weekly": "UNCERTAIN", "season": "UNCERTAIN"})
        self.assertEqual(self.sent, [])
        self.assertEqual(bot.deliver_reserved(), 0)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self._weekly()["2"]["delivery"], {"weekly": "SENT", "season": "SENT"})
        self.assertEqual(bot.prepare_reports(), 0)
        self.assertEqual(bot.reserve_deliveries(), 0)
        with patch.dict(os.environ, {"PERFORMANCE_RUN_KEY": "run-new-attempt"}):
            self.assertEqual(bot.deliver_reserved(), 0)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.records, self.orig_records)

    def test_crash_after_first_send_cannot_trigger_auto_retry(self):
        self.assertEqual(bot.prepare_reports(), 0)
        self.assertEqual(bot.reserve_deliveries(), 0)
        def fail_after_first(*args):
            self.sent.append(args)
            raise RuntimeError("Simulated Telegram timeout after acceptance")
        with patch.object(bot, "send_photo", side_effect=fail_after_first):
            with self.assertRaisesRegex(RuntimeError, "Simulated"):
                bot.deliver_reserved()
        state = self._weekly()["2"]["delivery"]
        self.assertEqual(state["weekly"], "UNCERTAIN")
        self.assertEqual(state["season"], "UNCERTAIN")
        with patch.dict(os.environ, {"PERFORMANCE_RUN_KEY": "run-124"}):
            self.assertEqual(bot.prepare_reports(), 0)
            self.assertEqual(bot.reserve_deliveries(), 0)
            self.assertEqual(bot.deliver_reserved(), 0)
        self.assertEqual(len(self.sent), 1)

    def test_user_confirmed_weeks_are_locked_without_resend(self):
        (self.data / "kicktipp_delivery_locks.json").write_text(json.dumps({"2": {"weekly": "SENT", "season": "SENT"}}))
        self.assertEqual(bot.prepare_reports(), 0)
        self.assertEqual(self._weekly()["2"]["delivery"], {"weekly": "SENT", "season": "SENT"})
        self.assertEqual(bot.reserve_deliveries(), 0)
        self.assertEqual(bot.deliver_reserved(), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.records, self.orig_records)

    def test_missing_historical_lock_fails_closed_in_production(self):
        with patch.dict(os.environ, {"REQUIRE_DELIVERY_LOCKS": "true"}):
            with self.assertRaisesRegex(RuntimeError, "delivery locks missing"):
                bot.prepare_reports()
        self.assertFalse((self.data / "kicktipp_weekly_reports.json").exists())
        self.assertEqual(self.sent, [])

    def test_existing_final_receipt_is_byte_identical(self):
        final = {"2": {"season": "2026/27", "status": "FINAL", "scoring_rule": SCORING_RULE,
                       "delivery": {"weekly": "SENT", "season": "SENT"},
                       "stats": {"models": {}, "consensus": {}},
                       "matches": [{"match_id": "100", "status": "EVALUATED", "verified_score": {"home": 2, "away": 1}}]}}
        path = self.data / "kicktipp_weekly_reports.json"
        path.write_text(json.dumps(final, indent=2), encoding="utf-8")
        original = path.read_bytes()
        self.assertEqual(bot.prepare_reports(), 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.data / "kicktipp_season_performance.json").exists())


class WorkflowOrderSafety(unittest.TestCase):
    def test_git_push_barrier_precedes_telegram_and_ignored_images_are_force_added(self):
        text = (Path(__file__).resolve().parents[1] / ".github/workflows/performance_bot.yml").read_text()
        indices = [text.index(term) for term in (
            "python performance_bot.py prepare",
            "Save verified performance archives BEFORE delivery",
            "python performance_bot.py reserve",
            "Persist delivery reservations BEFORE Telegram",
            "python performance_bot.py deliver",
            "Save Telegram delivery receipts",
        )]
        self.assertEqual(indices, sorted(indices))
        self.assertIn('git add -f -- "$f"', text)
        self.assertIn('git push origin "HEAD:${GITHUB_REF_NAME}"', text)
        locks = json.loads((Path(__file__).resolve().parents[1] / "data/kicktipp_delivery_locks.json").read_text())
        self.assertEqual(locks["1"]["weekly"], "SENT")
        self.assertEqual(locks["2"]["season"], "SENT")


if __name__ == "__main__":
    unittest.main()
