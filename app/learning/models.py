"""Learning progress and analytics SQLAlchemy models."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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

from infrastructure.database.base import Base, json_default


JSONType = JSON().with_variant(JSONB, "postgresql")


class EnrollmentStatus(str, Enum):
    """Lifecycle states for a user's enrollment."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    DROPPED = "DROPPED"


class ProgressEventType(str, Enum):
    """Events recorded for learning analytics."""

    STARTED = "STARTED"
    LESSON_OPENED = "LESSON_OPENED"
    LESSON_COMPLETED = "LESSON_COMPLETED"
    COURSE_COMPLETED = "COURSE_COMPLETED"
    PATH_COMPLETED = "PATH_COMPLETED"


def enrollment_status_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        EnrollmentStatus,
        name="enrollment_status",
        native_enum=True,
        values_callable=lambda enum_type: [
            status.value for status in enum_type
        ],
    )


def progress_event_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        ProgressEventType,
        name="progress_event_type",
        native_enum=True,
        values_callable=lambda enum_type: [
            event.value for event in enum_type
        ],
    )


class Enrollment(Base):
    """Enrollment in exactly one learning path or one course."""

    __tablename__ = "enrollments"
    __table_args__ = (
        CheckConstraint(
            "(learning_path_id IS NOT NULL AND course_id IS NULL) "
            "OR (learning_path_id IS NULL AND course_id IS NOT NULL)",
            name="ck_enrollments_exactly_one_target",
        ),
        UniqueConstraint(
            "user_id",
            "learning_path_id",
            name="uq_enrollments_user_learning_path",
        ),
        UniqueConstraint(
            "user_id",
            "course_id",
            name="uq_enrollments_user_course",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    learning_path_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=True,
    )
    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=True,
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        enrollment_status_type(),
        nullable=False,
        default=EnrollmentStatus.ACTIVE,
        server_default=EnrollmentStatus.ACTIVE.value,
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["User"] = relationship("User")
    learning_path: Mapped["LearningPath | None"] = relationship(
        "LearningPath",
    )
    course: Mapped["Course | None"] = relationship("Course")
    lesson_progress: Mapped[list["LessonProgress"]] = relationship(
        back_populates="enrollment",
    )
    progress_events: Mapped[list["ProgressEvent"]] = relationship(
        back_populates="enrollment",
    )


class LessonProgress(Base):
    """The current progress of one user on one lesson."""

    __tablename__ = "lesson_progress"
    __table_args__ = (
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_lesson_progress_percent_range",
        ),
        UniqueConstraint(
            "user_id",
            "lesson_id",
            name="uq_lesson_progress_user_lesson",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    lesson_id: Mapped[UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("enrollments.id", ondelete="SET NULL"),
        nullable=True,
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["User"] = relationship("User")
    lesson: Mapped["Lesson"] = relationship("Lesson")
    enrollment: Mapped["Enrollment | None"] = relationship(
        back_populates="lesson_progress",
    )


class ProgressEvent(Base):
    """An immutable event used for progress analytics."""

    __tablename__ = "progress_events"
    __table_args__ = (
        CheckConstraint(
            "length(trim(event_name)) > 0",
            name="ck_progress_events_event_name_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    enrollment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("enrollments.id", ondelete="SET NULL"),
        nullable=True,
    )
    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
    )
    lesson_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[ProgressEventType] = mapped_column(
        progress_event_type(),
        nullable=False,
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")
    enrollment: Mapped["Enrollment | None"] = relationship(
        back_populates="progress_events",
    )
    course: Mapped["Course | None"] = relationship("Course")
    lesson: Mapped["Lesson | None"] = relationship("Lesson")


class UserFavorite(Base):
    """A user's favorite educational content item."""

    __tablename__ = "user_favorites"
    __table_args__ = (
        CheckConstraint(
            "length(trim(content_type)) > 0",
            name="ck_user_favorites_content_type_not_blank",
        ),
        UniqueConstraint(
            "user_id",
            "content_type",
            "content_id",
            name="uq_user_favorites_user_content",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")