"""Async rate limiting for Web App endpoints.

Redis is preferred so limits apply consistently across multiple instances. A
small bounded in-process fallback keeps development and degraded mode usable.
"""
from __future__ import annotations

import time
from collections import OrderedDict, deque

from infrastructure.redis.connection import get_redis_client


class AsyncRateLimiter:
    def __init__(self, limit: int, window_seconds: int, *, prefix: str) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.prefix = prefix
        self._local: OrderedDict[str, deque[float]] = OrderedDict()
        self._max_keys = 10_000

    async def allow(self, key: str) -> bool:
        try:
            redis = get_redis_client()
        except Exception:
            redis = None
        if redis is not None:
            redis_key = f"academy:ratelimit:{self.prefix}:{key}"
            try:
                count = await redis.incr(redis_key)
                if count == 1:
                    await redis.expire(redis_key, self.window_seconds)
                return int(count) <= self.limit
            except Exception:
                # A temporary Redis outage must not make the endpoint unusable;
                # fall back to a bounded local limiter for this process.
                pass
        return self._allow_local(key)

    def _allow_local(self, key: str) -> bool:
        now = time.monotonic()
        events = self._local.setdefault(key, deque())
        while events and now - events[0] >= self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            self._local.move_to_end(key)
            return False
        events.append(now)
        self._local.move_to_end(key)
        while len(self._local) > self._max_keys:
            self._local.popitem(last=False)
        return True
