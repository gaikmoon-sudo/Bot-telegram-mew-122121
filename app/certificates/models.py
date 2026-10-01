"""Certificate templates, issued certificates, and certificate events."""

from __future__ import annotations

from datetime import datetime
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
    UniqueConstraint,
    Enum as SQLAlchemyEnum,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base, TimestampMixin, json_default


JSONType = JSON().with_variant(JSONB, "postgresql")


class CertificateStatus(str, Enum):
    """Lifecycle states for an issued certificate."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class CertificateEventType(str, Enum):
    """Events recorded against a certificate."""

    ISSUED = "ISSUED"
    REVOKED = "REVOKED"
    REINSTATED = "REINSTATED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"


def certificate_status_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        CertificateStatus,
        name="certificate_status",
        native_enum=True,
        values_callable=lambda enum_type: [
            status.value for status in enum_type
        ],
    )


def certificate_event_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        CertificateEventType,
        name="certificate_event_type",
        native_enum=True,
        values_callable=lambda enum_type: [
            event.value for event in enum_type
        ],
    )


class CertificateTemplate(TimestampMixin, Base):
    """A reusable template used to render certificates."""

    __tablename__ = "certificate_templates"
    __table_args__ = (
        UniqueConstraint(
            "code",
            name="uq_certificate_templates_code",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_certificate_templates_name_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_body: Mapped[str] = mapped_column(Text, nullable=False)
    template_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    version: Mapped[int] = mapped_column(
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

    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="template",
    )


class Certificate(TimestampMixin, Base):
    """An issued certificate with globally unique identifiers."""

    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint(
            "certificate_number",
            name="uq_certificates_certificate_number",
        ),
        UniqueConstraint(
            "verification_code",
            name="uq_certificates_verification_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    certificate_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    verification_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("certificate_templates.id", ondelete="RESTRICT"),
        nullable=False,
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
    status: Mapped[CertificateStatus] = mapped_column(
        certificate_status_type(),
        nullable=False,
        default=CertificateStatus.ACTIVE,
        server_default=CertificateStatus.ACTIVE.value,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    template: Mapped["CertificateTemplate"] = relationship(
        back_populates="certificates",
    )
    user: Mapped["User"] = relationship("User")
    enrollment: Mapped["Enrollment | None"] = relationship("Enrollment")
    course: Mapped["Course | None"] = relationship("Course")
    events: Mapped[list["CertificateEvent"]] = relationship(
        back_populates="certificate",
        cascade="all, delete-orphan",
    )


class CertificateEvent(Base):
    """An immutable audit event for an issued certificate."""

    __tablename__ = "certificate_events"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    certificate_id: Mapped[UUID] = mapped_column(
        ForeignKey("certificates.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[CertificateEventType] = mapped_column(
        certificate_event_type(),
        nullable=False,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONType,
        nullable=False,
        default=json_default,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    certificate: Mapped["Certificate"] = relationship(
        back_populates="events",
    )
    actor: Mapped["User | None"] = relationship("User")