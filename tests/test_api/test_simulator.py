from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.main import REQUEST_ID_HEADER, create_app
from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.db_models import Base
from src.core.parking_state import ParkingStateService
from src.core.seed import seed_if_missing


@dataclass(slots=True)
class SimulatorApi:
    client: AsyncClient
    application: FastAPI
    session_factory: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def simulator_api() -> AsyncGenerator[SimulatorApi, None]:
    database_url = get_settings().database_url
    schema_name = f"test_simulator_api_{uuid4().hex}"
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
            yield SimulatorApi(
                client=client,
                application=application,
                session_factory=session_factory,
            )
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


async def _reset(api: SimulatorApi) -> None:
    response = await api.client.post("/api/v1/simulator/reset", json={})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reset_updates_parking_status(simulator_api: SimulatorApi):
    await _reset(simulator_api)

    response = await simulator_api.client.get("/api/v1/parking/status")

    assert response.status_code == 200
    status = response.json()["data"]
    assert (status["available"], status["reserved"], status["occupied"]) == (39, 0, 1)


@pytest.mark.asyncio
async def test_park_updates_slot_through_parking_api(simulator_api: SimulatorApi):
    await _reset(simulator_api)

    response = await simulator_api.client.post(
        "/api/v1/simulator/park",
        json={"slot_id": "F1-A04", "vehicle_id": "SIM-CAR-01"},
    )
    slot_response = await simulator_api.client.get("/api/v1/parking/slots/F1-A04")

    assert response.status_code == 200
    assert slot_response.status_code == 200
    assert slot_response.json()["data"]["status"] == "OCCUPIED"
    assert slot_response.json()["data"]["occupied_by_vehicle_id"] == "SIM-CAR-01"


@pytest.mark.asyncio
async def test_leave_updates_slot_through_parking_api(simulator_api: SimulatorApi):
    await _reset(simulator_api)
    await simulator_api.client.post(
        "/api/v1/simulator/park",
        json={"slot_id": "F1-A04", "vehicle_id": "SIM-CAR-01"},
    )

    response = await simulator_api.client.post(
        "/api/v1/simulator/leave",
        json={"slot_id": "F1-A04", "vehicle_id": "SIM-CAR-01"},
    )
    slot_response = await simulator_api.client.get("/api/v1/parking/slots/F1-A04")

    assert response.status_code == 200
    assert slot_response.status_code == 200
    assert slot_response.json()["data"]["status"] == "AVAILABLE"
    assert slot_response.json()["data"]["occupied_by_vehicle_id"] is None


@pytest.mark.asyncio
async def test_fixed_scenario_updates_parking_status(simulator_api: SimulatorApi):
    response = await simulator_api.client.post(
        "/api/v1/simulator/run-scenario",
        json={},
    )
    status_response = await simulator_api.client.get("/api/v1/parking/status")

    assert response.status_code == 200
    assert [step["action"] for step in response.json()["data"]] == [
        "RESET",
        "PARK",
        "LEAVE",
        "PARK",
    ]
    status = status_response.json()["data"]
    assert (status["available"], status["reserved"], status["occupied"]) == (38, 0, 2)


@pytest.mark.asyncio
async def test_reserved_slot_rejects_simulator_park(simulator_api: SimulatorApi):
    async with simulator_api.session_factory() as session, session.begin():
        await ParkingStateService(session).reserve_slot(
            "F1-C01",
            "RESERVATION-001",
            user_id="USER-001",
            vehicle_id="VEHICLE-001",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    response = await simulator_api.client.post(
        "/api/v1/simulator/park",
        json={"slot_id": "F1-C01", "vehicle_id": "SIM-CAR-04"},
    )
    slot_response = await simulator_api.client.get("/api/v1/parking/slots/F1-C01")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    assert slot_response.json()["data"]["status"] == "RESERVED"
    assert slot_response.json()["data"]["version"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("simulator_enabled", "demo_mode"),
    [(False, True), (True, False)],
)
async def test_simulator_disabled_rejects_endpoint(
    simulator_api: SimulatorApi,
    simulator_enabled: bool,
    demo_mode: bool,
):
    simulator_api.application.dependency_overrides[get_settings] = lambda: Settings(
        simulator_enabled=simulator_enabled,
        demo_mode=demo_mode,
    )

    response = await simulator_api.client.post("/api/v1/simulator/reset", json={})
    status_response = await simulator_api.client.get("/api/v1/parking/status")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    status = status_response.json()["data"]
    assert (status["available"], status["reserved"], status["occupied"]) == (40, 0, 0)


@pytest.mark.asyncio
async def test_simulator_error_contains_request_id(simulator_api: SimulatorApi):
    request_id = str(uuid4())

    response = await simulator_api.client.post(
        "/api/v1/simulator/leave",
        headers={REQUEST_ID_HEADER: request_id},
        json={"slot_id": "F1-A04", "vehicle_id": "SIM-CAR-01"},
    )

    assert response.status_code == 400
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json()["error"]["request_id"] == request_id
