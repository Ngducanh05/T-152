import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.agent_quota import (
    AgentQuotaError,
    AgentQuotaExceeded,
    AgentQuotaService,
)
from src.core.config import Settings, get_settings
from src.core.db_models import AgentDailyUsage, Base, ParkingUser
from src.core.seed import seed_if_missing
from src.models.schemas import ErrorCode


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def quota_engine() -> AsyncGenerator[AsyncEngine, None]:
    schema_name = f"test_agent_quota_{uuid4().hex}"
    database_url = get_settings().database_url
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))
    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_if_missing(session)
        async with session.begin():
            session.add(ParkingUser(id="USER-002", display_name="Quota User 2"))
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def clear_agent_usage(quota_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(delete(AgentDailyUsage))


def _clock(value: datetime) -> Callable[[], datetime]:
    return lambda: value


async def _usage_count(engine: AsyncEngine) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return int(await session.scalar(select(func.count()).select_from(AgentDailyUsage)) or 0)


@pytest.mark.asyncio(loop_scope="module")
async def test_disabled_limit_does_not_create_usage_row(quota_engine: AsyncEngine):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await AgentQuotaService(
            session,
            settings=Settings(agent_daily_request_limit=0),
            clock=_clock(datetime(2026, 8, 24, 8, tzinfo=UTC)),
        ).consume("UNKNOWN-USER")

    assert await _usage_count(quota_engine) == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_requests_through_limit_are_accepted(quota_engine: AsyncEngine):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    settings = Settings(agent_daily_request_limit=3)
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)

    for _ in range(3):
        async with factory() as session, session.begin():
            await AgentQuotaService(session, settings=settings, clock=_clock(now)).consume("USER-001")

    async with factory() as session:
        usage = await session.get(AgentDailyUsage, ("USER-001", now.date()))
    assert usage is not None
    assert usage.request_count == 3


@pytest.mark.asyncio(loop_scope="module")
async def test_request_after_limit_is_rejected_without_increment(
    quota_engine: AsyncEngine,
):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    settings = Settings(agent_daily_request_limit=1)
    now = datetime(2026, 8, 24, 23, 59, tzinfo=UTC)
    async with factory() as session, session.begin():
        await AgentQuotaService(session, settings=settings, clock=_clock(now)).consume("USER-001")

    async with factory() as session:
        with pytest.raises(AgentQuotaExceeded) as exc_info:
            async with session.begin():
                await AgentQuotaService(session, settings=settings, clock=_clock(now)).consume("USER-001")

    assert exc_info.value.reset_at == datetime(2026, 8, 25, tzinfo=UTC)
    async with factory() as session:
        usage = await session.get(AgentDailyUsage, ("USER-001", now.date()))
    assert usage is not None
    assert usage.request_count == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_users_have_independent_daily_quotas(quota_engine: AsyncEngine):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    settings = Settings(agent_daily_request_limit=1)
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    for user_id in ("USER-001", "USER-002"):
        async with factory() as session, session.begin():
            await asyncio.wait_for(
                AgentQuotaService(session, settings=settings, clock=_clock(now)).consume(user_id),
                timeout=5,
            )

    assert await _usage_count(quota_engine) == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_new_utc_day_resets_quota(quota_engine: AsyncEngine):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    settings = Settings(agent_daily_request_limit=1)
    for now in (
        datetime(2026, 8, 24, 23, 59, tzinfo=UTC),
        datetime(2026, 8, 25, 0, 0, tzinfo=UTC),
    ):
        async with factory() as session, session.begin():
            await AgentQuotaService(session, settings=settings, clock=_clock(now)).consume("USER-001")

    assert await _usage_count(quota_engine) == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_concurrent_transactions_cannot_exceed_limit(
    quota_engine: AsyncEngine,
):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    settings = Settings(agent_daily_request_limit=1)
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    start = asyncio.Event()

    async def consume() -> bool:
        await start.wait()
        async with factory() as session:
            try:
                async with session.begin():
                    await AgentQuotaService(session, settings=settings, clock=_clock(now)).consume("USER-001")
            except AgentQuotaExceeded:
                return False
        return True

    tasks = [asyncio.create_task(consume()), asyncio.create_task(consume())]
    start.set()
    assert sorted(await asyncio.gather(*tasks)) == [False, True]

    async with factory() as session:
        usage = await session.get(AgentDailyUsage, ("USER-001", now.date()))
    assert usage is not None
    assert usage.request_count == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_unknown_user_is_rejected_safely(quota_engine: AsyncEngine):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    async with factory() as session:
        with pytest.raises(AgentQuotaError) as exc_info:
            async with session.begin():
                await AgentQuotaService(
                    session,
                    settings=Settings(agent_daily_request_limit=1),
                ).consume("UNKNOWN-USER")

    assert exc_info.value.code is ErrorCode.USER_NOT_FOUND
    assert await _usage_count(quota_engine) == 0


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "invalid_now",
    [
        datetime(2026, 8, 24, 8),
        datetime(2026, 8, 24, 15, tzinfo=timezone(timedelta(hours=7))),
    ],
)
async def test_non_utc_clock_is_rejected(
    quota_engine: AsyncEngine,
    invalid_now: datetime,
):
    factory = async_sessionmaker(quota_engine, expire_on_commit=False)
    async with factory() as session:
        with pytest.raises(AgentQuotaError, match="timezone-aware UTC"):
            async with session.begin():
                await AgentQuotaService(
                    session,
                    settings=Settings(agent_daily_request_limit=1),
                    clock=_clock(invalid_now),
                ).consume("USER-001")

    assert await _usage_count(quota_engine) == 0
