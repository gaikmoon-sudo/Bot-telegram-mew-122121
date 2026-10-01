"""Gamification and rewards SQLAlchemy models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base, json_default


JSONType = JSON().with_variant(JSONB, "postgresql")


class PointsTransaction(Base):
    """An immutable points ledger entry with an idempotency key."""

    __tablename__ = "points_transactions"
    __table_args__ = (
        CheckConstraint(
            "points <> 0",
            name="ck_points_transactions_points_non_zero",
        ),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_points_transactions_user_idempotency",
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
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    reference_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    transaction_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")


class Badge(Base):
    """A reward definition that can be awarded to users."""

    __tablename__ = "badges"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    points_reward: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    criteria: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )

    user_badges: Mapped[list["UserBadge"]] = relationship(
        back_populates="badge",
        cascade="all, delete-orphan",
    )


class UserBadge(Base):
    """An award of one badge to one user."""

    __tablename__ = "user_badges"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "badge_id",
            name="uq_user_badges_user_badge",
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
    badge_id: Mapped[UUID] = mapped_column(
        ForeignKey("badges.id", ondelete="CASCADE"),
        nullable=False,
    )
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    award_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )

    user: Mapped["User"] = relationship("User")
    badge: Mapped["Badge"] = relationship(back_populates="user_badges")


class UserStreak(Base):
    """Current and longest consecutive activity streak for a user."""

    __tablename__ = "user_streaks"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    current_streak: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    longest_streak: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_activity_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")