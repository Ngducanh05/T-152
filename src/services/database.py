from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings


@lru_cache
def get_engine():
    """Create one async SQLAlchemy engine for the configured database."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create sessions on demand so importing the app does not open a DB connection."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that gives every request its own database session."""
    async with get_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """Return true only when PostgreSQL accepts a simple query."""
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True
