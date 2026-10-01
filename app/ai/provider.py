from __future__ import annotations

import os
from config import settings
from typing import Any


class AIConfigurationError(RuntimeError):
    pass


class AIProvider:
    async def generate(self, *, system: str, messages: list[dict[str, str]], model: str, temperature: float = 0.2) -> str:
        raise NotImplementedError


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise AIConfigurationError("حزمة OpenAI غير مثبتة. ثبّت متطلبات المشروع أولًا.") from exc
        self._client = AsyncOpenAI(api_key=api_key)

    async def generate(self, *, system: str, messages: list[dict[str, str]], model: str, temperature: float = 0.2) -> str:
        kwargs = {
            "model": model,
            "instructions": system,
            "input": messages,
        }
        # Some newer reasoning models do not accept the legacy temperature
        # control. Keep the provider compatible with both model families.
        if not model.lower().startswith("gpt-5"):
            kwargs["temperature"] = temperature
        response = await self._client.responses.create(**kwargs)
        text = getattr(response, "output_text", "") or ""
        return text.strip()


def build_provider() -> AIProvider:
    provider = settings.ai_provider.lower()
    api_key = settings.openai_api_key
    if provider != "openai":
        raise AIConfigurationError(f"مزود AI غير مدعوم حاليًا: {provider}. استخدم AI_PROVIDER=openai.")
    if not api_key:
        raise AIConfigurationError("AI غير مفعّل بعد: أضف OPENAI_API_KEY في إعدادات الخادم لاحقًا.")
    return OpenAIProvider(api_key)
