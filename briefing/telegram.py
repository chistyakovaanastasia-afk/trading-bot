"""Telegram delivery for briefings.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment.
If either is missing, the caller falls back to stdout — the bot never
fails a trading cycle because a chat message couldn't be sent.
"""

from __future__ import annotations

import os

import requests


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        return resp.ok
    except requests.RequestException as exc:
        print(f"[telegram] send failed: {exc}")
        return False
