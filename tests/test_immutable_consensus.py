"""Regression coverage: historical predictions and receipts are immutable."""
import copy
import json
import unittest

from performance_engine import (archived_consensus, grade_record,
                                merge_latest_results, build_weekly_stats)
from performance_bot import _prepare_render_records


def vote(score, outcome, model="Gemini 3.6 Flash"):
    return {"model": model, "success": True,
            "result": {"score": score, "outcome": outcome}}


def archived_record(mid, matchday, consensus, votes, published=None):
    return {"match_id": str(mid), "matchday": matchday, "final_sent": True,
            "prediction_mode": "NORMAL", "ai_votes": votes,
            "consensus": copy.deepcopy(consensus),
            "published_consensus": copy.deepcopy(published or consensus),
            "actual": {"home": 1, "away": 4, "scope": "REGULAR_90"},
            "post_match_analysis": {"locked": "historical"}}


class ImmutableConsensusTests(unittest.TestCase):
    def test_mismatch_with_reconstructed_vote_never_changes_record(self):
        frozen = {"winner_consensus": True, "score_consensus": False,
                  "score": None, "outcome": "AWAY", "consensus_mode": "OUTCOME_COMMON_SCORE_SPLIT"}
        votes = [vote("0-3", "AWAY") for _ in range(3)]
        record = archived_record(575344, 2, frozen, votes)
        original = copy.deepcopy(record)
        graded = grade_record(record, 1, 4)
        self.assertEqual(record, original)
        for field in ("consensus", "published_consensus", "prediction_mode", "final_sent", "post_match_analysis"):
            self.assertEqual(graded[field], original[field])
        self.assertEqual(graded["consensus_points"], 4)
        self.assertEqual(graded["ai_votes"][0]["points"], 6)

    def test_published_receipt_is_authoritative_when_consensus_drifted(self):
        original = {"winner_consensus": True, "score_consensus": True,
                    "score": "2-1", "outcome": "HOME"}
        drift = {"winner_consensus": False, "score_consensus": False,
                 "score": None, "outcome": None}
        record = archived_record(575329, 1, drift, [vote("1-1", "DRAW")], published=original)
        graded = grade_record(record, 2, 1)
        self.assertEqual(graded["consensus"], drift)
        self.assertEqual(graded["published_consensus"], original)
        self.assertEqual(graded["consensus_points"], 8)
        display = _prepare_render_records({"matches": [{"status": "EVALUATED", "match_id": "575329"}]},
                                          {"575329": graded})
        self.assertEqual(display["render_records"][0]["consensus"], original)

    def test_no_saved_consensus_does_not_invent_past_decision(self):
        record = {"matchday": 1, "ai_votes": [vote("2-1", "HOME") for _ in range(3)]}
        graded = grade_record(record, 2, 1)
        self.assertNotIn("consensus", graded)
        self.assertIsNone(graded["consensus_points"])
        stats = build_weekly_stats({"a": graded}, 1)
        self.assertEqual(stats["consensus"]["matches"], 0)
        self.assertEqual(stats["consensus"]["no_consensus"], 1)

    def test_merged_weeks_never_mutate_sources_or_consensus(self):
        c1 = {"winner_consensus": True, "score_consensus": True, "outcome": "HOME", "score": "3-1"}
        c2 = {"winner_consensus": True, "score_consensus": False, "outcome": "AWAY", "score": None}
        records = {"575329": archived_record(575329, 1, c1, [vote("0-1", "AWAY")]),
                   "575344": archived_record(575344, 2, c2, [vote("0-3", "AWAY")])}
        prior = json.dumps(records, sort_keys=True)
        status_map = {
            "575329": {"status": "FINISHED", "score": {"duration": "REGULAR", "fullTime": {"home": 5, "away": 1}}},
            "575344": {"status": "FINISHED", "score": {"duration": "REGULAR", "fullTime": {"home": 1, "away": 4}}},
        }
        graded = merge_latest_results(records, status_map)
        self.assertEqual(json.dumps(records, sort_keys=True), prior)
        for mid in records:
            for field in ("consensus", "published_consensus", "prediction_mode", "final_sent", "post_match_analysis"):
                self.assertEqual(graded[mid][field], records[mid][field])
        self.assertEqual(graded["575329"]["consensus_points"], 4)
        self.assertEqual(graded["575344"]["consensus_points"], 4)

if __name__ == "__main__":
    unittest.main()
