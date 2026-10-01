from __future__ import annotations

import logging
import time
from collections import OrderedDict

from aiogram import BaseMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        started = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            if user:
                logger.info("telegram_update user=%s type=%s duration_ms=%.1f", user.id, type(event).__name__, elapsed)


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 0.6):
        self.rate = rate
        self.last: OrderedDict[int, float] = OrderedDict()
        self.max_entries = 100_000

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)
        now = time.monotonic()
        last = self.last.get(user.id, 0.0)
        if now - last < self.rate:
            # Callback queries can still be answered by Telegram without blocking
            # the UI; text messages are silently throttled.
            if hasattr(event, "answer"):
                try:
                    await event.answer("⏳ تمهل قليلًا...")
                except Exception:
                    pass
            return None
        self.last[user.id] = now
        self.last.move_to_end(user.id)
        if len(self.last) > self.max_entries:
            self.last.popitem(last=False)
        return await handler(event, data)
