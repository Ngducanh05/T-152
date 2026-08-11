from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Create the canonical async engine without connecting at import time."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create sessions bound to the canonical ParkSmart engine."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide one async database session per FastAPI request."""
    async with get_session_factory()() as session:
        yield session


async def check_database_connection() -> bool:
    """Return true when PostgreSQL accepts a simple query."""
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True
