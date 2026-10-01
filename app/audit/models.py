"""Security, administrative audit, and system setting models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
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
from app.identity.models import User


JSONType = JSON().with_variant(JSONB, "postgresql")


class AuditOutcome(str, Enum):
    """Result of the audited operation."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


def audit_outcome_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        AuditOutcome,
        name="audit_outcome",
        native_enum=True,
        values_callable=lambda enum_type: [
            outcome.value for outcome in enum_type
        ],
    )


class AuditLog(Base):
    """Immutable record of security and administrative activity."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_user_id", "actor_user_id"),
        Index("ix_audit_logs_occurred_at", "occurred_at"),
        CheckConstraint(
            "length(trim(action)) > 0",
            name="action_not_blank",
        ),
        CheckConstraint(
            "length(trim(resource_type)) > 0",
            name="resource_type_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=True,
    )
    resource_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[AuditOutcome] = mapped_column(
        audit_outcome_type(),
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    actor: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[actor_user_id],
        primaryjoin="AuditLog.actor_user_id == User.telegram_id",
    )


class SystemSetting(TimestampMixin, Base):
    """A typed JSON-backed setting controlled by administrators."""

    __tablename__ = "system_settings"
    __table_args__ = (
        UniqueConstraint(
            "key",
            name="uq_system_settings_key",
        ),
        CheckConstraint(
            "length(trim(key)) > 0",
            name="ck_system_settings_key_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    updated_by: Mapped["User | None"] = relationship("User")
