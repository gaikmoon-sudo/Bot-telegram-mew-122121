from __future__ import annotations
import time
from collections import defaultdict, deque
from threading import Lock

class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit=limit; self.window=window_seconds; self._events=defaultdict(deque); self._lock=Lock()
    def allow(self, key: str) -> bool:
        now=time.monotonic()
        with self._lock:
            q=self._events[key]
            while q and now-q[0]>=self.window: q.popleft()
            if len(q)>=self.limit: return False
            q.append(now); return True

def clamp_text(value: str, max_chars: int) -> str:
    return (value or '')[:max_chars]
