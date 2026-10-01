"""Async client for the Piston code-execution API.

The bot never executes learner code locally. Piston is an external execution
boundary; this module normalizes successful, rejected, timed-out, and network
failures into one result shape for both the Web IDE and AI review.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import aiohttp
from config import settings

from infrastructure.observability.sentry import capture_exception


class PistonClient:
    def __init__(self) -> None:
        self.base_url = settings.piston_api_url
        self.api_key = settings.piston_api_key
        self.timeout_seconds = settings.piston_timeout_seconds
        self.compile_timeout_ms = settings.piston_compile_timeout_ms
        self.run_timeout_ms = settings.piston_run_timeout_ms
        self.max_code_chars = settings.piston_max_code_chars
        self.max_stdin_chars = settings.piston_max_stdin_chars
        self.max_output_chars = settings.piston_max_output_chars
        self._semaphore = asyncio.Semaphore(settings.piston_max_concurrency)
        self._runtimes: list[dict[str, Any]] | None = None
        self._runtimes_at = 0.0
        self._runtimes_lock = asyncio.Lock()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _error_result(message: str, *, phase: str = "piston", error_type: str = "unavailable") -> dict[str, Any]:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "output": "",
            "exit_code": None,
            "signal": None,
            "phase": phase,
            "error": message,
            "error_type": error_type,
        }

    async def _get_runtimes(self, session: aiohttp.ClientSession) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._runtimes is not None and now - self._runtimes_at < 600:
            return self._runtimes
        async with self._runtimes_lock:
            now = time.monotonic()
            if self._runtimes is not None and now - self._runtimes_at < 600:
                return self._runtimes
            async with session.get(f"{self.base_url}/runtimes") as response:
                body = await response.json(content_type=None)
                if response.status >= 400 or not isinstance(body, list):
                    message = body.get("message") if isinstance(body, dict) else None
                    raise RuntimeError(message or f"Piston runtimes request failed ({response.status})")
                self._runtimes = [item for item in body if isinstance(item, dict)]
                self._runtimes_at = time.monotonic()
                return self._runtimes

    @staticmethod
    def _resolve_runtime(runtimes: list[dict[str, Any]], language: str) -> tuple[str, str] | None:
        requested = language.lower().strip()
        for runtime in runtimes:
            name = str(runtime.get("language", "")).lower()
            aliases = {str(alias).lower() for alias in runtime.get("aliases", [])}
            if requested == name or requested in aliases:
                version = str(runtime.get("version", "")).strip()
                if version:
                    return name, version
        return None

    async def execute(self, *, language: str, code: str, stdin: str = "") -> dict[str, Any]:
        language = language.lower().strip()
        if language not in {"cpp", "python"}:
            return self._error_result("اللغة غير مدعومة من مختبر التنفيذ.", error_type="validation")
        if not code.strip():
            return self._error_result("لا يوجد كود للتنفيذ.", error_type="validation")
        if len(code) > self.max_code_chars:
            return self._error_result(
                f"حجم الكود يتجاوز الحد المسموح ({self.max_code_chars} حرفًا).",
                error_type="validation",
            )
        if len(stdin) > self.max_stdin_chars:
            return self._error_result(
                f"حجم الإدخال يتجاوز الحد المسموح ({self.max_stdin_chars} حرفًا).",
                error_type="validation",
            )

        timeout = aiohttp.ClientTimeout(
            total=self.timeout_seconds,
            connect=min(5, self.timeout_seconds),
            sock_read=self.timeout_seconds,
        )
        try:
            async with self._semaphore:
                async with aiohttp.ClientSession(timeout=timeout, headers=self._headers()) as session:
                    runtimes = await self._get_runtimes(session)
                    resolved = self._resolve_runtime(runtimes, language)
                    if not resolved:
                        return self._error_result(
                            f"لم يتم العثور على runtime للغة {language} في Piston.",
                            error_type="runtime_unavailable",
                        )
                    runtime_name, version = resolved
                    payload = {
                        "language": runtime_name,
                        "version": version,
                        "files": [{"name": "main.cpp" if language == "cpp" else "main.py", "content": code}],
                        "stdin": str(stdin)[: self.max_stdin_chars],
                        "compile_timeout": self.compile_timeout_ms,
                        "run_timeout": self.run_timeout_ms,
                    }
                    async with session.post(f"{self.base_url}/execute", json=payload) as response:
                        body = await response.json(content_type=None)
                        if response.status >= 400:
                            message = body.get("message") if isinstance(body, dict) else None
                            return self._error_result(
                                message or f"رفض Piston الطلب (HTTP {response.status}).",
                                error_type="rejected",
                            )
                        result = self._normalize(body, runtime_name, version)
                        for key in ("stdout", "stderr", "output"):
                            result[key] = str(result.get(key, ""))[: self.max_output_chars]
                        return result
        except asyncio.TimeoutError as exc:
            capture_exception(exc, tags={"component": "piston", "operation": "execute", "error_type": "timeout", "language": language})
            return self._error_result(
                "انتهت مهلة الاتصال بخدمة تنفيذ الأكواد.", error_type="timeout"
            )
        except (aiohttp.ClientError, OSError) as exc:
            capture_exception(exc, tags={"component": "piston", "operation": "execute", "error_type": "network", "language": language})
            return self._error_result(
                "تعذر الوصول إلى خدمة تنفيذ الأكواد مؤقتًا.", error_type="network"
            )
        except Exception as exc:
            capture_exception(exc, tags={"component": "piston", "operation": "execute", "error_type": "internal", "language": language})
            return self._error_result(
                "حدث خطأ غير متوقع في خدمة تنفيذ الأكواد.", error_type="internal"
            )

    @classmethod
    def _normalize(cls, body: Any, language: str, version: str) -> dict[str, Any]:
        if not isinstance(body, dict):
            return cls._error_result("استجابة غير صالحة من Piston.", error_type="protocol")
        compile_result = body.get("compile") or {}
        run_result = body.get("run") or {}
        stage = compile_result if compile_result and compile_result.get("code") not in (0, None) else run_result
        if not isinstance(stage, dict):
            return cls._error_result("استجابة تنفيذ غير مكتملة من Piston.", error_type="protocol")
        stdout = str(run_result.get("stdout", ""))
        stderr = str(run_result.get("stderr", ""))
        if compile_result and compile_result.get("code") not in (0, None):
            stdout = str(compile_result.get("stdout", ""))
            stderr = str(compile_result.get("stderr", ""))
        status = stage.get("status")
        error = stage.get("message") or (f"Piston execution status: {status}" if status else "")
        return {
            "ok": stage.get("code") == 0 and not stage.get("signal"),
            "stdout": stdout,
            "stderr": stderr,
            "output": str(stage.get("output", "")),
            "exit_code": stage.get("code"),
            "signal": stage.get("signal"),
            "status": status,
            "phase": "compile" if compile_result and compile_result.get("code") not in (0, None) else "run",
            "error": error,
            "language": language,
            "version": version,
        }


piston_client = PistonClient()


async def execute_code(*, language: str, code: str, stdin: str = "") -> dict[str, Any]:
    return await piston_client.execute(language=language, code=code, stdin=stdin)
