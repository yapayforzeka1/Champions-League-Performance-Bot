import copy
import unittest
from performance_engine import merge_latest_results, build_weekly_stats
from config import MODEL_ORDER
class SeparationTests(unittest.TestCase):
    def test_scores_independent_and_source_immutable(self):
        records={'1':{'match_id':'1','matchday':1,'actual':{'home':2,'away':1,'scope':'REGULAR_90'},
          'consensus':{},'ai_votes':[{'model':'Groq Qwen 3.8 27B','success':True,'points':6,
          'result':{'score':'2-1','outcome':'HOME'}}]}}
        original=copy.deepcopy(records)
        graded=merge_latest_results(records,{})
        self.assertEqual(records,original)
        self.assertEqual(graded['1']['ai_votes'][0]['points'],5)
        stats=build_weekly_stats(graded,1)['models']
        self.assertEqual(stats['Groq Qwen 3.6 27B']['successful_predictions'],0)
        self.assertEqual(stats['Groq Qwen 3.8 27B']['successful_predictions'],1)
        self.assertEqual(stats['Groq Qwen 3.6 27B']['points'],0)
        self.assertEqual(stats['Groq Qwen 3.8 27B']['points'],5)
    def test_extra_time_not_graded_as_regular(self):
        records={'1':{'matchday':1,'ai_votes':[]}}
        graded=merge_latest_results(records,{'1':{'status':'FINISHED','score':{'duration':'EXTRA_TIME','fullTime':{'home':3,'away':2}}}})
        self.assertNotIn('actual',graded['1'])


class DeliveryTests(unittest.TestCase):
    def test_weekly_season_delivery_and_no_repeat(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import performance_bot as bot
        from config import MODEL_ORDER
        votes=[{'model':m,'success':True,'result':{'score':'2-1','outcome':'HOME'}} for m in MODEL_ORDER]
        predictions={'1':{'match_id':'1','matchday':1,'home_team':'A','away_team':'B','ai_votes':votes}}
        fixtures={1:[{'id':1,'status':'FINISHED','homeTeam':{'name':'A'},'awayTeam':{'name':'B'},
                       'score':{'duration':'REGULAR','fullTime':{'home':2,'away':1}}}]}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.multiple(bot,DATA_DIR=root,WEEKLY_REPORTS_FILE=root/'weekly.json',SEASON_PERFORMANCE_FILE=root/'season.json',TELEGRAM_ENABLED=True), \
                 patch.object(bot,'load_prediction_archive',return_value=predictions), \
                 patch.object(bot,'FootballDataResultProvider') as provider, \
                 patch.object(bot,'render_weekly_image',return_value=root/'weekly.png'), \
                 patch.object(bot,'render_season_image',return_value=root/'season.png'), \
                 patch.object(bot,'send_photo') as send:
                provider.return_value.get_matches_by_matchday.return_value=fixtures
                self.assertEqual(bot.main(),0)
                self.assertEqual(send.call_count,2)
                self.assertEqual(bot.main(),0)
                self.assertEqual(send.call_count,2)
                state=bot._load_json(root/'weekly.json',{})
                self.assertEqual(state['1']['delivery'],{'weekly':'SENT','season':'SENT'})
    def test_corrupt_archive_does_not_become_empty(self):
        import tempfile
        from pathlib import Path
        from performance_bot import _load_json
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';path.write_text('{broken')
            with self.assertRaises(RuntimeError):_load_json(path,{})
            self.assertEqual(path.read_text(),'{broken')


class SourceTests(unittest.TestCase):
    def test_raw_archive_loading(self):
        from unittest.mock import patch, Mock
        import source_loader
        data={'1':{'ai_votes':[]}}
        response=Mock(status_code=200);response.json.return_value=data
        with patch.object(source_loader.requests,'get',return_value=response) as get:
            self.assertEqual(source_loader.load_prediction_archive(),data)
            self.assertEqual(get.call_args.kwargs['headers']['Accept'],'application/vnd.github.raw+json')


class ModelVersionTests(unittest.TestCase):
    def test_qwen_versions_and_cloudflare_are_separate(self):
        from performance_engine import grade_record, build_weekly_stats, build_season_snapshot
        names=['Groq Qwen 3.6 27B','Groq Qwen 3.8 27B','Cloudflare Clef-omni','Mistral Small Latest']
        rec={'matchday':2,'ai_votes':[{'model':m,'success':True,'result':{'score':'2-1','outcome':'HOME'}} for m in names]}
        graded=grade_record(rec,2,1)
        stats=build_weekly_stats({'x':graded},2)['models']
        for name in names:
            self.assertEqual(stats[name]['points'],5)
            self.assertEqual(stats[name]['point_distribution']['5'],1)
        self.assertEqual(len({name for name in names if stats[name]['points']==5}),4)
        old={'status':'FINAL','stats':{'models':{'Groq Qwen 3.6 27B':{'points':12,'successful_predictions':3}},'consensus':{}}}
        new={'status':'FINAL','stats':{'models':stats,'consensus':{}}}
        season=build_season_snapshot({'1':old,'2':new})
        self.assertEqual(season['models']['Groq Qwen 3.6 27B']['points'],17)
        self.assertEqual(season['models']['Groq Qwen 3.8 27B']['points'],5)
        self.assertEqual(season['models']['Cloudflare Clef-omni']['points'],5)

    def test_report_percent_uses_five_point_maximum(self):
        from weekly_report import _model_row
        self.assertEqual(_model_row('Groq Qwen 3.8 27B',{'points':5,'successful_predictions':1})['pct'],100)

class CurrentReportVisibilityTests(unittest.TestCase):
    def test_retired_models_not_in_new_report_tables(self):
        from weekly_report import _display_models, _summary_rows
        record = {'ai_votes': [
            {'model': 'Mistral Small Latest', 'success': True},
            {'model': 'Groq Qwen 3.6 27B', 'success': True},
            {'model': 'Groq Qwen 3.8 27B', 'success': True},
            {'model': 'Cloudflare Clef-omni', 'success': False},
        ]}
        displayed = _display_models([record])
        self.assertIn('Groq Qwen 3.8 27B', displayed)
        self.assertIn('Cloudflare Clef-omni', displayed)
        self.assertNotIn('Groq Qwen 3.6 27B', displayed)
        self.assertNotIn('Mistral Small Latest', displayed)
        stats = {'models': {
            name: {'successful_predictions': 1, 'points': 5}
            for name in ['Mistral Small Latest', 'Groq Qwen 3.6 27B', 'Groq Qwen 3.8 27B']
        }, 'consensus': {}}
        names = [row['name'] for row in _summary_rows(stats)]
        self.assertNotIn('Mistral Small Latest', names)
        self.assertNotIn('Groq Qwen 3.6 27B', names)
        self.assertIn('Groq Qwen 3.8 27B', names)
