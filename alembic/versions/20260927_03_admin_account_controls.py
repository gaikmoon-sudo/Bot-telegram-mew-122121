"""Persist administrative account enable/disable state.

Revision ID: 20260927_03
Revises: 20260927_02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260927_03"
down_revision = "20260927_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_accounts",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "disabled_by_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.telegram_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(is_enabled = true AND disabled_at IS NULL) "
            "OR (is_enabled = false AND disabled_at IS NOT NULL)",
            name="ck_admin_accounts_enabled_state",
        ),
    )
    op.create_index("ix_admin_accounts_is_enabled", "admin_accounts", ["is_enabled"])


def downgrade() -> None:
    op.drop_index("ix_admin_accounts_is_enabled", table_name="admin_accounts")
    op.drop_table("admin_accounts")
