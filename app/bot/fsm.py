"""Redis-backed FSM storage for all environments."""
from __future__ import annotations
from config import settings
from aiogram.fsm.storage.redis import RedisStorage


def build_fsm_storage():
    if not settings.redis_url:
        raise RuntimeError("REDIS_URL is required for FSM storage.")
    return RedisStorage.from_url(settings.redis_url), "redis"
