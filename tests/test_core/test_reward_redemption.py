import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import Settings, get_settings
from src.core.db_models import Base, ParkingVoucher, RewardCatalogItem, RewardRedemption, RewardTransaction
from src.core.reward import RewardError, RewardService
from src.core.reward_redemption import RewardRedemptionService
from src.core.seed import seed_if_missing
from src.models.schemas import ErrorCode, RewardSourceType, RewardTransactionStatus, RewardTransactionType


def _redemption_settings() -> Settings:
    return Settings(_env_file=None, rewards_redemption_enabled=True)


@pytest_asyncio.fixture
async def redemption_engine() -> AsyncGenerator[AsyncEngine, None]:
    schema_name = f"test_reward_redemption_{uuid4().hex}"
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


async def _catalog_and_balance(
    session, *, cost: int = 100, finalized_points: int = 100
) -> RewardCatalogItem:
    item = RewardCatalogItem(
        id="CATALOG-100",
        code="PARKING_TEST",
        name="Test parking credit",
        points_cost=cost,
        free_minutes=15,
        validity_days=30,
        is_active=True,
    )
    session.add_all(
        (
            item,
            RewardTransaction(
                id=f"REWARD-EARNED-{finalized_points}",
                user_id="USER-001",
                source_type=RewardSourceType.WRONG_PARKING_REPORT,
                source_reference=f"REPORT-EARNED-{finalized_points}",
                transaction_type=RewardTransactionType.CONTRIBUTION_REWARD,
                status=RewardTransactionStatus.EARNED,
                points_delta=finalized_points,
                created_at=datetime.now(UTC),
                settled_at=datetime.now(UTC),
                transaction_metadata={},
            ),
        )
    )
    await session.flush()
    return item


@pytest.mark.asyncio
async def test_successful_redemption_creates_signed_debit_and_owned_voucher(redemption_engine: AsyncEngine):
    factory = async_sessionmaker(redemption_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        item = await _catalog_and_balance(session)
        redemption, voucher, available = await RewardRedemptionService(session, settings=_redemption_settings()).redeem(
            user_id="USER-001", catalog_item_id=item.id
        )

    assert available == 0
    assert redemption.points_cost_snapshot == 100
    assert voucher.user_id == "USER-001"
    assert voucher.status.value == "ISSUED"
    async with factory() as session:
        ledger = list(await session.scalars(select(RewardTransaction)))
        assert await RewardService(session).finalized_balance("USER-001") == 0
    assert len(ledger) == 2
    entries_by_type = {entry.transaction_type: entry for entry in ledger}
    assert (
        entries_by_type[RewardTransactionType.CONTRIBUTION_REWARD].status,
        entries_by_type[RewardTransactionType.CONTRIBUTION_REWARD].points_delta,
    ) == (RewardTransactionStatus.EARNED, 100)
    assert (
        entries_by_type[RewardTransactionType.VOUCHER_REDEMPTION].status,
        entries_by_type[RewardTransactionType.VOUCHER_REDEMPTION].points_delta,
    ) == (RewardTransactionStatus.POSTED, -100)


@pytest.mark.asyncio
async def test_redemption_disabled_fails_closed_without_any_reward_mutation(redemption_engine: AsyncEngine):
    factory = async_sessionmaker(redemption_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        item = await _catalog_and_balance(session)
        with pytest.raises(RewardError) as error:
            await RewardRedemptionService(
                session,
                settings=Settings(_env_file=None, rewards_redemption_enabled=False),
            ).redeem(user_id="USER-001", catalog_item_id=item.id)
        assert error.value.code is ErrorCode.REDEMPTION_DISABLED

    async with factory() as session:
        assert await RewardService(session).finalized_balance("USER-001") == 100
        assert await session.scalar(select(func.count()).select_from(RewardRedemption)) == 0
        assert await session.scalar(select(func.count()).select_from(ParkingVoucher)) == 0


@pytest.mark.asyncio
async def test_redemption_uses_authoritative_finalized_signed_balance(redemption_engine: AsyncEngine):
    factory = async_sessionmaker(redemption_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        item = await _catalog_and_balance(session, cost=70, finalized_points=50)
        session.add(
            RewardTransaction(
                id="REWARD-PENDING-100",
                user_id="USER-001",
                source_type=RewardSourceType.ADJACENT_SLOT_OBSERVATION,
                source_reference="OBS-PENDING-100",
                transaction_type=RewardTransactionType.CONTRIBUTION_REWARD,
                status=RewardTransactionStatus.PENDING,
                points_delta=100,
                created_at=datetime.now(UTC),
                transaction_metadata={},
            )
        )
        assert await RewardService(session).finalized_balance("USER-001") == 50
        with pytest.raises(RewardError) as error:
            await RewardRedemptionService(session, settings=_redemption_settings()).redeem(user_id="USER-001", catalog_item_id=item.id)
        assert error.value.code is ErrorCode.INSUFFICIENT_REWARD_POINTS

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RewardRedemption)) == 0
        assert await session.scalar(select(func.count()).select_from(ParkingVoucher)) == 0
        assert await RewardService(session).finalized_balance("USER-001") == 50


@pytest.mark.asyncio
async def test_insufficient_balance_rolls_back_without_debit_or_voucher(redemption_engine: AsyncEngine):
    factory = async_sessionmaker(redemption_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        item = await _catalog_and_balance(session, cost=101, finalized_points=100)
        assert await RewardService(session).finalized_balance("USER-001") == 100
        with pytest.raises(RewardError) as error:
            await RewardRedemptionService(session, settings=_redemption_settings()).redeem(user_id="USER-001", catalog_item_id=item.id)
        assert error.value.code is ErrorCode.INSUFFICIENT_REWARD_POINTS

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RewardRedemption)) == 0
        assert await session.scalar(select(func.count()).select_from(ParkingVoucher)) == 0
        assert await session.scalar(
            select(func.count()).select_from(RewardTransaction).where(RewardTransaction.points_delta < 0)
        ) == 0


@pytest.mark.asyncio
async def test_redemption_snapshots_survive_catalog_changes(redemption_engine: AsyncEngine):
    factory = async_sessionmaker(redemption_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        item = await _catalog_and_balance(session)
        redemption, voucher, _ = await RewardRedemptionService(session, settings=_redemption_settings()).redeem(user_id="USER-001", catalog_item_id=item.id)
        item.points_cost = 500
        item.free_minutes = 60
        item.validity_days = 7

    async with factory() as session:
        stored_redemption = await session.get(RewardRedemption, redemption.id)
        stored_voucher = await session.get(ParkingVoucher, voucher.id)
    assert stored_redemption is not None and stored_voucher is not None
    assert (stored_redemption.points_cost_snapshot, stored_redemption.free_minutes_snapshot, stored_redemption.validity_days_snapshot) == (100, 15, 30)
    assert (stored_voucher.points_cost_snapshot, stored_voucher.free_minutes_snapshot, stored_voucher.validity_days_snapshot) == (100, 15, 30)


@pytest.mark.asyncio
async def test_concurrent_redemptions_cannot_double_spend_same_points(redemption_engine: AsyncEngine):
    factory = async_sessionmaker(redemption_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        item = await _catalog_and_balance(session)
    start = asyncio.Event()

    async def redeem() -> bool:
        await start.wait()
        try:
            async with factory() as session, session.begin():
                await RewardRedemptionService(session, settings=_redemption_settings()).redeem(user_id="USER-001", catalog_item_id=item.id)
            return True
        except RewardError:
            return False

    tasks = [asyncio.create_task(redeem()), asyncio.create_task(redeem())]
    start.set()
    assert sorted(await asyncio.gather(*tasks)) == [False, True]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RewardRedemption)) == 1
        assert await session.scalar(select(func.count()).select_from(ParkingVoucher)) == 1
        assert await RewardService(session).finalized_balance("USER-001") == 0
