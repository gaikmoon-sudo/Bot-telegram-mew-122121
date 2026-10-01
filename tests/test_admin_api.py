"""HTTP integration tests for the protected Admin Panel API."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from urllib.parse import urlencode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.audit.models import AuditLog
from app.authorization import middleware as authorization_middleware
from app.authorization.models import AdminAccount, Permission, Role, RolePermission, UserPermission, UserRole
from app.authorization.service import seed_builtin_roles
from app.content.models import ContentStatus, Course, LearningPath, Lesson, LessonVersion, Module
from app.identity.models import User
from app.webapp import admin_api
from app.webapp import telegram_auth
from infrastructure.database.base import Base


TABLES = [
    User.__table__, AdminAccount.__table__, Role.__table__, Permission.__table__, RolePermission.__table__,
    UserRole.__table__, UserPermission.__table__, AuditLog.__table__,
    LearningPath.__table__, Course.__table__, Module.__table__, Lesson.__table__,
    LessonVersion.__table__,
]


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=TABLES)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await seed_builtin_roles(session)
            session.add_all([
                User(telegram_id=22001, username="root"),
                User(telegram_id=22002, username="manager"),
                User(telegram_id=22003, username="editor"),
                User(telegram_id=22004, username="learner"),
            ])
        roles = {role.name: role for role in (await session.scalars(select(Role))).all()}
        session.add_all([
            UserRole(user_id=22001, role_id=roles["SUPER_ADMIN"].id),
            UserRole(user_id=22002, role_id=roles["CONTENT_MANAGER"].id),
            UserRole(user_id=22003, role_id=roles["CONTENT_EDITOR"].id),
        ])
        await session.commit()
    async with factory() as session:
        async with session.begin():
            path = LearningPath(title="مسار تجريبي", slug="test-path", status=ContentStatus.DRAFT)
            session.add(path)
            await session.flush()
            course = Course(learning_path_id=path.id, title="دورة تجريبية", slug="test-course", status=ContentStatus.DRAFT)
            session.add(course)
            await session.flush()
            module = Module(course_id=course.id, title="وحدة تجريبية", slug="test-module", status=ContentStatus.DRAFT)
            session.add(module)
            await session.flush()
            lesson = Lesson(module_id=module.id, title="درس تجريبي", slug="test-lesson", status=ContentStatus.DRAFT)
            session.add(lesson)
            await session.flush()
            session.add(LessonVersion(
                lesson_id=lesson.id,
                version_number=1,
                content_body="محتوى أصلي",
                content_metadata={},
                change_summary="fixture",
                status=ContentStatus.DRAFT,
            ))
        ids = {"path": str(path.id), "course": str(course.id), "module": str(module.id), "lesson": str(lesson.id)}
    return engine, factory, ids


async def _client(monkeypatch, tmp_path):
    engine, factory, ids = await _database()
    monkeypatch.setattr(admin_api, "session_factory", factory)
    monkeypatch.setattr(authorization_middleware, "session_factory", factory)
    monkeypatch.setattr(admin_api, "UPLOAD_DIR", tmp_path / "admin-files")
    monkeypatch.setattr(admin_api, "CONTENT_STORAGE_BACKEND", "local")
    # The normalized content DB is SQLite in these tests; the runtime mirror is
    # a separate PostgreSQL integration and is covered through its own adapter.
    async def no_sync(*_args, **_kwargs):
        return None

    async def no_delete(*_args, **_kwargs):
        return None

    monkeypatch.setattr(admin_api, "_sync_runtime_lesson", no_sync)
    monkeypatch.setattr(admin_api, "_delete_runtime_lesson", no_delete)
    monkeypatch.setattr(
        admin_api,
        "telegram_user_id",
        lambda request: int(request.headers["X-Test-User"]) if request.headers.get("X-Test-User", "").isdigit() else None,
    )
    app = web.Application(middlewares=[admin_api.telegram_admin_identity_middleware, authorization_middleware.admin_http_middleware])
    admin_api.setup_admin_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client, engine, factory, ids


def _headers(user_id: int) -> dict[str, str]:
    return {"X-Test-User": str(user_id)}


def test_office_upload_signature_rejects_non_ooxml_files(tmp_path):
    import zipfile

    forged = tmp_path / "forged.docx"
    forged.write_bytes(b"not a zip archive")
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert not admin_api._valid_file_signature(forged, mime)

    valid = tmp_path / "valid.docx"
    with zipfile.ZipFile(valid, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    assert admin_api._valid_file_signature(valid, mime)


def test_telegram_webapp_init_data_signature_and_freshness(monkeypatch):
    token = "test-bot-token-never-used-outside-this-test"
    monkeypatch.setattr(telegram_auth, "settings", SimpleNamespace(bot_token=token))
    auth_date = int(time.time())
    values = {"auth_date": str(auth_date), "query_id": "query", "user": json.dumps({"id": 22001})}
    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    signed = urlencode(values)
    assert telegram_auth.validate_telegram_init_data(signed)["id"] == 22001
    tampered = signed.replace("22001", "22002")
    assert telegram_auth.validate_telegram_init_data(tampered) is None

    values["auth_date"] = str(auth_date - 301)
    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(k for k in values if k != "hash"))
    values["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    assert telegram_auth.validate_telegram_init_data(urlencode(values)) is None


def test_admin_api_authentication_and_role_scoped_content_crud(monkeypatch, tmp_path):
    async def run():
        client, engine, factory, ids = await _client(monkeypatch, tmp_path)
        try:
            # Public shell only; no protected data or routes are available anonymously.
            shell = await client.get("/admin")
            assert shell.status == 200
            public_asset = await client.get("/admin/assets/admin.js")
            assert public_asset.status == 200
            anonymous = await client.get("/api/admin/courses")
            assert anonymous.status == 401

            # The ordinary user cannot access even unimplemented admin surfaces.
            regular = _headers(22004)
            assert (await client.get("/api/admin/courses", headers=regular)).status == 403
            assert (await client.get("/api/admin/users", headers=regular)).status == 403
            assert (await client.get("/api/admin/payments", headers=regular)).status == 403

            manager = _headers(22002)
            manager_session = await (await client.get("/api/admin/session", headers=manager)).json()
            assert "courses.create" in manager_session["permissions"]
            assert "users.view" not in manager_session["permissions"]
            assert (await client.get("/api/admin/dashboard", headers=manager)).status == 403
            assert (await client.get("/api/admin/users", headers=manager)).status == 403
            assert (await client.get("/api/admin/payments", headers=manager)).status == 403
            assert (await client.get("/api/admin/roles", headers=manager)).status == 403
            assert (await client.get("/api/admin/courses", headers=manager)).status == 200

            # A manager can create courses, modules and lessons at the actual API boundary.
            created_course = await client.post("/api/admin/courses", headers=manager, json={
                "title": "دورة جديدة", "learning_path_id": ids["path"], "summary": "اختبار",
            })
            assert created_course.status == 200
            course = await created_course.json()
            created_module = await client.post("/api/admin/modules", headers=manager, json={
                "title": "وحدة جديدة", "course_id": course["id"],
            })
            assert created_module.status == 200
            module = await created_module.json()
            created_lesson = await client.post("/api/admin/lessons", headers=manager, json={
                "title": "درس جديد", "module_id": module["id"], "content_body": "النص الأول",
            })
            assert created_lesson.status == 200
            lesson = await created_lesson.json()

            # Ordering is a server-side adjacent move scoped to the parent,
            # rather than trusting a client-supplied partial list.
            sibling_response = await client.post("/api/admin/lessons", headers=manager, json={
                "title": "درس ثانٍ", "module_id": ids["module"], "content_body": "نص ثانٍ", "position": 10,
            })
            assert sibling_response.status == 200
            sibling = await sibling_response.json()
            moved = await client.post("/api/admin/lessons/order", headers=manager, json={
                "parent_id": ids["module"], "item_id": ids["lesson"], "direction": "down",
            })
            assert moved.status == 200
            assert (await moved.json())["ordered_ids"] == [sibling["id"], ids["lesson"]]

            # Editor may update lesson text, but cannot create lessons or administer roles.
            editor = _headers(22003)
            update = await client.patch(f"/api/admin/lessons/{ids['lesson']}", headers=editor, json={
                "content_body": "النص المعدل", "change_summary": "تحرير اختبار",
            })
            assert update.status == 200
            assert (await update.json())["content_body"] == "النص المعدل"
            editor_session = await (await client.get("/api/admin/session", headers=editor)).json()
            assert "lessons.edit" in editor_session["permissions"]
            assert "admins.manage" not in editor_session["permissions"]
            video = await client.post(f"/api/admin/lessons/{ids['lesson']}/videos", headers=editor, json={
                "label": "شرح", "url": "https://video.example/lesson",
            })
            assert video.status == 200
            assert (await client.post("/api/admin/lessons", headers=editor, json={
                "title": "محظور", "module_id": ids["module"], "content_body": "لا",
            })).status == 403
            assert (await client.get("/api/admin/roles", headers=editor)).status == 403
            assert (await client.get("/api/admin/users", headers=editor)).status == 403

            # Super admin has the full dashboard; each action has a persisted audit event.
            root = _headers(22001)
            assert (await client.get("/api/admin/dashboard", headers=root)).status == 200
            assert (await client.get("/api/admin/roles", headers=root)).status == 200
            async with factory() as session:
                events = (await session.scalars(select(AuditLog))).all()
                assert events
                assert any(event.resource_key == ids["lesson"] for event in events)
                assert all("password" not in str(event.details).lower() for event in events)
        finally:
            await client.close()
            await engine.dispose()
    asyncio.run(run())


def test_content_manager_uploads_and_editor_cannot_delete_files(monkeypatch, tmp_path):
    async def run():
        client, engine, factory, ids = await _client(monkeypatch, tmp_path)
        try:
            import io
            from aiohttp import FormData

            form = FormData()
            form.add_field("file", io.BytesIO(b"%PDF-1.4\nfixture pdf\n%%EOF"), filename="lesson.pdf", content_type="application/pdf")
            manager = _headers(22002)
            upload = await client.post(f"/api/admin/lessons/{ids['lesson']}/files", headers=manager, data=form)
            assert upload.status == 200
            asset = await upload.json()
            assert asset["content_type"] == "application/pdf"
            assert "storage_name" not in asset

            listing = await client.get(f"/api/admin/lessons/{ids['lesson']}/files", headers=manager)
            assert listing.status == 200
            assert (await listing.json())[0]["id"] == asset["id"]
            download = await client.get(f"/api/admin/files/{asset['id']}", headers=manager)
            assert download.status == 200
            assert download.headers["X-Content-Type-Options"] == "nosniff"
            assert await download.read() == b"%PDF-1.4\nfixture pdf\n%%EOF"

            editor = _headers(22003)
            denied = await client.delete(f"/api/admin/lessons/{ids['lesson']}/files/{asset['id']}", headers=editor)
            assert denied.status == 403
            assert (await client.get(f"/api/admin/files/{asset['id']}", headers={"X-Test-User": "22004"})).status == 403
        finally:
            await client.close()
            await engine.dispose()
    asyncio.run(run())


def test_replit_app_storage_upload_and_download(monkeypatch, tmp_path):
    async def run():
        import io
        from pathlib import Path
        from aiohttp import FormData

        client, engine, _factory, ids = await _client(monkeypatch, tmp_path)
        objects = {}

        class FakeAppStorage:
            def upload_from_filename(self, object_name, src_filename):
                objects[object_name] = Path(src_filename).read_bytes()

            def download_as_bytes(self, object_name):
                return objects[object_name]

        monkeypatch.setattr(admin_api, "CONTENT_STORAGE_BACKEND", "replit")
        monkeypatch.setattr(admin_api, "_app_storage_client", lambda: FakeAppStorage())
        try:
            form = FormData()
            payload = b"%PDF-1.4\ncloud fixture\n%%EOF"
            form.add_field("file", io.BytesIO(payload), filename="lesson.pdf", content_type="application/pdf")
            response = await client.post(
                f"/api/admin/lessons/{ids['lesson']}/files",
                headers=_headers(22002), data=form,
            )
            assert response.status == 200
            asset = await response.json()
            assert "storage_name" not in asset  # internal locator is never public
            assert len(objects) == 1 and next(iter(objects.values())) == payload
            download = await client.get(
                f"/api/admin/files/{asset['id']}", headers=_headers(22002),
            )
            assert download.status == 200
            assert await download.read() == payload
        finally:
            await client.close()
            await engine.dispose()
    asyncio.run(run())


def test_super_admin_admin_management_api_and_security_guards(monkeypatch, tmp_path):
    async def run():
        client, engine, factory, ids = await _client(monkeypatch, tmp_path)
        try:
            async with factory() as session:
                session.add(User(telegram_id=22005, username="root-two"))
                await session.commit()

            manager = _headers(22002)
            editor = _headers(22003)
            new_admin_payload = {
                "telegram_id": 22004,
                "role_name": "CONTENT_EDITOR",
                "permissions": ["lessons.create"],
            }
            for actor in (manager, editor):
                assert (await client.get("/api/admin/admins", headers=actor)).status == 403
                assert (await client.post("/api/admin/admins", headers=actor, json=new_admin_payload)).status == 403
                assert (await client.patch("/api/admin/admins/22001/role", headers=actor, json={"role_name": "CONTENT_EDITOR"})).status == 403
                assert (await client.patch("/api/admin/admins/22001/status", headers=actor, json={"enabled": False})).status == 403
                assert (await client.put("/api/admin/admins/22001/permissions", headers=actor, json={"permission": "users.view", "granted": True})).status == 403
                assert (await client.get("/api/admin/admins/22001/audit", headers=actor)).status == 403
                assert (await client.get("/api/admin/permissions", headers=actor)).status == 403

            root = _headers(22001)
            created = await client.post("/api/admin/admins", headers=root, json=new_admin_payload)
            assert created.status == 201
            assert (await created.json())["role"] == "CONTENT_EDITOR"
            async with factory() as session:
                grant = await session.scalar(
                    select(UserPermission).where(UserPermission.user_id == 22004)
                )
                assert grant.granted is True
                assert grant.assigned_by_user_id == 22001

            # The newly managed editor can act with the explicit extra permission.
            editor_headers = _headers(22004)
            assert (await client.post("/api/admin/lessons", headers=editor_headers, json={
                "title": "درس للمشرف الجديد",
                "module_id": ids["module"],
                "content_body": "نص اختبار",
            })).status == 200
            activity = await client.get("/api/admin/admins/22004/audit", headers=root)
            assert activity.status == 200
            activity_items = (await activity.json())["items"]
            assert any(item["actor_user_id"] == 22004 for item in activity_items)

            listing = await client.get("/api/admin/admins?q=22004", headers=root)
            assert listing.status == 200
            admin_row = (await listing.json())["items"][0]
            assert admin_row["telegram_id"] == 22004
            assert admin_row["roles"] == ["CONTENT_EDITOR"]
            assert "lessons.create" in admin_row["permissions"]
            assert admin_row["last_activity"] is not None
            assert {"permission": "lessons.create", "granted": True} in admin_row["overrides"]

            # Permission removal is represented by an explicit per-user denial,
            # which overrides a role grant and is independently reversible.
            changed = await client.put("/api/admin/admins/22004/permissions", headers=root, json={
                "permission": "lessons.create", "granted": False,
            })
            assert changed.status == 200
            assert (await client.post("/api/admin/lessons", headers=editor_headers, json={
                "title": "محظور بعد السحب", "module_id": ids["module"], "content_body": "لا",
            })).status == 403
            assert (await client.put("/api/admin/admins/22004/permissions", headers=root, json={
                "permission": "courses.view", "granted": True,
            })).status == 200
            assert (await client.get("/api/admin/courses", headers=editor_headers)).status == 200
            assert (await client.put("/api/admin/admins/22004/permissions", headers=root, json={
                "permission": "courses.view", "granted": False,
            })).status == 200
            assert (await client.get("/api/admin/courses", headers=editor_headers)).status == 403

            # A role change replaces the previous role assignments.
            changed_role = await client.patch("/api/admin/admins/22004/role", headers=root, json={
                "role_name": "CONTENT_MANAGER",
            })
            assert changed_role.status == 200
            listing = await client.get("/api/admin/admins?q=22004", headers=root)
            assert (await listing.json())["items"][0]["roles"] == ["CONTENT_MANAGER"]

            disabled = await client.patch("/api/admin/admins/22004/status", headers=root, json={"enabled": False})
            assert disabled.status == 200
            assert (await client.get("/api/admin/session", headers=editor_headers)).status == 403
            enabled = await client.patch("/api/admin/admins/22004/status", headers=root, json={"enabled": True})
            assert enabled.status == 200
            assert (await client.get("/api/admin/session", headers=editor_headers)).status == 200

            # A second Super Admin can be added, but cannot be disabled; changing
            # its role is allowed only while another active Super Admin remains.
            second_root = await client.post("/api/admin/admins", headers=root, json={
                "telegram_id": 22005, "role_name": "SUPER_ADMIN", "permissions": [],
            })
            assert second_root.status == 201
            assert (await client.patch("/api/admin/admins/22005/status", headers=root, json={"enabled": False})).status == 403
            demoted = await client.patch("/api/admin/admins/22005/role", headers=root, json={
                "role_name": "CONTENT_MANAGER",
            })
            assert demoted.status == 200

            # Every route that could let the actor grant himself access rejects it.
            assert (await client.post("/api/admin/admins", headers=root, json={
                "telegram_id": 22001, "role_name": "SUPER_ADMIN", "permissions": [],
            })).status == 403
            assert (await client.put("/api/admin/admins/22001/permissions", headers=root, json={
                "permission": "payments.manage", "granted": True,
            })).status == 403
            assert (await client.post("/api/admin/users/22001/roles", headers=root, json={"role_name": "CONTENT_MANAGER"})).status == 403
            assert (await client.put("/api/admin/users/22001/permissions", headers=root, json={
                "permission": "payments.manage", "granted": True,
            })).status == 403
            assert (await client.patch("/api/admin/admins/22001/role", headers=root, json={
                "role_name": "CONTENT_MANAGER",
            })).status == 403
            assert (await client.patch("/api/admin/admins/22001/status", headers=root, json={"enabled": False})).status == 403

            # Invalid wildcards and unknown users/roles are rejected; sensitive
            # mutations generated persisted audit rows without secret material.
            assert (await client.put("/api/admin/admins/22004/permissions", headers=root, json={
                "permission": "*.*", "granted": True,
            })).status == 403
            assert (await client.put("/api/admin/roles/SUPER_ADMIN/permissions", headers=root, json={
                "permission": "*.*", "granted": False,
            })).status == 403
            async with factory() as session:
                events = (await session.scalars(select(AuditLog))).all()
                assert any(event.actor_user_id == 22001 and event.action == "admin.create_admin" for event in events)
                assert any(event.actor_user_id == 22001 and event.action == "admin.set_admin_enabled" for event in events)
                assert all("token" not in str(event.details).lower() for event in events)
        finally:
            await client.close()
            await engine.dispose()

    asyncio.run(run())
