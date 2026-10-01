"""Educational content and publishing SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Enum as SQLAlchemyEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base, TimestampMixin, json_default


class ContentStatus(str, Enum):
    """Lifecycle states shared by publishable content."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


JSONType = JSON().with_variant(JSONB, "postgresql")


def content_status_type() -> SQLAlchemyEnum:
    """Return the native PostgreSQL enum used by content tables."""
    return SQLAlchemyEnum(
        ContentStatus,
        name="content_status",
        native_enum=True,
        values_callable=lambda enum_type: [
            status.value for status in enum_type
        ],
    )


def status_column() -> Mapped[ContentStatus]:
    """Type annotation helper for content status columns."""
    return mapped_column(
        content_status_type(),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=ContentStatus.DRAFT.value,
    )


class LearningPath(TimestampMixin, Base):
    """An ordered learning journey made up of multiple courses."""

    __tablename__ = "learning_paths"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_learning_paths_title_not_blank",
        ),
        UniqueConstraint("slug", name="uq_learning_paths_slug"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ContentStatus] = status_column()

    courses: Mapped[list["Course"]] = relationship(
        back_populates="learning_path",
        cascade="all, delete-orphan",
        order_by="Course.position",
    )


class Course(TimestampMixin, Base):
    """A course belonging to one learning path."""

    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_courses_title_not_blank",
        ),
        UniqueConstraint(
            "learning_path_id",
            "slug",
            name="uq_courses_learning_path_slug",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    learning_path_id: Mapped[UUID] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    status: Mapped[ContentStatus] = status_column()

    learning_path: Mapped["LearningPath"] = relationship(
        back_populates="courses",
    )
    modules: Mapped[list["Module"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Module.position",
    )
    prerequisites: Mapped[list["CoursePrerequisite"]] = relationship(
        "CoursePrerequisite",
        back_populates="course",
        foreign_keys=lambda: [CoursePrerequisite.course_id],
        cascade="all, delete-orphan",
    )
    required_for: Mapped[list["CoursePrerequisite"]] = relationship(
        "CoursePrerequisite",
        back_populates="prerequisite_course",
        foreign_keys=lambda: [CoursePrerequisite.prerequisite_course_id],
        cascade="all, delete-orphan",
    )


class CoursePrerequisite(Base):
    """A directed prerequisite relationship between two courses."""

    __tablename__ = "course_prerequisites"
    __table_args__ = (
        CheckConstraint(
            "course_id <> prerequisite_course_id",
            name="ck_course_prerequisites_not_self_referential",
        ),
    )

    course_id: Mapped[UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    prerequisite_course_id: Mapped[UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )

    course: Mapped["Course"] = relationship(
        "Course",
        foreign_keys=[course_id],
        back_populates="prerequisites",
    )
    prerequisite_course: Mapped["Course"] = relationship(
        "Course",
        foreign_keys=[prerequisite_course_id],
        back_populates="required_for",
    )


class Module(TimestampMixin, Base):
    """An ordered unit within a course."""

    __tablename__ = "modules"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_modules_title_not_blank",
        ),
        UniqueConstraint(
            "course_id",
            "slug",
            name="uq_modules_course_slug",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    course_id: Mapped[UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    status: Mapped[ContentStatus] = status_column()

    course: Mapped["Course"] = relationship(back_populates="modules")
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="Lesson.position",
    )


class Lesson(TimestampMixin, Base):
    """An ordered lesson within a module."""

    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_lessons_title_not_blank",
        ),
        UniqueConstraint(
            "module_id",
            "slug",
            name="uq_lessons_module_slug",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    module_id: Mapped[UUID] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    status: Mapped[ContentStatus] = status_column()

    module: Mapped["Module"] = relationship(back_populates="lessons")
    versions: Mapped[list["LessonVersion"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LessonVersion.version_number",
    )


class LessonVersion(Base):
    """An immutable version of a lesson's educational content."""

    __tablename__ = "lesson_versions"
    __table_args__ = (
        CheckConstraint(
            "version_number > 0",
            name="ck_lesson_versions_version_number_positive",
        ),
        CheckConstraint(
            "length(trim(content_body)) > 0",
            name="ck_lesson_versions_content_not_blank",
        ),
        UniqueConstraint(
            "lesson_id",
            "version_number",
            name="uq_lesson_versions_lesson_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    lesson_id: Mapped[UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_body: Mapped[str] = mapped_column(Text, nullable=False)
    content_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ContentStatus] = status_column()
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    lesson: Mapped["Lesson"] = relationship(back_populates="versions")


class ContentRevision(Base):
    """An audit snapshot for a change to any content entity."""

    __tablename__ = "content_revisions"
    __table_args__ = (
        CheckConstraint(
            "length(trim(content_type)) > 0",
            name="ck_content_revisions_content_type_not_blank",
        ),
        CheckConstraint(
            "revision_number > 0",
            name="ck_content_revisions_revision_number_positive",
        ),
        Index(
            "ix_content_revisions_content",
            "content_type",
            "content_id",
        ),
        UniqueConstraint(
            "content_type",
            "content_id",
            "revision_number",
            name="uq_content_revisions_content_revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ContentStatus] = status_column()
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Tag(TimestampMixin, Base):
    """A reusable label for categorizing educational content."""

    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    content_tags: Mapped[list["ContentTag"]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class ContentTag(Base):
    """Polymorphic association between a tag and a content entity."""

    __tablename__ = "content_tags"
    __table_args__ = (
        CheckConstraint(
            "length(trim(content_type)) > 0",
            name="ck_content_tags_content_type_not_blank",
        ),
        Index(
            "ix_content_tags_content",
            "content_type",
            "content_id",
        ),
    )

    content_type: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )
    content_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
    )
    tag_id: Mapped[UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    tag: Mapped["Tag"] = relationship(back_populates="content_tags")