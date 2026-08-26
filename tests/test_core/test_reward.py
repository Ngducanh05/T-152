import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import Settings, get_settings
from src.core.db_models import Base, RewardTransaction
from src.core.reward import RewardError, RewardService
from src.core.seed import seed_if_missing
from src.models.schemas import RewardSourceType, RewardTransactionStatus


@pytest_asyncio.fixture
async def reward_engine() -> AsyncGenerator[AsyncEngine, None]:
    schema_name = f"test_reward_{uuid4().hex}"
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
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_shared_daily_cap_is_safe_for_concurrent_source_types(
    reward_engine: AsyncEngine,
):
    factory = async_sessionmaker(reward_engine, expire_on_commit=False)
    settings = Settings(contribution_daily_points_limit=20)
    start = asyncio.Event()

    async def reserve(source_type: RewardSourceType, reference: str) -> int:
        await start.wait()
        async with factory() as session, session.begin():
            reward = await RewardService(session, settings=settings).reserve_contribution_reward(
                user_id="USER-001",
                source_type=source_type,
                source_reference=reference,
                requested_points=20,
                metadata={"slot_id": "F1-A01", "floor_id": "F1"},
            )
            return reward.points if reward is not None else 0

    tasks = [
        asyncio.create_task(reserve(RewardSourceType.ADJACENT_SLOT_OBSERVATION, "OBS-1")),
        asyncio.create_task(reserve(RewardSourceType.WRONG_PARKING_REPORT, "REPORT-1")),
    ]
    start.set()
    results = await asyncio.gather(*tasks)

    assert sorted(results) == [0, 20]
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(RewardTransaction))
        pending_points = await session.scalar(
            select(func.sum(RewardTransaction.points)).where(
                RewardTransaction.status == RewardTransactionStatus.PENDING
            )
        )
    assert count == 1
    assert pending_points == 20


@pytest.mark.asyncio
async def test_summary_is_derived_from_ledger_and_settlement_is_single_use(
    reward_engine: AsyncEngine,
):
    factory = async_sessionmaker(reward_engine, expire_on_commit=False)
    settings = Settings(contribution_daily_points_limit=100)
    async with factory() as session, session.begin():
        service = RewardService(session, settings=settings)
        reward = await service.reserve_contribution_reward(
            user_id="USER-001",
            source_type=RewardSourceType.WRONG_PARKING_REPORT,
            source_reference="REPORT-SUMMARY",
            requested_points=20,
            metadata={"slot_id": "F3-D01", "floor_id": "F3"},
        )
        assert reward is not None
        await service.settle_pending(RewardSourceType.WRONG_PARKING_REPORT, "REPORT-SUMMARY")

    async with factory() as session:
        summary = await RewardService(session, settings=settings).get_summary("USER-001")
    assert summary.available_points == 20
    assert summary.pending_points == 0
    assert summary.verified_contributions == 1
    assert summary.daily_earned_points == 20

    async with factory() as session, session.begin():
        with pytest.raises(RewardError):
            await RewardService(session, settings=settings).settle_pending(
                RewardSourceType.WRONG_PARKING_REPORT, "REPORT-SUMMARY"
            )
