"""Role-based authorization SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base, TimestampMixin
from app.identity.models import User


class Role(TimestampMixin, Base):
    """A named set of permissions assignable to users."""

    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        viewonly=True,
        overlaps="role_permissions,roles",
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
        viewonly=True,
        overlaps="user_roles,users",
    )
    scopes: Mapped[list["RoleScope"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )


class Permission(TimestampMixin, Base):
    """An action that can be granted for a resource."""

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint(
            "resource",
            "action",
            name="uq_permissions_resource_action",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission",
        cascade="all, delete-orphan",
    )
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        viewonly=True,
        overlaps="role_permissions,permissions",
    )


class RolePermission(Base):
    """Association table linking roles to permissions."""

    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    role: Mapped["Role"] = relationship(back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship(
        back_populates="role_permissions",
    )


class UserRole(Base):
    """Association table assigning a role to a user."""

    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_id", "role_id"),)

    # Match the Telegram identity key used by the existing runtime store.
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_roles",
    )
    role: Mapped["Role"] = relationship(back_populates="user_roles")


class UserPermission(Base):
    """A per-user grant or explicit denial that overrides role membership."""

    __tablename__ = "user_permissions"
    __table_args__ = (
        Index("ix_user_permissions_permission_id", "permission_id"),
        CheckConstraint(
            "expires_at IS NULL OR expires_at > granted_at",
            name="expiry_after_grant",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    granted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )

    permission: Mapped["Permission"] = relationship()
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        primaryjoin="UserPermission.user_id == User.telegram_id",
    )


class AdminAccount(Base):
    """Administrative access state without changing normal user accounts."""

    __tablename__ = "admin_accounts"
    __table_args__ = (
        CheckConstraint(
            "(is_enabled = true AND disabled_at IS NULL) "
            "OR (is_enabled = false AND disabled_at IS NOT NULL)",
            name="ck_admin_accounts_enabled_state",
        ),
        Index("ix_admin_accounts_is_enabled", "is_enabled"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disabled_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        onupdate=func.now(),
    )


class RoleScope(TimestampMixin, Base):
    """A resource scope within which a role is effective."""

    __tablename__ = "role_scopes"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "scope_type",
            "scope_value",
            name="uq_role_scopes_role_type_value",
        ),
        CheckConstraint(
            "length(trim(scope_type)) > 0",
            name="scope_type_not_blank",
        ),
        CheckConstraint(
            "length(trim(scope_value)) > 0",
            name="scope_value_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(255), nullable=False)
    is_inclusive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    role: Mapped["Role"] = relationship(back_populates="scopes")
