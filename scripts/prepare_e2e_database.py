"""Recreate and seed the isolated PostgreSQL database used by browser E2E."""

import asyncio
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import get_settings
from src.core.database import get_session_factory
from src.core.db_models import Base
from src.core.seed import seed_if_missing


def _database_name_and_admin_url(database_url: str) -> tuple[str, str]:
    parsed = urlsplit(database_url)
    database_name = parsed.path.lstrip("/")
    if not database_name or database_name == "parksmart":
        raise RuntimeError("E2E_DATABASE_URL must target a dedicated non-parksmart database")
    admin_url = urlunsplit(parsed._replace(path="/postgres"))
    return database_name, admin_url


async def prepare() -> None:
    settings = get_settings()
    database_name, admin_url = _database_name_and_admin_url(settings.database_url)
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    quoted_database = '"' + database_name.replace('"', '""') + '"'
    async with admin_engine.connect() as connection:
        await connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        await connection.execute(text(f"DROP DATABASE IF EXISTS {quoted_database}"))
        await connection.execute(text(f"CREATE DATABASE {quoted_database}"))
    await admin_engine.dispose()

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    async with get_session_factory()() as session:
        await seed_if_missing(session)


if __name__ == "__main__":
    asyncio.run(prepare())
