from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.main import REQUEST_ID_HEADER, create_app
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import Base
from src.core.seed import seed_if_missing


@pytest_asyncio.fixture
async def parking_client() -> AsyncGenerator[AsyncClient, None]:
    database_url = get_settings().database_url
    schema_name = f"test_parking_api_{uuid4().hex}"
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

    async def override_db_session():
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


@pytest.mark.asyncio
async def test_parking_status_returns_seeded_baseline(parking_client: AsyncClient):
    response = await parking_client.get("/api/v1/parking/status")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "total": 40,
            "available": 40,
            "reserved": 0,
            "occupied": 0,
            "by_zone": {
                zone: {"AVAILABLE": 10, "RESERVED": 0, "OCCUPIED": 0}
                for zone in "ABCD"
            },
        },
        "message": None,
    }


@pytest.mark.asyncio
async def test_parking_slots_and_all_filters(parking_client: AsyncClient):
    cases = (
        ({}, 40),
        ({"zone_id": "A"}, 10),
        ({"status": "AVAILABLE"}, 40),
        ({"status": "RESERVED"}, 0),
        ({"has_charger": "true"}, 10),
        ({"has_charger": "false"}, 30),
        ({"is_accessible": "true"}, 0),
        ({"is_accessible": "false"}, 40),
        ({"zone_id": "C", "has_charger": "true"}, 5),
    )

    for parameters, expected_count in cases:
        response = await parking_client.get("/api/v1/parking/slots", params=parameters)
        assert response.status_code == 200
        assert len(response.json()["data"]) == expected_count

    response = await parking_client.get("/api/v1/parking/slots")
    slots = response.json()["data"]
    assert [slot["id"] for slot in slots] == sorted(slot["id"] for slot in slots)
    assert sum(slot["has_charger"] for slot in slots) == 10


@pytest.mark.asyncio
async def test_parking_slot_detail_and_missing_error(parking_client: AsyncClient):
    response = await parking_client.get("/api/v1/parking/slots/F1-C03")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": "F1-C03",
        "floor_id": "F1",
        "zone_id": "C",
        "node_id": "F1-C-W",
        "status": "AVAILABLE",
        "has_charger": True,
        "is_accessible": False,
        "version": 0,
        "occupied_by_vehicle_id": None,
    }

    request_id = str(uuid4())
    missing = await parking_client.get(
        "/api/v1/parking/slots/F1-Z99",
        headers={REQUEST_ID_HEADER: request_id},
    )
    assert missing.status_code == 404
    assert missing.headers[REQUEST_ID_HEADER] == request_id
    assert missing.json() == {
        "success": False,
        "error": {
            "code": "SLOT_NOT_FOUND",
            "message": "Parking slot F1-Z99 was not found",
            "request_id": request_id,
        },
    }


@pytest.mark.asyncio
async def test_parking_map_returns_canonical_graph_and_current_slots(
    parking_client: AsyncClient,
):
    response = await parking_client.get("/api/v1/parking/map")

    assert response.status_code == 200
    parking_map = response.json()["data"]
    assert len(parking_map["nodes"]) == 54
    assert len(parking_map["edges"]) == 58
    assert len(parking_map["slots"]) == 40
    assert sum(slot["has_charger"] for slot in parking_map["slots"]) == 10
    assert {edge["to_node"] for edge in parking_map["edges"] if edge["from_node"] == "F1-ELEVATOR"} == set()
    elevator_edges = {
        frozenset((edge["from_node"], edge["to_node"]))
        for edge in parking_map["edges"]
        if "F1-ELEVATOR" in (edge["from_node"], edge["to_node"])
    }
    assert elevator_edges == {
        frozenset(("F1-C-E", "F1-ELEVATOR")),
        frozenset(("F1-D-W", "F1-ELEVATOR")),
    }


@pytest.mark.asyncio
async def test_parking_filters_validate_contract_and_health_routes_remain(
    parking_client: AsyncClient,
):
    invalid = await parking_client.get("/api/v1/parking/slots", params={"zone_id": "Z"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid.json()["error"]["request_id"]

    openapi = (await parking_client.get("/openapi.json")).json()["paths"]
    assert "/health" in openapi
    assert "/api/v1/health/database" in openapi

