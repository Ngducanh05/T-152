from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.main import create_app
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import Base
from src.core.seed import seed_if_missing


@pytest_asyncio.fixture
async def phase3_client() -> AsyncGenerator[AsyncClient, None]:
    database_url = get_settings().database_url
    schema_name = f"test_phase3_flow_{uuid4().hex}"
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))

    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_if_missing(session)

    async def override_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db_session] = override_db_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


def _recommendation_payload() -> dict[str, object]:
    return {
        "user_id": "USER-001",
        "start_node_id": "F1-ENTRANCE",
        "charging_required": True,
        "accessible_required": False,
        "near_elevator": True,
        "limit": 3,
    }


@pytest.mark.asyncio
async def test_phase3_recommend_route_park_and_recommend_again(
    phase3_client: AsyncClient,
):
    reset = await phase3_client.post("/api/v1/simulator/reset", json={})
    assert reset.status_code == 200

    first = await phase3_client.post(
        "/api/v1/recommendations",
        json=_recommendation_payload(),
    )
    assert first.status_code == 200
    first_data = first.json()["data"]
    candidate_id = first_data["recommendations"][0]["slot_id"]

    route = await phase3_client.post(
        "/api/v1/routes",
        json={
            "start_node_id": "F1-ENTRANCE",
            "destination_node_id": candidate_id,
            "mode": "VEHICLE",
        },
    )
    assert route.status_code == 200
    assert route.json()["data"]["path"][-1] == candidate_id

    parked = await phase3_client.post(
        "/api/v1/simulator/park",
        json={"slot_id": candidate_id, "vehicle_id": "SIM-CAR-99"},
    )
    assert parked.status_code == 200

    second = await phase3_client.post(
        "/api/v1/recommendations",
        json=_recommendation_payload(),
    )
    assert second.status_code == 200
    second_data = second.json()["data"]
    second_ids = {item["slot_id"] for item in second_data["recommendations"]}
    assert candidate_id not in second_ids
    assert second_data["parking_state_version"] > first_data["parking_state_version"]
