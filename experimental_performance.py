"""Isolated, immutable performance view of recorded experimental scores.

Never generate new experimental picks. Never mutate source predictions or
production Kicktipp FINALs. Only verified pre-kickoff (PROSPECTIVE) records
count toward live performance. BACKTEST and unverified records are excluded.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from config import ACTIVE_MODEL_ORDER, SEASON
from github_provenance import utc_datetime, eligible_source_vote_digest
from performance_engine import (SCORING_RULE, actual_outcome, archived_consensus,
                                _model_identity, score_points)

SCHEMA_VERSION = 1
METHODS = ('al_score_average_v1', 'al_most_frequent_score_v1')
METHOD_LABELS = {'al_score_average_v1': 'AL Skor Ortalaması',
                 'al_most_frequent_score_v1': 'En Sık AL Skoru'}
PREDICTION_PATTERN = re.compile(r'([0-9]{1,2})-([0-9]{1,2})\Z')


def _empty(method: str, opportunities: int) -> dict:
    return {'method': method, 'label': METHOD_LABELS[method], 'version': SCHEMA_VERSION,
            'opportunities': opportunities, 'valid_predictions': 0,
            'missing_predictions': opportunities, 'outcome': 0, 'exact': 0,
            'points': 0, 'avg': 0.0, 'coverage_pct': 0.0, 'outcome_pct': 0.0,
            'exact_pct': 0.0, 'point_efficiency_pct': 0.0,
            'point_distribution': {'8': 0, '6': 0, '4': 0, '0': 0},
            'failure_reasons': {}, 'models_used_counts': {}, 'used_ai_sum': 0,
            'avg_valid_ai_count': 0.0, 'provenance': {}, 'head_to_head': {},
            'valid_match_ids': [], 'match_evaluations': {}}



def _policy_excluded_fixture(fixture: dict, matchday: int, season: str) -> bool:
    """Mirror the user-approved 2026/27 league-phase do-not-analyse policy.

    Only absent *experimental* predictions are skipped. Historical already
    recorded experimental scores still remain eligible for evaluation.
    """
    if season != '2026/27' or not 1 <= int(matchday) <= 8:
        return False
    for side in ('homeTeam', 'awayTeam'):
        team = str((fixture.get(side) or {}).get('name') or '')
        ascii_name = ''.join(c for c in unicodedata.normalize('NFKD', team.casefold())
                             if not unicodedata.combining(c))
        ascii_name = re.sub(r'[^a-z0-9]+', ' ', ascii_name).strip()
        if any(ascii_name == club or ascii_name.startswith(club + ' ')
               for club in ('fenerbahce', 'galatasaray')):
            return True
    return False

def validate_experiment(record: dict, match_id: str, kickoff: str) -> tuple[dict | None, str | None]:
    """Validate the frozen record schema, not its algorithmic prediction."""
    block = record.get('experimental_predictions')
    if block is None:
        return None, 'EXPERIMENT_ABSENT'
    if not isinstance(block, dict) or block.get('schema_version') != SCHEMA_VERSION:
        return None, 'INVALID_SCHEMA'
    if block.get('classification') == 'BACKTEST':
        return None, 'BACKTEST_NOT_PROSPECTIVE'
    if block.get('classification') != 'PROSPECTIVE':
        return None, 'UNVERIFIED_CLASSIFICATION'
    kickoff_dt = utc_datetime(kickoff)
    archived_kickoff = utc_datetime(record.get('match_utc'))
    if kickoff_dt is None or archived_kickoff != kickoff_dt:
        return None, 'KICKOFF_MISMATCH'
    methods = block.get('methods')
    if not isinstance(methods, dict):
        return None, 'MISSING_METHODS'
    return block, None


def validate_method(entry: Any, record: dict, match_id: str,
                    kickoff: str, method: str) -> str | None:
    if not isinstance(entry, dict):
        return 'METHOD_ABSENT'
    kickoff_dt = utc_datetime(kickoff)
    created = utc_datetime(entry.get('created_at'))
    if (created is None or kickoff_dt is None or created >= kickoff_dt
            or entry.get('classification') != 'PROSPECTIVE'
            or entry.get('match_id') != str(match_id) or entry.get('method') != method
            or entry.get('version') != SCHEMA_VERSION):
        return 'INVALID_PREMATCH_METADATA'
    models = entry.get('models_used')
    n = entry.get('valid_ai_count')
    if (not isinstance(n, int) or isinstance(n, bool) or n < 0
            or not isinstance(models, list) or len(models) != n
            or any(not isinstance(x, dict) or not x.get('model') for x in models)):
        return 'INVALID_MODEL_COUNT'
    if entry.get('source_votes_sha256') != eligible_source_vote_digest(record.get('ai_votes')):
        return 'SOURCE_VOTES_HASH_MISMATCH'
    score = entry.get('predicted_score')
    if score is not None:
        if not isinstance(score, str) or not PREDICTION_PATTERN.fullmatch(score):
            return 'INVALID_SCORE'
        h, a = (int(v) for v in score.split('-'))
        if entry.get('predicted_outcome') != actual_outcome(h, a) or entry.get('failure_reason') is not None:
            return 'INVALID_SCORE_METADATA'
    elif entry.get('predicted_outcome') is not None:
        return 'INVALID_FAILURE_METADATA'
    return None


def _recorded_score(record: dict, target: str) -> str | None:
    for vote in record.get('ai_votes') or []:
        if not isinstance(vote, dict) or _model_identity(vote) != target or vote.get('success') is not True:
            continue
        result = vote.get('result')
        score = result.get('score') if isinstance(result, dict) else None
        if isinstance(score, str) and PREDICTION_PATTERN.fullmatch(score):
            h, a = map(int, score.split('-'))
            if result.get('outcome') == actual_outcome(h, a):
                return score
    return None


def _comparator_score(record: dict, target: str, home: int, away: int) -> int | None:
    if target == 'Ortak karar':
        c = archived_consensus(record)
        if not c.get('winner_consensus') or c.get('outcome') not in ('HOME', 'AWAY', 'DRAW'):
            return None
        score = c.get('score') if c.get('score_consensus') else None
        return score_points(score, c.get('outcome'), home, away)[0]
    score = _recorded_score(record, target)
    return score_points(score, None, home, away)[0] if score is not None else None


def build_experimental_week(matchday: int, fixtures: list[dict], predictions: dict,
                            evidence, *, season: str = SEASON) -> dict | None:
    """Produce a self-contained, read-only FINAL; only finished fixtures are scorable.

    Returns None if no source match contains any experimental record; old
    seasons/weeks are not retroactively populated with invented experiments.
    """
    from performance_engine import _provider_regular_score
    if not fixtures or any(_provider_regular_score(f) is None for f in fixtures):
        return None
    # This year's methods were introduced after weeks 1 and 2 had finished.
    # Never allow retrospective backfill to masquerade as a historic live test.
    if season == '2026/27' and int(matchday) <= 2:
        return None
    eligible = []
    excluded_ids = []
    for fixture in fixtures:
        mid = str(fixture.get('id'))
        row = predictions.get(mid)
        preexisting = isinstance(row, dict) and 'experimental_predictions' in row
        if _policy_excluded_fixture(fixture, matchday, season) and not preexisting:
            excluded_ids.append(mid)
        else:
            eligible.append(fixture)
    data = {key: _empty(key, len(eligible)) for key in METHODS}
    for fixture in eligible:
        mid = str(fixture['id'])
        actual_home, actual_away = _provider_regular_score(fixture)
        record = predictions.get(mid)
        for method in METHODS:
            stats = data[method]
            reason = None
            entry = None
            if not isinstance(record, dict):
                reason = 'NO_SOURCE_PREDICTION'
            else:
                block, reason = validate_experiment(record, mid, fixture.get('utcDate'))
                if block is not None:
                    entry = block['methods'].get(method)
                    reason = validate_method(entry, record, mid, fixture.get('utcDate'), method)
                    if reason is not None:
                        pass
                    elif entry.get('predicted_score') is None:
                        reason = entry.get('failure_reason') or 'NO_EXPERIMENTAL_SCORE'
                    elif method == METHODS[0] and entry.get('valid_ai_count', 0) < 3:
                        reason = 'MIN_3_VALID_AI'
                    elif method == METHODS[1] and entry.get('valid_ai_count', 0) < 2:
                        reason = 'MIN_2_VALID_AI'
                    else:
                        proof = evidence.verify(mid, fixture['utcDate'], block)
                        if not proof.get('verified'):
                            reason = proof.get('reason') or 'PROVENANCE_NOT_VERIFIED'
            if reason is not None:
                reasons = stats['failure_reasons']
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            pts, exact, outcome = score_points(entry['predicted_score'],
                                               entry['predicted_outcome'], actual_home, actual_away)
            stats['valid_predictions'] += 1
            stats['points'] += pts
            stats['exact'] += int(exact)
            stats['outcome'] += int(outcome)
            stats['point_distribution'][str(pts)] += 1
            stats['used_ai_sum'] += entry['valid_ai_count']
            count = str(entry['valid_ai_count'])
            stats['models_used_counts'][count] = stats['models_used_counts'].get(count, 0) + 1
            stats['valid_match_ids'].append(mid)
            stats['match_evaluations'][mid] = {
                'predicted_score': entry['predicted_score'],
                'actual_score': f'{actual_home}-{actual_away}',
                'points': pts, 'outcome_correct': bool(outcome), 'exact': bool(exact),
                'created_at': entry['created_at'], 'source_votes_sha256': entry['source_votes_sha256'],
            }
            stats['provenance'][mid] = {k: v for k, v in proof.items() if k != 'verified'}
            for target in [*ACTIVE_MODEL_ORDER, 'Ortak karar']:
                comparator = _comparator_score(record, target, actual_home, actual_away)
                if comparator is None:
                    continue
                against = stats['head_to_head'].setdefault(target, {
                    'common_matches': 0, 'experimental_points': 0, 'comparison_points': 0,
                    'experimental_better': 0, 'equal': 0, 'comparison_better': 0,
                    'experimental_outcome': 0, 'comparison_outcome': 0})
                against['common_matches'] += 1
                against['experimental_points'] += pts
                against['comparison_points'] += comparator
                against['experimental_better'] += int(pts > comparator)
                against['equal'] += int(pts == comparator)
                against['comparison_better'] += int(pts < comparator)
                against['experimental_outcome'] += int(outcome)
                against['comparison_outcome'] += int(comparator > 0)
    # Same-fixture head-to-head between the two experimental methods as well.
    a, b = data[METHODS[0]], data[METHODS[1]]
    common = set(a['match_evaluations']) & set(b['match_evaluations'])
    for method, mine, theirs in ((METHODS[0], a, b), (METHODS[1], b, a)):
        competitor = METHODS[1] if method == METHODS[0] else METHODS[0]
        bucket = mine['head_to_head'].setdefault(METHOD_LABELS[competitor], {
            'common_matches': 0, 'experimental_points': 0, 'comparison_points': 0,
            'experimental_better': 0, 'equal': 0, 'comparison_better': 0,
            'experimental_outcome': 0, 'comparison_outcome': 0})
        for match_id in sorted(common):
            x = mine['match_evaluations'][match_id]
            y = theirs['match_evaluations'][match_id]
            bucket['common_matches'] += 1
            bucket['experimental_points'] += x['points']
            bucket['comparison_points'] += y['points']
            bucket['experimental_better'] += int(x['points'] > y['points'])
            bucket['equal'] += int(x['points'] == y['points'])
            bucket['comparison_better'] += int(x['points'] < y['points'])
            bucket['experimental_outcome'] += int(x['outcome_correct'])
            bucket['comparison_outcome'] += int(y['outcome_correct'])
    for stats in data.values():
        n = stats['valid_predictions']
        stats['missing_predictions'] = stats['opportunities'] - n
        stats['avg'] = round(stats['points'] / n, 2) if n else 0
        stats['coverage_pct'] = round(100 * n / stats['opportunities'], 1) if stats['opportunities'] else 0
        stats['outcome_pct'] = round(100 * stats['outcome'] / n, 1) if n else 0
        stats['exact_pct'] = round(100 * stats['exact'] / n, 1) if n else 0
        stats['point_efficiency_pct'] = round(100 * stats['points'] / (8 * n), 1) if n else 0
        stats['avg_valid_ai_count'] = round(stats['used_ai_sum'] / n, 2) if n else 0
    return {'season': season, 'matchday': int(matchday), 'status': 'FINAL',
            'scoring_rule': SCORING_RULE, 'schema_version': SCHEMA_VERSION,
            'scope': 'PROSPECTIVE_ONLY', 'total_fixtures': len(fixtures),
            'policy_excluded': len(excluded_ids), 'excluded_match_ids': excluded_ids,
            'opportunities': len(eligible), 'methods': data}


def build_experimental_season(weeks: dict[str, dict], *, season: str = SEASON) -> dict:
    totals = {key: _empty(key, 0) for key in METHODS}
    for md, week in sorted(weeks.items(), key=lambda kv: int(kv[0])):
        if week.get('status') != 'FINAL' or week.get('scoring_rule') != SCORING_RULE:
            raise ValueError(f'Experimental weekly archive invalid or mixed points at matchday {md}')
        if week.get('scope') != 'PROSPECTIVE_ONLY' or week.get('schema_version') != SCHEMA_VERSION:
            raise ValueError(f'Incompatible experimental archive version: matchday {md}')
        for method in METHODS:
            src, dst = week['methods'][method], totals[method]
            if src.get('version') != SCHEMA_VERSION or src.get('method') != method:
                raise ValueError(f'Mixed experimental method versions: {md}/{method}')
            for key in ('opportunities', 'valid_predictions', 'points', 'outcome', 'exact', 'used_ai_sum'):
                dst[key] += int(src.get(key, 0))
            for score, count in src.get('point_distribution', {}).items():
                dst['point_distribution'][score] += int(count)
            for reason, count in src.get('failure_reasons', {}).items():
                dst['failure_reasons'][reason] = dst['failure_reasons'].get(reason, 0) + int(count)
            for ai_count, count in src.get('models_used_counts', {}).items():
                dst['models_used_counts'][ai_count] = dst['models_used_counts'].get(ai_count, 0) + int(count)
            dst['valid_match_ids'].extend(src.get('valid_match_ids', []))
            dst['match_evaluations'].update(src.get('match_evaluations', {}))
            for opponent, metrics in src.get('head_to_head', {}).items():
                merged = dst['head_to_head'].setdefault(opponent, {k: 0 for k in metrics})
                for key, value in metrics.items():
                    merged[key] += int(value)
    for dst in totals.values():
        n, opportunities = dst['valid_predictions'], dst['opportunities']
        dst['missing_predictions'] = opportunities - n
        dst['avg'] = round(dst['points'] / n, 2) if n else 0
        dst['coverage_pct'] = round(100 * n / opportunities, 1) if opportunities else 0
        dst['outcome_pct'] = round(100 * dst['outcome'] / n, 1) if n else 0
        dst['exact_pct'] = round(100 * dst['exact'] / n, 1) if n else 0
        dst['point_efficiency_pct'] = round(100 * dst['points'] / (8 * n), 1) if n else 0
        dst['avg_valid_ai_count'] = round(dst['used_ai_sum'] / n, 2) if n else 0
    return {'season': season, 'scoring_rule': SCORING_RULE, 'scope': 'PROSPECTIVE_ONLY',
            'finalized_matchdays': sorted(weeks, key=int), 'methods': totals}
