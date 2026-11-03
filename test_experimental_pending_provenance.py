"""Offline regression: transient provenance failures must never create FINAL."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experimental_performance import METHODS, build_experimental_week, build_experimental_season
from github_provenance import GitHubPreKickoffEvidence
import experimental_runner as runner
from test_experimental_performance import KICKOFF, fixture, record, Proof


class UnavailableProof:
    def __init__(self, reason='PROVENANCE_LOOKUP_FAILED', detail='Timeout'):
        self.reason, self.detail, self.calls = reason, detail, []

    def verify(self, match_id, kickoff, block):
        self.calls.append((match_id, kickoff))
        return {'verified': False, 'reason': self.reason, 'detail': self.detail}


class TestPendingEvidence(unittest.TestCase):
    def test_http_timeout_or_quota_do_not_seal_final(self):
        for reason in ('PROVENANCE_LOOKUP_FAILED', 'PROVENANCE_TOKEN_MISSING',
                       'COMMIT_ARCHIVE_INVALID', 'PROVENANCE_NOT_VERIFIED',
                       'UNKNOWN_PROVIDER_RESPONSE'):
            with self.subTest(reason=reason):
                proof = UnavailableProof(reason)
                source = record()
                before = copy.deepcopy(source)
                report = build_experimental_week(3, [fixture()], {'101': source}, proof)
                self.assertEqual(report['status'], 'PENDING')
                self.assertEqual(len(report['pending_verifications']), 2)
                self.assertEqual(report['methods'][METHODS[0]]['valid_predictions'], 0)
                self.assertEqual(report['methods'][METHODS[0]]['failure_reasons'], {})
                self.assertEqual(source, before)
                with self.assertRaises(ValueError):
                    build_experimental_season({'3': report})

    def test_permanent_invalid_evidence_is_final_but_not_valid(self):
        for reason in ('NOT_IN_PREKICKOFF_SNAPSHOT', 'NO_PREKICKOFF_COMMIT',
                       'COMMIT_NOT_PREKICKOFF', 'COMMITTED_VOTE_HASH_MISMATCH',
                       'SOURCE_KICKOFF_MISMATCH'):
            with self.subTest(reason=reason):
                report = build_experimental_week(3, [fixture()], {'101': record()},
                                                 UnavailableProof(reason))
                self.assertEqual(report['status'], 'FINAL')
                self.assertNotIn('pending_verifications', report)
                for method in METHODS:
                    self.assertEqual(report['methods'][method]['valid_predictions'], 0)
                    self.assertEqual(report['methods'][method]['point_distribution']['0'], 0)
                    self.assertEqual(report['methods'][method]['failure_reasons'][reason], 1)

    def test_partial_valid_evidence_keeps_week_pending(self):
        source = {'101': record(), '102': record('102')}

        class PartialProof:
            def verify(self, match_id, *_):
                return ({'verified': True, 'commit_sha': 'oldsha'} if match_id == '101'
                        else {'verified': False, 'reason': 'PROVENANCE_LOOKUP_FAILED'})

        report = build_experimental_week(3, [fixture(), fixture('102')], source, PartialProof())
        self.assertEqual(report['status'], 'PENDING')
        for method in METHODS:
            self.assertEqual(report['methods'][method]['valid_predictions'], 1)
            self.assertEqual(report['methods'][method]['points'], 8)
        self.assertEqual(len(report['pending_verifications']), 2)

    def test_no_regular_90min_result_or_missing_experiment(self):
        self.assertIsNone(build_experimental_week(3, [fixture(status='SCHEDULED')],
                                                  {'101': record()}, Proof()))
        r = record()
        r.pop('experimental_predictions')
        report = build_experimental_week(3, [fixture()], {'101': r}, UnavailableProof())
        self.assertEqual(report['status'], 'FINAL')
        for method in METHODS:
            self.assertEqual(report['methods'][method]['failure_reasons']['EXPERIMENT_ABSENT'], 1)
            self.assertEqual(report['methods'][method]['point_distribution']['0'], 0)

    def test_backtest_is_terminal_and_not_prospective(self):
        r = record()
        r['experimental_predictions']['classification'] = 'BACKTEST'
        report = build_experimental_week(3, [fixture()], {'101': r}, UnavailableProof())
        self.assertEqual(report['status'], 'FINAL')
        for method in METHODS:
            self.assertEqual(report['methods'][method]['valid_predictions'], 0)
            self.assertEqual(report['methods'][method]['failure_reasons']['BACKTEST_NOT_PROSPECTIVE'], 1)

    def test_github_timeout_and_missing_token_have_retryable_reasons(self):
        import requests

        class TimedOut:
            def get(self, *args, **kwargs):
                raise requests.Timeout('offline simulated request timeout')

        r = record()
        proof = GitHubPreKickoffEvidence(token='test', session=TimedOut()).verify(
            '101', KICKOFF, r['experimental_predictions'])
        self.assertEqual(proof['reason'], 'PROVENANCE_LOOKUP_FAILED')
        missing = GitHubPreKickoffEvidence(token='', session=TimedOut()).verify(
            '101', KICKOFF, r['experimental_predictions'])
        self.assertEqual(missing['reason'], 'PROVENANCE_TOKEN_MISSING')


class TestRunnerRetries(unittest.TestCase):
    def make_paths(self, tmp):
        root = Path(tmp)
        official = root / 'official_weekly.json'
        official.write_text(json.dumps({'3': {'status': 'FINAL', 'season': '2026/27'}}))
        return dict(EXPERIMENTAL_WEEKLY=root/'experimental_weekly_reports.json',
                    EXPERIMENTAL_SEASON=root/'experimental_season_performance.json',
                    EXPERIMENTAL_OVERVIEW=root/'experimental_performance.md',
                    OFFICIAL_WEEKLY=official)

    def test_api_fails_then_recovers_next_run_without_data_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = self.make_paths(tmp)
            original = record()
            source = {'101': original}
            baseline = copy.deepcopy(source)
            proof = UnavailableProof()
            official_final = Path(tmp) / 'kicktipp_weekly_reports.json'
            official_final.write_bytes(b'{"1":{"status":"FINAL"},"2":{"status":"FINAL"}}')
            sent_lock = Path(tmp) / 'kicktipp_delivery_locks.json'
            sent_lock.write_bytes(b'{"1":{"weekly":"SENT"},"2":{"weekly":"SENT"}}')
            existing = {p:p.read_bytes() for p in (official_final, sent_lock)}
            with patch.multiple(runner, **files), \
                 patch.object(runner, 'load_prediction_archive', return_value=source), \
                 patch.object(runner, 'FootballDataResultProvider') as provider, \
                 patch.object(runner, 'GitHubPreKickoffEvidence', side_effect=lambda: proof):
                provider.return_value.get_matches_by_matchday.return_value = {3: [fixture()]}
                self.assertEqual(runner.prepare_experimental_reports(), 1)
                self.assertFalse(files['EXPERIMENTAL_WEEKLY'].exists())
                self.assertFalse(files['EXPERIMENTAL_SEASON'].exists())
                self.assertFalse(files['EXPERIMENTAL_OVERVIEW'].exists())
                self.assertEqual(source, baseline)
                proof = Proof()
                self.assertEqual(runner.prepare_experimental_reports(), 0)
                saved = json.loads(files['EXPERIMENTAL_WEEKLY'].read_text())
                self.assertEqual(saved['3']['status'], 'FINAL')
                for method in METHODS:
                    self.assertEqual(saved['3']['methods'][method]['valid_predictions'], 1)
                    self.assertEqual(saved['3']['methods'][method]['points'], 8)
                season_bytes = files['EXPERIMENTAL_SEASON'].read_bytes()
                weekly_bytes = files['EXPERIMENTAL_WEEKLY'].read_bytes()
                self.assertEqual(runner.prepare_experimental_reports(), 0)
                self.assertEqual(files['EXPERIMENTAL_WEEKLY'].read_bytes(), weekly_bytes)
                self.assertEqual(files['EXPERIMENTAL_SEASON'].read_bytes(), season_bytes)
            for path, content in existing.items():
                self.assertEqual(path.read_bytes(), content)
            self.assertEqual(source, baseline)

    def test_existing_final_week_not_reverified_or_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = self.make_paths(tmp)
            final_week = build_experimental_week(3, [fixture()], {'101': record()}, Proof())
            final_bytes = json.dumps({'3': final_week}).encode()
            files['EXPERIMENTAL_WEEKLY'].write_bytes(final_bytes)
            with patch.multiple(runner, **files), \
                 patch.object(runner, 'load_prediction_archive', side_effect=AssertionError('No API')), \
                 patch.object(runner, 'FootballDataResultProvider', side_effect=AssertionError('No provider')):
                self.assertEqual(runner.prepare_experimental_reports(), 0)
            self.assertEqual(files['EXPERIMENTAL_WEEKLY'].read_bytes(), final_bytes)
            self.assertFalse(files['EXPERIMENTAL_SEASON'].exists())

    def test_one_week_pending_other_week_can_final_without_archiving_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = self.make_paths(tmp)
            files['OFFICIAL_WEEKLY'].write_text(json.dumps({
                '3': {'status': 'FINAL', 'season': '2026/27'},
                '4': {'status': 'FINAL', 'season': '2026/27'}}))
            r3, r4 = record(), record('201')
            r4['matchday'] = 4
            f4 = fixture('201')
            f4['matchday'] = 4

            class PartlyUnavailable:
                def verify(self, mid, kickoff, exp):
                    if mid == '101':
                        return {'verified': False, 'reason': 'PROVENANCE_LOOKUP_FAILED'}
                    return {'verified': True, 'commit_sha': '123'}

            with patch.multiple(runner, **files), \
                 patch.object(runner, 'load_prediction_archive', return_value={'101':r3,'201':r4}), \
                 patch.object(runner, 'FootballDataResultProvider') as provider, \
                 patch.object(runner, 'GitHubPreKickoffEvidence', return_value=PartlyUnavailable()):
                provider.return_value.get_matches_by_matchday.return_value = {3:[fixture()], 4:[f4]}
                self.assertEqual(runner.prepare_experimental_reports(), 0)
                saved = json.loads(files['EXPERIMENTAL_WEEKLY'].read_text())
                self.assertNotIn('3', saved)
                self.assertEqual(saved['4']['status'], 'FINAL')
                self.assertEqual(runner.prepare_experimental_reports(), 1)
                self.assertEqual(set(json.loads(files['EXPERIMENTAL_WEEKLY'].read_text())), {'4'})


if __name__ == '__main__':
    unittest.main()
