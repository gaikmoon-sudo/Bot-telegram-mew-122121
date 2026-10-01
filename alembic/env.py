"""Alembic environment configured for asynchronous SQLAlchemy migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_engine_from_config,
)

from app.authorization.models import (
    AdminAccount,
    Permission,
    Role,
    RolePermission,
    RoleScope,
    UserRole,
    UserPermission,
)
from app.content.models import (
    ContentRevision,
    ContentTag,
    Course,
    CoursePrerequisite,
    LearningPath,
    Lesson,
    LessonVersion,
    Module,
    Tag,
)
from app.learning.models import (
    Enrollment,
    LessonProgress,
    ProgressEvent,
    UserFavorite,
)
from app.assessment.models import (
    Quiz,
    Question,
    QuizQuestion,
    QuestionOption,
    QuizAttempt,
    QuizAnswer,
)
from app.gamification.models import (
    PointsTransaction,
    Badge,
    UserBadge,
    UserStreak,
)
from app.notifications.models import (
    NotificationCampaign,
    NotificationDelivery,
    NotificationPreference,
    ScheduledJob,
)
from app.certificates.models import (
    CertificateTemplate,
    Certificate,
    CertificateEvent,
)
from app.audit.models import (
    AuditLog,
    SystemSetting,
)
from app.identity.models import (
    User,
    UserConsent,
    UserPreference,
    UserProfile,
)
from config import settings
from infrastructure.database.base import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _async_database_url(database_url: str) -> str:
    """Ensure PostgreSQL uses SQLAlchemy's asyncpg dialect."""
    if database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )
    if database_url.startswith("postgres://"):
        return database_url.replace(
            "postgres://",
            "postgresql+asyncpg://",
            1,
        )
    return database_url


# Importing all model classes above registers their tables on Base.metadata.
# Alembic uses this metadata for autogenerate comparisons.
_imported_models = (
    User,
    UserProfile,
    UserConsent,
    UserPreference,
    Role,
    Permission,
    RolePermission,
    UserRole,
    UserPermission,
    RoleScope,
    LearningPath,
    Course,
    CoursePrerequisite,
    Module,
    Lesson,
    LessonVersion,
    ContentRevision,
    Tag,
    ContentTag,
    Enrollment,
    LessonProgress,
    ProgressEvent,
    UserFavorite,
    Quiz,
    Question,
    QuizQuestion,
    QuestionOption,
    QuizAttempt,
    QuizAnswer,
    PointsTransaction,
    Badge,
    UserBadge,
    UserStreak,
    NotificationCampaign,
    NotificationDelivery,
    NotificationPreference,
    ScheduledJob,
    CertificateTemplate,
    Certificate,
    CertificateEvent,
    AuditLog,
    SystemSetting,
)
target_metadata = Base.metadata


database_url = _async_database_url(settings.database_url)
# ConfigParser treats '%' as interpolation syntax, so escape it before
# storing a URL that may contain encoded credentials or query parameters.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations against a synchronous connection facade."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through run_sync."""
    connectable: AsyncEngine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
