from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings


@lru_cache
def _get_engine_cached() -> AsyncEngine:
    """Create the canonical async engine without connecting at import time."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )


def _instrument_active_engine(engine: AsyncEngine) -> None:
    """Instrument the shared engine when an enabled request runtime is active."""
    from src.core.observability import get_active_observability

    runtime = get_active_observability()
    if runtime is not None:
        runtime.instrument_sqlalchemy_engine(engine.sync_engine)


def get_engine() -> AsyncEngine:
    """Return the canonical async engine and bind safe tracing when applicable."""
    engine = _get_engine_cached()
    _instrument_active_engine(engine)
    return engine


@lru_cache
def _get_session_factory_cached() -> async_sessionmaker[AsyncSession]:
    """Create sessions bound to the canonical ParkSmart engine."""
    return async_sessionmaker(
        bind=_get_engine_cached(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create sessions bound to the canonical ParkSmart engine."""
    _instrument_active_engine(_get_engine_cached())
    return _get_session_factory_cached()


# Preserve the cache-management hooks exposed by the former public cached functions.
get_engine.cache_clear = _get_engine_cached.cache_clear  # type: ignore[attr-defined]
get_session_factory.cache_clear = _get_session_factory_cached.cache_clear  # type: ignore[attr-defined]


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide one async database session per FastAPI request."""
    async with get_session_factory()() as session:
        yield session


async def check_database_connection() -> bool:
    """Return true when PostgreSQL accepts a simple query."""
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))
    return True
