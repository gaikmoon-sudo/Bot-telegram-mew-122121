"""Best-effort Redis response cache for AI requests.

This is response caching, not provider-side prompt caching.  The cache key
includes the complete model input so one user's personalized answer cannot be
returned for a different request.  Redis failures are intentionally ignored:
the AI provider remains the source of truth.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Awaitable, Callable

from infrastructure.redis.connection import get_redis_client

logger = logging.getLogger(__name__)

CACHE_VERSION = "v2"
DEFAULT_TTL = 86_400


def build_cache_key(*, provider: str, model: str, payload: Any, user_id: int | None = None) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    scope = f"user:{user_id}" if user_id is not None else "global"
    return f"ai_cache:{CACHE_VERSION}:{scope}:{provider}:{model}:{digest}"


async def get_or_generate(
    *,
    provider: str,
    model: str,
    payload: Any,
    generate: Callable[[], Awaitable[str]],
    ttl: int = DEFAULT_TTL,
    user_id: int | None = None,
) -> str:
    """Read an AI response from Redis or generate and cache it.

    The function is deliberately best-effort: if Redis is missing, down, or
    returns malformed data, the request proceeds normally without caching.
    """
    if ttl <= 0:
        return await generate()

    redis = get_redis_client()
    key = build_cache_key(provider=provider, model=model, payload=payload, user_id=user_id)

    if redis is not None:
        try:
            cached = await redis.get(key)
            if cached:
                data = json.loads(cached)
                if isinstance(data, dict) and isinstance(data.get("response"), str):
                    return data["response"]
        except Exception:
            logger.warning("AI Redis cache read failed; bypassing cache", exc_info=True)

    response = await generate()

    if redis is not None and response:
        try:
            await redis.set(
                key,
                json.dumps({"response": response}, ensure_ascii=False),
                ex=ttl,
            )
        except Exception:
            logger.warning("AI Redis cache write failed; continuing without cache", exc_info=True)

    return response


async def delete_user_cache(user_id: int) -> int:
    """Best-effort deletion of all AI cache entries belonging to a user."""
    redis = get_redis_client()
    if redis is None:
        return 0
    pattern = f"ai_cache:{CACHE_VERSION}:user:{int(user_id)}:*"
    deleted = 0
    try:
        keys = []
        async for key in redis.scan_iter(match=pattern, count=200):
            keys.append(key)
            if len(keys) >= 200:
                deleted += int(await redis.delete(*keys))
                keys.clear()
        if keys:
            deleted += int(await redis.delete(*keys))
    except Exception:
        logger.warning("AI Redis cache deletion failed for user=%s", user_id, exc_info=True)
    return deleted
