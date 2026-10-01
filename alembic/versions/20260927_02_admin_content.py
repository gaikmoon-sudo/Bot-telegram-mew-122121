"""Materialize the existing content models and correct manager access.

Revision ID: 20260927_02
Revises: 20260927_01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260927_02"
down_revision = "20260927_01"
branch_labels = None
depends_on = None


CONTENT_STATUSES = ("DRAFT", "IN_REVIEW", "APPROVED", "PUBLISHED", "ARCHIVED")
UUID = postgresql.UUID(as_uuid=True)
CONTENT_STATUS = postgresql.ENUM(
    *CONTENT_STATUSES,
    name="content_status",
    create_type=False,
)
JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # Proven RBAC defect: CONTENT_MANAGER was granted admin.dashboard.view,
    # contradicting the required content-only boundary.
    op.execute(
        sa.text(
            """DELETE FROM role_permissions rp
               USING roles r, permissions p
               WHERE rp.role_id = r.id
                 AND rp.permission_id = p.id
                 AND r.name = 'CONTENT_MANAGER'
                 AND p.resource = 'admin'
                 AND p.action = 'dashboard.view'"""
        )
    )

    CONTENT_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "learning_paths",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", CONTENT_STATUS, nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_learning_paths_title_not_blank"),
        sa.UniqueConstraint("slug", name="uq_learning_paths_slug"),
    )
    op.create_table(
        "courses",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("learning_path_id", UUID, sa.ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", CONTENT_STATUS, nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_courses_title_not_blank"),
        sa.UniqueConstraint("learning_path_id", "slug", name="uq_courses_learning_path_slug"),
    )
    op.create_table(
        "course_prerequisites",
        sa.Column("course_id", UUID, sa.ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("prerequisite_course_id", UUID, sa.ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
        sa.CheckConstraint("course_id <> prerequisite_course_id", name="ck_course_prerequisites_not_self_referential"),
    )
    op.create_table(
        "modules",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("course_id", UUID, sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", CONTENT_STATUS, nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_modules_title_not_blank"),
        sa.UniqueConstraint("course_id", "slug", name="uq_modules_course_slug"),
    )
    op.create_table(
        "lessons",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("module_id", UUID, sa.ForeignKey("modules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", CONTENT_STATUS, nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_lessons_title_not_blank"),
        sa.UniqueConstraint("module_id", "slug", name="uq_lessons_module_slug"),
    )
    op.create_table(
        "lesson_versions",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("lesson_id", UUID, sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_body", sa.Text(), nullable=False),
        sa.Column("content_metadata", JSON, nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("status", CONTENT_STATUS, nullable=False, server_default="DRAFT"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version_number > 0", name="ck_lesson_versions_version_number_positive"),
        sa.CheckConstraint("length(trim(content_body)) > 0", name="ck_lesson_versions_content_not_blank"),
        sa.UniqueConstraint("lesson_id", "version_number", name="uq_lesson_versions_lesson_version"),
    )
    op.create_table(
        "content_revisions",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("content_id", UUID, nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", CONTENT_STATUS, nullable=False, server_default="DRAFT"),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("snapshot", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(content_type)) > 0", name="ck_content_revisions_content_type_not_blank"),
        sa.CheckConstraint("revision_number > 0", name="ck_content_revisions_revision_number_positive"),
        sa.UniqueConstraint("content_type", "content_id", "revision_number", name="uq_content_revisions_content_revision"),
    )
    op.create_index("ix_content_revisions_content", "content_revisions", ["content_type", "content_id"])
    op.create_table(
        "tags",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "content_tags",
        sa.Column("content_type", sa.String(50), primary_key=True, nullable=False),
        sa.Column("content_id", UUID, primary_key=True, nullable=False),
        sa.Column("tag_id", UUID, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
        sa.CheckConstraint("length(trim(content_type)) > 0", name="ck_content_tags_content_type_not_blank"),
    )
    op.create_index("ix_content_tags_content", "content_tags", ["content_type", "content_id"])


def downgrade() -> None:
    op.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.name = 'CONTENT_MANAGER'
                 AND p.resource = 'admin' AND p.action = 'dashboard.view'
               ON CONFLICT DO NOTHING"""
        )
    )
    op.drop_index("ix_content_tags_content", table_name="content_tags")
    op.drop_table("content_tags")
    op.drop_table("tags")
    op.drop_index("ix_content_revisions_content", table_name="content_revisions")
    op.drop_table("content_revisions")
    op.drop_table("lesson_versions")
    op.drop_table("lessons")
    op.drop_table("modules")
    op.drop_table("course_prerequisites")
    op.drop_table("courses")
    op.drop_table("learning_paths")
    CONTENT_STATUS.drop(op.get_bind(), checkfirst=True)
