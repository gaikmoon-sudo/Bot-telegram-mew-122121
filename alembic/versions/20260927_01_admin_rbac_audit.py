"""Create permission-based admin RBAC and audit tables.

Revision ID: 20260927_01
Revises: None
"""
from __future__ import annotations

from uuid import uuid4
import os

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "20260927_01"
down_revision = None
branch_labels = None
depends_on = None

_PERMISSION_ROWS = (
    ("*", "*", "All current and future permissions"),
    ("admin", "dashboard.view", "View the administrative landing page"),
    ("analytics", "view", "View administrative analytics"),
    ("users", "view", "View user records"),
    ("users", "manage", "Manage user accounts"),
    ("courses", "view", "View courses"),
    ("courses", "create", "Create courses"),
    ("courses", "edit", "Edit courses"),
    ("courses", "delete", "Delete courses"),
    ("modules", "view", "View modules"),
    ("modules", "create", "Create modules"),
    ("modules", "edit", "Edit modules"),
    ("modules", "delete", "Delete modules"),
    ("lessons", "view", "View lessons"),
    ("lessons", "create", "Create lessons"),
    ("lessons", "edit", "Edit lessons"),
    ("lessons", "delete", "Delete lessons"),
    ("text", "edit", "Edit lesson and course text"),
    ("content", "order", "Change content ordering"),
    ("files", "view", "View content files"),
    ("files", "upload", "Upload content files"),
    ("files", "delete", "Delete content files"),
    ("videos", "add_link", "Add or update video links"),
    ("videos", "manage", "Manage all video links"),
    ("images", "manage", "Manage course images"),
    ("ai", "manage", "Manage AI features and configuration"),
    ("payments", "view", "View payment records"),
    ("payments", "manage", "Manage payments and refunds"),
    ("certificates", "manage", "Manage certificates"),
    ("notifications", "manage", "Manage and send notifications"),
    ("bot", "settings", "Manage bot settings"),
    ("admins", "manage", "Manage administrator assignments"),
    ("permissions", "manage", "Manage roles and permissions"),
    ("security", "logs.view", "View security and audit logs"),
    ("security", "settings", "Manage security settings"),
    ("settings", "manage", "Manage system settings"),
)

_ROLE_GRANTS = {
    "SUPER_ADMIN": {"*.*"},
    "CONTENT_MANAGER": {
        "admin.dashboard.view",
        "courses.view", "courses.create", "courses.edit", "courses.delete",
        "modules.view", "modules.create", "modules.edit", "modules.delete",
        "lessons.view", "lessons.create", "lessons.edit", "lessons.delete",
        "text.edit", "content.order", "files.view", "files.upload",
        "files.delete", "videos.manage", "images.manage",
    },
    "CONTENT_EDITOR": {
        "lessons.view", "lessons.edit", "text.edit", "videos.add_link",
        "files.view", "files.upload",
    },
}


LEGACY_TABLES = (
    "users", "lesson_progress", "xp_events", "favorites", "user_stats",
    "quiz_attempts", "quiz_answers", "active_polls", "launch_notifications",
    "badges", "certificates", "certificate_payments", "custom_lessons",
    "code_drafts", "ai_messages", "ai_memory", "ai_usage", "ai_feedback",
)


def _ensure_identity_schema() -> None:
    """Create the normalized identity table and safely migrate the old runtime schema.

    Older releases created a Telegram-specific ``users`` table before Alembic ran.
    New releases use ``academy_*`` tables for that legacy runtime state and reserve
    ``users`` for the normalized UUID-backed identity/RBAC schema.
    """
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("users"):
        columns = {column["name"] for column in inspector.get_columns("users")}
        # Old runtime schema: telegram_id was the primary key and profile fields were
        # stored directly on users. Rename the complete legacy family before creating
        # the normalized identity table. PostgreSQL updates dependent FKs on rename.
        if "id" not in columns and "telegram_id" in columns:
            for table in LEGACY_TABLES:
                legacy_name = f"academy_{table}"
                if inspector.has_table(table) and not inspector.has_table(legacy_name):
                    op.rename_table(table, legacy_name)
            inspector = sa.inspect(bind)

    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("telegram_id", sa.BigInteger(), nullable=True),
            sa.Column("email", sa.String(320), nullable=True),
            sa.Column("username", sa.String(255), nullable=True),
            sa.Column("password_hash", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("email IS NOT NULL OR telegram_id IS NOT NULL", name="ck_users_contact_identifier"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # Copy legacy Telegram identities into the normalized identity table once.
    inspector = sa.inspect(bind)
    if inspector.has_table("academy_users"):
        rows = bind.execute(sa.text(
            "SELECT telegram_id, username FROM academy_users WHERE telegram_id IS NOT NULL"
        )).mappings().all()
        for row in rows:
            bind.execute(
                sa.text(
                    """INSERT INTO users (id, telegram_id, username, is_active, is_verified)
                       VALUES (:id, :telegram_id, :username, TRUE, FALSE)
                       ON CONFLICT (telegram_id) DO UPDATE SET username=EXCLUDED.username"""
                ),
                {"id": uuid4(), "telegram_id": int(row["telegram_id"]), "username": row["username"]},
            )


def _check_existing_identity_schema() -> None:
    """Verify the normalized identity contract used by RBAC."""
    if context.is_offline_mode():
        return
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")} if inspector.has_table("users") else set()
    required = {"id", "telegram_id", "is_active"}
    if not required.issubset(columns):
        raise RuntimeError("users table is incompatible with the normalized identity schema")


def upgrade() -> None:
    _ensure_identity_schema()
    _check_existing_identity_schema()
    uuid_type = postgresql.UUID(as_uuid=True)
    json_type = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "roles",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "permissions",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("resource", "action", name="uq_permissions_resource_action"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", uuid_type, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", uuid_type, sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", uuid_type, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", uuid_type, sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by_user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > granted_at", name="ck_user_permissions_expiry_after_grant"),
    )
    op.create_index("ix_user_permissions_permission_id", "user_permissions", ["permission_id"])
    op.create_table(
        "role_scopes",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("role_id", uuid_type, sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_value", sa.String(length=255), nullable=False),
        sa.Column("is_inclusive", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("role_id", "scope_type", "scope_value", name="uq_role_scopes_role_type_value"),
        sa.CheckConstraint("length(trim(scope_type)) > 0", name="ck_role_scopes_scope_type_not_blank"),
        sa.CheckConstraint("length(trim(scope_value)) > 0", name="ck_role_scopes_scope_value_not_blank"),
    )

    audit_outcome = postgresql.ENUM(
        "SUCCESS", "FAILURE", name="audit_outcome", create_type=False
    )
    audit_outcome.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "audit_logs",
        sa.Column("id", uuid_type, primary_key=True, nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", uuid_type, nullable=True),
        sa.Column("resource_key", sa.String(length=255), nullable=True),
        sa.Column("outcome", audit_outcome, nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
        sa.Column("details", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(action)) > 0", name="ck_audit_logs_action_not_blank"),
        sa.CheckConstraint("length(trim(resource_type)) > 0", name="ck_audit_logs_resource_type_not_blank"),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])

    permissions = sa.table(
        "permissions",
        sa.column("id", uuid_type),
        sa.column("resource", sa.String()),
        sa.column("action", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    roles = sa.table(
        "roles",
        sa.column("id", uuid_type),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_system", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    permission_ids = {f"{resource}.{action}": uuid4() for resource, action, _ in _PERMISSION_ROWS}
    op.bulk_insert(
        permissions,
        [
            {
                "id": permission_ids[f"{resource}.{action}"],
                "resource": resource,
                "action": action,
                "description": description,
            }
            for resource, action, description in _PERMISSION_ROWS
        ],
    )
    role_ids = {name: uuid4() for name in _ROLE_GRANTS}
    op.bulk_insert(
        roles,
        [
            {
                "id": role_ids[name],
                "name": name,
                "description": f"Built-in role: {name}",
                "is_system": True,
            }
            for name in _ROLE_GRANTS
        ],
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", uuid_type),
        sa.column("permission_id", uuid_type),
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[role_name], "permission_id": permission_ids[key]}
            for role_name, keys in _ROLE_GRANTS.items()
            for key in keys
        ],
    )

    # Bootstrap the configured Replit administrators so the first deployment is usable.
    admin_ids = [int(value.strip()) for value in os.getenv("ADMIN_IDS", "").split(",") if value.strip().isdigit()]
    super_admin_role_id = role_ids["SUPER_ADMIN"]
    for telegram_id in admin_ids:
        op.execute(
            sa.text(
                """INSERT INTO users (id, telegram_id, is_active, is_verified)
                   VALUES (:id, :telegram_id, TRUE, TRUE)
                   ON CONFLICT (telegram_id) DO UPDATE SET is_active=TRUE"""
            ).bindparams(id=uuid4(), telegram_id=telegram_id)
        )
        op.execute(
            sa.text(
                """INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)
                   ON CONFLICT DO NOTHING"""
            ).bindparams(user_id=telegram_id, role_id=super_admin_role_id)
        )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_occurred_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_user_permissions_permission_id", table_name="user_permissions")
    op.drop_table("user_permissions")
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("role_scopes")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    postgresql.ENUM(name="audit_outcome").drop(op.get_bind(), checkfirst=True)
