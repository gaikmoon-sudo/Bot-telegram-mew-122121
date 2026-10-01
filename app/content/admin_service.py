"""Database-backed operations used by the permission-guarded content admin API."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.content.models import (
    ContentStatus,
    Course,
    CoursePrerequisite,
    Lesson,
    LessonVersion,
    LearningPath,
    Module,
)


class ContentNotFound(Exception):
    """Requested content resource does not exist."""


class ContentConflict(Exception):
    """Requested content operation conflicts with current data."""


def slug_for(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.lower()).strip("-")
    return (slug[:210] if slug else f"item-{uuid4().hex[:8]}")


def parse_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("معرّف المحتوى غير صالح") from exc


def _status(value: Any, default: ContentStatus = ContentStatus.DRAFT) -> ContentStatus:
    if value is None:
        return default
    try:
        return ContentStatus(str(value).upper())
    except ValueError as exc:
        raise ValueError("حالة المحتوى غير صالحة") from exc


def _required_text(data: dict[str, Any], name: str, *, maximum: int = 255) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"الحقل {name} مطلوب")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"الحقل {name} يتجاوز الحد المسموح")
    return value


def _page(page: int, page_size: int, total: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _path_row(item: LearningPath) -> dict[str, Any]:
    return {
        "id": str(item.id), "title": item.title, "slug": item.slug,
        "description": item.description, "status": item.status.value,
    }


def _course_row(item: Course, module_count: int = 0) -> dict[str, Any]:
    return {
        "id": str(item.id), "learning_path_id": str(item.learning_path_id),
        "learning_path_title": item.learning_path.title if item.learning_path else "",
        "title": item.title, "slug": item.slug, "summary": item.summary,
        "position": item.position, "status": item.status.value, "module_count": module_count,
        "created_at": _stamp(item.created_at), "updated_at": _stamp(item.updated_at),
    }


def _module_row(item: Module, lesson_count: int = 0) -> dict[str, Any]:
    return {
        "id": str(item.id), "course_id": str(item.course_id),
        "course_title": item.course.title if item.course else "",
        "title": item.title, "slug": item.slug, "description": item.description,
        "position": item.position, "status": item.status.value, "lesson_count": lesson_count,
        "created_at": _stamp(item.created_at), "updated_at": _stamp(item.updated_at),
    }


def _lesson_row(item: Lesson, latest: LessonVersion | None = None) -> dict[str, Any]:
    module = item.module
    course = module.course if module else None
    return {
        "id": str(item.id), "module_id": str(item.module_id),
        "module_title": module.title if module else "",
        "course_id": str(course.id) if course else None,
        "course_title": course.title if course else "",
        "title": item.title, "slug": item.slug, "summary": item.summary,
        "position": item.position, "status": item.status.value,
        "version": latest.version_number if latest else 0,
        "content_body": latest.content_body if latest else "",
        "content_metadata": latest.content_metadata if latest else {},
        "created_at": _stamp(item.created_at), "updated_at": _stamp(item.updated_at),
    }


class ContentAdminService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _count(self, stmt) -> int:
        return int(await self.session.scalar(stmt) or 0)

    async def list_learning_paths(self, *, q: str, page: int, page_size: int) -> dict[str, Any]:
        stmt = select(LearningPath)
        count_stmt = select(func.count(LearningPath.id))
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(LearningPath.title.ilike(pattern), LearningPath.slug.ilike(pattern)))
            count_stmt = count_stmt.where(or_(LearningPath.title.ilike(pattern), LearningPath.slug.ilike(pattern)))
        rows = (await self.session.scalars(stmt.order_by(LearningPath.title).offset((page - 1) * page_size).limit(page_size))).all()
        return _page(page, page_size, await self._count(count_stmt), [_path_row(row) for row in rows])

    async def create_learning_path(self, data: dict[str, Any]) -> dict[str, Any]:
        title = _required_text(data, "title")
        item = LearningPath(
            title=title,
            slug=str(data.get("slug") or slug_for(title)).strip()[:255],
            description=(str(data.get("description") or "").strip() or None),
            status=_status(data.get("status")),
        )
        self.session.add(item)
        await self.session.flush()
        return _path_row(item)

    async def update_learning_path(self, path_id: str, data: dict[str, Any]) -> dict[str, Any]:
        item = await self.session.get(LearningPath, parse_uuid(path_id))
        if item is None:
            raise ContentNotFound("مسار التعلم غير موجود")
        if "title" in data:
            item.title = _required_text(data, "title")
            item.slug = slug_for(item.title)
        if "description" in data:
            item.description = str(data.get("description") or "").strip() or None
        if "status" in data:
            item.status = _status(data.get("status"))
        await self.session.flush()
        return _path_row(item)

    async def delete_learning_path(self, path_id: str) -> dict[str, Any]:
        item = await self.session.get(LearningPath, parse_uuid(path_id), options=[selectinload(LearningPath.courses)])
        if item is None:
            raise ContentNotFound("مسار التعلم غير موجود")
        title = item.title
        await self.session.delete(item)
        await self.session.flush()
        return {"deleted": True, "id": path_id, "title": title}

    async def list_courses(self, *, q: str, status: str, page: int, page_size: int) -> dict[str, Any]:
        stmt = select(Course).options(selectinload(Course.learning_path))
        count_stmt = select(func.count(Course.id))
        filters = []
        if q:
            pattern = f"%{q}%"
            filters.append(or_(Course.title.ilike(pattern), Course.slug.ilike(pattern)))
        if status:
            filters.append(Course.status == _status(status))
        if filters:
            stmt, count_stmt = stmt.where(*filters), count_stmt.where(*filters)
        rows = (await self.session.scalars(stmt.order_by(Course.position, Course.title).offset((page - 1) * page_size).limit(page_size))).all()
        items = []
        for row in rows:
            modules = await self._count(select(func.count(Module.id)).where(Module.course_id == row.id))
            items.append(_course_row(row, modules))
        return _page(page, page_size, await self._count(count_stmt), items)

    async def create_course(self, data: dict[str, Any]) -> dict[str, Any]:
        title = _required_text(data, "title")
        path_id = parse_uuid(data.get("learning_path_id", ""))
        if await self.session.get(LearningPath, path_id) is None:
            raise ContentNotFound("مسار التعلم غير موجود")
        item = Course(
            learning_path_id=path_id,
            title=title,
            slug=str(data.get("slug") or slug_for(title)).strip()[:255],
            summary=(str(data.get("summary") or "").strip() or None),
            position=max(0, int(data.get("position", 0))),
            status=_status(data.get("status")),
        )
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item, attribute_names=["learning_path"])
        return _course_row(item)

    async def update_course(self, course_id: str, data: dict[str, Any]) -> dict[str, Any]:
        item = await self.session.get(Course, parse_uuid(course_id), options=[selectinload(Course.learning_path)])
        if item is None:
            raise ContentNotFound("الدورة غير موجودة")
        if "title" in data:
            item.title = _required_text(data, "title")
            if "slug" not in data:
                item.slug = slug_for(item.title)
        if "slug" in data:
            item.slug = _required_text(data, "slug")
        if "summary" in data:
            item.summary = str(data["summary"] or "").strip() or None
        if "position" in data:
            item.position = max(0, int(data["position"]))
        if "status" in data:
            item.status = _status(data["status"])
        await self.session.flush()
        return _course_row(item)

    async def delete_course(self, course_id: str) -> str:
        item = await self.session.get(Course, parse_uuid(course_id))
        if item is None:
            raise ContentNotFound("الدورة غير موجودة")
        identifier = str(item.id)
        await self.session.delete(item)
        return identifier

    async def list_modules(self, *, course_id: str, q: str, status: str, page: int, page_size: int) -> dict[str, Any]:
        stmt = select(Module).options(selectinload(Module.course))
        count_stmt = select(func.count(Module.id))
        filters = []
        if course_id:
            filters.append(Module.course_id == parse_uuid(course_id))
        if q:
            pattern = f"%{q}%"
            filters.append(or_(Module.title.ilike(pattern), Module.slug.ilike(pattern)))
        if status:
            filters.append(Module.status == _status(status))
        if filters:
            stmt, count_stmt = stmt.where(*filters), count_stmt.where(*filters)
        rows = (await self.session.scalars(stmt.order_by(Module.position, Module.title).offset((page - 1) * page_size).limit(page_size))).all()
        items = []
        for row in rows:
            lessons = await self._count(select(func.count(Lesson.id)).where(Lesson.module_id == row.id))
            items.append(_module_row(row, lessons))
        return _page(page, page_size, await self._count(count_stmt), items)

    async def create_module(self, data: dict[str, Any]) -> dict[str, Any]:
        title = _required_text(data, "title")
        course_id = parse_uuid(data.get("course_id", ""))
        course = await self.session.get(Course, course_id)
        if course is None:
            raise ContentNotFound("الدورة غير موجودة")
        item = Module(
            course_id=course_id, title=title,
            slug=str(data.get("slug") or slug_for(title)).strip()[:255],
            description=(str(data.get("description") or "").strip() or None),
            position=max(0, int(data.get("position", 0))), status=_status(data.get("status")),
        )
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item, attribute_names=["course"])
        return _module_row(item)

    async def update_module(self, module_id: str, data: dict[str, Any]) -> dict[str, Any]:
        item = await self.session.get(Module, parse_uuid(module_id), options=[selectinload(Module.course)])
        if item is None:
            raise ContentNotFound("الوحدة غير موجودة")
        if "title" in data:
            item.title = _required_text(data, "title")
            if "slug" not in data:
                item.slug = slug_for(item.title)
        if "slug" in data:
            item.slug = _required_text(data, "slug")
        if "description" in data:
            item.description = str(data["description"] or "").strip() or None
        if "position" in data:
            item.position = max(0, int(data["position"]))
        if "status" in data:
            item.status = _status(data["status"])
        await self.session.flush()
        return _module_row(item)

    async def delete_module(self, module_id: str) -> str:
        item = await self.session.get(Module, parse_uuid(module_id))
        if item is None:
            raise ContentNotFound("الوحدة غير موجودة")
        identifier = str(item.id)
        await self.session.delete(item)
        return identifier

    async def _latest_version(self, lesson_id: UUID) -> LessonVersion | None:
        return await self.session.scalar(
            select(LessonVersion).where(LessonVersion.lesson_id == lesson_id)
            .order_by(LessonVersion.version_number.desc()).limit(1)
        )

    async def list_lessons(self, *, q: str, module_id: str, course_id: str, status: str, page: int, page_size: int) -> dict[str, Any]:
        stmt = select(Lesson).options(selectinload(Lesson.module).selectinload(Module.course))
        count_stmt = select(func.count(Lesson.id))
        filters = []
        if module_id:
            filters.append(Lesson.module_id == parse_uuid(module_id))
        if course_id:
            stmt = stmt.join(Lesson.module)
            count_stmt = count_stmt.join(Module, Lesson.module_id == Module.id)
            filters.append(Module.course_id == parse_uuid(course_id))
        if q:
            pattern = f"%{q}%"
            filters.append(or_(Lesson.title.ilike(pattern), Lesson.slug.ilike(pattern)))
        if status:
            filters.append(Lesson.status == _status(status))
        if filters:
            stmt, count_stmt = stmt.where(*filters), count_stmt.where(*filters)
        rows = (await self.session.scalars(stmt.order_by(Lesson.position, Lesson.title).offset((page - 1) * page_size).limit(page_size))).all()
        items = []
        for row in rows:
            items.append(_lesson_row(row, await self._latest_version(row.id)))
        return _page(page, page_size, await self._count(count_stmt), items)

    async def get_lesson(self, lesson_id: str) -> dict[str, Any]:
        item = await self.session.get(Lesson, parse_uuid(lesson_id), options=[selectinload(Lesson.module).selectinload(Module.course)])
        if item is None:
            raise ContentNotFound("الدرس غير موجود")
        return _lesson_row(item, await self._latest_version(item.id))

    async def list_lesson_versions(self, lesson_id: str) -> list[dict[str, Any]]:
        lesson = await self.session.get(Lesson, parse_uuid(lesson_id))
        if lesson is None:
            raise ContentNotFound("الدرس غير موجود")
        rows = (await self.session.scalars(
            select(LessonVersion).where(LessonVersion.lesson_id == lesson.id).order_by(LessonVersion.version_number.desc())
        )).all()
        return [{"version": row.version_number, "content_body": row.content_body, "content_metadata": row.content_metadata, "change_summary": row.change_summary, "status": row.status.value, "published_at": row.published_at.isoformat() if row.published_at else None} for row in rows]

    async def create_lesson(self, data: dict[str, Any]) -> dict[str, Any]:
        title = _required_text(data, "title")
        module_id = parse_uuid(data.get("module_id", ""))
        if await self.session.get(Module, module_id) is None:
            raise ContentNotFound("الوحدة غير موجودة")
        body = _required_text(data, "content_body", maximum=200_000)
        status = _status(data.get("status"))
        item = Lesson(
            module_id=module_id, title=title,
            slug=str(data.get("slug") or slug_for(title)).strip()[:255],
            summary=(str(data.get("summary") or "").strip() or None),
            position=max(0, int(data.get("position", 0))), status=status,
        )
        self.session.add(item)
        await self.session.flush()
        version = LessonVersion(
            lesson_id=item.id, version_number=1, content_body=body,
            content_metadata={}, change_summary="إنشاء الدرس", status=status,
            published_at=datetime.now(timezone.utc) if status == ContentStatus.PUBLISHED else None,
        )
        self.session.add(version)
        await self.session.flush()
        item = await self.session.scalar(
            select(Lesson)
            .options(selectinload(Lesson.module).selectinload(Module.course))
            .where(Lesson.id == item.id)
        )
        return _lesson_row(item, version)

    async def update_lesson(self, lesson_id: str, data: dict[str, Any]) -> dict[str, Any]:
        item = await self.session.get(Lesson, parse_uuid(lesson_id), options=[selectinload(Lesson.module).selectinload(Module.course)])
        if item is None:
            raise ContentNotFound("الدرس غير موجود")
        latest = await self._latest_version(item.id)
        if latest is None:
            raise ContentConflict("إصدار محتوى الدرس غير موجود")
        changed_content = any(key in data for key in ("content_body", "change_summary", "status"))
        if "title" in data:
            item.title = _required_text(data, "title")
            if "slug" not in data:
                item.slug = slug_for(item.title)
        if "slug" in data:
            item.slug = _required_text(data, "slug")
        if "summary" in data:
            item.summary = str(data["summary"] or "").strip() or None
        if "position" in data:
            item.position = max(0, int(data["position"]))
        if "status" in data:
            item.status = _status(data["status"])
        if changed_content:
            body = _required_text(data, "content_body", maximum=200_000) if "content_body" in data else latest.content_body
            status = item.status
            version = LessonVersion(
                lesson_id=item.id, version_number=latest.version_number + 1,
                content_body=body, content_metadata=dict(latest.content_metadata or {}),
                change_summary=str(data.get("change_summary") or "تحديث محتوى الدرس")[:500],
                status=status,
                published_at=datetime.now(timezone.utc) if status == ContentStatus.PUBLISHED else None,
            )
            self.session.add(version)
            latest = version
        await self.session.flush()
        return _lesson_row(item, latest)

    async def delete_lesson(self, lesson_id: str) -> str:
        item = await self.session.get(Lesson, parse_uuid(lesson_id))
        if item is None:
            raise ContentNotFound("الدرس غير موجود")
        identifier = str(item.id)
        await self.session.delete(item)
        return identifier

    async def _append_version(self, lesson: Lesson, latest: LessonVersion, *, body: str | None = None, metadata: dict[str, Any] | None = None, change: str) -> LessonVersion:
        version = LessonVersion(
            lesson_id=lesson.id, version_number=latest.version_number + 1,
            content_body=body if body is not None else latest.content_body,
            content_metadata=metadata if metadata is not None else dict(latest.content_metadata or {}),
            change_summary=change[:500], status=lesson.status,
            published_at=datetime.now(timezone.utc) if lesson.status == ContentStatus.PUBLISHED else None,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def list_assets(self, lesson_id: str, *, category: str = "assets") -> list[dict[str, Any]]:
        lesson = await self.session.get(Lesson, parse_uuid(lesson_id))
        if lesson is None:
            raise ContentNotFound("الدرس غير موجود")
        latest = await self._latest_version(lesson.id)
        return list((latest.content_metadata or {}).get(category, [])) if latest else []

    async def add_asset(self, lesson_id: str, asset: dict[str, Any], *, category: str = "assets") -> dict[str, Any]:
        lesson = await self.session.get(Lesson, parse_uuid(lesson_id))
        if lesson is None:
            raise ContentNotFound("الدرس غير موجود")
        latest = await self._latest_version(lesson.id)
        if latest is None:
            raise ContentConflict("إصدار محتوى الدرس غير موجود")
        metadata = dict(latest.content_metadata or {})
        rows = list(metadata.get(category, []))
        rows.append(asset)
        metadata[category] = rows
        await self._append_version(lesson, latest, metadata=metadata, change="إرفاق ملف محتوى")
        return asset

    async def delete_asset(self, lesson_id: str, asset_id: str, *, category: str = "assets") -> dict[str, Any]:
        lesson = await self.session.get(Lesson, parse_uuid(lesson_id))
        if lesson is None:
            raise ContentNotFound("الدرس غير موجود")
        latest = await self._latest_version(lesson.id)
        if latest is None:
            raise ContentNotFound("الملف غير موجود")
        metadata = dict(latest.content_metadata or {})
        rows = list(metadata.get(category, []))
        found = next((row for row in rows if row.get("id") == asset_id), None)
        if found is None:
            raise ContentNotFound("الملف غير موجود")
        metadata[category] = [row for row in rows if row.get("id") != asset_id]
        await self._append_version(lesson, latest, metadata=metadata, change="إزالة ملف من المحتوى")
        return found

    async def find_asset(self, asset_id: str) -> tuple[str, dict[str, Any], str] | None:
        # Metadata is JSON so this portable lookup inspects only each lesson's
        # latest immutable version; deleted assets are not downloadable.
        latest_versions = (
            select(LessonVersion.lesson_id, func.max(LessonVersion.version_number).label("max_version"))
            .group_by(LessonVersion.lesson_id).subquery()
        )
        rows = (await self.session.scalars(
            select(LessonVersion).join(
                latest_versions,
                (LessonVersion.lesson_id == latest_versions.c.lesson_id)
                & (LessonVersion.version_number == latest_versions.c.max_version),
            )
        )).all()
        for version in rows:
            metadata = version.content_metadata or {}
            for category in ("assets", "images"):
                for asset in metadata.get(category, []):
                    if asset.get("id") == asset_id:
                        return str(version.lesson_id), asset, category
        return None

    async def add_video_link(self, lesson_id: str, url: str, label: str) -> dict[str, Any]:
        lesson = await self.session.get(Lesson, parse_uuid(lesson_id))
        if lesson is None:
            raise ContentNotFound("الدرس غير موجود")
        latest = await self._latest_version(lesson.id)
        if latest is None:
            raise ContentConflict("إصدار محتوى الدرس غير موجود")
        metadata = dict(latest.content_metadata or {})
        links = list(metadata.get("video_links", []))
        if any(item.get("url") == url for item in links):
            raise ContentConflict("رابط الفيديو موجود بالفعل")
        item = {"id": str(uuid4()), "url": url, "label": label[:120], "created_at": datetime.now(timezone.utc).isoformat()}
        links.append(item)
        metadata["video_links"] = links
        await self._append_version(lesson, latest, metadata=metadata, change="إضافة رابط فيديو")
        return item

    async def delete_video_link(self, lesson_id: str, link_id: str) -> dict[str, Any]:
        lesson = await self.session.get(Lesson, parse_uuid(lesson_id))
        if lesson is None:
            raise ContentNotFound("الدرس غير موجود")
        latest = await self._latest_version(lesson.id)
        if latest is None:
            raise ContentNotFound("رابط الفيديو غير موجود")
        metadata = dict(latest.content_metadata or {})
        links = list(metadata.get("video_links", []))
        found = next((item for item in links if item.get("id") == link_id), None)
        if found is None:
            raise ContentNotFound("رابط الفيديو غير موجود")
        metadata["video_links"] = [item for item in links if item.get("id") != link_id]
        await self._append_version(lesson, latest, metadata=metadata, change="إزالة رابط فيديو")
        return found

    async def update_video_link(self, lesson_id: str, link_id: str, url: str, label: str) -> dict[str, Any]:
        lesson = await self.session.get(Lesson, parse_uuid(lesson_id))
        if lesson is None:
            raise ContentNotFound("الدرس غير موجود")
        latest = await self._latest_version(lesson.id)
        if latest is None:
            raise ContentNotFound("إصدار محتوى الدرس غير موجود")
        metadata = dict(latest.content_metadata or {})
        links = list(metadata.get("video_links", []))
        found = next((item for item in links if item.get("id") == link_id), None)
        if found is None:
            raise ContentNotFound("رابط الفيديو غير موجود")
        if any(item.get("id") != link_id and item.get("url") == url for item in links):
            raise ContentConflict("رابط الفيديو موجود بالفعل")
        updated = {**found, "url": url, "label": label[:120]}
        metadata["video_links"] = [updated if item.get("id") == link_id else item for item in links]
        await self._append_version(lesson, latest, metadata=metadata, change="تعديل رابط فيديو")
        return updated

    async def course_relationships(self, course_id: str) -> dict[str, Any]:
        course = await self.session.get(Course, parse_uuid(course_id))
        if course is None:
            raise ContentNotFound("الدورة غير موجودة")
        rows = (await self.session.scalars(
            select(CoursePrerequisite).options(selectinload(CoursePrerequisite.prerequisite_course))
            .where(CoursePrerequisite.course_id == course.id)
        )).all()
        return {"course_id": str(course.id), "prerequisites": [
            {"id": str(row.prerequisite_course.id), "title": row.prerequisite_course.title}
            for row in rows
        ]}

    async def set_course_relationships(self, course_id: str, prerequisite_ids: list[str]) -> dict[str, Any]:
        course = await self.session.get(Course, parse_uuid(course_id))
        if course is None:
            raise ContentNotFound("الدورة غير موجودة")
        ids = {parse_uuid(value) for value in prerequisite_ids}
        if course.id in ids:
            raise ValueError("لا يمكن أن تكون الدورة متطلبًا لنفسها")
        rows = (await self.session.scalars(select(Course).where(Course.id.in_(ids)))).all() if ids else []
        if len(rows) != len(ids):
            raise ContentNotFound("أحد المتطلبات غير موجود")
        await self.session.execute(
            CoursePrerequisite.__table__.delete().where(CoursePrerequisite.course_id == course.id)
        )
        for prerequisite_id in ids:
            self.session.add(CoursePrerequisite(course_id=course.id, prerequisite_course_id=prerequisite_id))
        await self.session.flush()
        return await self.course_relationships(str(course.id))

    async def validate_path(self, path_id: str) -> dict[str, Any]:
        path = await self.session.get(LearningPath, parse_uuid(path_id), options=[selectinload(LearningPath.courses).selectinload(Course.modules).selectinload(Module.lessons).selectinload(Lesson.versions)])
        if path is None:
            raise ContentNotFound("مسار التعلم غير موجود")
        errors: list[str] = []
        for course in path.courses:
            if not course.modules:
                errors.append(f"الدورة «{course.title}» بلا وحدات")
            for module in course.modules:
                if not module.lessons:
                    errors.append(f"الوحدة «{module.title}» بلا دروس")
                for lesson in module.lessons:
                    latest = max(lesson.versions, key=lambda item: item.version_number, default=None)
                    if latest is None or not latest.content_body.strip():
                        errors.append(f"الدرس «{lesson.title}» بلا محتوى")
        return {"valid": not errors, "path_id": str(path.id), "errors": errors}

    async def publish_path(self, path_id: str) -> dict[str, Any]:
        validation = await self.validate_path(path_id)
        if not validation["valid"]:
            raise ValueError("لا يمكن نشر المسار: " + "؛ ".join(validation["errors"][:8]))
        path = await self.session.get(LearningPath, parse_uuid(path_id), options=[selectinload(LearningPath.courses).selectinload(Course.modules).selectinload(Module.lessons).selectinload(Lesson.versions)])
        path.status = ContentStatus.PUBLISHED
        courses = modules = lessons = 0
        for course in path.courses:
            course.status = ContentStatus.PUBLISHED; courses += 1
            for module in course.modules:
                module.status = ContentStatus.PUBLISHED; modules += 1
                for lesson in module.lessons:
                    lesson.status = ContentStatus.PUBLISHED; lessons += 1
                    latest = max(lesson.versions, key=lambda item: item.version_number, default=None)
                    if latest:
                        latest.status = ContentStatus.PUBLISHED
                        latest.published_at = datetime.now(timezone.utc)
        await self.session.flush()
        return {"published": True, "path_id": str(path.id), "courses": courses, "modules": modules, "lessons": lessons}

    async def copy_course(self, course_id: str, title: str) -> dict[str, Any]:
        source = await self.session.get(Course, parse_uuid(course_id), options=[selectinload(Course.modules).selectinload(Module.lessons).selectinload(Lesson.versions)])
        if source is None:
            raise ContentNotFound("الدورة غير موجودة")
        title = _required_text({"title": title}, "title")
        copy = Course(learning_path_id=source.learning_path_id, title=title, slug=slug_for(title), summary=source.summary, position=source.position, status=ContentStatus.DRAFT)
        self.session.add(copy); await self.session.flush()
        for source_module in source.modules:
            module = Module(course_id=copy.id, title=source_module.title, slug=slug_for(source_module.title), description=source_module.description, position=source_module.position, status=ContentStatus.DRAFT)
            self.session.add(module); await self.session.flush()
            for source_lesson in source_module.lessons:
                lesson = Lesson(module_id=module.id, title=source_lesson.title, slug=slug_for(source_lesson.title), summary=source_lesson.summary, position=source_lesson.position, status=ContentStatus.DRAFT)
                self.session.add(lesson); await self.session.flush()
                latest = max(source_lesson.versions, key=lambda item: item.version_number, default=None)
                self.session.add(LessonVersion(lesson_id=lesson.id, version_number=1, content_body=latest.content_body if latest else "محتوى جديد", content_metadata=dict(latest.content_metadata or {}) if latest else {}, change_summary="نسخ الدورة", status=ContentStatus.DRAFT))
        await self.session.flush()
        return _course_row(copy)

    async def reorder(self, *, entity: str, parent_id: str, ordered_ids: list[str]) -> list[str]:
        parent = parse_uuid(parent_id)
        model, parent_field = {
            "courses": (Course, Course.learning_path_id),
            "modules": (Module, Module.course_id),
            "lessons": (Lesson, Lesson.module_id),
        }[entity]
        ids = [parse_uuid(value) for value in ordered_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("قائمة الترتيب تحتوي عناصر مكررة")
        rows = (await self.session.scalars(select(model).where(parent_field == parent))).all()
        existing = {row.id: row for row in rows}
        if set(existing) != set(ids):
            raise ValueError("يجب إرسال جميع العناصر التابعة للترتيب")
        for index, identifier in enumerate(ids):
            existing[identifier].position = index
        await self.session.flush()
        return [str(identifier) for identifier in ids]

    async def move(self, *, entity: str, parent_id: str, item_id: str, direction: str) -> list[str]:
        parent = parse_uuid(parent_id)
        identifier = parse_uuid(item_id)
        model, parent_field = {
            "courses": (Course, Course.learning_path_id),
            "modules": (Module, Module.course_id),
            "lessons": (Lesson, Lesson.module_id),
        }[entity]
        rows = list((await self.session.scalars(
            select(model).where(parent_field == parent).order_by(model.position, model.id)
        )).all())
        index = next((i for i, row in enumerate(rows) if row.id == identifier), None)
        if index is None:
            raise ContentNotFound("العنصر غير موجود ضمن الحاوية المطلوبة")
        if direction not in {"up", "down"}:
            raise ValueError("اتجاه الترتيب غير صالح")
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(rows):
            rows[index], rows[target] = rows[target], rows[index]
            for position, row in enumerate(rows):
                row.position = position
            await self.session.flush()
        return [str(row.id) for row in rows]
