from __future__ import annotations

import base64
import json
from typing import Any

import requests

from config import PREDICTION_BRANCH, PREDICTION_FILE, PREDICTION_REPO, PREDICTION_REPO_TOKEN, REQUEST_TIMEOUT


class SourceLoadError(RuntimeError):
    pass


def _decode_github_contents(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content")
    if not content:
        raise SourceLoadError("GitHub dosya içeriği boş.")
    try:
        raw = base64.b64decode(content).decode("utf-8")
        data = json.loads(raw)
    except Exception as exc:
        raise SourceLoadError(f"GitHub prediction arşivi çözülemedi: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceLoadError("match_predictions.json bir JSON nesnesi olmalı.")
    return data


def load_prediction_archive() -> dict[str, Any]:
    url = f"https://api.github.com/repos/{PREDICTION_REPO}/contents/{PREDICTION_FILE}"
    params = {"ref": PREDICTION_BRANCH}
    headers = {"Accept": "application/vnd.github+json"}
    if PREDICTION_REPO_TOKEN:
        headers["Authorization"] = f"Bearer {PREDICTION_REPO_TOKEN}"

    response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        raise SourceLoadError(
            f"Prediction arşivi bulunamadı: {PREDICTION_REPO}/{PREDICTION_FILE}. "
            "Repo private ise PREDICTION_REPO_TOKEN secret'ı gerekli."
        )
    if response.status_code in {401, 403}:
        raise SourceLoadError(
            f"Prediction repo erişimi reddedildi ({response.status_code}). "
            "Private repo için Contents: Read yetkili PREDICTION_REPO_TOKEN kullanın."
        )
    response.raise_for_status()
    return _decode_github_contents(response.json())
