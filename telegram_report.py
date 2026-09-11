from __future__ import annotations

import os
from pathlib import Path

import requests

from config import ANALYSIS_TELEGRAM_BOT_TOKEN, ANALYSIS_TELEGRAM_CHAT_ID, TELEGRAM_ENABLED, REQUEST_TIMEOUT


def _check() -> None:
    if not TELEGRAM_ENABLED:
        return
    if not ANALYSIS_TELEGRAM_BOT_TOKEN or not ANALYSIS_TELEGRAM_CHAT_ID:
        raise RuntimeError("ANALYSIS_TELEGRAM_BOT_TOKEN / ANALYSIS_TELEGRAM_CHAT_ID eksik.")


def send_photo(path: Path, caption: str) -> None:
    if not TELEGRAM_ENABLED:
        print(f"ℹ️ Telegram kapalı; gönderim atlandı: {path}")
        return
    _check()
    with path.open("rb") as photo:
        response = requests.post(
            f"https://api.telegram.org/bot{ANALYSIS_TELEGRAM_BOT_TOKEN}/sendPhoto",
            data={"chat_id": ANALYSIS_TELEGRAM_CHAT_ID, "caption": caption},
            files={"photo": photo},
            timeout=REQUEST_TIMEOUT,
        )
    response.raise_for_status()
