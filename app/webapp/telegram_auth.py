"""Shared validation for Telegram WebApp initData headers."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from aiohttp import web

from config import settings


def validate_telegram_init_data(init_data: str) -> dict | None:
    """Validate initData signature and freshness using the configured bot token."""
    if not init_data or len(init_data) > 20_000 or not settings.bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    if not received or len(received) != 64:
        return None
    data_check = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        if abs(int(time.time()) - auth_date) > 300:
            return None
        user = json.loads(pairs.get("user", "{}"))
        user_id = user.get("id") if isinstance(user, dict) else None
        if isinstance(user_id, bool) or int(user_id) <= 0:
            return None
        return user
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def telegram_user_id(request: web.Request) -> int | None:
    """Return the authenticated Telegram user id, or ``None`` on any failure."""
    user = validate_telegram_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    try:
        return int(user["id"]) if user else None
    except (KeyError, TypeError, ValueError):
        return None
