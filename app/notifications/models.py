"""Notification campaign, delivery, preference, and worker models."""

from __future__ import annotations

from datetime import datetime, time
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
    String,
    Text,
    Time,
    UniqueConstraint,
    Enum as SQLAlchemyEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base, TimestampMixin, json_default


JSONType = JSON().with_variant(JSONB, "postgresql")


class NotificationCampaignStatus(str, Enum):
    """Lifecycle states for a notification campaign."""

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class NotificationDeliveryStatus(str, Enum):
    """Delivery states tracked per recipient."""

    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    READ = "READ"


class NotificationChannel(str, Enum):
    """Supported notification delivery channels."""

    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    TELEGRAM = "TELEGRAM"


class ScheduledJobStatus(str, Enum):
    """Worker lifecycle states for scheduled jobs."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def campaign_status_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        NotificationCampaignStatus,
        name="notification_campaign_status",
        native_enum=True,
        values_callable=lambda enum_type: [
            status.value for status in enum_type
        ],
    )


def delivery_status_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        NotificationDeliveryStatus,
        name="notification_delivery_status",
        native_enum=True,
        values_callable=lambda enum_type: [
            status.value for status in enum_type
        ],
    )


def notification_channel_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        NotificationChannel,
        name="notification_channel",
        native_enum=True,
        values_callable=lambda enum_type: [
            channel.value for channel in enum_type
        ],
    )


def scheduled_job_status_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        ScheduledJobStatus,
        name="scheduled_job_status",
        native_enum=True,
        values_callable=lambda enum_type: [
            status.value for status in enum_type
        ],
    )


class NotificationCampaign(TimestampMixin, Base):
    """A reusable campaign that can target many users."""

    __tablename__ = "notification_campaigns"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_notification_campaigns_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(body)) > 0",
            name="ck_notification_campaigns_body_not_blank",
        ),
        UniqueConstraint(
            "name",
            name="uq_notification_campaigns_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    notification_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        notification_channel_type(),
        nullable=False,
    )
    audience_filter: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    status: Mapped[NotificationCampaignStatus] = mapped_column(
        campaign_status_type(),
        nullable=False,
        default=NotificationCampaignStatus.DRAFT,
        server_default=NotificationCampaignStatus.DRAFT.value,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class NotificationDelivery(Base):
    """The delivery state of one campaign for one recipient."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "user_id",
            "channel",
            name="uq_notification_deliveries_campaign_user_channel",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_notification_deliveries_attempt_count_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("notification_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        notification_channel_type(),
        nullable=False,
    )
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        delivery_status_type(),
        nullable=False,
        default=NotificationDeliveryStatus.PENDING,
        server_default=NotificationDeliveryStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped["NotificationCampaign"] = relationship(
        back_populates="deliveries",
    )
    user: Mapped["User"] = relationship("User")


class NotificationPreference(Base):
    """Per-user opt-in setting for a notification type and channel."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "notification_type",
            "channel",
            name="uq_notification_preferences_user_type_channel",
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
    notification_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        notification_channel_type(),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    quiet_hours_start: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )
    quiet_hours_end: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User")


class ScheduledJob(TimestampMixin, Base):
    """A durable job record claimed by background workers."""

    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_scheduled_jobs_attempt_count_non_negative",
        ),
        CheckConstraint(
            "max_attempts > 0",
            name="ck_scheduled_jobs_max_attempts_positive",
        ),
        UniqueConstraint(
            "job_key",
            name="uq_scheduled_jobs_job_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    job_key: Mapped[str] = mapped_column(String(255), nullable=False)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    status: Mapped[ScheduledJobStatus] = mapped_column(
        scheduled_job_status_type(),
        nullable=False,
        default=ScheduledJobStatus.PENDING,
        server_default=ScheduledJobStatus.PENDING.value,
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)