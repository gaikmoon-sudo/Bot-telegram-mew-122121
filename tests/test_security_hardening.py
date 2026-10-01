from __future__ import annotations

import asyncio

import pytest

from app.security import async_rate_limit
from config import Settings


def test_local_async_rate_limiter_is_bounded(monkeypatch):
    monkeypatch.setattr(async_rate_limit, "get_redis_client", lambda: None)

    async def run():
        limiter = async_rate_limit.AsyncRateLimiter(2, 60, prefix="test")
        assert await limiter.allow("user")
        assert await limiter.allow("user")
        assert not await limiter.allow("user")

    asyncio.run(run())


def test_production_rejects_local_content_storage(monkeypatch):
    values = {
        "BOT_TOKEN": "123456:placeholder-token",
        "ADMIN_IDS": "123456789",
        "DATABASE_URL": "postgresql://user:pass@db.example:5432/academy",
        "REDIS_URL": "rediss://default:pass@redis.example:6380/0",
        "WEBHOOK_SECRET": "Valid_webhook-secret_123",
        "WEBHOOK_URL": "https://academy.example/telegram/webhook",
        "CONTENT_STORAGE_BACKEND": "local",
        "SENTRY_ENVIRONMENT": "production_replit",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="local is not allowed"):
        Settings().validate_production()


def test_production_rejects_http_web_app(monkeypatch):
    values = {
        "BOT_TOKEN": "123456:placeholder-token",
        "ADMIN_IDS": "123456789",
        "DATABASE_URL": "postgresql://user:pass@db.example:5432/academy",
        "REDIS_URL": "rediss://default:pass@redis.example:6380/0",
        "WEBHOOK_SECRET": "Valid_webhook-secret_123",
        "WEBHOOK_URL": "https://academy.example/telegram/webhook",
        "WEB_APP_URL": "http://academy.example",
        "CONTENT_STORAGE_BACKEND": "replit",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="WEB_APP_URL"):
        Settings().validate_production()
