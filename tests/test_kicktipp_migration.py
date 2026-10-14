"""Legacy FINAL stays intact; current Kicktipp points are recomputed only once."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import performance_bot as bot
from performance_engine import SCORING_RULE


class KicktippMigrationIntegration(unittest.TestCase):
    def test_legacy_week_one_new_week_two_and_90min_guard(self):
        with tempfile.TemporaryDirectory() as rootstr:
            root = Path(rootstr)
            legacy = {'1': {'status': 'FINAL', 'season': '2026/27',
                            'matches': [{'match_id':'1','status':'EVALUATED','verified_score': {'home':2,'away':1}}],
                            'delivery': {'weekly':'SENT','season':'SENT'},
                            'stats':{'models': {'Gemini 3.6 Flash': {'points':5}}, 'consensus':{}}}}
            before = json.dumps(legacy, indent=2)
            (root/'weekly_reports.json').write_text(before)
            votes = [{'model':'Gemini 3.6 Flash','success':True,'result': {'score':'2-1','outcome':'HOME'}}]
            records = {'1': {'matchday':1,'ai_votes':votes,'actual':{'scope':'REGULAR_90','home':2,'away':1}},
                       '2': {'matchday':2,'ai_votes':votes,'actual':{'scope':'REGULAR_90','home':2,'away':1}}}
            def fixture(n,md):
                return {'id':n,'matchday':md,'status':'FINISHED',
                        'score': {'duration':'REGULAR', 'fullTime': {'home':2,'away':1}},
                        'homeTeam':{'name':'A'},'awayTeam':{'name':'B'}}
            sent = []
            with patch.multiple(bot,DATA_DIR=root,WEEKLY_REPORTS_FILE=root/'kicktipp_weekly_reports.json',
                                SEASON_PERFORMANCE_FILE=root/'kicktipp_season_performance.json',TELEGRAM_ENABLED=True), \
                 patch.object(bot,'load_prediction_archive',return_value=records), \
                 patch.object(bot,'FootballDataResultProvider') as provider, \
                 patch.object(bot,'render_weekly_image',return_value=root/'test_week.png'), \
                 patch.object(bot,'render_season_image',return_value=root/'test_season.png'), \
                 patch.object(bot,'send_photo',side_effect=lambda *a:sent.append(a)):
                provider.return_value.get_matches_by_matchday.return_value = {1: [fixture(1,1)],2:[fixture(2,2)]}
                self.assertEqual(bot.main(),0)
                current = json.loads((root/'kicktipp_weekly_reports.json').read_text())
                self.assertEqual(current['1']['stats']['models']['Gemini 3.6 Flash']['points'],8)
                self.assertEqual(current['2']['stats']['models']['Gemini 3.6 Flash']['points'],8)
                self.assertEqual(current['1']['scoring_rule'],SCORING_RULE)
                self.assertTrue(current['1']['migrated_from_legacy_final'])
                self.assertEqual(current['1']['delivery'],{'weekly':'SENT','season':'SENT'})
                self.assertEqual(len(sent),2)  # Only matchday 2, weekly + season.
                season=json.loads((root/'kicktipp_season_performance.json').read_text())
                self.assertEqual(season['models']['Gemini 3.6 Flash']['points'],16)
                self.assertEqual(bot.main(),0)
                self.assertEqual(len(sent),2)
            self.assertEqual((root/'weekly_reports.json').read_text(),before)


class ProviderVerifiedOnly(unittest.TestCase):
    def test_stale_actual_on_unverified_match_never_scores(self):
        from performance_engine import build_weekly_snapshot, grade_record
        votes = [{'model':'Gemini 3.6 Flash','success':True,'result':{'score':'2-1','outcome':'HOME'}}]
        verified = grade_record({'matchday':1,'ai_votes':votes},2,1)
        stale = grade_record({'matchday':1,'ai_votes':votes},2,1)
        snapshot = build_weekly_snapshot({'1':verified,'2':stale},1,{
            'planned_matches':2,'evaluated_matches':1,'unavailable_matches':0,'postponed_matches':1,
            'pending_matches':0,'matches':[{'match_id':'1','status':'EVALUATED'},
                                          {'match_id':'2','status':'POSTPONED'}]})
        self.assertEqual(snapshot['stats']['models']['Gemini 3.6 Flash']['points'],8)
        self.assertEqual(snapshot['stats']['models']['Gemini 3.6 Flash']['successful_predictions'],1)
