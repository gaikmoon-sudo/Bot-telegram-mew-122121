"""Async PostgreSQL engine and per-task SQLAlchemy sessions."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings


def _async_database_url(database_url: str) -> str:
    """Ensure a PostgreSQL URL uses the asyncpg SQLAlchemy dialect."""
    if database_url.startswith("postgresql://"):
        return database_url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


_database_url = settings.database_url
engine: AsyncEngine | None = (
    create_async_engine(_async_database_url(_database_url), pool_pre_ping=True)
    if _database_url else None
)

session_factory = (
    async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    if engine is not None else None
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a dedicated session for one async task/request.

    A new session is created for every call, so a session is never shared
    between concurrent tasks.
    """
    if session_factory is None:
        raise RuntimeError("DATABASE_URL is not configured; PostgreSQL session is disabled.")
    async with session_factory() as session:
        yield session


async def close_database() -> None:
    """Dispose of the engine's connection pool during application shutdown."""
    if engine is not None:
        await engine.dispose()