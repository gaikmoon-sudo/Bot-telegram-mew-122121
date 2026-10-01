from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from app.ai.provider import AIConfigurationError, AIProvider, build_provider
from app.ai.cache import get_or_generate
from app.ai.prompts import reviewer_prompt, tutor_prompt
from app.ai.rag import retrieve
from app.storage.postgres import store
from app.webapp.piston import execute_code
from config import settings
from infrastructure.observability.sentry import capture_exception


@dataclass(frozen=True)
class AIQuota:
    tutor: int = 10
    review: int = 3
    quiz: int = 1


class AIService:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self._provider = provider
        self.model = settings.ai_model
        self.enabled = settings.ai_enabled
        self._provider_lock = asyncio.Lock()

    async def _get_provider(self) -> AIProvider:
        if not self.enabled:
            raise AIConfigurationError("ميزة AI غير مفعلة حاليًا. سيتم تفعيلها بعد إضافة الإعدادات المطلوبة.")
        if not self.model:
            raise AIConfigurationError("AI_MODEL غير محدد. أضف اسم النموذج عند إعداد مفتاح API.")
        if self._provider is None:
            async with self._provider_lock:
                if self._provider is None:
                    self._provider = build_provider()
        return self._provider

    def quota(self, kind: str) -> int:
        limits = {
            "tutor": settings.ai_tutor_daily_limit,
            "review": settings.ai_review_daily_limit,
            "quiz": settings.ai_quiz_daily_limit,
        }
        return limits[kind]

    async def tutor(self, user_id: int, question: str, *, lesson_id: int | None = None) -> tuple[str, int]:
        try:
            provider = await self._get_provider()
        except Exception as exc:
            capture_exception(exc, tags={"component": "ai_tutor", "operation": "provider_init"}, extras={"user_id": user_id, "model": self.model})
            raise
        quota_limit = self.quota("tutor")
        reserved, _ = store.consume_ai_quota(user_id, "tutor", quota_limit)
        if not reserved:
            raise AIConfigurationError(f"وصلت إلى حد المعلم الذكي اليومي ({quota_limit} رسائل). حاول غدًا.")
        profile = store.get_profile(user_id) or {}
        progress = store.snapshot(user_id, 13)
        from app.bot.routers.start import LESSONS
        lesson_context = retrieve(question, LESSONS, limit=4)
        if lesson_id and lesson_id in LESSONS:
            direct = LESSONS[lesson_id]
            lesson_context = (
                f"[الدرس الحالي {lesson_id}] {direct.get('title','')}\n"
                f"الهدف: {direct.get('objective','')}\n"
                f"الشرح: {direct.get('theory','')}\n"
                f"أمثلة: {direct.get('examples','')}\n\n" + lesson_context
            )
        memory = store.get_ai_memory(user_id)
        history = store.ai_history(user_id, 12)
        messages = [{"role": x["role"], "content": x["content"]} for x in history]
        messages.append({"role": "user", "content": question[:8000]})
        try:
            system_prompt = tutor_prompt(profile, progress, lesson_context, memory)
            cache_payload = {
                "mode": "tutor",
                "system": system_prompt,
                "messages": messages,
                "model": self.model,
            }
            answer = await get_or_generate(
                provider="openai",
                model=self.model,
                payload=cache_payload,
                generate=lambda: provider.generate(
                    system=system_prompt,
                    messages=messages,
                    model=self.model,
                    temperature=0.25,
                ),
                ttl=settings.ai_cache_ttl,
                user_id=user_id,
            )
            if not answer:
                raise RuntimeError("لم يُرجع مزود AI إجابة.")
        except Exception as exc:
            capture_exception(exc, tags={"component": "ai_tutor", "operation": "generate"}, extras={"user_id": user_id, "model": self.model})
            store.refund_ai_quota(user_id, "tutor")
            raise
        store.add_ai_message(user_id, "user", question, mode="tutor", lesson_id=lesson_id)
        message_id = store.add_ai_message(user_id, "assistant", answer, mode="tutor", lesson_id=lesson_id)
        store.refresh_ai_memory(user_id)
        return answer, message_id

    async def review_code(
        self,
        user_id: int,
        code: str,
        language: str = "cpp",
        lesson_id: int | None = None,
        execution_result: dict | None = None,
    ) -> tuple[str, int]:
        if len(code) > 20000:
            raise ValueError("الكود طويل جدًا للمراجعة. الحد الأقصى 20,000 حرف.")
        try:
            provider = await self._get_provider()
        except Exception as exc:
            capture_exception(exc, tags={"component": "ai_tutor", "operation": "provider_init", "mode": "review"}, extras={"user_id": user_id, "model": self.model})
            raise
        quota_limit = self.quota("review")
        reserved, _ = store.consume_ai_quota(user_id, "review", quota_limit)
        if not reserved:
            raise AIConfigurationError(f"وصلت إلى حد مراجعة الأكواد اليومي ({quota_limit}). حاول غدًا.")
        profile = store.get_profile(user_id) or {}
        from app.bot.routers.start import LESSONS
        context = retrieve(code, LESSONS, limit=3)
        if lesson_id and lesson_id in LESSONS:
            context = f"الدرس الحالي: {LESSONS[lesson_id].get('title','')}\n{LESSONS[lesson_id].get('objective','')}\n\n{context}"
        if execution_result is None:
            try:
                execution_result = await execute_code(language=language, code=code)
            except Exception:
                store.refund_ai_quota(user_id, "review")
                raise
        prompt = f"لغة البرمجة: {language}\n\nالكود المراد مراجعته:\n```{language}\n{code}\n```"
        try:
            system_prompt = reviewer_prompt(profile, context, execution_result)
            review_messages = [{"role": "user", "content": prompt}]
            cache_payload = {
                "mode": "review",
                "system": system_prompt,
                "messages": review_messages,
                "model": self.model,
            }
            answer = await get_or_generate(
                provider="openai",
                model=self.model,
                payload=cache_payload,
                generate=lambda: provider.generate(
                    system=system_prompt,
                    messages=review_messages,
                    model=self.model,
                    temperature=0.15,
                ),
                ttl=settings.ai_cache_ttl,
                user_id=user_id,
            )
            if not answer:
                raise RuntimeError("لم يُرجع مزود AI مراجعة.")
        except Exception as exc:
            capture_exception(exc, tags={"component": "ai_tutor", "operation": "review_code", "language": language}, extras={"user_id": user_id, "model": self.model})
            store.refund_ai_quota(user_id, "review")
            raise
        message_id = store.add_ai_message(user_id, "assistant", answer, mode="review", lesson_id=lesson_id)
        store.refresh_ai_memory(user_id)
        return answer, message_id

    def usage(self, user_id: int) -> dict[str, int]:
        return store.ai_usage(user_id)


ai_service = AIService()
