from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.main import REQUEST_ID_HEADER, create_app
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import Base
from src.core.seed import seed_if_missing


@pytest_asyncio.fixture
async def recommendation_client() -> AsyncGenerator[AsyncClient, None]:
    database_url = get_settings().database_url
    schema_name = f"test_recommendation_api_{uuid4().hex}"
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


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "user_id": "USER-001",
        "start_node_id": "F1-ENTRANCE",
        "charging_required": True,
        "accessible_required": False,
        "near_elevator": True,
        "limit": 3,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_recommendations_return_contract(recommendation_client: AsyncClient):
    response = await recommendation_client.post(
        "/api/v1/recommendations",
        json=_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] is None
    assert body["data"]["parking_state_version"] == 0
    assert len(body["data"]["recommendations"]) == 3
    for candidate in body["data"]["recommendations"]:
        assert set(candidate) == {"slot_id", "score", "distance_m", "reasons"}
        assert candidate["slot_id"].startswith(("F1-C", "F1-D"))
        assert candidate["reasons"]


@pytest.mark.asyncio
async def test_empty_recommendations_return_http_200(recommendation_client: AsyncClient):
    response = await recommendation_client.post(
        "/api/v1/recommendations",
        json=_payload(accessible_required=True),
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "recommendations": [],
        "parking_state_version": 0,
    }


@pytest.mark.asyncio
async def test_recommendation_error_contains_request_id(recommendation_client: AsyncClient):
    request_id = str(uuid4())

    response = await recommendation_client.post(
        "/api/v1/recommendations",
        headers={REQUEST_ID_HEADER: request_id},
        json=_payload(start_node_id="F1-UNKNOWN"),
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json()["error"] == {
        "code": "ROUTE_NODE_NOT_FOUND",
        "message": "Route node F1-UNKNOWN was not found",
        "request_id": request_id,
    }


@pytest.mark.asyncio
async def test_recommendation_does_not_reserve_candidate(recommendation_client: AsyncClient):
    response = await recommendation_client.post(
        "/api/v1/recommendations",
        json=_payload(limit=1),
    )
    candidate_id = response.json()["data"]["recommendations"][0]["slot_id"]

    slot = await recommendation_client.get(f"/api/v1/parking/slots/{candidate_id}")
    status = await recommendation_client.get("/api/v1/parking/status")

    assert slot.json()["data"]["status"] == "AVAILABLE"
    assert status.json()["data"]["reserved"] == 0


@pytest.mark.asyncio
async def test_api_recommendation_releases_and_reuses_expired_slot(
    recommendation_client: AsyncClient,
):
    payload = _payload(limit=1)
    initial = await recommendation_client.post("/api/v1/recommendations", json=payload)
    slot_id = initial.json()["data"]["recommendations"][0]["slot_id"]
    slot = await recommendation_client.get(f"/api/v1/parking/slots/{slot_id}")
    reserved = await recommendation_client.post(
        "/api/v1/reservations",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "slot_id": slot_id,
            "expected_version": slot.json()["data"]["version"],
        },
    )
    assert reserved.status_code == 201
    expires_at = datetime.fromisoformat(
        reserved.json()["data"]["expires_at"].replace("Z", "+00:00")
    )

    with patch("src.core.recommendation.datetime") as recommendation_datetime:
        recommendation_datetime.now.return_value = expires_at + timedelta(seconds=1)
        refreshed = await recommendation_client.post(
            "/api/v1/recommendations", json=payload
        )

    current_slot = await recommendation_client.get(f"/api/v1/parking/slots/{slot_id}")
    active = await recommendation_client.get(
        "/api/v1/reservations/active", params={"user_id": "USER-001"}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["recommendations"][0]["slot_id"] == slot_id
    assert current_slot.json()["data"]["status"] == "AVAILABLE"
    assert active.status_code == 404


@pytest.mark.asyncio
async def test_recommendation_router_preserves_existing_apis(
    recommendation_client: AsyncClient,
):
    openapi = await recommendation_client.get("/openapi.json")
    paths = openapi.json()["paths"]

    assert "/api/v1/recommendations" in paths
    assert "/api/v1/routes" in paths
    assert "/api/v1/simulator/reset" in paths
    assert (await recommendation_client.get("/health")).status_code == 200
