"""API coverage for database-backed reward redemption and voucher wallets."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.dependencies import require_parking_user_or_demo
from src.api.main import create_app
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import (
    Base,
    ParkingUser,
    ParkingVoucher,
    RewardCatalogItem,
    RewardRedemption,
    RewardTransaction,
)
from src.core.reward import RewardService
from src.core.reward_redemption import RewardRedemptionService
from src.core.seed import seed_if_missing
from src.models.auth import AppRole, CurrentUser
from src.models.schemas import (
    RewardSourceType,
    RewardTransactionStatus,
    RewardTransactionType,
)


@dataclass(slots=True)
class RewardsApi:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]
    application: FastAPI


@pytest_asyncio.fixture
async def rewards_api() -> AsyncGenerator[RewardsApi, None]:
    schema_name = f"test_rewards_api_{uuid4().hex}"
    admin_engine = create_async_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))
    engine = create_async_engine(get_settings().database_url, connect_args={"server_settings": {"search_path": schema_name}})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_if_missing(session)

    async def override_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db_session] = override_db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            yield RewardsApi(client, factory, application)
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


async def _authenticate(api: RewardsApi, user_id: str = "USER-001") -> None:
    async def current_user() -> CurrentUser:
        return CurrentUser(id=uuid4(), email="user@example.com", role=AppRole.USER, parking_user_id=user_id)

    api.application.dependency_overrides[require_parking_user_or_demo] = current_user


async def _catalog_and_credit(
    api: RewardsApi,
    *,
    cost: int = 200,
    finalized_points: int = 200,
    pending_points: int = 0,
    credited_at: datetime | None = None,
) -> RewardCatalogItem:
    credited_at = credited_at or datetime.now(UTC)
    async with api.session_factory() as session, session.begin():
        item = RewardCatalogItem(
            id=f"CATALOG-{uuid4().hex}", code=f"CODE-{uuid4().hex[:10]}", name="Database-defined reward",
            points_cost=cost, free_minutes=37, validity_days=19, is_active=True,
        )
        session.add_all((
            item,
            RewardTransaction(
                id=f"CREDIT-{uuid4().hex}", user_id="USER-001", source_type=RewardSourceType.WRONG_PARKING_REPORT,
                source_reference=f"REPORT-{uuid4().hex}", transaction_type=RewardTransactionType.CONTRIBUTION_REWARD,
                status=RewardTransactionStatus.EARNED, points_delta=finalized_points, created_at=credited_at,
                settled_at=credited_at, transaction_metadata={},
            ),
        ))
        if pending_points:
            session.add(RewardTransaction(
                id=f"PENDING-{uuid4()}", user_id="USER-001", source_type=RewardSourceType.ADJACENT_SLOT_OBSERVATION,
                source_reference=f"OBS-{uuid4()}", transaction_type=RewardTransactionType.CONTRIBUTION_REWARD,
                status=RewardTransactionStatus.PENDING, points_delta=pending_points, created_at=credited_at,
                transaction_metadata={},
            ))
    return item


@pytest.mark.asyncio
async def test_catalog_returns_active_database_items_in_deterministic_order(rewards_api: RewardsApi):
    async with rewards_api.session_factory() as session, session.begin():
        session.add_all((
            RewardCatalogItem(id="ACTIVE-200", code="ZETA", name="From database", points_cost=200, free_minutes=37, validity_days=11, is_active=True),
            RewardCatalogItem(id="ACTIVE-100", code="ALPHA", name="Also database", points_cost=100, free_minutes=22, validity_days=13, is_active=True),
            RewardCatalogItem(id="INACTIVE", code="HIDDEN", name="Hidden", points_cost=50, free_minutes=5, validity_days=1, is_active=False),
        ))
    response = await rewards_api.client.get("/api/v1/rewards/catalog")
    assert response.status_code == 200
    data = response.json()["data"]
    assert [(item["id"], item["free_minutes"], item["validity_days"]) for item in data] == [
        ("ACTIVE-100", 22, 13), ("ACTIVE-200", 37, 11)
    ]


@pytest.mark.asyncio
async def test_authenticated_wallet_is_owned_and_expires_without_refund(rewards_api: RewardsApi):
    now = datetime.now(UTC)
    issued_at = now - timedelta(days=20)
    item = await _catalog_and_credit(rewards_api, credited_at=issued_at)
    async with rewards_api.session_factory() as session, session.begin():
        session.add(ParkingUser(id="USER-002", display_name="Other"))
        await RewardRedemptionService(session, clock=lambda: issued_at).redeem(
            user_id="USER-001", catalog_item_id=item.id
        )
    await _authenticate(rewards_api)
    owned = await rewards_api.client.get("/api/v1/rewards/users/USER-001/vouchers")
    other = await rewards_api.client.get("/api/v1/rewards/users/USER-002/vouchers")
    assert owned.status_code == 200
    assert owned.json()["data"][0]["status"] == "EXPIRED"
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "PARKING_OWNERSHIP_MISMATCH"
    async with rewards_api.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(RewardTransaction).where(RewardTransaction.transaction_type == RewardTransactionType.VOUCHER_REFUND)) == 0


@pytest.mark.asyncio
async def test_redemption_is_atomic_owned_and_idempotent(rewards_api: RewardsApi):
    item = await _catalog_and_credit(rewards_api, cost=200)
    await _authenticate(rewards_api)
    payload = {"user_id": "USER-001", "catalog_item_id": item.id}
    first = await rewards_api.client.post("/api/v1/rewards/redemptions", json=payload, headers={"Idempotency-Key": "reward-claim-1"})
    replay = await rewards_api.client.post("/api/v1/rewards/redemptions", json=payload, headers={"Idempotency-Key": "reward-claim-1"})
    assert first.status_code == replay.status_code == 201
    assert first.json()["data"] == replay.json()["data"]
    assert first.json()["data"]["available_points"] == 0
    assert first.json()["data"]["voucher"]["free_minutes_snapshot"] == 37
    async with rewards_api.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(RewardRedemption)) == 1
        assert await session.scalar(select(func.count()).select_from(ParkingVoucher)) == 1
        debit = await session.scalar(select(RewardTransaction).where(RewardTransaction.points_delta < 0))
    assert debit is not None and debit.points_delta == -200
    async with rewards_api.session_factory() as session, session.begin():
        session.add(RewardCatalogItem(id="OTHER-CATALOG", code="OTHER", name="Other", points_cost=100, free_minutes=10, validity_days=30, is_active=True))
    reused = await rewards_api.client.post("/api/v1/rewards/redemptions", json={"user_id": "USER-001", "catalog_item_id": "OTHER-CATALOG"}, headers={"Idempotency-Key": "reward-claim-1"})
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_insufficient_redemption_conflict_leaves_no_mutations(rewards_api: RewardsApi):
    item = await _catalog_and_credit(rewards_api, cost=201, finalized_points=100, pending_points=100)
    async with rewards_api.session_factory() as session:
        assert await RewardService(session).finalized_balance("USER-001") == 100
    await _authenticate(rewards_api)
    response = await rewards_api.client.post("/api/v1/rewards/redemptions", json={"user_id": "USER-001", "catalog_item_id": item.id})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_REWARD_POINTS"
    async with rewards_api.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(RewardRedemption)) == 0
        assert await session.scalar(select(func.count()).select_from(ParkingVoucher)) == 0
        assert await session.scalar(select(func.count()).select_from(RewardTransaction).where(RewardTransaction.points_delta < 0)) == 0
