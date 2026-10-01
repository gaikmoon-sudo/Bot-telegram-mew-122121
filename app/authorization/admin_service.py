"""Permission-checked administrative service operations (no UI)."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import re
from typing import Any, Callable

from sqlalchemy import String, cast, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditOutcome
from app.audit.service import AuditService
from app.authorization.models import (
    AdminAccount,
    Permission,
    Role,
    RolePermission,
    UserPermission,
    UserRole,
)
from app.authorization.permissions import evaluate_permissions
from app.authorization.service import AuthorizationError, RBACService
from app.identity.models import User
from config import settings


_RESOURCE_TYPES = {
    "assign_role": "user_role",
    "set_user_permission": "user_permission",
    "create_admin": "admin_account",
    "set_admin_role": "admin_account",
    "set_admin_enabled": "admin_account",
    "set_admin_permission": "user_permission",
    "create_role": "roles",
    "create_permission": "permissions",
    "set_role_permission": "role_permissions",
    "list_audit_events": "audit_logs",
    "list_admin_audit": "audit_logs",
    "list_admins": "admin_accounts",
}


class AdminPolicyError(PermissionError):
    """A sensitive administrator operation violates an explicit security rule."""


class LastSuperAdminError(AdminPolicyError):
    """An operation would remove the last active SUPER_ADMIN assignment."""


def requires_permission(permission_key: str):
    """Enforce permission keys at the service boundary, never role names."""
    def decorate(method: Callable[..., Any]):
        @wraps(method)
        async def wrapped(self: "AdminService", *args, **kwargs):
            resource_key = (
                kwargs.get("target_user_id")
                or kwargs.get("role_name")
                or kwargs.get("role_id")
                or kwargs.get("name")
                or kwargs.get("permission_key")
            )
            resource_type = _RESOURCE_TYPES.get(
                method.__name__, "administrative_resource"
            )
            try:
                await RBACService(self.session).require(
                    self.actor_user_id,
                    permission_key,
                )
            except AuthorizationError:
                self._audit(
                    permission_key,
                    method.__name__,
                    AuditOutcome.FAILURE,
                    resource_type=resource_type,
                    resource_key=resource_key,
                )
                raise

            try:
                result = await method(self, *args, **kwargs)
                await self.session.flush()
            except Exception:
                self._audit(
                    permission_key,
                    method.__name__,
                    AuditOutcome.FAILURE,
                    resource_type=resource_type,
                    resource_key=resource_key,
                )
                raise

            self._audit(
                permission_key,
                method.__name__,
                AuditOutcome.SUCCESS,
                resource_type=resource_type,
                resource_key=resource_key,
                resource_id=getattr(result, "id", None),
            )
            await self.session.flush()
            return result

        return wrapped
    return decorate


class AdminService:
    """Initial service layer for role, permission, and audit administration."""

    def __init__(self, session: AsyncSession, actor_user_id: int):
        self.session = session
        self.actor_user_id = actor_user_id

    @staticmethod
    def _primary_owner_id() -> int | None:
        """The first configured admin is the immutable system owner."""
        return settings.admin_ids[0] if settings.admin_ids else None

    def _ensure_not_primary_owner(self, target_user_id: int) -> None:
        if target_user_id == self._primary_owner_id():
            raise AdminPolicyError("لا يمكن تعديل أو تعطيل المالك الرئيسي للنظام")

    def _audit(
        self,
        permission: str,
        operation: str,
        outcome: AuditOutcome,
        *,
        resource_type: str,
        resource_key: int | str | None = None,
        resource_id=None,
    ) -> None:
        AuditService(self.session).record(
            actor_user_id=self.actor_user_id,
            action=f"admin.{operation}",
            resource_type=resource_type,
            resource_id=resource_id,
            resource_key=(str(resource_key) if resource_key is not None else None),
            outcome=outcome,
            details={"permission": permission, "operation": operation},
        )

    @requires_permission("admins.manage")
    async def assign_role(
        self,
        *,
        target_user_id: int,
        role_name: str,
        expires_at: datetime | None = None,
    ) -> UserRole:
        if target_user_id == self.actor_user_id:
            raise AdminPolicyError("لا يمكن للمشرف إسناد Role إلى حسابه بنفسه")
        role = await self.session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            raise ValueError("Unknown role")
        if role.name == "SUPER_ADMIN":
            await self._active_super_admin_ids(lock=True)
        assignment = await self.session.get(UserRole, (target_user_id, role.id))
        if assignment is None:
            assignment = UserRole(
                user_id=target_user_id,
                role_id=role.id,
                expires_at=expires_at,
            )
            self.session.add(assignment)
        else:
            assignment.expires_at = expires_at
        return assignment

    @requires_permission("permissions.manage")
    async def set_user_permission(
        self,
        *,
        target_user_id: int,
        permission_key: str,
        granted: bool,
        expires_at: datetime | None = None,
    ) -> UserPermission:
        if target_user_id == self.actor_user_id:
            raise AdminPolicyError("لا يمكن للمشرف تغيير صلاحيات حسابه بنفسه")
        if permission_key.strip() == "*.*":
            raise AdminPolicyError("لا يمكن منح wildcard كصلاحية فردية؛ استخدم Role معتمدًا")
        try:
            resource, action = permission_key.split(".", 1)
        except ValueError as exc:
            raise ValueError("Permission keys must use resource.action form") from exc
        permission = await self.session.scalar(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            )
        )
        if permission is None:
            raise ValueError("Unknown permission")
        override = await self.session.get(
            UserPermission,
            (target_user_id, permission.id),
        )
        if override is None:
            override = UserPermission(
                user_id=target_user_id,
                permission_id=permission.id,
                granted=granted,
                expires_at=expires_at,
                assigned_by_user_id=self.actor_user_id,
            )
            self.session.add(override)
        else:
            override.granted = granted
            override.expires_at = expires_at
            override.assigned_by_user_id = self.actor_user_id
        return override

    @requires_permission("permissions.manage")
    async def create_role(
        self,
        *,
        name: str,
        description: str | None = None,
    ) -> Role:
        normalized_name = name.strip().upper()
        if not normalized_name or len(normalized_name) > 100:
            raise ValueError("Role name must be 1 to 100 characters")
        existing_id = await self.session.scalar(
            select(Role.id).where(Role.name == normalized_name)
        )
        if existing_id is not None:
            raise ValueError("Role already exists")
        role = Role(
            name=normalized_name,
            description=description[:2000] if description else None,
            is_system=False,
        )
        self.session.add(role)
        await self.session.flush()
        return role

    @requires_permission("permissions.manage")
    async def create_permission(
        self,
        *,
        resource: str,
        action: str,
        description: str | None = None,
    ) -> Permission:
        normalized_resource = resource.strip().lower()
        normalized_action = action.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", normalized_resource):
            raise ValueError("Invalid permission resource")
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,49}", normalized_action):
            raise ValueError("Invalid permission action")
        existing = await self.session.scalar(
            select(Permission.id).where(
                Permission.resource == normalized_resource,
                Permission.action == normalized_action,
            )
        )
        if existing is not None:
            raise ValueError("Permission already exists")
        permission = Permission(
            resource=normalized_resource,
            action=normalized_action,
            description=description[:2000] if description else None,
        )
        self.session.add(permission)
        await self.session.flush()
        return permission

    @requires_permission("permissions.manage")
    async def set_role_permission(
        self,
        *,
        role_name: str,
        permission_key: str,
        granted: bool,
    ) -> bool:
        try:
            resource, action = permission_key.split(".", 1)
        except ValueError as exc:
            raise ValueError("Permission keys must use resource.action form") from exc
        role = await self.session.scalar(select(Role).where(Role.name == role_name))
        permission = await self.session.scalar(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            )
        )
        if role is None or permission is None:
            raise ValueError("Unknown role or permission")
        if role.name == "SUPER_ADMIN" and permission_key.strip() == "*.*" and not granted:
            raise AdminPolicyError("صلاحية wildcard أساسية ولا يمكن سحبها من دور SUPER_ADMIN")
        if granted and permission_key.strip() == "*.*" and role.name != "SUPER_ADMIN":
            raise AdminPolicyError("صلاحية wildcard محجوزة لدور SUPER_ADMIN")
        if granted:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            member = await self.session.scalar(
                select(UserRole.user_id).where(
                    UserRole.user_id == self.actor_user_id,
                    UserRole.role_id == role.id,
                    or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
                )
            )
            if member is not None and not await RBACService(self.session).has_permission(
                self.actor_user_id, permission_key
            ):
                raise AdminPolicyError("لا يمكن منح صلاحية تزيد وصول المشرف عبر Role مسند إليه")
        association = await self.session.get(
            RolePermission,
            (role.id, permission.id),
        )
        if granted and association is None:
            self.session.add(
                RolePermission(role_id=role.id, permission_id=permission.id)
            )
        elif not granted and association is not None:
            await self.session.delete(association)
        return granted

    @requires_permission("security.logs.view")
    async def list_audit_events(self, *, limit: int = 100) -> list:
        from app.audit.models import AuditLog

        bounded_limit = max(1, min(int(limit), 500))
        result = await self.session.scalars(
            select(AuditLog)
            .order_by(AuditLog.occurred_at.desc())
            .limit(bounded_limit)
        )
        return list(result)

    async def _admin_record_exists(self, user_id: int) -> bool:
        ids = union(
            select(UserRole.user_id.label("user_id")),
            select(UserPermission.user_id.label("user_id")),
            select(AdminAccount.user_id.label("user_id")),
        ).subquery()
        return await self.session.scalar(
            select(ids.c.user_id).where(ids.c.user_id == user_id).limit(1)
        ) is not None

    async def _active_super_admin_ids(self, *, lock: bool = False) -> list[int]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = (
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .join(User, User.telegram_id == UserRole.user_id)
            .outerjoin(AdminAccount, AdminAccount.user_id == UserRole.user_id)
            .where(
                Role.name == "SUPER_ADMIN",
                User.is_active.is_(True),
                or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
                or_(AdminAccount.user_id.is_(None), AdminAccount.is_enabled.is_(True)),
            )
            .order_by(UserRole.user_id)
        )
        if lock:
            query = query.with_for_update(of=Role)
        return list((await self.session.scalars(query)).all())

    async def _upsert_user_override(
        self, *, target_user_id: int, permission_key: str, granted: bool
    ) -> UserPermission:
        if permission_key.strip() == "*.*":
            raise AdminPolicyError("لا يمكن منح wildcard كصلاحية فردية؛ استخدم Role معتمدًا")
        try:
            resource, action = permission_key.split(".", 1)
        except ValueError as exc:
            raise ValueError("Permission keys must use resource.action form") from exc
        permission = await self.session.scalar(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            )
        )
        if permission is None:
            raise ValueError("Unknown permission")
        override = await self.session.get(UserPermission, (target_user_id, permission.id))
        if override is None:
            override = UserPermission(
                user_id=target_user_id,
                permission_id=permission.id,
                granted=granted,
                assigned_by_user_id=self.actor_user_id,
            )
            self.session.add(override)
        else:
            override.granted = granted
            override.expires_at = None
            override.assigned_by_user_id = self.actor_user_id
        return override

    @requires_permission("admins.manage")
    async def list_admins(
        self, *, page: int = 1, page_size: int = 20, query: str = ""
    ) -> dict:
        """Return paginated admin identities, effective permissions and activity."""
        from app.audit.models import AuditLog

        bounded_page = max(1, int(page))
        bounded_size = min(100, max(1, int(page_size)))
        admin_ids = union(
            select(UserRole.user_id.label("user_id")),
            select(UserPermission.user_id.label("user_id")),
            select(AdminAccount.user_id.label("user_id")),
        ).subquery()
        base = (
            select(
                User.telegram_id,
                User.username,
                User.is_active,
                AdminAccount.is_enabled,
                AdminAccount.disabled_at,
            )
            .join(admin_ids, admin_ids.c.user_id == User.telegram_id)
            .outerjoin(AdminAccount, AdminAccount.user_id == User.telegram_id)
            .where(User.telegram_id.is_not(None))
        )
        needle = query.strip()[:120]
        if needle:
            clauses = [User.username.ilike(f"%{needle}%")]
            if needle.isdigit():
                clauses.append(cast(User.telegram_id, String).like(f"%{needle}%"))
            base = base.where(or_(*clauses))
        total = int(await self.session.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        ) or 0)
        rows = (await self.session.execute(
            base.order_by(User.telegram_id).offset((bounded_page - 1) * bounded_size).limit(bounded_size)
        )).all()
        user_ids = [int(row.telegram_id) for row in rows]
        if not user_ids:
            return {"items": [], "page": bounded_page, "page_size": bounded_size, "total": total, "pages": (total + bounded_size - 1) // bounded_size}

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        role_rows = (await self.session.execute(
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id.in_(user_ids),
                or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
            )
            .order_by(Role.name)
        )).all()
        role_names: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
        for user_id, role_name in role_rows:
            role_names[int(user_id)].append(role_name)

        grant_rows = (await self.session.execute(
            select(UserRole.user_id, Permission.resource, Permission.action)
            .join(RolePermission, RolePermission.role_id == UserRole.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                UserRole.user_id.in_(user_ids),
                or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
            )
        )).all()
        grants: dict[int, set[str]] = {user_id: set() for user_id in user_ids}
        for user_id, resource, action in grant_rows:
            grants[int(user_id)].add(f"{resource}.{action}")

        override_rows = (await self.session.execute(
            select(UserPermission.user_id, Permission.resource, Permission.action, UserPermission.granted)
            .join(Permission, Permission.id == UserPermission.permission_id)
            .where(
                UserPermission.user_id.in_(user_ids),
                or_(UserPermission.expires_at.is_(None), UserPermission.expires_at > now),
            )
        )).all()
        overrides: dict[int, dict[str, bool]] = {user_id: {} for user_id in user_ids}
        override_items: dict[int, list[dict[str, object]]] = {user_id: [] for user_id in user_ids}
        for user_id, resource, action, granted in override_rows:
            user_id = int(user_id)
            key = f"{resource}.{action}"
            overrides[user_id][key] = bool(granted)
            override_items[user_id].append({"permission": key, "granted": bool(granted)})

        catalog = (await self.session.execute(select(Permission.resource, Permission.action))).all()
        last_activity_rows = (await self.session.execute(
            select(AuditLog.actor_user_id, func.max(AuditLog.occurred_at))
            .where(AuditLog.actor_user_id.in_(user_ids))
            .group_by(AuditLog.actor_user_id)
        )).all()
        last_activity = {int(user_id): occurred_at for user_id, occurred_at in last_activity_rows if user_id is not None}

        items = []
        for row in rows:
            user_id = int(row.telegram_id)
            enabled = bool(row.is_active) and row.is_enabled is not False
            effective = sorted(
                f"{resource}.{action}"
                for resource, action in catalog
                if evaluate_permissions(
                    f"{resource}.{action}",
                    role_grants=grants[user_id],
                    user_overrides=overrides[user_id],
                )
            )
            activity = last_activity.get(user_id)
            items.append({
                "telegram_id": user_id,
                "username": row.username,
                "enabled": enabled,
                "disabled_at": row.disabled_at.isoformat() if row.disabled_at else None,
                "roles": role_names[user_id],
                "permissions": effective,
                "overrides": sorted(override_items[user_id], key=lambda item: str(item["permission"])),
                "last_activity": activity.isoformat() if activity else None,
            })
        return {
            "items": items,
            "page": bounded_page,
            "page_size": bounded_size,
            "total": total,
            "pages": (total + bounded_size - 1) // bounded_size,
        }

    @requires_permission("admins.manage")
    async def create_admin(
        self,
        *,
        target_user_id: int,
        role_name: str,
        extra_permissions: list[str] | None = None,
    ) -> dict:
        self._ensure_not_primary_owner(target_user_id)
        if target_user_id == self.actor_user_id:
            raise AdminPolicyError("لا يمكن للمشرف إنشاء صلاحيات لحسابه بنفسه")
        await RBACService(self.session).require(self.actor_user_id, "permissions.manage")
        user = await self.session.scalar(
            select(User).where(User.telegram_id == target_user_id).with_for_update()
        )
        if user is None:
            raise ValueError("المستخدم غير موجود؛ يمكن تعيين مستخدم Telegram مسجل فقط")
        if not user.is_active:
            raise AdminPolicyError("لا يمكن منح الإدارة لحساب مستخدم معطّل")
        if await self._admin_record_exists(target_user_id):
            raise AdminPolicyError("المستخدم لديه إسناد أو سجل Admin بالفعل")
        role = await self.session.scalar(select(Role).where(Role.name == role_name.strip().upper()))
        if role is None:
            raise ValueError("Unknown role")
        if role.name == "SUPER_ADMIN":
            await self._active_super_admin_ids(lock=True)
        permissions = list(dict.fromkeys((extra_permissions or [])))
        if len(permissions) > 100:
            raise ValueError("Too many additional permissions")
        self.session.add(UserRole(user_id=target_user_id, role_id=role.id))
        self.session.add(AdminAccount(user_id=target_user_id, is_enabled=True))
        self._audit(
            "admins.manage", "assign_role", AuditOutcome.SUCCESS,
            resource_type="user_role", resource_key=target_user_id,
        )
        for permission_key in permissions:
            await self._upsert_user_override(
                target_user_id=target_user_id,
                permission_key=permission_key,
                granted=True,
            )
            self._audit(
                "permissions.manage", "set_user_permission", AuditOutcome.SUCCESS,
                resource_type="user_permission", resource_key=target_user_id,
            )
        return {"user_id": target_user_id, "role": role.name, "permissions": permissions}

    @requires_permission("admins.manage")
    async def set_admin_role(self, *, target_user_id: int, role_name: str) -> UserRole:
        self._ensure_not_primary_owner(target_user_id)
        if target_user_id == self.actor_user_id:
            raise AdminPolicyError("لا يمكن للمشرف تغيير Role حسابه بنفسه")
        if not await self._admin_record_exists(target_user_id):
            raise ValueError("المستخدم ليس ضمن سجلات Admin")
        role = await self.session.scalar(select(Role).where(Role.name == role_name.strip().upper()))
        if role is None:
            raise ValueError("Unknown role")
        active_roots = await self._active_super_admin_ids(lock=True)
        current = list((await self.session.scalars(
            select(UserRole).where(UserRole.user_id == target_user_id).with_for_update()
        )).all())
        was_super_admin = target_user_id in active_roots
        if was_super_admin and role.name != "SUPER_ADMIN" and len(active_roots) <= 1:
            raise LastSuperAdminError("لا يمكن إزالة آخر SUPER_ADMIN نشط")
        for assignment in current:
            await self.session.delete(assignment)
        replacement = UserRole(user_id=target_user_id, role_id=role.id)
        self.session.add(replacement)
        return replacement

    @requires_permission("admins.manage")
    async def set_admin_enabled(self, *, target_user_id: int, enabled: bool) -> AdminAccount:
        self._ensure_not_primary_owner(target_user_id)
        if target_user_id == self.actor_user_id:
            raise AdminPolicyError("لا يمكن للمشرف تعطيل حسابه أو إعادة تفعيله من هذه الجلسة")
        if not await self._admin_record_exists(target_user_id):
            raise ValueError("المستخدم ليس ضمن سجلات Admin")
        if not enabled:
            active_roots = await self._active_super_admin_ids(lock=True)
            if target_user_id in active_roots:
                if len(active_roots) <= 1:
                    raise LastSuperAdminError("لا يمكن تعطيل آخر SUPER_ADMIN نشط")
                raise AdminPolicyError("لا يمكن تعطيل حساب SUPER_ADMIN")
        account = await self.session.get(AdminAccount, target_user_id)
        if account is None:
            account = AdminAccount(
                user_id=target_user_id,
                is_enabled=enabled,
                disabled_at=None if enabled else datetime.now(timezone.utc),
                disabled_by_user_id=None if enabled else self.actor_user_id,
            )
            self.session.add(account)
        else:
            account.is_enabled = enabled
            account.disabled_at = None if enabled else datetime.now(timezone.utc)
            account.disabled_by_user_id = None if enabled else self.actor_user_id
        return account

    @requires_permission("permissions.manage")
    async def set_admin_permission(
        self, *, target_user_id: int, permission_key: str, granted: bool
    ) -> UserPermission:
        self._ensure_not_primary_owner(target_user_id)
        if target_user_id == self.actor_user_id:
            raise AdminPolicyError("لا يمكن للمشرف منح أو إزالة صلاحية عن حسابه بنفسه")
        if not await self._admin_record_exists(target_user_id):
            raise ValueError("المستخدم ليس ضمن سجلات Admin")
        if not granted and permission_key in {"admins.manage", "permissions.manage"}:
            active_roots = await self._active_super_admin_ids(lock=True)
            if target_user_id in active_roots and len(active_roots) <= 1:
                raise LastSuperAdminError("لا يمكن حجب صلاحيات التحكم عن آخر SUPER_ADMIN نشط")
        override = await self._upsert_user_override(
            target_user_id=target_user_id,
            permission_key=permission_key,
            granted=granted,
        )
        self._audit(
            "permissions.manage", "set_admin_permission", AuditOutcome.SUCCESS,
            resource_type="user_permission", resource_key=target_user_id,
        )
        return override

    @requires_permission("security.logs.view")
    async def list_admin_audit(self, *, target_admin_id: int, limit: int = 100) -> list:
        from app.audit.models import AuditLog

        if not await self._admin_record_exists(target_admin_id):
            raise ValueError("المستخدم ليس ضمن سجلات Admin")
        bounded_limit = max(1, min(int(limit), 200))
        result = await self.session.scalars(
            select(AuditLog)
            .where(AuditLog.actor_user_id == target_admin_id)
            .order_by(AuditLog.occurred_at.desc())
            .limit(bounded_limit)
        )
        return list(result)
