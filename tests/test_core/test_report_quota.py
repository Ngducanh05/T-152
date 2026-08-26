import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import Settings, get_settings
from src.core.db_models import (
    Base,
    ParkingUser,
    ReportDailyUsage,
    RewardTransaction,
    WrongParkingReport,
)
from src.core.parking_report import ParkingReportService
from src.core.report_quota import ReportQuotaExceeded, ReportSubmissionQuotaService
from src.core.seed import seed_if_missing
from src.models.schemas import WrongParkingReason


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def report_quota_engine() -> AsyncGenerator[AsyncEngine, None]:
    schema_name = f"test_report_quota_{uuid4().hex}"
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
            session.add(ParkingUser(id="USER-002", display_name="Report User 2"))
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def clear_report_usage(report_quota_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(delete(RewardTransaction))
        await session.execute(delete(WrongParkingReport))
        await session.execute(delete(ReportDailyUsage))


def _clock(value: datetime) -> Callable[[], datetime]:
    return lambda: value


async def _usage_count(engine: AsyncEngine) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return int(await session.scalar(select(func.count()).select_from(ReportDailyUsage)) or 0)


@pytest.mark.asyncio(loop_scope="module")
async def test_disabled_limit_does_not_query_or_write_usage() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = ReportSubmissionQuotaService(
        session,
        settings=Settings(wrong_parking_report_daily_limit=0),
    )

    await service.preflight("UNKNOWN")
    assert await service.consume("UNKNOWN") == 0
    session.scalar.assert_not_awaited()
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio(loop_scope="module")
async def test_requests_within_limit_succeed_and_next_is_rejected(
    report_quota_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    settings = Settings(wrong_parking_report_daily_limit=2)
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    for expected in (1, 2):
        async with factory() as session, session.begin():
            count = await ReportSubmissionQuotaService(session, settings=settings, clock=_clock(now)).consume(
                "USER-001"
            )
            assert count == expected

    async with factory() as session:
        with pytest.raises(ReportQuotaExceeded):
            async with session.begin():
                await ReportSubmissionQuotaService(session, settings=settings, clock=_clock(now)).consume("USER-001")
    async with factory() as session:
        usage = await session.get(ReportDailyUsage, ("USER-001", now.date()))
    assert usage is not None
    assert usage.submission_count == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_users_and_utc_days_have_independent_quotas(
    report_quota_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    settings = Settings(wrong_parking_report_daily_limit=1)
    for user_id, now in (
        ("USER-001", datetime(2026, 8, 24, 23, 59, tzinfo=UTC)),
        ("USER-002", datetime(2026, 8, 24, 23, 59, tzinfo=UTC)),
        ("USER-001", datetime(2026, 8, 25, 0, 0, tzinfo=UTC)),
    ):
        async with factory() as session, session.begin():
            await ReportSubmissionQuotaService(session, settings=settings, clock=_clock(now)).consume(user_id)

    assert await _usage_count(report_quota_engine) == 3


@pytest.mark.asyncio(loop_scope="module")
async def test_concurrent_transactions_cannot_exceed_limit(
    report_quota_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    settings = Settings(wrong_parking_report_daily_limit=1)
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    start = asyncio.Event()

    async def consume() -> bool:
        await start.wait()
        async with factory() as session:
            try:
                async with session.begin():
                    await ReportSubmissionQuotaService(session, settings=settings, clock=_clock(now)).consume(
                        "USER-001"
                    )
            except ReportQuotaExceeded:
                return False
        return True

    tasks = [asyncio.create_task(consume()), asyncio.create_task(consume())]
    start.set()
    assert sorted(await asyncio.gather(*tasks)) == [False, True]


@pytest.mark.asyncio(loop_scope="module")
async def test_report_transaction_rollback_does_not_consume_quota(
    report_quota_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    settings = Settings(wrong_parking_report_daily_limit=1)
    with pytest.raises(RuntimeError, match="force rollback"):
        async with factory() as session, session.begin():
            await ParkingReportService(session, settings=settings).create_wrong_parking_report(
                reporter_user_id="USER-001",
                slot_id="F1-D01",
                reason_code=WrongParkingReason.CROSSED_LINE,
                description=None,
                observed_plate_number=None,
            )
            raise RuntimeError("force rollback")

    assert await _usage_count(report_quota_engine) == 0


@pytest.mark.asyncio(loop_scope="module")
async def test_duplicate_report_still_consumes_quota(
    report_quota_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    settings = Settings(wrong_parking_report_daily_limit=2)
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    reports = []
    for _ in range(2):
        async with factory() as session, session.begin():
            reports.append(
                await ParkingReportService(session, settings=settings, clock=_clock(now)).create_wrong_parking_report(
                    reporter_user_id="USER-001",
                    slot_id="F1-D01",
                    reason_code=WrongParkingReason.CROSSED_LINE,
                    description=None,
                    observed_plate_number=None,
                )
            )

    assert reports[1].duplicate_candidate_of_id == reports[0].id
    async with factory() as session:
        usage = await session.get(
            ReportDailyUsage,
            ("USER-001", now.date()),
        )
    assert usage is not None
    assert usage.submission_count == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_hard_delete_does_not_refund_quota(
    report_quota_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    settings = Settings(wrong_parking_report_daily_limit=1)
    async with factory() as session, session.begin():
        report = await ParkingReportService(session, settings=settings).create_wrong_parking_report(
            reporter_user_id="USER-001",
            slot_id="F1-D01",
            reason_code=WrongParkingReason.WRONG_SLOT,
            description=None,
            observed_plate_number=None,
        )
    async with factory() as session, session.begin():
        await ParkingReportService(session, settings=settings).delete_wrong_parking_report(
            report.id,
            expected_version=0,
        )

    assert await _usage_count(report_quota_engine) == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_user_deletion_cascades_report_usage(
    report_quota_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(report_quota_engine, expire_on_commit=False)
    now = datetime(2026, 8, 24, 8, tzinfo=UTC)
    async with factory() as session, session.begin():
        session.add(ParkingUser(id="USER-CASCADE", display_name="Cascade User"))
    async with factory() as session, session.begin():
        await ReportSubmissionQuotaService(
            session,
            settings=Settings(wrong_parking_report_daily_limit=1),
            clock=_clock(now),
        ).consume("USER-CASCADE")
    async with factory() as session, session.begin():
        user = await session.get(ParkingUser, "USER-CASCADE")
        assert user is not None
        await session.delete(user)
    async with factory() as session:
        assert await session.get(ReportDailyUsage, ("USER-CASCADE", now.date())) is None
