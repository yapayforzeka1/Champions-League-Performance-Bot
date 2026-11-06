import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from config import ACTIVE_MODEL_ORDER, MODEL_ORDER
from performance_engine import (_model_identity, grade_record, build_weekly_stats,
                                build_season_snapshot, SCORING_RULE)
from weekly_report import _display_models, _summary_rows, render_season_image, render_weekly_image
from match_prediction_archive import match_entry

OLD = 'Gemini 3.6 Flash'
NEW = 'Gemini 3.5 Flash-Lite'


def record(mid, name, model_id, score):
    return {'match_id': mid, 'matchday': 5, 'home_team': 'Home', 'away_team': 'Away',
            'match_utc': '2026-11-24T20:00:00Z', 'consensus': {},
            'ai_votes': [{'model': name, 'success': True,
                          'result': {'model_id': model_id, 'score': score, 'outcome': 'HOME'}}]}


class GeminiTransition(unittest.TestCase):
    def test_both_versions_retained_but_only_lite_active(self):
        self.assertIn(OLD, MODEL_ORDER)
        self.assertIn(NEW, MODEL_ORDER)
        self.assertIn(NEW, ACTIVE_MODEL_ORDER)
        self.assertNotIn(OLD, ACTIVE_MODEL_ORDER)
        self.assertEqual(len(ACTIVE_MODEL_ORDER), 5)

    def test_provider_id_beats_stale_label_but_legacy_not_relabelled(self):
        vote = record('1', OLD, 'gemini-3.5-flash-lite', '2-1')['ai_votes'][0]
        self.assertEqual(_model_identity(vote), NEW)
        vote['result'].pop('model_id')
        self.assertEqual(_model_identity(vote), OLD)

    def test_points_and_counts_kept_separate_without_mutating_inputs(self):
        source = {'1': record('1', OLD, 'gemini-3.6-flash', '2-1'),
                  '2': record('2', NEW, 'gemini-3.5-flash-lite', '1-0')}
        original = copy.deepcopy(source)
        graded = {k: grade_record(r, 2, 1) for k, r in source.items()}
        stats = build_weekly_stats(graded, 5)
        self.assertEqual(stats['models'][OLD]['points'], 8)
        self.assertEqual(stats['models'][NEW]['points'], 6)
        self.assertEqual(stats['models'][OLD]['successful_predictions'], 1)
        self.assertEqual(stats['models'][NEW]['successful_predictions'], 1)
        season = build_season_snapshot({'5': {'status': 'FINAL', 'scoring_rule': SCORING_RULE, 'stats': stats}})
        self.assertEqual(season['models'][OLD]['points'], 8)
        self.assertEqual(season['models'][NEW]['points'], 6)
        self.assertEqual(source, original)
        self.assertIn(OLD, _display_models(list(graded.values())))
        self.assertIn(NEW, _display_models(list(graded.values())))
        names = [r['name'] for r in _summary_rows(stats)]
        self.assertIn(OLD, names)
        self.assertIn(NEW, names)

    def test_failure_name_and_native_match_archive_supported(self):
        row = record('1', NEW, 'gemini-3.5-flash-lite', '2-1')
        graded = grade_record(row, 2, 1)
        entry = match_entry({'match_id': '1', 'home': 'Home', 'away': 'Away'}, graded)
        self.assertEqual(entry['models'][NEW]['points'], 8)
        row['ai_votes'][0].update(success=False, result=None)
        stats = build_weekly_stats({'1': grade_record(row, 2, 1)}, 5)
        self.assertEqual(stats['models'][NEW]['failed_predictions'], 1)
        self.assertEqual(stats['models'][OLD]['prediction_opportunities'], 0)

    def test_historical_and_new_model_can_render_without_merging(self):
        graded = {'1': grade_record(record('1', OLD, 'gemini-3.6-flash', '2-1'), 2, 1),
                  '2': grade_record(record('2', NEW, 'gemini-3.5-flash-lite', '1-0'), 2, 1)}
        stats = build_weekly_stats(graded, 5)
        season = build_season_snapshot({'5': {'status': 'FINAL', 'scoring_rule': SCORING_RULE, 'stats': stats}})
        snapshot = {'matchday': 5, 'season': '2026/27', 'stats': stats,
                    'render_records': list(graded.values())}
        with tempfile.TemporaryDirectory() as tmp, patch('weekly_report.REPORT_DIR', Path(tmp)):
            self.assertTrue(render_weekly_image(snapshot).is_file())
            self.assertTrue(render_season_image(season).is_file())
