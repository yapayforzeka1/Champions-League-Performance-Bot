import unittest

from consensus_engine import build_consensus
from performance_engine import grade_record, matchday_resolution


def vote(model, score, success=True):
    if not success:
        return {"model": model, "success": False, "result": None, "error": "429"}
    h, a = map(int, score.split("-"))
    outcome = "HOME" if h > a else "AWAY" if h < a else "DRAW"
    return {"model": model, "success": True, "result": {"score": score, "outcome": outcome}}


class CoreTests(unittest.TestCase):
    def test_strict_majority(self):
        c = build_consensus([vote("a", "2-1"), vote("b", "2-1"), vote("c", "1-1"), vote("d", "1-2"), vote("e", "2-0")])
        self.assertEqual(c["consensus_mode"], "OUTCOME_COMMON_SCORE_SPLIT")
        self.assertEqual(c["outcome"], "HOME")
        self.assertIsNone(c["score"])

    def test_no_plurality_consensus(self):
        c = build_consensus([vote("a", "2-1"), vote("b", "1-2"), vote("c", "1-1"), vote("d", "2-1", False)])
        self.assertEqual(c["consensus_mode"], "NO_COMMON")
        self.assertFalse(c["winner_consensus"])

    def test_scoring(self):
        r = {"match_id": "1", "matchday": 1, "home_team": "A", "away_team": "B", "ai_votes": [vote("a", "2-1"), vote("b", "1-0"), vote("c", "2-2")]}
        graded = grade_record(r, 2, 1)
        self.assertEqual([v["points"] for v in graded["ai_votes"]], [5, 3, 0])
        self.assertEqual(graded["consensus_points"], 3)

    def test_no_prediction_is_unavailable_not_zero(self):
        fixtures = [
            {"id": 1, "matchday": 1, "status": "FINISHED", "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}},
            {"id": 2, "matchday": 1, "status": "FINISHED", "homeTeam": {"name": "C"}, "awayTeam": {"name": "D"}},
            {"id": 3, "matchday": 1, "status": "SCHEDULED", "homeTeam": {"name": "E"}, "awayTeam": {"name": "F"}},
        ]
        predictions = {"1": {"actual": {"home": 1, "away": 0}}}
        resolution = matchday_resolution(fixtures, predictions)
        self.assertFalse(resolution["final"])
        self.assertEqual(resolution["evaluated_matches"], 1)
        self.assertEqual(resolution["unavailable_matches"], 1)
        self.assertEqual(resolution["pending_matches"], 1)

    def test_final_when_all_fixtures_resolved(self):
        fixtures = [
            {"id": 1, "matchday": 1, "status": "FINISHED", "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}},
            {"id": 2, "matchday": 1, "status": "CANCELLED", "homeTeam": {"name": "C"}, "awayTeam": {"name": "D"}},
        ]
        predictions = {"1": {"actual": {"home": 1, "away": 0}}}
        resolution = matchday_resolution(fixtures, predictions)
        self.assertTrue(resolution["final"])
        self.assertEqual(resolution["unavailable_matches"], 0)
        self.assertEqual(resolution["postponed_matches"], 1)


if __name__ == "__main__":
    unittest.main()
