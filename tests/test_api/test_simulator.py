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

from src.api.main import REQUEST_ID_HEADER, create_app
from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.db_models import (
    Base,
    ParkingEvent,
    ParkingReservation,
    ParkingSession,
    ParkingUser,
    Vehicle,
)
from src.core.parking_state import ParkingStateService
from src.core.reservation import ReservationService
from src.core.seed import seed_if_missing
from src.models.schemas import ParkingSessionStatus, ReservationStatus


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


async def _reserve_demo_slot(api: SimulatorApi, slot_id: str = "F1-A01") -> str:
    slot_response = await api.client.get(f"/api/v1/parking/slots/{slot_id}")
    response = await api.client.post(
        "/api/v1/reservations",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "slot_id": slot_id,
            "expected_version": slot_response.json()["data"]["version"],
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _assert_current_baseline(api: SimulatorApi) -> None:
    status_response = await api.client.get("/api/v1/parking/status")
    slots_response = await api.client.get("/api/v1/parking/slots")
    location_response = await api.client.get(
        "/api/v1/locations/current", params={"user_id": "USER-001"}
    )
    reservation_response = await api.client.get(
        "/api/v1/reservations/active", params={"user_id": "USER-001"}
    )
    session_response = await api.client.get(
        "/api/v1/sessions/active", params={"user_id": "USER-001"}
    )

    status = status_response.json()["data"]
    assert (status["total"], status["available"], status["reserved"], status["occupied"]) == (
        40,
        39,
        0,
        1,
    )
    occupied = [
        slot for slot in slots_response.json()["data"] if slot["status"] == "OCCUPIED"
    ]
    assert [(slot["id"], slot["occupied_by_vehicle_id"]) for slot in occupied] == [
        ("F1-B03", "SIM-CAR-02")
    ]
    assert location_response.json()["data"]["node_id"] == "F1-ENTRANCE"
    assert reservation_response.status_code == 404
    assert session_response.status_code == 404


@pytest.mark.asyncio
async def test_reset_updates_parking_status(simulator_api: SimulatorApi):
    await _reset(simulator_api)
    await _assert_current_baseline(simulator_api)


@pytest.mark.asyncio
async def test_reset_closes_active_demo_reservation_and_preserves_history(
    simulator_api: SimulatorApi,
):
    reservation_id = await _reserve_demo_slot(simulator_api)

    await _reset(simulator_api)
    await _assert_current_baseline(simulator_api)

    async with simulator_api.session_factory() as session:
        reservation = await session.get(ParkingReservation, reservation_id)
        event_count = await session.scalar(select(func.count()).select_from(ParkingEvent))
    assert reservation is not None
    assert reservation.status is ReservationStatus.CANCELLED
    assert event_count is not None and event_count >= 3


@pytest.mark.asyncio
async def test_reset_completes_active_session_and_releases_user_slot(
    simulator_api: SimulatorApi,
):
    reservation_id = await _reserve_demo_slot(simulator_api, "F1-D06")
    slot = await simulator_api.client.get("/api/v1/parking/slots/F1-D06")
    confirm = await simulator_api.client.post(
        "/api/v1/sessions/confirm-parking",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "reservation_id": reservation_id,
            "expected_version": slot.json()["data"]["version"],
        },
    )
    assert confirm.status_code == 200
    session_id = confirm.json()["data"]["id"]

    await _reset(simulator_api)
    await _assert_current_baseline(simulator_api)

    async with simulator_api.session_factory() as session:
        parking_session = await session.get(ParkingSession, session_id)
        reservation = await session.get(ParkingReservation, reservation_id)
    assert parking_session is not None
    assert parking_session.status is ParkingSessionStatus.COMPLETED
    assert parking_session.completed_at is not None
    assert reservation is not None
    assert reservation.status is ReservationStatus.CONFIRMED


@pytest.mark.asyncio
async def test_reset_twice_is_idempotent_for_current_state(simulator_api: SimulatorApi):
    await _reset(simulator_api)
    first = (await simulator_api.client.get("/api/v1/parking/slots")).json()["data"]

    await _reset(simulator_api)
    second = (await simulator_api.client.get("/api/v1/parking/slots")).json()["data"]

    assert second == first
    await _assert_current_baseline(simulator_api)


@pytest.mark.asyncio
async def test_reset_does_not_modify_another_users_active_state(
    simulator_api: SimulatorApi,
):
    demo_reservation_id = await _reserve_demo_slot(simulator_api, "F1-A01")
    async with simulator_api.session_factory() as session, session.begin():
        session.add(
            ParkingUser(
                id="USER-OTHER",
                display_name="Other User",
                current_node_id="F1-CP1",
            )
        )
        session.add(
            Vehicle(
                id="VEHICLE-OTHER",
                user_id="USER-OTHER",
                plate_number="51A-99999",
                requires_charging=False,
            )
        )
        await session.flush()
        other_reservation = await ReservationService(
            session, ParkingStateService(session)
        ).create_reservation("USER-OTHER", "VEHICLE-OTHER", "F1-C01")
        other_reservation_id = other_reservation.id

    response = await simulator_api.client.post("/api/v1/simulator/reset", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TRANSITION"
    async with simulator_api.session_factory() as session:
        demo_reservation = await session.get(ParkingReservation, demo_reservation_id)
        other_reservation = await session.get(ParkingReservation, other_reservation_id)
        other_user = await session.get(ParkingUser, "USER-OTHER")
    assert demo_reservation is not None
    assert demo_reservation.status is ReservationStatus.ACTIVE
    assert other_reservation is not None
    assert other_reservation.status is ReservationStatus.ACTIVE
    assert other_user is not None and other_user.current_node_id == "F1-CP1"


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
