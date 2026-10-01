from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class LearningSnapshot:
    completed: int
    total: int
    percent: int
    xp: int
    streak: int

class LearningService:
    """Application-level learning logic kept independent from Telegram handlers."""
    def __init__(self, store: Any, lesson_ids: list[int]):
        self.store = store
        self.lesson_ids = lesson_ids

    def snapshot(self, user_id: int) -> LearningSnapshot:
        stats = self.store.snapshot(user_id, len(self.lesson_ids))
        return LearningSnapshot(**stats)

    def complete(self, user_id: int, lesson_id: int) -> dict[str, Any]:
        first = self.store.complete_lesson(user_id, lesson_id)
        return {"first_completion": first, "snapshot": self.snapshot(user_id)}
