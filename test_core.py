import unittest
from consensus_engine import build_consensus
from performance_engine import grade_record, matchday_resolution, score_points


def vote(model, score, success=True):
    if not success:
        return {"model": model, "success": False, "result": None, "error": "429"}
    h, a = map(int, score.split("-")); outcome = "HOME" if h > a else "AWAY" if h < a else "DRAW"
    return {"model": model, "success": True, "result": {"score": score, "outcome": outcome}}


class CoreTests(unittest.TestCase):
    def test_consensus_requires_three_successful_ai(self):
        c = build_consensus([vote("a", "2-1"), vote("b", "2-1"), vote("c", "1-1", False), vote("d", "1-2", False), vote("e", "2-0", False)])
        self.assertFalse(c["minimum_ai_met"]); self.assertFalse(c["winner_consensus"])

    def test_strict_majority_with_three_or_more(self):
        c = build_consensus([vote("a", "2-1"), vote("b", "2-1"), vote("c", "1-1"), vote("d", "1-2"), vote("e", "2-0")])
        self.assertEqual(c["consensus_mode"], "OUTCOME_COMMON_SCORE_SPLIT"); self.assertEqual(c["outcome"], "HOME"); self.assertIsNone(c["score"])

    def test_performance_scoring(self):
        self.assertEqual(score_points("3-1", "HOME", 3, 1)[0], 8)
        self.assertEqual(score_points("2-0", "HOME", 3, 1)[0], 6)
        self.assertEqual(score_points("1-0", "HOME", 3, 1)[0], 4)
        self.assertEqual(score_points("0-0", "DRAW", 2, 2)[0], 6)
        self.assertEqual(score_points("1-1", "DRAW", 3, 1)[0], 0)

    def test_outcome_only_consensus_is_four_even_for_draw(self):
        self.assertEqual(score_points(None, "DRAW", 2, 2)[0], 4)
        self.assertEqual(score_points(None, "HOME", 2, 1)[0], 4)
        self.assertEqual(score_points("1-1", "DRAW", 2, 2)[0], 6)
        self.assertEqual(score_points("3-2", "HOME", 2, 1)[0], 6)
        self.assertEqual(score_points("3-0", "HOME", 2, 1)[0], 4)

    def test_individual_scored_without_consensus(self):
        r={"match_id":"1","matchday":1,"ai_votes":[vote("a","3-1"),vote("b","1-1"),vote("c","0-1",False)]}
        g=grade_record(r,3,1); self.assertEqual(g["ai_votes"][0]["points"],8); self.assertEqual(g["ai_votes"][1]["points"],0); self.assertIsNone(g["consensus_points"])

    def test_no_prediction_is_unavailable_not_zero(self):
        fixtures=[{"id":1,"status":"FINISHED","homeTeam":{"name":"A"},"awayTeam":{"name":"B"},
                   "score":{"duration":"REGULAR","fullTime":{"home":1,"away":0}}},
                  {"id":2,"status":"SCHEDULED","homeTeam":{"name":"C"},"awayTeam":{"name":"D"}}]
        r=matchday_resolution(fixtures,{"1":{"actual":{"home":1,"away":0},"ai_votes":[vote("a","1-0")]}})
        self.assertFalse(r["final"]); self.assertEqual(r["evaluated_matches"],1); self.assertEqual(r["pending_matches"],1)

    def test_matchday_final_when_all_resolved(self):
        fixtures=[{"id":1,"status":"FINISHED","homeTeam":{"name":"A"},"awayTeam":{"name":"B"},
                   "score":{"duration":"REGULAR","fullTime":{"home":1,"away":0}}}]
        result=matchday_resolution(fixtures,{"1":{"actual":{"home":1,"away":0},"ai_votes":[vote("a","1-0")]}})
        self.assertTrue(result["final"])
        self.assertEqual(result["evaluated_matches"],1)


if __name__ == "__main__": unittest.main()
