"""Read-only GitHub evidence that an experimental prediction existed pre-kickoff.

The prediction's self-reported created_at is NEVER sufficient. An unchanged
experiment must appear in an earlier source-repository commit snapshot.
Git commit dates are still user-controlled; the audit records the exact commit
SHA and checksums so that external push-time attestation can be added later.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

import requests

from config import PREDICTION_REPO, PREDICTION_FILE, PREDICTION_REPO_TOKEN, REQUEST_TIMEOUT


def utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.astimezone(timezone.utc) if date.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def eligible_source_vote_digest(votes: Any) -> str:
    """Reproduce the frozen source votes digest, without recomputing a score."""
    selected, seen = [], set()
    if isinstance(votes, list):
        for vote in votes:
            if not isinstance(vote, dict) or vote.get('success') is not True:
                continue
            model, result = vote.get('model'), vote.get('result')
            if not isinstance(model, str) or not model.strip() or model in seen or not isinstance(result, dict):
                continue
            score = result.get('score')
            match = re.fullmatch(r'([0-9]{1,2})-([0-9]{1,2})', score.strip()) if isinstance(score, str) else None
            if not match:
                continue
            h, a = map(int, match.groups())
            outcome = 'HOME' if h > a else 'AWAY' if a > h else 'DRAW'
            if result.get('outcome') != outcome:
                continue
            selected.append((model, result.get('model_id') or model, f'{h}-{a}'))
            seen.add(model)
    raw = json.dumps(selected, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class GitHubPreKickoffEvidence:
    """Fail-closed source lookup; no GitHub write, AI service, or Telegram call."""
    def __init__(self, *, repo: str = PREDICTION_REPO, file: str = PREDICTION_FILE,
                 token: str = PREDICTION_REPO_TOKEN, session=None):
        self.repo, self.file, self.token = repo, file, token
        self.session = session or requests
        self._commit_cache: dict[str, Any] = {}
        self._archive_cache: dict[str, Any] = {}

    def _get(self, url: str, params: dict, *, raw: bool = False) -> Any:
        if not self.token:
            raise RuntimeError('GITHUB_PROVENANCE_TOKEN_MISSING')
        response = self.session.get(url, params=params, headers={
            'Accept': 'application/vnd.github.raw+json' if raw else 'application/vnd.github+json',
            'Authorization': f'Bearer {self.token}'}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()

    def verify(self, match_id: str, kickoff: str, experiment: dict) -> dict:
        """Find an earlier source-file commit containing the exact frozen experiment.

        A GitHub commit SHA + its server-returned contents is independent from
        the *latest* prediction archive's mutable created_at field. This does
        not purport to prove the historical push timestamp cryptographically.
        """
        kickoff_dt = utc_datetime(kickoff)
        if kickoff_dt is None:
            return {'verified': False, 'reason': 'INVALID_KICKOFF'}
        if not self.token:
            return {'verified': False, 'reason': 'PROVENANCE_TOKEN_MISSING'}
        iso = kickoff_dt.isoformat().replace('+00:00', 'Z')
        try:
            if iso not in self._commit_cache:
                self._commit_cache[iso] = self._get(
                    f'https://api.github.com/repos/{self.repo}/commits',
                    {'path': self.file, 'until': iso, 'per_page': 1})
            commits = self._commit_cache[iso]
            if not isinstance(commits, list) or not commits:
                return {'verified': False, 'reason': 'NO_PREKICKOFF_COMMIT'}
            commit = commits[0]
            sha = commit['sha']
            committed_at = utc_datetime(commit['commit']['committer']['date'])
            if committed_at is None or committed_at >= kickoff_dt:
                return {'verified': False, 'reason': 'COMMIT_NOT_PREKICKOFF'}
            if sha not in self._archive_cache:
                self._archive_cache[sha] = self._get(
                    f'https://api.github.com/repos/{self.repo}/contents/{self.file}',
                    {'ref': sha}, raw=True)
            archived = self._archive_cache[sha]
            if not isinstance(archived, dict):
                return {'verified': False, 'reason': 'COMMIT_ARCHIVE_INVALID'}
            row = archived.get(str(match_id))
            if not isinstance(row, dict) or row.get('experimental_predictions') != experiment:
                return {'verified': False, 'reason': 'NOT_IN_PREKICKOFF_SNAPSHOT'}
            if utc_datetime(row.get('match_utc')) != kickoff_dt:
                return {'verified': False, 'reason': 'SOURCE_KICKOFF_MISMATCH'}
            historical_hash = eligible_source_vote_digest(row.get('ai_votes'))
            if any((not isinstance(entry, dict) or
                    entry.get('source_votes_sha256') != historical_hash)
                   for entry in experiment.get('methods', {}).values()):
                return {'verified': False, 'reason': 'COMMITTED_VOTE_HASH_MISMATCH'}
            return {'verified': True, 'reason': 'PREKICKOFF_GITHUB_SNAPSHOT',
                    'commit_sha': sha, 'commit_date': committed_at.isoformat(),
                    'source_experiment_sha256': stable_hash(experiment)}
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            return {'verified': False, 'reason': 'PROVENANCE_LOOKUP_FAILED',
                    'detail': type(exc).__name__}
