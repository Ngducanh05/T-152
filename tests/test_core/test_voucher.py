from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import Settings, get_settings
from src.core.db_models import (
    Base,
    ParkingSession,
    ParkingUser,
    ParkingVoucher,
    RewardCatalogItem,
    RewardTransaction,
    Vehicle,
)
from src.core.parking_time_benefit import ParkingTimeBenefitService
from src.core.reward import RewardError
from src.core.reward_redemption import RewardRedemptionService
from src.core.seed import seed_if_missing
from src.core.voucher import VoucherService
from src.core.voucher_application import VoucherApplicationService
from src.models.schemas import (
    ErrorCode,
    ParkingSessionStatus,
    ParkingVoucherStatus,
    RewardSourceType,
    RewardTransactionStatus,
    RewardTransactionType,
)


@pytest_asyncio.fixture
async def voucher_engine() -> AsyncGenerator[AsyncEngine, None]:
    schema_name = f"test_voucher_{uuid4().hex}"
    admin_engine = create_async_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))
    engine = create_async_engine(get_settings().database_url, connect_args={"server_settings": {"search_path": schema_name}})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await seed_if_missing(session)
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


async def _issue_voucher(session, *, user_id: str = "USER-001", now: datetime | None = None) -> ParkingVoucher:
    now = now or datetime.now(UTC)
    item = RewardCatalogItem(
        id=f"CATALOG-{uuid4().hex}", code=f"TEST-{uuid4().hex[:8]}", name="Test voucher", points_cost=100,
        free_minutes=15, validity_days=30, is_active=True,
    )
    credit = RewardTransaction(
        id=f"CREDIT-{uuid4().hex}", user_id=user_id, source_type=RewardSourceType.WRONG_PARKING_REPORT,
        source_reference=f"REPORT-{uuid4().hex}", transaction_type=RewardTransactionType.CONTRIBUTION_REWARD,
        status=RewardTransactionStatus.EARNED, points_delta=100, created_at=now, settled_at=now, transaction_metadata={},
    )
    session.add_all((item, credit))
    await session.flush()
    _, voucher, _ = await RewardRedemptionService(
        session,
        settings=Settings(_env_file=None, rewards_redemption_enabled=True),
        clock=lambda: now,
    ).redeem(user_id=user_id, catalog_item_id=item.id)
    return voucher


@pytest.mark.asyncio
async def test_lists_user_owned_issued_vouchers(voucher_engine: AsyncEngine):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        voucher = await _issue_voucher(session)
    async with factory() as session:
        listed = await VoucherService(session).list_user_vouchers("USER-001")
    assert [(item.id, item.status) for item in listed] == [(voucher.id, ParkingVoucherStatus.ISSUED)]


@pytest.mark.asyncio
async def test_expiration_is_lazy_and_does_not_refund_points(voucher_engine: AsyncEngine):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    issued_at = datetime(2026, 8, 1, tzinfo=UTC)
    async with factory() as session, session.begin():
        voucher = await _issue_voucher(session, now=issued_at)
    async with factory() as session:
        assert (await session.get(ParkingVoucher, voucher.id)).status is ParkingVoucherStatus.ISSUED
    async with factory() as session, session.begin():
        expired = await VoucherService(session, clock=lambda: issued_at + timedelta(days=30)).expire_stale("USER-001")
    assert expired == 1
    async with factory() as session:
        stored = await session.get(ParkingVoucher, voucher.id)
        debits = list(await session.scalars(select(RewardTransaction).where(RewardTransaction.points_delta < 0)))
        refunds = list(await session.scalars(select(RewardTransaction).where(RewardTransaction.transaction_type == RewardTransactionType.VOUCHER_REFUND)))
    assert stored is not None and stored.status is ParkingVoucherStatus.EXPIRED
    assert len(debits) == 1 and refunds == []


@pytest.mark.asyncio
async def test_vouchers_are_owned_and_keep_catalog_snapshot_values(voucher_engine: AsyncEngine):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add_all(
            (
                ParkingUser(id="USER-002", display_name="Second user"),
                Vehicle(
                    id="VEHICLE-002",
                    user_id="USER-002",
                    plate_number="51A-00002",
                    requires_charging=False,
                ),
            )
        )
        first = await _issue_voucher(session)
        second = await _issue_voucher(session, user_id="USER-002")
        catalog = await session.get(RewardCatalogItem, first.catalog_item_id)
        assert catalog is not None
        catalog.points_cost, catalog.free_minutes, catalog.validity_days = 200, 30, 7
    async with factory() as session:
        own = await VoucherService(session).list_user_vouchers("USER-001")
        other = await VoucherService(session).list_user_vouchers("USER-002")
    assert [voucher.id for voucher in own] == [first.id]
    assert [voucher.id for voucher in other] == [second.id]
    assert (own[0].points_cost_snapshot, own[0].free_minutes_snapshot, own[0].validity_days_snapshot) == (100, 15, 30)


def test_future_one_voucher_per_session_partial_unique_index_is_declared():
    indexes = {index.name: index for index in ParkingVoucher.__table__.indexes}
    index = indexes["uq_parking_vouchers_applied_session"]
    assert index.unique is True
    assert [column.name for column in index.columns] == ["applied_session_id"]
    assert index.dialect_options["postgresql"]["where"] is not None


@pytest.mark.asyncio
async def test_owned_issued_voucher_applies_once_without_changing_the_reward_ledger(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    now = datetime(2026, 8, 31, tzinfo=UTC)
    async with factory() as session, session.begin():
        voucher = await _issue_voucher(session, now=now)
        session.add(
            ParkingSession(
                id="SESSION-APPLICATION-001",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F1-A01",
                status=ParkingSessionStatus.ACTIVE,
                parked_at=now - timedelta(minutes=20),
                completed_at=None,
            )
        )
        ledger_before = len(list(await session.scalars(select(RewardTransaction))))
        applied = await VoucherApplicationService(session, clock=lambda: now).apply(
            user_id="USER-001",
            voucher_id=voucher.id,
        )
        assert applied.status is ParkingVoucherStatus.APPLIED
        assert applied.applied_session_id == "SESSION-APPLICATION-001"
        assert len(list(await session.scalars(select(RewardTransaction)))) == ledger_before


@pytest.mark.asyncio
async def test_voucher_application_rejects_another_users_session_and_session_reuse(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    now = datetime(2026, 8, 31, tzinfo=UTC)
    async with factory() as session, session.begin():
        session.add_all(
            (
                ParkingUser(id="USER-002", display_name="Second user"),
                Vehicle(
                    id="VEHICLE-002",
                    user_id="USER-002",
                    plate_number="51A-00003",
                    requires_charging=False,
                ),
            )
        )
        first = await _issue_voucher(session, now=now)
        second = await _issue_voucher(session, user_id="USER-002", now=now)
        session.add_all(
            (
                ParkingSession(
                    id="SESSION-APPLICATION-002",
                    user_id="USER-001",
                    vehicle_id="VEHICLE-001",
                    slot_id="F1-A01",
                    status=ParkingSessionStatus.ACTIVE,
                    parked_at=now,
                    completed_at=None,
                ),
                ParkingSession(
                    id="SESSION-APPLICATION-003",
                    user_id="USER-002",
                    vehicle_id="VEHICLE-002",
                    slot_id="F1-A02",
                    status=ParkingSessionStatus.ACTIVE,
                    parked_at=now,
                    completed_at=None,
                ),
            )
        )
        await session.flush()
        service = VoucherApplicationService(session, clock=lambda: now)
        await service.apply(user_id="USER-001", voucher_id=first.id, session_id="SESSION-APPLICATION-002")
        with pytest.raises(RewardError) as reused:
            await service.apply(user_id="USER-002", voucher_id=second.id, session_id="SESSION-APPLICATION-002")
        assert reused.value.code is ErrorCode.VOUCHER_OWNERSHIP_MISMATCH


@pytest.mark.asyncio
async def test_time_benefit_is_duration_only_and_forfeits_unused_minutes(voucher_engine: AsyncEngine):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    parked_at = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        voucher = await _issue_voucher(session, now=parked_at)
        voucher.free_minutes_snapshot = 30
        session.add(
            ParkingSession(
                id="SESSION-BENEFIT-001",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F1-A01",
                status=ParkingSessionStatus.COMPLETED,
                parked_at=parked_at,
                completed_at=parked_at + timedelta(minutes=20),
            )
        )
        voucher.status = ParkingVoucherStatus.APPLIED
        voucher.applied_at = parked_at
        voucher.applied_session_id = "SESSION-BENEFIT-001"
        await session.flush()
        benefit = await ParkingTimeBenefitService(session).calculate("SESSION-BENEFIT-001")
    assert (benefit.total_minutes, benefit.free_minutes, benefit.billable_minutes) == (20, 20, 0)
    assert benefit.voucher_id == voucher.id


@pytest.mark.asyncio
async def test_voucher_application_retries_same_voucher_and_session_without_reuse(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    now = datetime(2026, 9, 1, tzinfo=UTC)
    async with factory() as session, session.begin():
        first = await _issue_voucher(session, now=now)
        second = await _issue_voucher(session, now=now)
        first_session = ParkingSession(
            id="SESSION-RETRY-ONE",
            user_id="USER-001",
            vehicle_id="VEHICLE-001",
            slot_id="F1-A01",
            status=ParkingSessionStatus.ACTIVE,
            parked_at=now,
            completed_at=None,
        )
        session.add(first_session)
        service = VoucherApplicationService(session, clock=lambda: now)
        applied = await service.apply(user_id="USER-001", voucher_id=first.id, session_id="SESSION-RETRY-ONE")
        replay = await service.apply(user_id="USER-001", voucher_id=first.id, session_id="SESSION-RETRY-ONE")
        assert replay.id == applied.id
        with pytest.raises(RewardError) as session_conflict:
            await service.apply(user_id="USER-001", voucher_id=second.id, session_id="SESSION-RETRY-ONE")
        assert session_conflict.value.code is ErrorCode.VOUCHER_SESSION_CONFLICT
        first_session.status = ParkingSessionStatus.COMPLETED
        first_session.completed_at = now
        session.add(
            ParkingSession(
                id="SESSION-RETRY-TWO",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F1-A02",
                status=ParkingSessionStatus.ACTIVE,
                parked_at=now,
                completed_at=None,
            )
        )
        with pytest.raises(RewardError) as different_session:
            await service.apply(user_id="USER-001", voucher_id=first.id, session_id="SESSION-RETRY-TWO")
        assert different_session.value.code is ErrorCode.VOUCHER_NOT_USABLE


@pytest.mark.asyncio
async def test_expired_issued_voucher_application_does_not_create_a_transient_side_commit(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    issued_at = datetime(2026, 8, 1, tzinfo=UTC)
    async with factory() as session, session.begin():
        voucher = await _issue_voucher(session, now=issued_at)
        session.add(
            ParkingSession(
                id="SESSION-EXPIRED-VOUCHER",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F1-A01",
                status=ParkingSessionStatus.ACTIVE,
                parked_at=issued_at,
                completed_at=None,
            )
        )

    async with factory() as session, session.begin():
        stored = await session.get(ParkingVoucher, voucher.id)
        assert stored is not None
        version_before = stored.version
        with pytest.raises(RewardError) as expired:
            await VoucherApplicationService(session, clock=lambda: issued_at + timedelta(days=30)).apply(
                user_id="USER-001", voucher_id=voucher.id, session_id="SESSION-EXPIRED-VOUCHER"
            )
        assert expired.value.code is ErrorCode.VOUCHER_EXPIRED
        assert stored.status is ParkingVoucherStatus.ISSUED
        assert stored.version == version_before
        assert stored.applied_session_id is None

    async with factory() as session, session.begin():
        assert await VoucherService(session, clock=lambda: issued_at + timedelta(days=30)).expire_stale("USER-001") == 1
    async with factory() as session:
        stored = await session.get(ParkingVoucher, voucher.id)
        debits = list(await session.scalars(select(RewardTransaction).where(RewardTransaction.points_delta < 0)))
    assert stored is not None and stored.status is ParkingVoucherStatus.EXPIRED
    assert len(debits) == 1


@pytest.mark.asyncio
async def test_time_benefit_covers_long_sessions_and_no_voucher_without_pricing(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    parked_at = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        voucher = await _issue_voucher(session, now=parked_at)
        voucher.free_minutes_snapshot = 30
        voucher.status = ParkingVoucherStatus.APPLIED
        voucher.applied_session_id = "SESSION-BENEFIT-LONG"
        voucher.applied_at = parked_at
        session.add_all(
            (
                ParkingSession(
                    id="SESSION-BENEFIT-LONG",
                    user_id="USER-001",
                    vehicle_id="VEHICLE-001",
                    slot_id="F1-A01",
                    status=ParkingSessionStatus.COMPLETED,
                    parked_at=parked_at,
                    completed_at=parked_at + timedelta(minutes=75),
                ),
                ParkingSession(
                    id="SESSION-BENEFIT-NONE",
                    user_id="USER-001",
                    vehicle_id="VEHICLE-001",
                    slot_id="F1-A02",
                    status=ParkingSessionStatus.COMPLETED,
                    parked_at=parked_at,
                    completed_at=parked_at + timedelta(minutes=20),
                ),
            )
        )
        long = await ParkingTimeBenefitService(session).calculate("SESSION-BENEFIT-LONG")
        without_voucher = await ParkingTimeBenefitService(session).calculate("SESSION-BENEFIT-NONE")
    assert (long.total_minutes, long.free_minutes, long.billable_minutes, long.voucher_id) == (75, 30, 45, voucher.id)
    assert (without_voucher.total_minutes, without_voucher.free_minutes, without_voucher.billable_minutes, without_voucher.voucher_id) == (20, 0, 20, None)
