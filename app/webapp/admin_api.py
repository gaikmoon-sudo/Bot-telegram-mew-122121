"""Telegram-authenticated admin HTTP routes; permissions are enforced centrally."""
from __future__ import annotations

import json
import asyncio
import logging
import mimetypes
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

from aiohttp import web
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import selectinload

from app.audit.models import AuditLog
from app.authorization.admin_service import (
    AdminPolicyError,
    AdminService,
    LastSuperAdminError,
)
from app.authorization.middleware import ADMIN_USER_ID_KEY, AUDIT_RESOURCE_KEY
from app.authorization.models import Permission, Role, RolePermission, UserRole
from app.authorization.permissions import evaluate_permissions
from app.authorization.service import AuthorizationError, RBACService
from app.content.admin_service import ContentAdminService, ContentConflict, ContentNotFound
from app.content.models import ContentStatus, Course, Lesson, Module
from app.learning.models import LessonProgress
from app.storage.postgres import store
from infrastructure.redis.connection import ping_redis
from app.webapp.telegram_auth import telegram_user_id
from config import settings
from infrastructure.database.session import session_factory

ROOT = Path(__file__).resolve().parents[2]
ADMIN_STATIC = Path(__file__).resolve().parent / "static" / "admin"
UPLOAD_DIR = Path(os.getenv("CONTENT_UPLOAD_DIR", str(ROOT / "data" / "content_uploads"))).resolve()
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
CONTENT_STORAGE_BACKEND = settings.content_storage_backend
logger = logging.getLogger(__name__)
_APP_STORAGE_CLIENT = None
PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100


def _app_storage_client():
    """Return the official Replit App Storage client, initialized on first use."""
    global _APP_STORAGE_CLIENT
    if _APP_STORAGE_CLIENT is None:
        try:
            from replit.object_storage import Client
        except ImportError as exc:
            raise RuntimeError(
                "Replit App Storage support is unavailable; install project requirements."
            ) from exc
        bucket_id = settings.app_storage_bucket_id or None
        _APP_STORAGE_CLIENT = Client(bucket_id=bucket_id)
    return _APP_STORAGE_CLIENT


async def _discard_uploaded_asset(asset: dict, path: Path) -> None:
    """Remove an upload when its database transaction fails."""
    if CONTENT_STORAGE_BACKEND == "replit":
        try:
            await asyncio.to_thread(
                _app_storage_client().delete,
                asset["storage_name"],
                ignore_not_found=True,
            )
        except Exception:
            logger.exception("Could not clean up failed Replit App Storage upload")
    else:
        path.unlink(missing_ok=True)


@web.middleware
async def telegram_admin_identity_middleware(request: web.Request, handler):
    """Populate only the verified Telegram ID consumed by the RBAC boundary."""
    if request.path == "/api/admin" or request.path.startswith("/api/admin/"):
        actor_id = telegram_user_id(request)
        if actor_id is not None:
            request[ADMIN_USER_ID_KEY] = actor_id
    return await handler(request)


def _set_resource(request: web.Request, resource_key: object) -> None:
    value = str(resource_key)
    if len(value) <= 100 and re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        request[AUDIT_RESOURCE_KEY] = value


def _db_factory():
    if session_factory is None:
        raise web.HTTPServiceUnavailable(text="Database session is not configured")
    return session_factory


def _raise_admin_error(exc: Exception) -> None:
    if isinstance(exc, LastSuperAdminError):
        raise web.HTTPConflict(text=str(exc)) from exc
    if isinstance(exc, (AdminPolicyError, AuthorizationError)):
        raise web.HTTPForbidden(text=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise web.HTTPBadRequest(text=str(exc)) from exc
    raise web.HTTPInternalServerError(text="تعذر تنفيذ عملية الإدارة") from exc


async def _json_body(request: web.Request) -> dict:
    try:
        value = await request.json()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON body")
    if not isinstance(value, dict):
        raise web.HTTPBadRequest(text="Expected a JSON object")
    return value


def _public_data(value):
    """Remove internal storage locators before returning content metadata."""
    if isinstance(value, dict):
        return {key: _public_data(item) for key, item in value.items() if key != "storage_name"}
    if isinstance(value, list):
        return [_public_data(item) for item in value]
    return value


def _pagination(request: web.Request) -> tuple[int, int, str, str]:
    try:
        page = int(request.query.get("page", "1"))
        page_size = int(request.query.get("page_size", str(PAGE_SIZE_DEFAULT)))
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid pagination values")
    if page < 1 or page_size < 1:
        raise web.HTTPBadRequest(text="Pagination values must be positive")
    return page, min(page_size, PAGE_SIZE_MAX), request.query.get("q", "")[:120].strip(), request.query.get("status", "")[:24].strip()


async def _content(request: web.Request, operation):
    factory = _db_factory()
    try:
        async with factory() as session:
            async with session.begin():
                result = await operation(ContentAdminService(session))
        return web.json_response(_public_data(result))
    except ContentNotFound as exc:
        raise web.HTTPNotFound(text=str(exc))
    except ContentConflict as exc:
        raise web.HTTPConflict(text=str(exc))
    except (TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(text=str(exc))
    except IntegrityError:
        raise web.HTTPConflict(text="تعذر الحفظ بسبب تعارض في البيانات")


async def admin_shell(_request: web.Request) -> web.StreamResponse:
    return web.FileResponse(ADMIN_STATIC / "index.html")


HOLOGRAPHIC_STATIC = ADMIN_STATIC / "holographic"


async def holographic_shell(_request: web.Request) -> web.StreamResponse:
    """Serve the React navigator; every data mutation remains API-protected."""
    return web.FileResponse(HOLOGRAPHIC_STATIC / "index.html")


async def admin_session(request: web.Request) -> web.Response:
    actor_id = request.get(ADMIN_USER_ID_KEY)
    if actor_id is None:
        raise web.HTTPUnauthorized(text="Telegram authentication required")
    async with _db_factory()() as session:
        service = RBACService(session)
        role_grants, overrides = await service.permissions_for(actor_id)
        all_permissions = (await session.scalars(select(Permission))).all()
        allowed = sorted(
            f"{item.resource}.{item.action}"
            for item in all_permissions
            if evaluate_permissions(
                f"{item.resource}.{item.action}",
                role_grants=role_grants,
                user_overrides=overrides,
            )
        )
        roles = (await session.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == actor_id)
            .where(
                (UserRole.expires_at.is_(None))
                | (UserRole.expires_at > datetime.now(timezone.utc).replace(tzinfo=None))
            )
            .order_by(Role.name)
        )).all()
    return web.json_response({"user_id": actor_id, "roles": list(roles), "permissions": allowed})


async def dashboard(request: web.Request) -> web.Response:
    async def service_health() -> dict[str, bool]:
        try:
            database = bool(await asyncio.to_thread(store.ping))
        except Exception:
            database = False
        try:
            redis = bool(await ping_redis())
        except Exception:
            redis = False
        return {"database": database, "redis": redis, "telegram": bool(settings.bot_token)}

    async def query(service):
        session = service.session
        courses = int(await session.scalar(select(func.count(Course.id))) or 0)
        modules = int(await session.scalar(select(func.count(Module.id))) or 0)
        lessons = int(await session.scalar(select(func.count(Lesson.id))) or 0)
        published = int(await session.scalar(select(func.count(Lesson.id)).where(Lesson.status == ContentStatus.PUBLISHED)) or 0)
        try:
            stats = (await session.execute(
                select(Lesson.title, func.count(LessonProgress.id), func.count(LessonProgress.completed_at))
                .join(LessonProgress, LessonProgress.lesson_id == Lesson.id, isouter=True)
                .group_by(Lesson.id, Lesson.title)
                .order_by(func.count(LessonProgress.id).desc())
                .limit(5)
            )).all()
        except (OperationalError, ProgrammingError):
            # Some installations intentionally deploy the content-only schema.
            # Keep the dashboard healthy and show an empty analytics state.
            await session.rollback()
            stats = []
        return {"courses": courses, "modules": modules, "lessons": lessons, "published_lessons": published,
                "lesson_stats": [{"title": title, "views": int(views or 0), "completed": int(completed or 0)} for title, views, completed in stats],
                "service_health": await service_health()}
    return await _content(request, query)


async def learning_paths(request: web.Request) -> web.Response:
    page, page_size, q, _ = _pagination(request)
    return await _content(request, lambda service: service.list_learning_paths(q=q, page=page, page_size=page_size))


async def create_learning_path(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.create_learning_path(payload))
    _set_resource(request, json.loads(result.text).get("id", "learning_paths"))
    return result


async def update_learning_path(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.update_learning_path(request.match_info["path_id"], payload))
    _set_resource(request, request.match_info["path_id"])
    return result


async def delete_learning_path(request: web.Request) -> web.Response:
    result = await _content(request, lambda service: service.delete_learning_path(request.match_info["path_id"]))
    _set_resource(request, request.match_info["path_id"])
    return result


async def validate_path(request: web.Request) -> web.Response:
    return await _content(request, lambda service: service.validate_path(request.match_info["path_id"]))


async def publish_path(request: web.Request) -> web.Response:
    return await _content(request, lambda service: service.publish_path(request.match_info["path_id"]))


async def list_courses(request: web.Request) -> web.Response:
    page, page_size, q, status = _pagination(request)
    return await _content(request, lambda service: service.list_courses(q=q, status=status, page=page, page_size=page_size))


async def create_course(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.create_course(payload))
    _set_resource(request, json.loads(result.text).get("id", "courses"))
    return result


async def update_course(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.update_course(request.match_info["course_id"], payload))
    _set_resource(request, request.match_info["course_id"])
    return result


async def course_relationships(request: web.Request) -> web.Response:
    return await _content(request, lambda service: service.course_relationships(request.match_info["course_id"]))


async def set_course_relationships(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    values = payload.get("prerequisite_ids", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise web.HTTPBadRequest(text="prerequisite_ids must be an array")
    return await _content(request, lambda service: service.set_course_relationships(request.match_info["course_id"], values))


async def copy_course(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    if not isinstance(payload.get("title"), str):
        raise web.HTTPBadRequest(text="title is required")
    return await _content(request, lambda service: service.copy_course(request.match_info["course_id"], payload["title"]))


async def delete_course(request: web.Request) -> web.Response:
    result = await _content(request, lambda service: service.delete_course(request.match_info["course_id"]))
    _set_resource(request, result.text if hasattr(result, "text") else request.match_info["course_id"])
    return web.json_response({"ok": True})


async def order_courses(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    if payload.get("item_id"):
        operation = lambda service: service.move(entity="courses", parent_id=str(payload.get("parent_id", "")), item_id=str(payload["item_id"]), direction=str(payload.get("direction", "")))
    else:
        operation = lambda service: service.reorder(entity="courses", parent_id=str(payload.get("parent_id", "")), ordered_ids=payload.get("ordered_ids", []))
    result = await _content(request, operation)
    _set_resource(request, payload.get("item_id") or payload.get("parent_id", "learning_paths"))
    return web.json_response({"ordered_ids": json.loads(result.text)})


async def list_modules(request: web.Request) -> web.Response:
    page, page_size, q, status = _pagination(request)
    course_id = request.query.get("course_id", "")[:64]
    return await _content(request, lambda service: service.list_modules(course_id=course_id, q=q, status=status, page=page, page_size=page_size))


async def create_module(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.create_module(payload))
    _set_resource(request, json.loads(result.text).get("id", "modules"))
    return result


async def update_module(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.update_module(request.match_info["module_id"], payload))
    _set_resource(request, request.match_info["module_id"])
    return result


async def delete_module(request: web.Request) -> web.Response:
    await _content(request, lambda service: service.delete_module(request.match_info["module_id"]))
    _set_resource(request, request.match_info["module_id"])
    return web.json_response({"ok": True})


async def order_modules(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    if payload.get("item_id"):
        operation = lambda service: service.move(entity="modules", parent_id=str(payload.get("parent_id", "")), item_id=str(payload["item_id"]), direction=str(payload.get("direction", "")))
    else:
        operation = lambda service: service.reorder(entity="modules", parent_id=str(payload.get("parent_id", "")), ordered_ids=payload.get("ordered_ids", []))
    result = await _content(request, operation)
    _set_resource(request, payload.get("item_id") or payload.get("parent_id", "modules"))
    return web.json_response({"ordered_ids": json.loads(result.text)})


async def list_lessons(request: web.Request) -> web.Response:
    page, page_size, q, status = _pagination(request)
    module_id = request.query.get("module_id", "")[:64]
    course_id = request.query.get("course_id", "")[:64]
    return await _content(request, lambda service: service.list_lessons(q=q, module_id=module_id, course_id=course_id, status=status, page=page, page_size=page_size))


def _sync_runtime_lesson_sync(data: dict, actor_user_id: int) -> None:
    """Mirror committed Admin Panel lesson data into the Telegram runtime catalog."""
    from app.storage.postgres import store
    store.sync_admin_lesson(
        data["id"], title=data["title"], theory=data.get("content_body", ""),
        summary=data.get("summary") or "", status=data.get("status", "DRAFT"),
        created_by=int(actor_user_id or 0),
    )
    from app.bot.routers.start import refresh_runtime_lessons
    refresh_runtime_lessons()


async def _sync_runtime_lesson(data: dict, actor_user_id: int) -> None:
    await asyncio.to_thread(_sync_runtime_lesson_sync, data, actor_user_id)


def _delete_runtime_lesson_sync(lesson_id: str) -> None:
    """Remove a deleted Admin Panel lesson from the Telegram runtime catalog."""
    from app.storage.postgres import store
    store.delete_admin_lesson(lesson_id)
    from app.bot.routers.start import refresh_runtime_lessons
    refresh_runtime_lessons()


async def _delete_runtime_lesson(lesson_id: str) -> None:
    await asyncio.to_thread(_delete_runtime_lesson_sync, lesson_id)


async def create_lesson(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.create_lesson(payload))
    data = json.loads(result.text)
    _set_resource(request, data.get("id", "lessons"))
    await _sync_runtime_lesson(data, request.get(ADMIN_USER_ID_KEY) or 0)
    return result


async def get_lesson(request: web.Request) -> web.Response:
    return await _content(request, lambda service: service.get_lesson(request.match_info["lesson_id"]))


async def update_lesson(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    result = await _content(request, lambda service: service.update_lesson(request.match_info["lesson_id"], payload))
    _set_resource(request, request.match_info["lesson_id"])
    data = json.loads(result.text)
    await _sync_runtime_lesson(data, request.get(ADMIN_USER_ID_KEY) or 0)
    return result


async def delete_lesson(request: web.Request) -> web.Response:
    lesson_id = request.match_info["lesson_id"]
    await _content(request, lambda service: service.delete_lesson(lesson_id))
    _set_resource(request, lesson_id)
    await _delete_runtime_lesson(lesson_id)
    return web.json_response({"ok": True})


async def preview_lesson(request: web.Request) -> web.Response:
    return await _content(request, lambda service: service.get_lesson(request.match_info["lesson_id"]))


async def lesson_versions(request: web.Request) -> web.Response:
    return await _content(request, lambda service: service.list_lesson_versions(request.match_info["lesson_id"]))


async def order_lessons(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    if payload.get("item_id"):
        operation = lambda service: service.move(entity="lessons", parent_id=str(payload.get("parent_id", "")), item_id=str(payload["item_id"]), direction=str(payload.get("direction", "")))
    else:
        operation = lambda service: service.reorder(entity="lessons", parent_id=str(payload.get("parent_id", "")), ordered_ids=payload.get("ordered_ids", []))
    result = await _content(request, operation)
    _set_resource(request, payload.get("item_id") or payload.get("parent_id", "lessons"))
    return web.json_response({"ordered_ids": json.loads(result.text)})


def _safe_filename(raw: str) -> str:
    name = Path(raw or "upload").name
    name = re.sub(r"[^\w.() -]+", "_", name, flags=re.UNICODE).strip(" .")[:160]
    return name or "upload"


def _validate_upload(filename: str, content_type: str, *, image_only: bool) -> str:
    suffix = Path(filename).suffix.lower()
    allowed = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if suffix not in allowed or content_type not in {allowed[suffix], "application/octet-stream"}:
        raise web.HTTPUnsupportedMediaType(text="نوع الملف غير مسموح")
    if image_only and not suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        raise web.HTTPUnsupportedMediaType(text="يسمح برفع PNG/JPEG/WebP للصور فقط")
    return allowed[suffix]


def _valid_file_signature(path: Path, mime: str) -> bool:
    with path.open("rb") as stream:
        head = stream.read(16)
    if mime == "application/pdf":
        return head.startswith(b"%PDF-")
    if mime == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if mime == "image/webp":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    office_parts = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word/document.xml",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt/presentation.xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xl/workbook.xml",
    }
    if mime in office_parts:
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                return "[Content_Types].xml" in names and office_parts[mime] in names
        except (OSError, zipfile.BadZipFile):
            return False
    if mime in {"text/plain", "text/markdown"}:
        try:
            with path.open("rb") as stream:
                stream.read().decode("utf-8-sig")
            return True
        except (OSError, UnicodeDecodeError):
            return False
    return bool(head)


async def _save_upload(request: web.Request, *, image_only: bool) -> tuple[dict, Path]:
    if not request.content_type.startswith("multipart/"):
        raise web.HTTPBadRequest(text="Expected multipart file upload")
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file" or not field.filename:
        raise web.HTTPBadRequest(text="Missing file field")
    filename = _safe_filename(field.filename)
    mime = _validate_upload(filename, field.headers.get("Content-Type", "application/octet-stream"), image_only=image_only)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    asset_id = str(uuid4())
    suffix = Path(filename).suffix.lower()
    path = (UPLOAD_DIR / f"{asset_id}{suffix}").resolve()
    if path.parent != UPLOAD_DIR:
        raise web.HTTPBadRequest(text="Invalid file path")
    size = 0
    try:
        with path.open("xb") as output:
            while True:
                chunk = await field.read_chunk(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise web.HTTPRequestEntityTooLarge(max_size=MAX_UPLOAD_BYTES, actual_size=size)
                output.write(chunk)
        if size == 0 or not _valid_file_signature(path, mime):
            raise web.HTTPBadRequest(text="File content does not match its declared type")
        if CONTENT_STORAGE_BACKEND == "replit":
            await asyncio.to_thread(
                _app_storage_client().upload_from_filename,
                path.name,
                str(path),
            )
            path.unlink(missing_ok=True)
        elif CONTENT_STORAGE_BACKEND != "local":
            raise RuntimeError("Unsupported CONTENT_STORAGE_BACKEND")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return ({"id": asset_id, "filename": filename, "content_type": mime, "size": size, "storage_name": path.name, "created_at": datetime.now(timezone.utc).isoformat()}, path)


async def list_lesson_files(request: web.Request) -> web.Response:
    lesson_id = request.match_info["lesson_id"]
    category = request.match_info.get("category", "assets")
    return await _content(request, lambda service: service.list_assets(lesson_id, category=category))


async def upload_lesson_file(request: web.Request) -> web.Response:
    image_only = request.path.endswith("/images")
    asset, path = await _save_upload(request, image_only=image_only)
    category = "images" if image_only else "assets"
    try:
        result = await _content(request, lambda service: service.add_asset(request.match_info["lesson_id"], asset, category=category))
        if result.status >= 400:
            await _discard_uploaded_asset(asset, path)
            return result
    except Exception:
        await _discard_uploaded_asset(asset, path)
        raise
    _set_resource(request, asset["id"])
    return result


async def delete_lesson_file(request: web.Request) -> web.Response:
    lesson_id, asset_id = request.match_info["lesson_id"], request.match_info["asset_id"]
    category = "images" if request.path.endswith("/images") else "assets"
    result = await _content(request, lambda service: service.delete_asset(lesson_id, asset_id, category=category))
    _set_resource(request, asset_id)
    # Immutable old versions keep their history; the current version no longer
    # references this id, so the protected download route cannot expose it.
    return web.json_response({"ok": True})


async def download_file(request: web.Request) -> web.StreamResponse:
    asset_id = request.match_info["asset_id"]
    try:
        async with _db_factory()() as session:
            async with session.begin():
                found = await ContentAdminService(session).find_asset(asset_id)
    except Exception:
        raise
    if found is None:
        raise web.HTTPNotFound(text="File not found")
    _lesson_id, asset, _category = found
    storage_name = asset.get("storage_name", "")
    if not re.fullmatch(r"[0-9a-f-]{36}\.[a-z0-9]{1,8}", storage_name):
        raise web.HTTPNotFound(text="File not found")
    path = (UPLOAD_DIR / storage_name).resolve()
    if path.parent != UPLOAD_DIR:
        raise web.HTTPNotFound(text="File not found")
    mime = asset.get("content_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    inline = request.query.get("preview") == "1" and (mime == "application/pdf" or mime.startswith("image/"))
    disposition = "inline" if inline else "attachment"
    filename = _safe_filename(asset.get("filename", "download"))
    headers = {
        "Content-Type": mime,
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    if CONTENT_STORAGE_BACKEND == "replit":
        try:
            contents = await asyncio.to_thread(
                _app_storage_client().download_as_bytes,
                storage_name,
            )
        except Exception as exc:
            logger.exception("Replit App Storage download failed")
            raise web.HTTPServiceUnavailable(text="File storage is temporarily unavailable") from exc
        response = web.Response(body=contents, headers=headers)
    elif CONTENT_STORAGE_BACKEND == "local":
        if not path.is_file():
            raise web.HTTPNotFound(text="File not found")
        response = web.FileResponse(path, headers=headers)
    else:
        raise web.HTTPServiceUnavailable(text="File storage is not configured")
    _set_resource(request, asset_id)
    return response


async def add_video_link(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    url = str(payload.get("url", "")).strip()
    parsed = urlparse(url)
    if len(url) > 2048 or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise web.HTTPBadRequest(text="أدخل رابط فيديو HTTPS صالحًا")
    label = str(payload.get("label") or "رابط فيديو").strip()[:120]
    result = await _content(request, lambda service: service.add_video_link(request.match_info["lesson_id"], url, label))
    _set_resource(request, request.match_info["lesson_id"])
    return result


async def delete_video_link(request: web.Request) -> web.Response:
    result = await _content(request, lambda service: service.delete_video_link(request.match_info["lesson_id"], request.match_info["link_id"]))
    _set_resource(request, request.match_info["link_id"])
    return result


async def update_video_link(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    url = str(payload.get("url", "")).strip()
    parsed = urlparse(url)
    if len(url) > 2048 or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise web.HTTPBadRequest(text="أدخل رابط فيديو HTTPS صالحًا")
    label = str(payload.get("label") or "رابط فيديو").strip()[:120]
    result = await _content(request, lambda service: service.update_video_link(
        request.match_info["lesson_id"], request.match_info["link_id"], url, label
    ))
    _set_resource(request, request.match_info["link_id"])
    return result


async def list_admins(request: web.Request) -> web.Response:
    page, page_size, query, _status = _pagination(request)
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        result = await AdminService(session, actor).list_admins(
            page=page, page_size=page_size, query=query
        )
    return web.json_response(result)


async def create_admin(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    try:
        target_id = int(payload.get("telegram_id", 0))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text="Invalid Telegram user id")
    role_name = payload.get("role_name")
    permissions = payload.get("permissions", [])
    if target_id <= 0 or not isinstance(role_name, str):
        raise web.HTTPBadRequest(text="telegram_id and role_name are required")
    if not isinstance(permissions, list) or any(not isinstance(item, str) for item in permissions):
        raise web.HTTPBadRequest(text="permissions must be an array of permission keys")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                result = await AdminService(session, actor).create_admin(
                    target_user_id=target_id,
                    role_name=role_name,
                    extra_permissions=permissions,
                )
        except (LastSuperAdminError, AdminPolicyError, AuthorizationError, ValueError) as exc:
            _raise_admin_error(exc)
        except IntegrityError as exc:
            raise web.HTTPConflict(text="تعارض في إسنادات Admin") from exc
    _set_resource(request, target_id)
    return web.json_response(result, status=201)


async def update_admin_role(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    role_name = payload.get("role_name")
    if not isinstance(role_name, str) or not role_name.strip():
        raise web.HTTPBadRequest(text="role_name is required")
    try:
        target_id = int(request.match_info["telegram_id"])
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid Telegram user id")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                assignment = await AdminService(session, actor).set_admin_role(
                    target_user_id=target_id,
                    role_name=role_name,
                )
                role = await session.get(Role, assignment.role_id)
                result = {"telegram_id": target_id, "role": role.name}
        except (LastSuperAdminError, AdminPolicyError, AuthorizationError, ValueError) as exc:
            _raise_admin_error(exc)
        except IntegrityError as exc:
            raise web.HTTPConflict(text="تعارض في إسناد Role") from exc
    _set_resource(request, target_id)
    return web.json_response(result)


async def update_admin_status(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    if not isinstance(payload.get("enabled"), bool):
        raise web.HTTPBadRequest(text="enabled must be a boolean")
    try:
        target_id = int(request.match_info["telegram_id"])
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid Telegram user id")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                account = await AdminService(session, actor).set_admin_enabled(
                    target_user_id=target_id,
                    enabled=payload["enabled"],
                )
                result = {"telegram_id": target_id, "enabled": account.is_enabled}
        except (LastSuperAdminError, AdminPolicyError, AuthorizationError, ValueError) as exc:
            _raise_admin_error(exc)
        except IntegrityError as exc:
            raise web.HTTPConflict(text="تعارض في حالة حساب Admin") from exc
    _set_resource(request, target_id)
    return web.json_response(result)


async def set_admin_permission(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    if not isinstance(payload.get("permission"), str) or not isinstance(payload.get("granted"), bool):
        raise web.HTTPBadRequest(text="permission and boolean granted are required")
    try:
        target_id = int(request.match_info["telegram_id"])
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid Telegram user id")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                override = await AdminService(session, actor).set_admin_permission(
                    target_user_id=target_id,
                    permission_key=payload["permission"],
                    granted=payload["granted"],
                )
                permission = await session.get(Permission, override.permission_id)
                result = {
                    "telegram_id": target_id,
                    "permission": f"{permission.resource}.{permission.action}",
                    "granted": override.granted,
                }
        except (LastSuperAdminError, AdminPolicyError, AuthorizationError, ValueError) as exc:
            _raise_admin_error(exc)
        except IntegrityError as exc:
            raise web.HTTPConflict(text="تعارض في صلاحية Admin") from exc
    _set_resource(request, target_id)
    return web.json_response(result)


async def list_admin_permissions(request: web.Request) -> web.Response:
    async with _db_factory()() as session:
        permissions = (await session.scalars(
            select(Permission)
            .where(~((Permission.resource == "*") & (Permission.action == "*")))
            .order_by(Permission.resource, Permission.action)
        )).all()
    return web.json_response({"items": [
        {"key": f"{item.resource}.{item.action}", "description": item.description}
        for item in permissions
    ]})


async def admin_audit(request: web.Request) -> web.Response:
    try:
        target_id = int(request.match_info["telegram_id"])
        limit = min(200, max(1, int(request.query.get("limit", "50"))))
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid user id or limit")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            rows = await AdminService(session, actor).list_admin_audit(
                target_admin_id=target_id,
                limit=limit,
            )
        except ValueError as exc:
            raise web.HTTPNotFound(text=str(exc)) from exc
    return web.json_response({"items": [{
        "id": str(row.id),
        "actor_user_id": row.actor_user_id,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id) if row.resource_id else None,
        "resource_key": row.resource_key,
        "outcome": row.outcome.value,
        "occurred_at": row.occurred_at.isoformat(),
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "details": row.details,
    } for row in rows]})


async def list_roles(request: web.Request) -> web.Response:
    async with _db_factory()() as session:
        roles = (await session.scalars(
            select(Role).options(selectinload(Role.role_permissions).selectinload(RolePermission.permission)).order_by(Role.name)
        )).all()
        payload = [{
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "permissions": sorted(f"{rp.permission.resource}.{rp.permission.action}" for rp in role.role_permissions),
        } for role in roles]
    return web.json_response({"items": payload})


async def create_role(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                role = await AdminService(session, actor).create_role(name=str(payload.get("name", "")), description=payload.get("description"))
                response = {"name": role.name, "description": role.description, "is_system": role.is_system, "permissions": []}
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
        except IntegrityError:
            raise web.HTTPConflict(text="الدور موجود مسبقًا")
    _set_resource(request, response["name"])
    return web.json_response(response, status=201)


async def set_role_permission(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    actor = request[ADMIN_USER_ID_KEY]
    role_name = request.match_info["role_name"].upper()
    permission_key = str(payload.get("permission", ""))
    if not isinstance(payload.get("granted"), bool):
        raise web.HTTPBadRequest(text="granted must be a boolean")
    granted = payload["granted"]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                value = await AdminService(session, actor).set_role_permission(role_name=role_name, permission_key=permission_key, granted=granted)
        except (LastSuperAdminError, AdminPolicyError, AuthorizationError, ValueError) as exc:
            _raise_admin_error(exc)
    _set_resource(request, role_name)
    return web.json_response({"role": role_name, "permission": permission_key, "granted": value})


async def assign_user_role(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    try:
        target_id = int(request.match_info["telegram_id"])
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid user id")
    expires_at = None
    if payload.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                raise ValueError
        except ValueError:
            raise web.HTTPBadRequest(text="expires_at must be an ISO-8601 timezone-aware timestamp")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                assignment = await AdminService(session, actor).assign_role(target_user_id=target_id, role_name=str(payload.get("role_name", "")).upper(), expires_at=expires_at)
                response = {"user_id": assignment.user_id, "role_id": str(assignment.role_id), "expires_at": assignment.expires_at.isoformat() if assignment.expires_at else None}
        except (LastSuperAdminError, AdminPolicyError, AuthorizationError, ValueError) as exc:
            _raise_admin_error(exc)
        except IntegrityError:
            raise web.HTTPNotFound(text="المستخدم غير موجود")
    _set_resource(request, target_id)
    return web.json_response(response)


async def set_user_permission(request: web.Request) -> web.Response:
    payload = await _json_body(request)
    try:
        target_id = int(request.match_info["telegram_id"])
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid user id")
    if not isinstance(payload.get("granted"), bool):
        raise web.HTTPBadRequest(text="granted must be a boolean")
    expires_at = None
    if payload.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                raise ValueError
        except ValueError:
            raise web.HTTPBadRequest(text="expires_at must be an ISO-8601 timezone-aware timestamp")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        try:
            async with session.begin():
                override = await AdminService(session, actor).set_user_permission(
                    target_user_id=target_id,
                    permission_key=str(payload.get("permission", "")),
                    granted=payload["granted"],
                    expires_at=expires_at,
                )
                response = {"user_id": override.user_id, "permission_id": str(override.permission_id), "granted": override.granted, "expires_at": override.expires_at.isoformat() if override.expires_at else None}
        except (LastSuperAdminError, AdminPolicyError, AuthorizationError, ValueError) as exc:
            _raise_admin_error(exc)
        except IntegrityError:
            raise web.HTTPNotFound(text="المستخدم غير موجود")
    _set_resource(request, target_id)
    return web.json_response(response)


async def list_audit(request: web.Request) -> web.Response:
    try:
        limit = min(200, max(1, int(request.query.get("limit", "50"))))
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid limit")
    actor = request[ADMIN_USER_ID_KEY]
    async with _db_factory()() as session:
        rows = await AdminService(session, actor).list_audit_events(limit=limit)
        items = [{
            "id": str(row.id),
            "actor_user_id": row.actor_user_id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id) if row.resource_id else None,
            "resource_key": row.resource_key,
            "outcome": row.outcome.value,
            "occurred_at": row.occurred_at.isoformat(),
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "details": row.details,
        } for row in rows]
    return web.json_response({"items": items})


def setup_admin_routes(app: web.Application) -> None:
    """Register the static panel shell and every protected administrative API."""
    app.router.add_get("/admin", admin_shell, name="admin.panel.shell")
    app.router.add_get("/admin/", admin_shell, name="admin.panel.shell-slash")
    app.router.add_static("/admin/assets/", ADMIN_STATIC / "assets", name="admin.panel.assets", show_index=False)
    app.router.add_get("/admin/holographic", holographic_shell, name="admin.holographic.shell")
    app.router.add_get("/admin/holographic/", holographic_shell, name="admin.holographic.shell-slash")
    app.router.add_static("/admin/holographic/assets/", HOLOGRAPHIC_STATIC / "assets", name="admin.holographic.assets", show_index=False)

    routes = [
        ("GET", "/api/admin/session", admin_session, "admin.panel.session"),
        ("GET", "/api/admin/dashboard", dashboard, "admin.dashboard"),
        ("GET", "/api/admin/learning-paths", learning_paths, "admin.learning_paths.list"),
        ("POST", "/api/admin/learning-paths", create_learning_path, "admin.learning_paths.create"),
        ("PATCH", "/api/admin/learning-paths/{path_id}", update_learning_path, "admin.learning_paths.update"),
        ("DELETE", "/api/admin/learning-paths/{path_id}", delete_learning_path, "admin.learning_paths.delete"),
        ("POST", "/api/admin/learning-paths/{path_id}/validate", validate_path, "admin.learning_paths.validate"),
        ("POST", "/api/admin/learning-paths/{path_id}/publish", publish_path, "admin.learning_paths.publish"),
        ("GET", "/api/admin/courses", list_courses, "admin.courses.list"),
        ("POST", "/api/admin/courses", create_course, "admin.courses.create"),
        ("POST", "/api/admin/courses/order", order_courses, "admin.courses.order"),
        ("PATCH", "/api/admin/courses/{course_id}", update_course, "admin.courses.update"),
        ("GET", "/api/admin/courses/{course_id}/relationships", course_relationships, "admin.courses.view"),
        ("PUT", "/api/admin/courses/{course_id}/relationships", set_course_relationships, "admin.courses.relationships.update"),
        ("POST", "/api/admin/courses/{course_id}/copy", copy_course, "admin.courses.copy"),
        ("DELETE", "/api/admin/courses/{course_id}", delete_course, "admin.courses.delete"),
        ("GET", "/api/admin/modules", list_modules, "admin.modules.list"),
        ("POST", "/api/admin/modules", create_module, "admin.modules.create"),
        ("POST", "/api/admin/modules/order", order_modules, "admin.modules.order"),
        ("PATCH", "/api/admin/modules/{module_id}", update_module, "admin.modules.update"),
        ("DELETE", "/api/admin/modules/{module_id}", delete_module, "admin.modules.delete"),
        ("GET", "/api/admin/lessons", list_lessons, "admin.lessons.list"),
        ("POST", "/api/admin/lessons", create_lesson, "admin.lessons.create"),
        ("POST", "/api/admin/lessons/order", order_lessons, "admin.lessons.order"),
        ("GET", "/api/admin/lessons/{lesson_id}/preview", preview_lesson, "admin.lessons.preview"),
        ("GET", "/api/admin/lessons/{lesson_id}/versions", lesson_versions, "admin.lessons.view"),
        ("GET", "/api/admin/lessons/{lesson_id}/files", list_lesson_files, "admin.lessons.files.list"),
        ("POST", "/api/admin/lessons/{lesson_id}/files", upload_lesson_file, "admin.files.upload"),
        ("DELETE", "/api/admin/lessons/{lesson_id}/files/{asset_id}", delete_lesson_file, "admin.files.delete"),
        ("POST", "/api/admin/lessons/{lesson_id}/images", upload_lesson_file, "admin.images.upload"),
        ("DELETE", "/api/admin/lessons/{lesson_id}/images/{asset_id}", delete_lesson_file, "admin.images.delete"),
        ("POST", "/api/admin/lessons/{lesson_id}/videos", add_video_link, "admin.videos.add"),
        ("PATCH", "/api/admin/lessons/{lesson_id}/videos/{link_id}", update_video_link, "admin.videos.manage"),
        ("DELETE", "/api/admin/lessons/{lesson_id}/videos/{link_id}", delete_video_link, "admin.videos.manage"),
        ("GET", "/api/admin/lessons/{lesson_id}", get_lesson, "admin.lessons.detail"),
        ("PATCH", "/api/admin/lessons/{lesson_id}", update_lesson, "admin.lessons.update"),
        ("DELETE", "/api/admin/lessons/{lesson_id}", delete_lesson, "admin.lessons.delete"),
        ("GET", "/api/admin/files/{asset_id}", download_file, "admin.files.download"),
        ("GET", "/api/admin/admins", list_admins, "admin.admins.list"),
        ("POST", "/api/admin/admins", create_admin, "admin.admins.create"),
        ("PATCH", "/api/admin/admins/{telegram_id}/role", update_admin_role, "admin.admins.role"),
        ("PATCH", "/api/admin/admins/{telegram_id}/status", update_admin_status, "admin.admins.status"),
        ("PUT", "/api/admin/admins/{telegram_id}/permissions", set_admin_permission, "admin.admins.permission"),
        ("GET", "/api/admin/admins/{telegram_id}/audit", admin_audit, "admin.admins.audit"),
        ("GET", "/api/admin/permissions", list_admin_permissions, "admin.permissions.list"),
        ("GET", "/api/admin/roles", list_roles, "admin.roles.list"),
        ("POST", "/api/admin/roles", create_role, "admin.roles.create"),
        ("PUT", "/api/admin/roles/{role_name}/permissions", set_role_permission, "admin.roles.permissions"),
        ("POST", "/api/admin/users/{telegram_id}/roles", assign_user_role, "admin.roles.assign"),
        ("PUT", "/api/admin/users/{telegram_id}/permissions", set_user_permission, "admin.roles.manage"),
        ("GET", "/api/admin/audit", list_audit, "admin.audit.list"),
    ]
    for method, path, handler, name in routes:
        app.router.add_route(method, path, handler, name=name)
