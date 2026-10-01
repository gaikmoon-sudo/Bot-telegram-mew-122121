from __future__ import annotations

import asyncio
import sys
import types

from app.webapp import admin_api
from main import reminder_loop


def test_reminder_loop_uses_injected_runtime_store():
    async def run():
        delivered = asyncio.Event()
        sent = []

        class FakeStore:
            def reminder_users(self, hour):
                assert 0 <= hour <= 23
                return [918273]

            def claim_reminder(self, user_id):
                assert user_id == 918273
                return True

            def snapshot(self, user_id, total):
                assert (user_id, total) == (918273, 13)
                return {"completed": 2, "streak": 4}

        class FakeBot:
            async def send_message(self, user_id, text, reply_markup=None):
                sent.append((user_id, text, reply_markup))
                delivered.set()

        task = asyncio.create_task(reminder_loop(FakeBot(), FakeStore()))
        try:
            await asyncio.wait_for(delivered.wait(), timeout=2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert len(sent) == 1
        assert sent[0][0] == 918273
        assert "2/13" in sent[0][1]
        assert "4" in sent[0][1]

    asyncio.run(run())


def test_admin_runtime_lesson_sync_delegates_to_both_stores(monkeypatch):
    calls = []
    storage_module = types.ModuleType("app.storage.postgres")
    storage_module.store = types.SimpleNamespace(
        sync_admin_lesson=lambda *args, **kwargs: calls.append(("store", args, kwargs)),
        delete_admin_lesson=lambda lesson_id: calls.append(("delete", lesson_id)),
    )
    start_module = types.ModuleType("app.bot.routers.start")
    start_module.refresh_runtime_lessons = lambda: calls.append(("refresh",))
    monkeypatch.setitem(sys.modules, "app.storage.postgres", storage_module)
    monkeypatch.setitem(sys.modules, "app.bot.routers.start", start_module)

    async def exercise_sync():
        await admin_api._sync_runtime_lesson(
            {
                "id": "lesson-uuid",
                "title": "Published lesson",
                "content_body": "Body",
                "summary": "Summary",
                "status": "PUBLISHED",
            },
            24680,
        )
    asyncio.run(exercise_sync())
    assert calls == [
        (
            "store",
            ("lesson-uuid",),
            {
                "title": "Published lesson",
                "theory": "Body",
                "summary": "Summary",
                "status": "PUBLISHED",
                "created_by": 24680,
            },
        ),
        ("refresh",),
    ]

    calls.clear()
    asyncio.run(admin_api._delete_runtime_lesson("lesson-uuid"))
    assert calls == [("delete", "lesson-uuid"), ("refresh",)]
