"""Read-only safety checks for report finalization and legacy FINAL receipts."""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import performance_bot as bot
from performance_engine import matchday_resolution, merge_latest_results


def fixture(match_id, score=None, status="FINISHED"):
    return {
        "id": match_id,
        "matchday": 2,
        "status": status,
        "homeTeam": {"name": "A"},
        "awayTeam": {"name": "B"},
        "score": score or {},
    }


def regular(home, away):
    return {"duration": "REGULAR", "fullTime": {"home": home, "away": away}}


def prediction(match_id, success=True, with_result=True):
    return {
        "match_id": str(match_id),
        "matchday": 2,
        "ai_votes": [{
            "model": "Groq Qwen 3.8 27B",
            "success": success,
            "result": {"score": "2-1", "outcome": "HOME"} if success and with_result else None,
        }],
    }


class FinalResolutionTests(unittest.TestCase):
    def test_missing_provider_result_blocks_final_with_successful_prediction(self):
        records = {"1": prediction(1)}
        records["1"]["actual"] = {"home": 2, "away": 1, "scope": "REGULAR_90"}
        records_before = copy.deepcopy(records)
        games = [fixture(1)]
        graded = merge_latest_results(records, {"1": games[0]})
        self.assertIn("actual", graded["1"])  # source actual is not official proof
        state = matchday_resolution(games, graded)
        self.assertFalse(state["final"])
        self.assertEqual(state["pending_matches"], 1)
        self.assertEqual(state["evaluated_matches"], 0)
        self.assertEqual(records, records_before)

    def test_no_prediction_or_failed_attempt_does_not_block_final(self):
        games = [fixture(1), fixture(2), fixture(3)]
        records = {"1": prediction(1, success=False), "2": prediction(2, with_result=False)}
        result = matchday_resolution(games, merge_latest_results(records, {str(m["id"]): m for m in games}))
        self.assertTrue(result["final"])
        self.assertEqual(result["unavailable_matches"], 3)
        self.assertEqual(result["pending_matches"], 0)

    def test_mixed_scored_and_unpredicted_finished_games_finalize(self):
        games = [fixture(1, regular(2, 1)), fixture(2)]
        graded = merge_latest_results({"1": prediction(1)}, {str(m["id"]): m for m in games})
        result = matchday_resolution(games, graded)
        self.assertTrue(result["final"])
        self.assertEqual(result["evaluated_matches"], 1)
        self.assertEqual(result["unavailable_matches"], 1)
        self.assertEqual(result["matches"][0]["verified_score"], {"home": 2, "away": 1})
        self.assertNotIn("verified_score", result["matches"][1])

    def test_wrong_or_extra_time_score_does_not_finalize(self):
        games = [
            fixture(1, {"duration": "EXTRA_TIME", "fullTime": {"home": 3, "away": 2}}),
            fixture(2, {"duration": "REGULAR", "fullTime": {"home": "?", "away": 0}}),
        ]
        preds = {str(m["id"]): prediction(m["id"]) for m in games}
        graded = merge_latest_results(preds, {str(m["id"]): m for m in games})
        result = matchday_resolution(games, graded)
        self.assertFalse(result["final"])
        self.assertEqual(result["pending_matches"], 2)

    def test_scheduled_and_postponed_respect_status(self):
        games = [fixture(1, status="SCHEDULED"), fixture(2, status="POSTPONED")]
        graded = merge_latest_results({"1": prediction(1), "2": prediction(2)}, {})
        result = matchday_resolution(games, graded)
        self.assertFalse(result["final"])
        self.assertEqual(result["pending_matches"], 1)
        self.assertEqual(result["postponed_matches"], 1)


class WorkflowFinalSafetyTests(unittest.TestCase):
    def run_bot(self, root, records, fixtures, sent=None):
        sent = sent or []
        with patch.multiple(
            bot,
            DATA_DIR=root,
            WEEKLY_REPORTS_FILE=root / "weekly.json",
            SEASON_PERFORMANCE_FILE=root / "season.json",
            TELEGRAM_ENABLED=True,
        ), patch.object(bot, "load_prediction_archive", return_value=records), \
             patch.object(bot, "FootballDataResultProvider") as provider, \
             patch.object(bot, "render_weekly_image", return_value=root / "weekly.png"), \
             patch.object(bot, "render_season_image", return_value=root / "season.png"), \
             patch.object(bot, "send_photo", side_effect=lambda *args: sent.append(args)):
            provider.return_value.get_matches_by_matchday.return_value = {2: fixtures}
            logs = io.StringIO()
            with contextlib.redirect_stdout(logs):
                result = bot.main()
        return result, logs.getvalue(), sent

    def test_pending_does_not_write_archive_or_send_telegram(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_season = '{"legacy_season":"DO NOT TOUCH"}'
            (root / "season.json").write_text(old_season, encoding="utf-8")
            code, logs, sent = self.run_bot(root, {"1": prediction(1)}, [fixture(1)])
            self.assertEqual(code, 0)
            self.assertIn("PENDING", logs)
            self.assertFalse((root / "weekly.json").exists())
            self.assertEqual((root / "season.json").read_text(encoding="utf-8"), old_season)
            self.assertEqual(sent, [])

    def test_original_final_is_immutable_and_never_resent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {
                "2": {
                    "season": "2026/27", "matchday": 2, "status": "FINAL",
                    "delivery": {"weekly": "PENDING", "season": "SENT"},
                    "matches": [{"match_id": "1", "status": "EVALUATED", "verified_score": {"home": 2, "away": 1}}],
                    "stats": {"models": {}, "consensus": {}},
                }
            }
            weekly_path = root / "weekly.json"
            weekly_path.write_text(json.dumps(previous, indent=4), encoding="utf-8")
            original_bytes = weekly_path.read_bytes()
            season_path = root / "season.json"
            season_path.write_bytes(b'{"old": true}')
            code, logs, sent = self.run_bot(root, {"1": prediction(1)}, [fixture(1, regular(1, 1))])
            self.assertEqual(code, 0)
            self.assertIn("official 90-minute score changed", logs)
            self.assertEqual(weekly_path.read_bytes(), original_bytes)
            self.assertEqual(season_path.read_bytes(), b'{"old": true}')
            self.assertEqual(sent, [])

    def test_old_final_without_stored_scores_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {"2": {"season": "2026/27", "matchday": 2, "status": "FINAL",
                              "matches": [{"match_id": "1", "status": "EVALUATED"}]}}
            path = root / "weekly.json"
            path.write_text(json.dumps(previous), encoding="utf-8")
            original = path.read_bytes()
            code, logs, sent = self.run_bot(root, {"1": prediction(1)}, [fixture(1, regular(1, 1))])
            self.assertEqual(code, 0)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(sent, [])
            # Old FINAL lacks saved scores: do not misreport a verified score change.
            self.assertNotIn("official 90-minute score changed", logs)

    def test_new_final_stores_score_and_sends_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pred = {"1": prediction(1)}
            games = [fixture(1, regular(2, 1)), fixture(2)]
            code, logs, sent = self.run_bot(root, pred, games)
            self.assertEqual(code, 0)
            self.assertEqual(len(sent), 2)
            report = json.loads((root / "weekly.json").read_text(encoding="utf-8"))["2"]
            self.assertEqual(report["matches"][0]["verified_score"], {"home": 2, "away": 1})
            self.assertEqual(report["unavailable_matches"], 1)
            self.assertTrue((root / "season.json").exists())
            code, logs, sent = self.run_bot(root, pred, games)
            self.assertEqual(code, 0)
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
