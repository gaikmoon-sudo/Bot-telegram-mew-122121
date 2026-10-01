"""Assessment, quiz, and answer SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Enum as SQLAlchemyEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.content.models import ContentStatus, content_status_type
from infrastructure.database.base import Base, json_default


JSONType = JSON().with_variant(JSONB, "postgresql")


class QuestionType(str, Enum):
    """Supported question formats."""

    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_TEXT = "SHORT_TEXT"


class QuizAttemptStatus(str, Enum):
    """Lifecycle states for a quiz attempt."""

    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"
    ABANDONED = "ABANDONED"


def question_type_enum() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        QuestionType,
        name="question_type",
        native_enum=True,
        values_callable=lambda enum_type: [
            question_type.value for question_type in enum_type
        ],
    )


def quiz_attempt_status_enum() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        QuizAttemptStatus,
        name="quiz_attempt_status",
        native_enum=True,
        values_callable=lambda enum_type: [
            status.value for status in enum_type
        ],
    )


class Quiz(Base):
    """A quiz attached to a course, a lesson, or both."""

    __tablename__ = "quizzes"
    __table_args__ = (
        CheckConstraint(
            "(course_id IS NOT NULL) OR (lesson_id IS NOT NULL)",
            name="ck_quizzes_has_parent_content",
        ),
        CheckConstraint(
            "passing_score >= 0 AND passing_score <= 100",
            name="ck_quizzes_passing_score_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    course_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=True,
    )
    lesson_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    passing_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=70,
        server_default="70",
    )
    status: Mapped[ContentStatus] = mapped_column(
        content_status_type(),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=ContentStatus.DRAFT.value,
    )

    course: Mapped["Course | None"] = relationship("Course")
    lesson: Mapped["Lesson | None"] = relationship("Lesson")
    quiz_questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.position",
    )
    attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
    )


class Question(Base):
    """A reusable question that can appear in multiple quizzes."""

    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(
            "points > 0",
            name="ck_questions_points_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    question_type: Mapped[QuestionType] = mapped_column(
        question_type_enum(),
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    quiz_questions: Mapped[list["QuizQuestion"]] = relationship(
        back_populates="question",
    )
    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.position",
    )
    answers: Mapped[list["QuizAnswer"]] = relationship(
        back_populates="question",
    )


class QuizQuestion(Base):
    """Association that orders reusable questions inside a quiz."""

    __tablename__ = "quiz_questions"
    __table_args__ = (
        UniqueConstraint(
            "quiz_id",
            "question_id",
            name="uq_quiz_questions_quiz_question",
        ),
        UniqueConstraint(
            "quiz_id",
            "position",
            name="uq_quiz_questions_quiz_position",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_quiz_questions_position_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    quiz_id: Mapped[UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    points_override: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    quiz: Mapped["Quiz"] = relationship(back_populates="quiz_questions")
    question: Mapped["Question"] = relationship(
        back_populates="quiz_questions",
    )


class QuestionOption(Base):
    """An answer option for a choice-based question."""

    __tablename__ = "question_options"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "position",
            name="uq_question_options_question_position",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_question_options_position_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_correct: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    question: Mapped["Question"] = relationship(back_populates="options")


class QuizAttempt(Base):
    """One user's attempt at a quiz."""

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        UniqueConstraint(
            "quiz_id",
            "user_id",
            "attempt_number",
            name="uq_quiz_attempts_quiz_user_number",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_quiz_attempts_attempt_number_positive",
        ),
        CheckConstraint(
            "score_percent >= 0 AND score_percent <= 100",
            name="ck_quiz_attempts_score_percent_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    quiz_id: Mapped[UUID] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[QuizAttemptStatus] = mapped_column(
        quiz_attempt_status_enum(),
        nullable=False,
        default=QuizAttemptStatus.IN_PROGRESS,
        server_default=QuizAttemptStatus.IN_PROGRESS.value,
    )
    score_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    earned_points: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    max_points: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    quiz: Mapped["Quiz"] = relationship(back_populates="attempts")
    user: Mapped["User"] = relationship("User")
    answers: Mapped[list["QuizAnswer"]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class QuizAnswer(Base):
    """A user's answer to one question in a quiz attempt."""

    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint(
            "attempt_id",
            "question_id",
            name="uq_quiz_answers_attempt_question",
        ),
        CheckConstraint(
            "points_earned >= 0",
            name="ck_quiz_answers_points_earned_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    attempt_id: Mapped[UUID] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_option_ids: Mapped[list[str] | None] = mapped_column(
        JSONType,
        nullable=True,
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    points_earned: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    attempt: Mapped["QuizAttempt"] = relationship(
        back_populates="answers",
    )
    question: Mapped["Question"] = relationship(
        back_populates="answers",
    )