"""Database-backed, fail-closed RBAC service."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.authorization.models import AdminAccount, Permission, RolePermission, UserPermission, UserRole
from app.authorization.permissions import evaluate_permissions
from app.identity.models import User


class AuthorizationError(PermissionError):
    """Raised when an actor does not hold the requested permission."""


class RBACService:
    """Resolve direct user grants and role-derived grants from PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def permissions_for(self, user_id: int) -> tuple[set[str], dict[str, bool]]:
        """Load active role grants and per-user overrides for one Telegram ID."""
        # Existing RBAC columns are timestamp without time zone.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        direct_result = await self.session.execute(
            select(Permission.resource, Permission.action, UserPermission.granted)
            .join(Permission, Permission.id == UserPermission.permission_id)
            .where(
                UserPermission.user_id == user_id,
                or_(UserPermission.expires_at.is_(None), UserPermission.expires_at > now),
            )
        )
        user_overrides = {
            f"{resource}.{action}": bool(granted)
            for resource, action, granted in direct_result.all()
        }

        roles_result = await self.session.execute(
            select(Permission.resource, Permission.action)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(
                UserRole.user_id == user_id,
                or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
            )
        )
        role_grants = {
            f"{resource}.{action}"
            for resource, action in roles_result.all()
        }
        return role_grants, user_overrides

    async def has_permission(self, user_id: int | None, permission_key: str) -> bool:
        """Check a permission; missing identities and query errors never allow."""
        if user_id is None or user_id <= 0 or not permission_key or "." not in permission_key:
            return False
        is_active = await self.session.scalar(
            select(User.is_active).where(User.telegram_id == user_id)
        )
        if is_active is not True:
            return False
        admin_account = await self.session.get(AdminAccount, user_id)
        if admin_account is not None and not admin_account.is_enabled:
            return False
        role_grants, user_overrides = await self.permissions_for(user_id)
        return evaluate_permissions(
            permission_key,
            role_grants=role_grants,
            user_overrides=user_overrides,
        )

    async def require(self, user_id: int | None, permission_key: str) -> None:
        if not await self.has_permission(user_id, permission_key):
            raise AuthorizationError(f"Permission required: {permission_key}")


async def seed_builtin_roles(session: AsyncSession) -> None:
    """Idempotently seed the built-in permission catalog and role grants.

    This helper is useful for controlled bootstrap jobs. Production deployments
    should normally seed through the matching Alembic revision.
    """
    from app.authorization.models import Role
    from app.authorization.permissions import PERMISSION_CATALOG, ROLE_GRANTS

    permission_by_key: dict[str, Permission] = {}
    for key, spec in PERMISSION_CATALOG.items():
        permission = await session.scalar(
            select(Permission).where(
                Permission.resource == spec.resource,
                Permission.action == spec.action,
            )
        )
        if permission is None:
            permission = Permission(
                resource=spec.resource,
                action=spec.action,
                description=spec.description,
            )
            session.add(permission)
            await session.flush()
        permission_by_key[key] = permission

    for name, grants in ROLE_GRANTS.items():
        role = await session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, description=f"Built-in role: {name}", is_system=True)
            session.add(role)
            await session.flush()
        elif not role.is_system:
            role.is_system = True
        desired = {permission_by_key[key].id for key in grants}
        current = set(
            await session.scalars(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            )
        )
        for permission_id in desired - current:
            session.add(RolePermission(role_id=role.id, permission_id=permission_id))
        # Built-in grants are reconciled to the source-of-truth catalog. Role
        # customizations belong in additional, non-system roles.
        for permission_id in current - desired:
            association = await session.get(RolePermission, (role.id, permission_id))
            if association is not None:
                await session.delete(association)
    await session.flush()
