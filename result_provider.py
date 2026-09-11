from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from config import COMPETITION_CODE, FOOTBALL_DATA_API_KEY, FOOTBALL_DATA_BASE_URL, REQUEST_TIMEOUT


class ResultProviderError(RuntimeError):
    pass


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


class FootballDataResultProvider:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or FOOTBALL_DATA_API_KEY
        if not self.api_key:
            raise ResultProviderError("FOOTBALL_DATA_API_KEY secret'ı eksik.")

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.get(
            f"{FOOTBALL_DATA_BASE_URL}{path}",
            headers={"X-Auth-Token": self.api_key},
            params=params or {},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 429:
            reset = response.headers.get("X-RequestCounter-Reset", "bilinmiyor")
            raise ResultProviderError(f"football-data.org rate limit (429), reset={reset}s")
        if response.status_code in {401, 403}:
            raise ResultProviderError(f"football-data.org yetki hatası ({response.status_code}).")
        response.raise_for_status()
        return response.json()

    def get_all_matches(self) -> list[dict[str, Any]]:
        data = self._get(f"/competitions/{COMPETITION_CODE}/matches")
        return data.get("matches", []) or []

    def get_matches_by_matchday(self) -> dict[int, list[dict[str, Any]]]:
        result: dict[int, list[dict[str, Any]]] = {}
        for match in self.get_all_matches():
            md = match.get("matchday")
            if md is None:
                continue
            try:
                md_int = int(md)
            except (TypeError, ValueError):
                continue
            result.setdefault(md_int, []).append(match)
        for rows in result.values():
            rows.sort(key=lambda m: str(m.get("utcDate", "")))
        return result

    def get_match_status_map(self) -> dict[str, dict[str, Any]]:
        return {str(m.get("id")): m for m in self.get_all_matches() if m.get("id") is not None}
