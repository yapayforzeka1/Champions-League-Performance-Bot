"""Zero-network, zero-AI, zero-Telegram regression checks for experimental tracking."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experimental_performance import (METHODS, build_experimental_week,
                                      build_experimental_season)
from github_provenance import GitHubPreKickoffEvidence
import experimental_runner as runner

KICKOFF = '2030-10-20T17:00:00Z'
CREATED = '2030-10-20T16:40:00Z'


def vote(model, score):
    h, a = map(int, score.split('-'))
    return {'model': model, 'success': True,
            'result': {'score': score, 'outcome': 'HOME' if h > a else 'AWAY' if h < a else 'DRAW',
                       'model_id': 'stable/' + model}}


def record(mid='101', scores=('2-1', '2-1', '1-0'), avg='2-1', mode='2-1'):
    import hashlib
    votes = [vote('model' + str(i), score) for i, score in enumerate(scores)]
    raw = json.dumps([(x['model'], x['result']['model_id'], x['result']['score']) for x in votes],
                     ensure_ascii=False, separators=(',', ':'))
    digest = hashlib.sha256(raw.encode()).hexdigest()

    def entry(method, score, error=None):
        outcome = None
        if score:
            h, a = map(int, score.split('-'))
            outcome = 'HOME' if h > a else 'AWAY' if h < a else 'DRAW'
        return {'match_id': mid, 'method': method, 'version': 1, 'classification': 'PROSPECTIVE',
                'predicted_score': score, 'predicted_outcome': outcome, 'valid_ai_count': len(votes),
                'models_used': [{'model': v['model'], 'model_id': v['result']['model_id']} for v in votes],
                'created_at': CREATED, 'failure_reason': error, 'source_votes_sha256': digest}

    exp = {'schema_version': 1, 'classification': 'PROSPECTIVE',
           'methods': {METHODS[0]: entry(METHODS[0], avg), METHODS[1]: entry(METHODS[1], mode)}}
    return {'match_id': mid, 'matchday': 3, 'match_utc': KICKOFF, 'ai_votes': votes,
            'consensus': {'winner_consensus': True, 'score_consensus': True,
                          'outcome': 'HOME', 'score': '2-1'},
            'published_consensus': {'winner_consensus': True, 'score_consensus': True,
                                    'outcome': 'HOME', 'score': '2-1'},
            'experimental_predictions': exp}


def fixture(mid='101', h=2, a=1, status='FINISHED'):
    return {'id': int(mid), 'matchday': 3, 'utcDate': KICKOFF, 'status': status,
            'homeTeam': {'name': 'A'}, 'awayTeam': {'name': 'B'},
            'score': {'duration': 'REGULAR', 'regularTime': {'home': h, 'away': a}}}


class Proof:
    def __init__(self, valid=True):
        self.valid = valid
        self.calls = []

    def verify(self, mid, kickoff, block):
        self.calls.append((mid, kickoff))
        return {'verified': self.valid, 'reason': 'PREKICKOFF_GITHUB_SNAPSHOT' if self.valid else 'NO_PROOF',
                'commit_sha': 'abc123'}


class ExperimentalScoringTests(unittest.TestCase):
    def test_two_methods_are_separate_and_score_8640(self):
        r = record(avg='3-2', mode='2-1')
        before = copy.deepcopy(r)
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        self.assertEqual(out['methods'][METHODS[0]]['points'], 6)
        self.assertEqual(out['methods'][METHODS[1]]['points'], 8)
        self.assertEqual(r, before)
        self.assertEqual(out['methods'][METHODS[0]]['valid_predictions'], 1)
        same = out['methods'][METHODS[0]]['head_to_head']['En Sık AL Skoru']
        self.assertEqual((same['common_matches'], same['experimental_points'], same['comparison_points']), (1, 6, 8))
        self.assertEqual(out['methods'][METHODS[0]]['head_to_head']['Ortak karar']['common_matches'], 1)

    def test_correct_draw_difference_six_points(self):
        r = record(scores=('1-1','1-1','2-2'),avg='1-1',mode='1-1')
        out = build_experimental_week(3, [fixture(h=2, a=2)], {'101': r}, Proof())
        for method in METHODS:
            self.assertEqual(out['methods'][method]['points'], 6)
            self.assertEqual(out['methods'][method]['outcome'], 1)

    def test_wrong_outcome_is_zero_and_counts_as_valid(self):
        r = record(avg='1-2', mode='0-3')
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        for method in METHODS:
            self.assertEqual(out['methods'][method]['points'], 0)
            self.assertEqual(out['methods'][method]['valid_predictions'], 1)
            self.assertEqual(out['methods'][method]['point_distribution']['0'], 1)

    def test_missing_experiment_is_not_wrong_prediction(self):
        r = record()
        del r['experimental_predictions']
        empty = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        self.assertEqual(empty['methods'][METHODS[0]]['valid_predictions'], 0)
        self.assertEqual(empty['methods'][METHODS[0]]['failure_reasons']['EXPERIMENT_ABSENT'], 1)
        present = record('102')
        result = build_experimental_week(3, [fixture(), fixture('102')], {'101': r, '102': present}, Proof())
        for method in METHODS:
            stats = result['methods'][method]
            self.assertEqual(stats['opportunities'], 2)
            self.assertEqual(stats['valid_predictions'], 1)
            self.assertEqual(stats['failure_reasons']['EXPERIMENT_ABSENT'], 1)
            self.assertEqual(stats['point_distribution']['0'], 0)

    def test_no_score_reason_excluded_independently(self):
        r = record(mode=None)
        r['experimental_predictions']['methods'][METHODS[1]]['failure_reason'] = 'NO_REPEATED_SCORE'
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        self.assertEqual(out['methods'][METHODS[0]]['valid_predictions'], 1)
        self.assertEqual(out['methods'][METHODS[1]]['valid_predictions'], 0)
        self.assertEqual(out['methods'][METHODS[1]]['failure_reasons']['NO_REPEATED_SCORE'], 1)

    def test_tampered_one_method_does_not_change_other_schema_validation(self):
        r = record()
        r['experimental_predictions']['methods'][METHODS[1]]['version'] = 5
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        self.assertEqual(out['methods'][METHODS[0]]['valid_predictions'], 1)
        self.assertEqual(out['methods'][METHODS[1]]['failure_reasons']['INVALID_PREMATCH_METADATA'], 1)

    def test_backtest_is_never_a_prospective_success(self):
        r = record()
        r['experimental_predictions']['classification'] = 'BACKTEST'
        for v in r['experimental_predictions']['methods'].values():
            v['classification'] = 'BACKTEST'
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        self.assertEqual(out['methods'][METHODS[0]]['valid_predictions'], 0)
        self.assertEqual(out['methods'][METHODS[0]]['failure_reasons']['BACKTEST_NOT_PROSPECTIVE'], 1)

    def test_post_kickoff_and_invalid_digests_excluded(self):
        r = record()
        for v in r['experimental_predictions']['methods'].values():
            v['created_at'] = '2030-10-20T17:01:00Z'
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        self.assertEqual(out['methods'][METHODS[0]]['failure_reasons']['INVALID_PREMATCH_METADATA'], 1)
        r = record()
        r['experimental_predictions']['methods'][METHODS[0]]['source_votes_sha256'] = 'fake'
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof())
        self.assertEqual(out['methods'][METHODS[0]]['failure_reasons']['SOURCE_VOTES_HASH_MISMATCH'], 1)
        self.assertEqual(out['methods'][METHODS[1]]['valid_predictions'], 1)

    def test_unverified_github_history_is_excluded(self):
        r = record()
        out = build_experimental_week(3, [fixture()], {'101': r}, Proof(valid=False))
        self.assertEqual(out['methods'][METHODS[0]]['valid_predictions'], 0)
        self.assertEqual(out['status'], 'PENDING')
        self.assertEqual(out['pending_verifications'][0]['reason'], 'NO_PROOF')

    def test_intentionally_excluded_club_is_not_failure_or_lost_history(self):
        excluded = fixture('102')
        excluded['homeTeam']['name'] = 'Fenerbahçe SK'
        out = build_experimental_week(3, [fixture(), excluded], {'101': record()}, Proof())
        self.assertEqual(out['total_fixtures'], 2)
        self.assertEqual(out['policy_excluded'], 1)
        self.assertEqual(out['opportunities'], 1)
        self.assertEqual(out['methods'][METHODS[0]]['missing_predictions'], 0)
        # Already archived predictions on a policy-excluded match are preserved.
        out2 = build_experimental_week(3, [fixture(), excluded],
                                       {'101': record(), '102': record('102')}, Proof())
        self.assertEqual(out2['opportunities'], 2)
        self.assertEqual(out2['methods'][METHODS[0]]['valid_predictions'], 2)

    def test_season_versions_must_not_mix(self):
        week = build_experimental_week(3, [fixture()], {'101': record()}, Proof())
        week['methods'][METHODS[0]]['version'] = 2
        with self.assertRaises(ValueError):
            build_experimental_season({'3': week})

    def test_no_90min_score_no_final(self):
        bad = fixture(status='SCHEDULED')
        self.assertIsNone(build_experimental_week(3, [bad], {'101': record()}, Proof()))

    def test_season_totals_and_no_duplicate_week(self):
        week = build_experimental_week(3, [fixture()], {'101': record()}, Proof())
        season = build_experimental_season({'3': week})
        self.assertEqual(season['methods'][METHODS[0]]['points'], 8)
        self.assertEqual(season['finalized_matchdays'], ['3'])
        self.assertEqual(season['methods'][METHODS[0]]['valid_predictions'], 1)


class _FakeReply:
    def __init__(self, obj): self.obj = obj
    def raise_for_status(self): return None
    def json(self): return self.obj


class _FakeSession:
    def __init__(self, before):
        self.before = before
        self.requests = []
    def get(self, url, params, headers, timeout):
        self.requests.append((url, params, headers))
        if url.endswith('/commits'):
            return _FakeReply([{'sha': 'testsha', 'commit': {'committer': {'date': '2030-10-20T16:45:00Z'}}}])
        return _FakeReply(self.before)


class GithubEvidenceTests(unittest.TestCase):
    def test_pre_kickoff_committed_snapshot_is_required(self):
        r = record()
        session = _FakeSession({'101': copy.deepcopy(r)})
        p = GitHubPreKickoffEvidence(token='test', session=session)
        out = p.verify('101', KICKOFF, r['experimental_predictions'])
        self.assertTrue(out['verified'])
        self.assertEqual(out['commit_sha'], 'testsha')
        self.assertEqual(len(session.requests), 2)
        self.assertIn('raw+json', session.requests[1][2]['Accept'])
        p.verify('101', KICKOFF, r['experimental_predictions'])
        self.assertEqual(len(session.requests), 2)

    def test_latest_archive_is_not_enough_without_historical_snapshot(self):
        r = record()
        session = _FakeSession({'101': record(avg='4-1')})
        p = GitHubPreKickoffEvidence(token='test', session=session)
        self.assertEqual(p.verify('101', KICKOFF, r['experimental_predictions'])['reason'],
                         'NOT_IN_PREKICKOFF_SNAPSHOT')

    def test_provenance_requires_token(self):
        self.assertEqual(GitHubPreKickoffEvidence(token='').verify('101', KICKOFF, {})['reason'],
                         'PROVENANCE_TOKEN_MISSING')


class RunnerSafetyTests(unittest.TestCase):
    def test_historical_finals_and_source_records_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            r = record()
            before = copy.deepcopy(r)
            existing_final = root / 'kicktipp_weekly_reports.json'
            existing_final.write_bytes(b'{"1": "immutable"}')
            existing_season = root / 'kicktipp_season_performance.json'
            existing_season.write_bytes(b'{"immutable": true}')
            expw = root / 'experimental_weekly_reports.json'
            exps = root / 'experimental_season_performance.json'
            report = root / 'experiment.md'
            official = root / 'official_weekly.json'
            official.write_text(json.dumps({'3': {'season': '2026/27', 'status': 'FINAL'}}))
            with patch.multiple(runner, EXPERIMENTAL_WEEKLY=expw, EXPERIMENTAL_SEASON=exps,
                                EXPERIMENTAL_OVERVIEW=report, OFFICIAL_WEEKLY=official), \
                    patch.object(runner, 'load_prediction_archive', return_value={'101': r}), \
                    patch.object(runner, 'FootballDataResultProvider') as provider, \
                    patch.object(runner, 'GitHubPreKickoffEvidence', return_value=Proof()):
                provider.return_value.get_matches_by_matchday.return_value = {3: [fixture()]}
                self.assertEqual(runner.prepare_experimental_reports(), 0)
                first = expw.read_bytes()
                self.assertEqual(runner.prepare_experimental_reports(), 0)
                self.assertEqual(expw.read_bytes(), first)
                self.assertIn('3', json.loads(first))
                self.assertIn('AL Skor Ortalaması', report.read_text())
            self.assertEqual(r, before)
            self.assertEqual(existing_final.read_bytes(), b'{"1": "immutable"}')
            self.assertEqual(existing_season.read_bytes(), b'{"immutable": true}')

    def test_existing_old_round_without_experimental_does_not_backfill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            official = root / 'official_weekly.json'
            official.write_text(json.dumps({'1': {'season': '2026/27', 'status': 'FINAL'}}))
            with patch.multiple(runner, EXPERIMENTAL_WEEKLY=root/'exp.json',
                                EXPERIMENTAL_SEASON=root/'season.json',
                                EXPERIMENTAL_OVERVIEW=root/'notes.md', OFFICIAL_WEEKLY=official), \
                    patch.object(runner, 'load_prediction_archive', return_value={}), \
                    patch.object(runner, 'FootballDataResultProvider') as provider:
                provider.return_value.get_matches_by_matchday.return_value = {1: [fixture()]}
                self.assertEqual(runner.prepare_experimental_reports(), 0)
                self.assertFalse((root/'exp.json').exists())


if __name__ == '__main__':
    unittest.main()
