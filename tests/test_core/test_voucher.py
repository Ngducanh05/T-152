import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import get_settings
from src.core.db_models import (
    Base,
    ParkingSession,
    ParkingUser,
    ParkingVoucher,
    RewardCatalogItem,
    RewardTransaction,
)
from src.core.reward import RewardError
from src.core.reward_redemption import RewardRedemptionService
from src.core.seed import seed_if_missing
from src.core.voucher import VoucherService
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
    _, voucher, _ = await RewardRedemptionService(session, clock=lambda: now).redeem(user_id=user_id, catalog_item_id=item.id)
    return voucher


async def _active_session(
    session,
    *,
    session_id: str = "SESSION-VOUCHER",
    status: ParkingSessionStatus = ParkingSessionStatus.ACTIVE,
) -> ParkingSession:
    parking_session = ParkingSession(
        id=session_id,
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        slot_id="F1-D01",
        status=status,
        parked_at=datetime.now(UTC) - timedelta(minutes=30),
        completed_at=(datetime.now(UTC) if status is ParkingSessionStatus.COMPLETED else None),
    )
    session.add(parking_session)
    await session.flush()
    return parking_session


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
        session.add(ParkingUser(id="USER-002", display_name="Second user"))
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
async def test_applies_owned_issued_voucher_to_owned_active_session(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        parking_session = await _active_session(session)
        voucher = await _issue_voucher(session)
        applied = await VoucherService(session).apply_to_session(
            user_id="USER-001",
            voucher_id=voucher.id,
            session_id=parking_session.id,
        )

        assert applied.status is ParkingVoucherStatus.APPLIED
        assert applied.applied_at is not None
        assert applied.applied_session_id == parking_session.id
        assert applied.version == 1
        assert (
            await VoucherService(session).get_applied_to_session(parking_session.id)
        ) is applied


@pytest.mark.asyncio
async def test_rejects_completed_session_expired_voucher_and_wrong_owner(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    issued_at = datetime(2026, 8, 1, tzinfo=UTC)
    async with factory() as session, session.begin():
        completed = await _active_session(
            session,
            session_id="SESSION-COMPLETED",
            status=ParkingSessionStatus.COMPLETED,
        )
        voucher = await _issue_voucher(session, now=issued_at)

        with pytest.raises(RewardError) as completed_error:
            await VoucherService(session).apply_to_session(
                user_id="USER-001",
                voucher_id=voucher.id,
                session_id=completed.id,
            )
        assert completed_error.value.code is ErrorCode.INVALID_TRANSITION

        active = await _active_session(session, session_id="SESSION-ACTIVE")
        with pytest.raises(RewardError) as expired_error:
            await VoucherService(
                session,
                clock=lambda: issued_at + timedelta(days=31),
            ).apply_to_session(
                user_id="USER-001",
                voucher_id=voucher.id,
                session_id=active.id,
            )
        assert expired_error.value.code is ErrorCode.INVALID_TRANSITION

        with pytest.raises(RewardError) as owner_error:
            await VoucherService(session).apply_to_session(
                user_id="USER-002",
                voucher_id=voucher.id,
                session_id=active.id,
            )
        assert owner_error.value.code is ErrorCode.INVALID_TRANSITION


@pytest.mark.asyncio
async def test_rejects_missing_resources_reapply_and_second_voucher_for_session(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        active = await _active_session(session)
        first = await _issue_voucher(session)
        second = await _issue_voucher(session)

        with pytest.raises(RewardError) as missing_session:
            await VoucherService(session).apply_to_session(
                user_id="USER-001",
                voucher_id=first.id,
                session_id="SESSION-MISSING",
            )
        assert missing_session.value.code is ErrorCode.SESSION_NOT_FOUND

        with pytest.raises(RewardError) as missing_voucher:
            await VoucherService(session).apply_to_session(
                user_id="USER-001",
                voucher_id="VOUCHER-MISSING",
                session_id=active.id,
            )
        assert missing_voucher.value.code is ErrorCode.VOUCHER_NOT_FOUND

        await VoucherService(session).apply_to_session(
            user_id="USER-001",
            voucher_id=first.id,
            session_id=active.id,
        )
        with pytest.raises(RewardError) as reapplied:
            await VoucherService(session).apply_to_session(
                user_id="USER-001",
                voucher_id=first.id,
                session_id=active.id,
            )
        assert reapplied.value.code is ErrorCode.INVALID_TRANSITION

        with pytest.raises(RewardError) as second_voucher:
            await VoucherService(session).apply_to_session(
                user_id="USER-001",
                voucher_id=second.id,
                session_id=active.id,
            )
        assert second_voucher.value.code is ErrorCode.INVALID_TRANSITION


@pytest.mark.asyncio
async def test_concurrent_vouchers_for_one_session_have_one_domain_winner(
    voucher_engine: AsyncEngine,
):
    factory = async_sessionmaker(voucher_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        parking_session = await _active_session(session, session_id="SESSION-CONCURRENT")
        first = await _issue_voucher(session)
        second = await _issue_voucher(session)
        session_id = parking_session.id
        voucher_ids = (first.id, second.id)

    async def worker(voucher_id: str):
        async with factory() as session, session.begin():
            return await VoucherService(session).apply_to_session(
                user_id="USER-001",
                voucher_id=voucher_id,
                session_id=session_id,
            )

    results = await asyncio.gather(
        worker(voucher_ids[0]),
        worker(voucher_ids[1]),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, ParkingVoucher)]
    failures = [result for result in results if isinstance(result, RewardError)]
    assert len(successes) == 1
    assert successes[0].status is ParkingVoucherStatus.APPLIED
    assert len(failures) == 1
    assert failures[0].code is ErrorCode.INVALID_TRANSITION

    async with factory() as session:
        applied = list(
            await session.scalars(
                select(ParkingVoucher).where(
                    ParkingVoucher.status == ParkingVoucherStatus.APPLIED,
                    ParkingVoucher.applied_session_id == session_id,
                )
            )
        )
    assert len(applied) == 1
