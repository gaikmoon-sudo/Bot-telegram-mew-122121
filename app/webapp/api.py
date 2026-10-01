from __future__ import annotations

import asyncio
import re
from pathlib import Path

from aiohttp import web

from app.security.async_rate_limit import AsyncRateLimiter
from app.security.limits import clamp_text
from app.storage.postgres import store
from app.webapp.piston import execute_code
from app.webapp.telegram_auth import telegram_user_id, validate_telegram_init_data

RUN_LIMITER = AsyncRateLimiter(8, 60, prefix="run")
DRAFT_LIMITER = AsyncRateLimiter(30, 60, prefix="draft")
MAX_CODE_CHARS = 20_000
MAX_STDIN_CHARS = 8_000
MAX_OUTPUT_CHARS = 12_000
SUPPORTED_LANGUAGES = {"cpp", "python"}
ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


def _telegram_user(init_data: str) -> dict | None:
    return validate_telegram_init_data(init_data)


def _auth(request: web.Request) -> int | None:
    return telegram_user_id(request)


def _lesson(lesson_id: int) -> dict:
    from app.bot.routers.start import LESSONS

    item = LESSONS.get(lesson_id)
    if not item:
        raise web.HTTPNotFound(text="Lesson not found")
    return item


def _lesson_code(lesson_id: int) -> str:
    raw = _lesson(lesson_id).get("code", "")
    return (
        re.sub(r"<[^>]+>", "", raw)
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
    )


async def _json(request: web.Request) -> dict:
    try:
        data = await request.json()
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="JSON object required")
    return data


def _rate_limited() -> web.HTTPTooManyRequests:
    response = web.HTTPTooManyRequests(text="Too many requests; try again later")
    response.headers["Retry-After"] = "60"
    return response


async def index(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def lesson(request: web.Request) -> web.Response:
    user_id = _auth(request)
    if not user_id:
        raise web.HTTPUnauthorized(text="Telegram authentication required")
    try:
        lesson_id = int(request.match_info["lesson_id"])
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="Invalid lesson")
    item = _lesson(lesson_id)
    language = "cpp"
    draft = await asyncio.to_thread(store.get_code_draft, user_id, lesson_id, language)
    return web.json_response(
        {
            "id": lesson_id,
            "title": str(item.get("title", "")),
            "objective": str(item.get("objective", "")),
            "duration": str(item.get("duration", "")),
            "theory": str(item.get("theory", "")),
            "examples": str(item.get("examples", "")),
            "code": draft if draft is not None else _lesson_code(lesson_id),
            "language": language,
            "completed": lesson_id in store.completed_lessons(user_id),
        }
    )


async def progress(request: web.Request) -> web.Response:
    """Return the learner dashboard data used by the Web App shell."""
    user_id = _auth(request)
    if not user_id:
        raise web.HTTPUnauthorized(text="Telegram authentication required")
    from app.bot.routers.start import CORE_LESSON_IDS, LESSONS

    profile = store.get_profile(user_id) or {}
    stats = store.snapshot(user_id, len(CORE_LESSON_IDS))
    completed = store.completed_lessons(user_id)
    lessons = []
    for lesson_id in CORE_LESSON_IDS:
        item = LESSONS.get(lesson_id, {})
        lessons.append({
            "id": lesson_id,
            "title": str(item.get("title", "")),
            "duration": str(item.get("duration", "")),
            "completed": lesson_id in completed,
            "current": lesson_id == stats.get("last_lesson") or (
                stats.get("last_lesson") is None and lesson_id == CORE_LESSON_IDS[0]
            ),
        })
    return web.json_response({
        "profile": {"name": profile.get("full_name") or "متعلم", "level": profile.get("level") or "مبتدئ"},
        "stats": stats,
        "badges": store.badges(user_id),
        "lessons": lessons,
    })


async def save_draft(request: web.Request) -> web.Response:
    user_id = _auth(request)
    if not user_id:
        raise web.HTTPUnauthorized(text="Telegram authentication required")
    if not await DRAFT_LIMITER.allow(str(user_id)):
        raise _rate_limited()
    data = await _json(request)
    try:
        lesson_id = int(data.get("lesson_id", 0))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="Invalid lesson")
    if lesson_id <= 0:
        raise web.HTTPBadRequest(text="Invalid lesson")
    _lesson(lesson_id)
    language = str(data.get("language", "cpp")).lower().strip()
    if language not in SUPPORTED_LANGUAGES:
        raise web.HTTPBadRequest(text="Supported languages: cpp, python")
    code = str(data.get("code", ""))
    if len(code) > MAX_CODE_CHARS:
        raise web.HTTPRequestEntityTooLarge(text="Code is too large")
    await asyncio.to_thread(
        store.save_code_draft,
        user_id,
        lesson_id,
        clamp_text(code, MAX_CODE_CHARS),
        language,
    )
    return web.json_response({"ok": True})


async def run_code(request: web.Request) -> web.Response:
    user_id = _auth(request)
    if not user_id:
        raise web.HTTPUnauthorized(text="Telegram authentication required")
    if not await RUN_LIMITER.allow(str(user_id)):
        raise _rate_limited()
    data = await _json(request)
    language = str(data.get("language", "cpp")).lower().strip()
    code = str(data.get("code", ""))
    if language not in SUPPORTED_LANGUAGES:
        raise web.HTTPBadRequest(text="Supported languages: cpp, python")
    if not code.strip():
        raise web.HTTPBadRequest(text="Code is required")
    if len(code) > MAX_CODE_CHARS:
        raise web.HTTPRequestEntityTooLarge(text="Code is too large")
    stdin = clamp_text(str(data.get("stdin", "")), MAX_STDIN_CHARS)
    result = await execute_code(
        language=language,
        code=clamp_text(code, MAX_CODE_CHARS),
        stdin=stdin,
    )
    for field in ("stdout", "stderr", "output", "error"):
        if field in result:
            result[field] = clamp_text(str(result.get(field, "")), MAX_OUTPUT_CHARS)
    error_type = result.get("error_type")
    status = 400 if error_type == "validation" else 503 if error_type in {"network", "timeout", "unavailable", "runtime_unavailable", "internal"} else 200
    return web.json_response(result, status=status)


def setup_webapp_routes(app: web.Application) -> None:
    app.router.add_get("/webapp", index)
    app.router.add_get("/api/lesson/{lesson_id}", lesson)
    app.router.add_get("/api/progress", progress)
    app.router.add_post("/api/draft", save_draft)
    app.router.add_post("/api/run", run_code)
    app.router.add_static("/webapp/", STATIC_DIR, show_index=False)
