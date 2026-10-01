"""Integration-level RBAC checks using a temporary SQLite database."""
from __future__ import annotations

import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.audit.models import AuditLog
from app.audit.service import safe_details
from app.authorization import middleware as authorization_middleware
from app.authorization.admin_service import AdminService
from app.authorization.models import AdminAccount, Permission, Role, RolePermission, UserPermission, UserRole
from app.authorization.permissions import ROLE_GRANTS, evaluate_permissions
from app.authorization.service import RBACService, seed_builtin_roles
from app.identity.models import User
from infrastructure.database.base import Base


RBAC_TABLES = [
    User.__table__,
    AdminAccount.__table__,
    Role.__table__,
    Permission.__table__,
    RolePermission.__table__,
    UserRole.__table__,
    UserPermission.__table__,
    AuditLog.__table__,
]


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=RBAC_TABLES)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_builtin_roles(session)
        session.add_all(
            [
                User(telegram_id=10001, username="root"),
                User(telegram_id=10002, username="manager"),
                User(telegram_id=10003, username="editor"),
                User(telegram_id=10004, username="learner"),
            ]
        )
        await session.flush()
        roles = {role.name: role for role in (await session.scalars(select(Role))).all()}
        for user_id, role_name in (
            (10001, "SUPER_ADMIN"),
            (10002, "CONTENT_MANAGER"),
            (10003, "CONTENT_EDITOR"),
        ):
            session.add(UserRole(user_id=user_id, role_id=roles[role_name].id))
        await session.commit()
    return engine, factory


def test_super_admin_has_all_current_and_future_permissions():
    async def run():
        engine, factory = await _database()
        try:
            async with factory() as session:
                rbac = RBACService(session)
                assert await rbac.has_permission(10001, "settings.manage")
                assert await rbac.has_permission(10001, "payments.manage")
                assert await rbac.has_permission(10001, "courses.publish")
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_content_manager_can_create_and_edit_lessons_but_not_users_or_payments():
    async def run():
        engine, factory = await _database()
        try:
            async with factory() as session:
                rbac = RBACService(session)
                assert await rbac.has_permission(10002, "lessons.create")
                assert await rbac.has_permission(10002, "lessons.edit")
                assert await rbac.has_permission(10002, "courses.create")
                assert await rbac.has_permission(10002, "files.upload")
                assert await rbac.has_permission(10002, "videos.manage")
                assert await rbac.has_permission(10002, "content.order")
                assert not await rbac.has_permission(10002, "admin.dashboard.view")
                assert not await rbac.has_permission(10002, "users.view")
                assert not await rbac.has_permission(10002, "payments.manage")
                assert not await rbac.has_permission(10002, "ai.manage")
                assert not await rbac.has_permission(10002, "bot.settings")
                assert not await rbac.has_permission(10002, "admins.manage")
                assert not await rbac.has_permission(10002, "permissions.manage")
                assert not await rbac.has_permission(10002, "security.logs.view")
                assert not await rbac.has_permission(10002, "settings.manage")
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_content_editor_can_edit_lesson_with_individual_override_but_not_admins():
    async def run():
        engine, factory = await _database()
        try:
            async with factory() as session:
                rbac = RBACService(session)
                assert await rbac.has_permission(10003, "lessons.edit")
                assert await rbac.has_permission(10003, "text.edit")
                assert await rbac.has_permission(10003, "videos.add_link")
                assert await rbac.has_permission(10003, "files.upload")
                assert not await rbac.has_permission(10003, "lessons.create")
                assert not await rbac.has_permission(10003, "admins.manage")
                assert not await rbac.has_permission(10003, "payments.view")

                # A narrowly-scoped direct grant attaches to the user, not role.
                permission = await session.scalar(
                    select(Permission).where(
                        Permission.resource == "lessons",
                        Permission.action == "create",
                    )
                )
                session.add(
                    UserPermission(
                        user_id=10003,
                        permission_id=permission.id,
                        granted=True,
                    )
                )
                await session.flush()
                assert await rbac.has_permission(10003, "lessons.create")
                assert not await rbac.has_permission(10003, "admins.manage")
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_explicit_user_denial_overrides_a_role_grant():
    async def run():
        engine, factory = await _database()
        try:
            async with factory() as session:
                permission = await session.scalar(
                    select(Permission).where(
                        Permission.resource == "lessons",
                        Permission.action == "edit",
                    )
                )
                session.add(
                    UserPermission(
                        user_id=10002,
                        permission_id=permission.id,
                        granted=False,
                    )
                )
                await session.flush()
                assert not await RBACService(session).has_permission(10002, "lessons.edit")
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_admin_service_can_create_future_roles_and_audit_permission_changes():
    async def run():
        engine, factory = await _database()
        try:
            async with factory() as session:
                service = AdminService(session, actor_user_id=10001)
                role = await service.create_role(
                    name="video_curator",
                    description="Can add course video links",
                )
                assert role.name == "VIDEO_CURATOR"
                permission = await service.create_permission(
                    resource="courses",
                    action="publish",
                    description="Publish a reviewed course",
                )
                assert permission.resource == "courses"
                await service.set_role_permission(
                    role_name=role.name,
                    permission_key="courses.publish",
                    granted=True,
                )
                session.add(UserRole(user_id=10004, role_id=role.id))
                await session.commit()

            async with factory() as session:
                rbac = RBACService(session)
                assert await rbac.has_permission(10004, "courses.publish")
                assert not await rbac.has_permission(10004, "payments.view")
                assert not await rbac.has_permission(10003, "courses.publish")
                events = (await session.scalars(select(AuditLog))).all()
                assert len(events) == 3
                assert all(event.outcome.value == "SUCCESS" for event in events)
                assert {event.resource_type for event in events} == {
                    "roles",
                    "permissions",
                    "role_permissions",
                }
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_regular_user_is_blocked_by_central_admin_http_middleware(monkeypatch):
    async def run():
        engine, factory = await _database()
        monkeypatch.setattr(authorization_middleware, "session_factory", factory)

        @web.middleware
        async def identify_user(request, handler):
            request[authorization_middleware.ADMIN_USER_ID_KEY] = 10004
            return await handler(request)

        app = web.Application(middlewares=[identify_user, authorization_middleware.admin_http_middleware])

        async def users_list(_request):
            return web.json_response({"users": []})

        app.router.add_get("/api/admin/users", users_list, name="admin.users.list")
        client = TestClient(TestServer(app))
        try:
            await client.start_server()
            response = await client.get("/api/admin/users")
            assert response.status == 403
            assert response.text  # the handler body was never authorized
            async with factory() as session:
                events = (await session.scalars(select(AuditLog))).all()
                assert len(events) == 1
                assert events[0].outcome.value == "FAILURE"
                assert events[0].details == {
                    "permission": "users.view",
                    "operation": "admin.users.list",
                }
        finally:
            await client.close()
            await engine.dispose()

    asyncio.run(run())


def test_permission_policy_is_permission_based_and_defaults_to_deny():
    assert evaluate_permissions("lessons.edit", role_grants=ROLE_GRANTS["CONTENT_EDITOR"])
    assert not evaluate_permissions("admins.manage", role_grants=ROLE_GRANTS["CONTENT_EDITOR"])
    assert evaluate_permissions(
        "lessons.create",
        role_grants=ROLE_GRANTS["CONTENT_EDITOR"],
        user_overrides={"lessons.create": True},
    )
    assert not evaluate_permissions("users.view")


def test_audit_details_are_allowlisted_and_drop_secrets_and_payloads():
    cleaned = safe_details(
        {
            "permission": "courses.edit",
            "operation": "update_course",
            "password": "should-never-be-recorded",
            "content": "private lesson text",
            "authorization": "Bearer secret",
        }
    )
    assert cleaned == {
        "permission": "courses.edit",
        "operation": "update_course",
    }


def test_disabled_admin_is_denied_by_rbac_and_cannot_self_assign():
    async def run():
        from datetime import datetime, timezone
        from app.authorization.admin_service import AdminPolicyError

        engine, factory = await _database()
        try:
            async with factory() as session:
                account = AdminAccount(
                    user_id=10001,
                    is_enabled=False,
                    disabled_at=datetime.now(timezone.utc),
                    disabled_by_user_id=10002,
                )
                session.add(account)
                await session.flush()
                assert not await RBACService(session).has_permission(10001, "admins.manage")
                await session.delete(account)
                await session.flush()
                service = AdminService(session, actor_user_id=10001)
                try:
                    await service.assign_role(target_user_id=10001, role_name="CONTENT_MANAGER")
                except AdminPolicyError:
                    pass
                else:
                    raise AssertionError("self role assignment must be rejected")
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_service_blocks_removing_the_last_super_admin(monkeypatch):
    async def run():
        from app.authorization.admin_service import LastSuperAdminError

        engine, factory = await _database()
        try:
            async with factory() as session:
                session.add(User(telegram_id=10005, username="last-root-target"))
                await session.flush()
                root_role = await session.scalar(select(Role).where(Role.name == "SUPER_ADMIN"))
                session.add(UserRole(user_id=10005, role_id=root_role.id))
                await session.flush()

                service = AdminService(session, actor_user_id=10001)

                async def one_active_root(*, lock=False):
                    return [10005]

                monkeypatch.setattr(service, "_active_super_admin_ids", one_active_root)
                try:
                    await service.set_admin_role(
                        target_user_id=10005,
                        role_name="CONTENT_MANAGER",
                    )
                except LastSuperAdminError:
                    pass
                else:
                    raise AssertionError("the last active SUPER_ADMIN must not be removable")

                try:
                    await service.set_admin_permission(
                        target_user_id=10005,
                        permission_key="admins.manage",
                        granted=False,
                    )
                except LastSuperAdminError:
                    pass
                else:
                    raise AssertionError("the last SUPER_ADMIN must retain administrator control")

                still_root = await session.scalar(
                    select(UserRole.user_id)
                    .join(Role, Role.id == UserRole.role_id)
                    .where(UserRole.user_id == 10005, Role.name == "SUPER_ADMIN")
                )
                assert still_root == 10005
        finally:
            await engine.dispose()
    asyncio.run(run())
