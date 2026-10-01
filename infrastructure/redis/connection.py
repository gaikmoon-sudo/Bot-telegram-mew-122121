"""Shared async Redis connection used by FSM, caching and temporary data.

Redis is required for FSM and is the sole cache backend.
"""
from __future__ import annotations

import os
from typing import Optional

from redis.asyncio import Redis

_client: Optional[object] = None


def _redis_url() -> str:
    from config import settings
    return settings.redis_url


def get_redis_client() -> object | None:
    """Return the shared Redis client configured through REDIS_URL."""
    global _client
    url = _redis_url()
    if not url:
        raise RuntimeError("REDIS_URL is required for Redis-backed state and cache.")
    if _client is None:
        _client = Redis.from_url(url, encoding="utf-8", decode_responses=True)
    return _client


async def ping_redis() -> bool:
    client = get_redis_client()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        return False


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None
