from __future__ import annotations

import re
from html import unescape
from typing import Iterable


def _plain(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return unescape(value)


def retrieve(query: str, lessons: dict[int, dict], limit: int = 4) -> str:
    tokens = {t.lower() for t in re.findall(r"[\w+#.-]+", query) if len(t) > 1}
    scored: list[tuple[int, int, dict]] = []
    for lesson_id, lesson in lessons.items():
        text = " ".join(str(lesson.get(k, "")) for k in ("title", "objective", "theory", "simple", "examples", "question"))
        plain = _plain(text)
        lower = plain.lower()
        score = sum(lower.count(token) for token in tokens)
        if score:
            scored.append((score, int(lesson_id), lesson))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chunks = []
    for _, lesson_id, lesson in scored[:limit]:
        chunks.append(
            f"[الدرس {lesson_id}] {lesson.get('title','')}\n"
            f"الهدف: {lesson.get('objective','')}\n"
            f"الشرح: {_plain(str(lesson.get('theory','')))}\n"
            f"أمثلة: {_plain(str(lesson.get('examples','')))}"
        )
    return "\n\n".join(chunks)
