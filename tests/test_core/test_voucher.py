from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import get_settings
from src.core.db_models import Base, ParkingUser, ParkingVoucher, RewardCatalogItem, RewardTransaction
from src.core.reward_redemption import RewardRedemptionService
from src.core.seed import seed_if_missing
from src.core.voucher import VoucherService
from src.models.schemas import ParkingVoucherStatus, RewardSourceType, RewardTransactionStatus, RewardTransactionType


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
