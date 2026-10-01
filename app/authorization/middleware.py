"""Central authorization boundaries for Telegram and HTTP admin handlers."""
from __future__ import annotations

import logging
from collections.abc import Mapping

from aiohttp import web
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.audit.models import AuditOutcome
from app.audit.service import AuditService
from app.authorization.service import RBACService
from infrastructure.database.session import session_factory

logger = logging.getLogger(__name__)
ADMIN_USER_ID_KEY = web.RequestKey("admin_user_id", int)
USER_ID_KEY = web.RequestKey("user_id", int)
AUDIT_RESOURCE_KEY = web.RequestKey("audit_resource_key", str)
ADMIN_FSM_PERMISSIONS = {
    "broadcast": "notifications.manage",
    "lesson_title": "lessons.create",
    "lesson_duration": "lessons.create",
    "lesson_objective": "lessons.create",
    "lesson_theory": "lessons.create",
    "lesson_code": "lessons.create",
    "lesson_examples": "lessons.create",
}

TELEGRAM_CALLBACK_PERMISSIONS = {
    "admin:stats": "analytics.view",
    "admin:broadcast": "notifications.manage",
    "admin:add_lesson": "lessons.create",
}
ADMIN_HTTP_ROUTE_PERMISSIONS = {
    "admin.panel.session": "lessons.view",
    "admin.dashboard": "admin.dashboard.view",
    "admin.learning_paths.list": "courses.view",
    "admin.learning_paths.create": "courses.create",
    "admin.learning_paths.update": "courses.edit",
    "admin.learning_paths.delete": "courses.delete",
    "admin.learning_paths.validate": "courses.edit",
    "admin.learning_paths.publish": "courses.edit",
    "admin.users.list": "users.view",
    "admin.users.update": "users.manage",
    "admin.courses.list": "courses.view",
    "admin.courses.detail": "courses.view",
    "admin.courses.create": "courses.create",
    "admin.courses.view": "courses.view",
    "admin.courses.update": "courses.edit",
    "admin.courses.relationships.update": "courses.edit",
    "admin.courses.copy": "courses.create",
    "admin.courses.delete": "courses.delete",
    "admin.courses.order": "content.order",
    "admin.modules.list": "modules.view",
    "admin.modules.create": "modules.create",
    "admin.modules.update": "modules.edit",
    "admin.modules.delete": "modules.delete",
    "admin.modules.order": "content.order",
    "admin.lessons.list": "lessons.view",
    "admin.lessons.detail": "lessons.view",
    "admin.lessons.create": "lessons.create",
    "admin.lessons.update": "lessons.edit",
    "admin.lessons.delete": "lessons.delete",
    "admin.lessons.preview": "lessons.view",
    "admin.lessons.view": "lessons.view",
    "admin.lessons.order": "content.order",
    "admin.lessons.files.list": "files.view",
    "admin.files.upload": "files.upload",
    "admin.files.delete": "files.delete",
    "admin.images.delete": "images.manage",
    "admin.files.download": "files.view",
    "admin.videos.add": "videos.add_link",
    "admin.videos.manage": "videos.manage",
    "admin.images.upload": "images.manage",
    "admin.payments.list": "payments.view",
    "admin.payments.manage": "payments.manage",
    "admin.roles.list": "permissions.manage",
    "admin.roles.create": "permissions.manage",
    "admin.roles.permissions": "permissions.manage",
    "admin.roles.assign": "admins.manage",
    "admin.roles.manage": "permissions.manage",
    "admin.admins.list": "admins.manage",
    "admin.admins.create": "admins.manage",
    "admin.admins.role": "admins.manage",
    "admin.admins.status": "admins.manage",
    "admin.admins.permission": "permissions.manage",
    "admin.admins.audit": "security.logs.view",
    "admin.permissions.list": "permissions.manage",
    "admin.audit.list": "security.logs.view",
    "admin.settings.update": "settings.manage",
}


def _telegram_admin_policy(event, data: Mapping) -> tuple[str, str] | None:
    """Return a permission and safe operation label for an admin event."""
    if isinstance(event, Message):
        text = event.text or event.caption or ""
        command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text else ""
        if command == "/admin":
            return "admin.dashboard.view", "command.admin"
        if command == "/contentadmin":
            return "lessons.view", "command.contentadmin"
        if command == "/broadcast":
            return "notifications.manage", "command.broadcast"
    elif isinstance(event, CallbackQuery):
        callback_data = event.data or ""
        if callback_data.startswith("admin:"):
            permission = TELEGRAM_CALLBACK_PERMISSIONS.get(callback_data, "admins.manage")
            return permission, callback_data[:100]

    return None


async def telegram_admin_policy(event, data: Mapping) -> tuple[str, str] | None:
    """Async wrapper so the FSM state is covered as well as commands/callbacks."""
    direct = _telegram_admin_policy(event, data)
    if direct is not None:
        return direct
    state = data.get("state")
    if state is None:
        return None
    try:
        state_name = await state.get_state()
    except Exception:
        return None
    if not isinstance(state_name, str) or "AdminStates:" not in state_name:
        return None
    suffix = state_name.rsplit("AdminStates:", 1)[-1]
    permission = ADMIN_FSM_PERMISSIONS.get(suffix, "admins.manage")
    return permission, f"state.{suffix[:60]}"


async def _write_access_audit(
    *,
    actor_user_id: int | None,
    permission: str,
    operation: str,
    outcome: AuditOutcome,
    resource_key: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    if session_factory is None:
        return
    try:
        async with session_factory() as session:
            AuditService(session).record(
                actor_user_id=actor_user_id,
                action="admin.access",
                resource_type=(permission.split(".", 1)[0] if "." in permission else "admin"),
                resource_key=resource_key,
                outcome=outcome,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"permission": permission, "operation": operation},
            )
            await session.commit()
    except Exception:
        # Logging failure must not reveal request data or open an authorization path.
        logger.warning("Could not persist admin audit event", exc_info=True)


class AdminAuthorizationMiddleware(BaseMiddleware):
    """Guard every existing/new Telegram admin command, callback and FSM step."""

    async def __call__(self, handler, event, data):
        policy = await telegram_admin_policy(event, data)
        if policy is None:
            return await handler(event, data)
        permission, operation = policy
        actor = getattr(getattr(event, "from_user", None), "id", None)
        allowed = False
        if session_factory is not None and isinstance(actor, int):
            try:
                async with session_factory() as session:
                    allowed = await RBACService(session).has_permission(actor, permission)
            except Exception:
                logger.warning("Admin authorization lookup failed closed", exc_info=True)
        if not allowed:
            await _write_access_audit(
                actor_user_id=actor,
                permission=permission,
                operation=operation,
                outcome=AuditOutcome.FAILURE,
            )
            if isinstance(event, CallbackQuery):
                await event.answer("غير مصرح.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ غير مصرح.")
            return None
        try:
            result = await handler(event, data)
        except Exception:
            await _write_access_audit(
                actor_user_id=actor,
                permission=permission,
                operation=operation,
                outcome=AuditOutcome.FAILURE,
            )
            raise
        await _write_access_audit(
            actor_user_id=actor,
            permission=permission,
            operation=operation,
            outcome=AuditOutcome.SUCCESS,
        )
        return result


@web.middleware
async def admin_http_middleware(request: web.Request, handler):
    """Protect /admin and /api/admin routes; unregistered routes are denied."""
    path = request.path
    if not (path == "/admin" or path.startswith("/admin/") or path == "/api/admin" or path.startswith("/api/admin/")):
        return await handler(request)

    route_name = request.match_info.route.name
    # The shell carries no privileged data. Telegram initData is available only
    # after JavaScript loads; every JSON and file endpoint remains protected.
    if route_name in {"admin.panel.shell", "admin.panel.shell-slash", "admin.panel.assets", "admin.holographic.shell", "admin.holographic.shell-slash", "admin.holographic.assets"}:
        return await handler(request)
    permission = ADMIN_HTTP_ROUTE_PERMISSIONS.get(route_name)
    actor = request.get(ADMIN_USER_ID_KEY, request.get(USER_ID_KEY))
    try:
        actor_id = int(actor) if actor is not None else None
    except (TypeError, ValueError):
        actor_id = None
    allowed = False
    if permission and actor_id and session_factory is not None:
        try:
            async with session_factory() as session:
                allowed = await RBACService(session).has_permission(actor_id, permission)
        except Exception:
            logger.warning("HTTP admin authorization lookup failed closed", exc_info=True)

    peer_ip = request.remote
    user_agent = request.headers.get("User-Agent")
    operation = route_name[:100] if route_name else "unregistered.admin.route"
    resource_key = request.get(AUDIT_RESOURCE_KEY)
    if resource_key is None:
        for key in ("course_id", "module_id", "lesson_id", "asset_id", "link_id", "telegram_id", "role_name"):
            candidate = request.match_info.get(key)
            if candidate and len(candidate) <= 100 and all(char.isalnum() or char in "_.:-" for char in candidate):
                resource_key = candidate
                break
    if not allowed:
        await _write_access_audit(
            actor_user_id=actor_id,
            permission=permission or "unregistered",
            operation=operation,
            outcome=AuditOutcome.FAILURE,
            resource_key=resource_key,
            ip_address=peer_ip,
            user_agent=user_agent,
        )
        if actor_id is None:
            raise web.HTTPUnauthorized(text="Authentication required")
        raise web.HTTPForbidden(text="Permission denied")

    try:
        response = await handler(request)
    except web.HTTPException as exc:
        outcome = AuditOutcome.FAILURE if exc.status >= 400 else AuditOutcome.SUCCESS
        await _write_access_audit(
            actor_user_id=actor_id,
            permission=permission,
            operation=operation,
            outcome=outcome,
            resource_key=resource_key,
            ip_address=peer_ip,
            user_agent=user_agent,
        )
        raise
    except Exception:
        await _write_access_audit(
            actor_user_id=actor_id,
            permission=permission,
            operation=operation,
            outcome=AuditOutcome.FAILURE,
            resource_key=resource_key,
            ip_address=peer_ip,
            user_agent=user_agent,
        )
        raise
    await _write_access_audit(
        actor_user_id=actor_id,
        permission=permission,
        operation=operation,
        outcome=AuditOutcome.SUCCESS,
        resource_key=resource_key,
        ip_address=peer_ip,
        user_agent=user_agent,
    )
    return response
