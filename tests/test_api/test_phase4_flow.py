import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema, DropSchema

import src.core.parking_session as parking_session_module
from src.api.main import create_app
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import (
    Base,
    ParkingEvent,
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.seed import seed_if_missing
from src.models.schemas import (
    ParkingEventType,
    ParkingSessionStatus,
    ReservationStatus,
    SlotStatus,
)


@dataclass(slots=True)
class Phase4Api:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def phase4_api() -> AsyncGenerator[Phase4Api, None]:
    database_url = get_settings().database_url
    schema_name = f"test_phase4_flow_{uuid4().hex}"
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
            yield Phase4Api(client=client, session_factory=session_factory)
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


def _reservation_payload(
    slot_id: str,
    *,
    user_id: str = "USER-001",
    vehicle_id: str = "VEHICLE-001",
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "vehicle_id": vehicle_id,
        "slot_id": slot_id,
        "expected_version": 0,
    }


@pytest.mark.asyncio
async def test_phase4_end_to_end_flow(phase4_api: Phase4Api):
    client = phase4_api.client
    entrance = await client.post(
        "/api/v1/locations/confirm",
        json={"user_id": "USER-001", "node_id": "F1-ENTRANCE"},
    )
    assert entrance.status_code == 200

    recommendation = await client.post(
        "/api/v1/recommendations",
        json={
            "user_id": "USER-001",
            "start_node_id": "F1-ENTRANCE",
            "charging_required": True,
            "accessible_required": False,
            "near_elevator": True,
            "limit": 1,
        },
    )
    assert recommendation.status_code == 200
    slot_id = recommendation.json()["data"]["recommendations"][0]["slot_id"]

    reserved = await client.post(
        "/api/v1/reservations",
        json=_reservation_payload(slot_id),
    )
    assert reserved.status_code == 201
    reservation_id = reserved.json()["data"]["id"]
    active_reservation = await client.get(
        "/api/v1/reservations/active",
        params={"user_id": "USER-001"},
    )
    assert active_reservation.status_code == 200
    assert active_reservation.json()["data"]["id"] == reservation_id

    route_to_slot = await client.post(
        "/api/v1/routes",
        json={
            "start_node_id": "F1-ENTRANCE",
            "destination_node_id": slot_id,
        },
    )
    assert route_to_slot.status_code == 200
    assert route_to_slot.json()["data"]["path"][-1] == slot_id

    confirmed = await client.post(
        "/api/v1/sessions/confirm-parking",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "reservation_id": reservation_id,
            "expected_version": 1,
        },
    )
    assert confirmed.status_code == 200
    session_id = confirmed.json()["data"]["id"]

    checkpoint = await client.post(
        "/api/v1/locations/confirm",
        json={"user_id": "USER-001", "node_id": "F1-CP3"},
    )
    assert checkpoint.status_code == 200
    current = await client.get(
        "/api/v1/locations/current",
        params={"user_id": "USER-001"},
    )
    assert current.json()["data"]["node_id"] == "F1-CP3"

    vehicle = await client.get(
        "/api/v1/sessions/active",
        params={"user_id": "USER-001"},
    )
    assert vehicle.status_code == 200
    vehicle_data = vehicle.json()["data"]
    assert vehicle_data["session_id"] == session_id
    assert vehicle_data["destination_node_id"] == slot_id

    route_to_vehicle = await client.post(
        "/api/v1/routes",
        json={
            "start_node_id": "F1-CP3",
            "destination_node_id": vehicle_data["destination_node_id"],
        },
    )
    assert route_to_vehicle.status_code == 200
    assert route_to_vehicle.json()["data"]["path"][-1] == slot_id

    completed = await client.post(
        f"/api/v1/sessions/{session_id}/complete",
        json={"user_id": "USER-001", "expected_version": 2},
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "COMPLETED"
    slot = await client.get(f"/api/v1/parking/slots/{slot_id}")
    assert slot.json()["data"]["status"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_two_reservation_requests_for_same_slot_have_one_winner(
    phase4_api: Phase4Api,
):
    async with phase4_api.session_factory() as session, session.begin():
        session.add(ParkingUser(id="USER-002", display_name="Second User"))
        session.add(
            Vehicle(
                id="VEHICLE-002",
                user_id="USER-002",
                plate_number="51A-00002",
                requires_charging=False,
            )
        )

    first, second = await asyncio.gather(
        phase4_api.client.post(
            "/api/v1/reservations",
            json=_reservation_payload("F1-D10"),
        ),
        phase4_api.client.post(
            "/api/v1/reservations",
            json=_reservation_payload(
                "F1-D10", user_id="USER-002", vehicle_id="VEHICLE-002"
            ),
        ),
    )
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["code"] == "SLOT_NOT_AVAILABLE"
    async with phase4_api.session_factory() as session:
        active_count = await session.scalar(
            select(func.count())
            .select_from(ParkingReservation)
            .where(
                ParkingReservation.slot_id == "F1-D10",
                ParkingReservation.status == ReservationStatus.ACTIVE,
            )
        )
    assert active_count == 1


@pytest.mark.asyncio
async def test_confirm_session_failure_rolls_back_all_state(
    phase4_api: Phase4Api,
    monkeypatch: pytest.MonkeyPatch,
):
    reserved = await phase4_api.client.post(
        "/api/v1/reservations",
        json=_reservation_payload("F1-B01"),
    )
    reservation_id = reserved.json()["data"]["id"]
    timestamp = datetime.now(UTC)
    async with phase4_api.session_factory() as session, session.begin():
        session.add(
            ParkingSession(
                id="SESSION-duplicate",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F1-B02",
                status=ParkingSessionStatus.COMPLETED,
                parked_at=timestamp,
                completed_at=timestamp,
            )
        )
    monkeypatch.setattr(parking_session_module, "uuid4", lambda: "duplicate")

    response = await phase4_api.client.post(
        "/api/v1/sessions/confirm-parking",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "reservation_id": reservation_id,
            "expected_version": 1,
        },
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"

    async with phase4_api.session_factory() as session:
        reservation = await session.get(ParkingReservation, reservation_id)
        slot = await session.get(ParkingSlot, "F1-B01")
        parked_events = await session.scalar(
            select(func.count())
            .select_from(ParkingEvent)
            .where(
                ParkingEvent.slot_id == "F1-B01",
                ParkingEvent.event_type == ParkingEventType.VEHICLE_PARKED,
            )
        )
    assert reservation is not None and reservation.status is ReservationStatus.ACTIVE
    assert slot is not None and slot.status is SlotStatus.RESERVED
    assert parked_events == 0


@pytest.mark.asyncio
async def test_expired_confirm_commits_cleanup_before_returning_conflict(
    phase4_api: Phase4Api,
):
    reserved = await phase4_api.client.post(
        "/api/v1/reservations",
        json=_reservation_payload("F1-C01"),
    )
    reservation_id = reserved.json()["data"]["id"]
    async with phase4_api.session_factory() as session, session.begin():
        reservation = await session.get(ParkingReservation, reservation_id)
        assert reservation is not None
        current_time = datetime.now(UTC)
        reservation.created_at = current_time - timedelta(seconds=2)
        reservation.expires_at = current_time - timedelta(seconds=1)

    expired = await phase4_api.client.post(
        "/api/v1/sessions/confirm-parking",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "reservation_id": reservation_id,
            "expected_version": 1,
        },
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "RESERVATION_EXPIRED"
    async with phase4_api.session_factory() as session:
        reservation = await session.get(ParkingReservation, reservation_id)
        slot = await session.get(ParkingSlot, "F1-C01")
        session_count = await session.scalar(select(func.count()).select_from(ParkingSession))
    assert reservation is not None and reservation.status is ReservationStatus.EXPIRED
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert session_count == 0


@pytest.mark.asyncio
async def test_openapi_exposes_exactly_eight_phase4_operations(phase4_api: Phase4Api):
    response = await phase4_api.client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    expected_operations = {
        ("/api/v1/reservations", "post"),
        ("/api/v1/reservations/active", "get"),
        ("/api/v1/reservations/{reservation_id}", "delete"),
        ("/api/v1/sessions/confirm-parking", "post"),
        ("/api/v1/sessions/active", "get"),
        ("/api/v1/sessions/{session_id}/complete", "post"),
        ("/api/v1/locations/confirm", "post"),
        ("/api/v1/locations/current", "get"),
    }
    actual_operations = {
        (path, method)
        for path, operations in paths.items()
        for method in operations
        if path.startswith(
            ("/api/v1/reservations", "/api/v1/sessions", "/api/v1/locations")
        )
    }
    assert actual_operations == expected_operations


@pytest.mark.asyncio
async def test_phase4_request_models_reject_extra_fields(phase4_api: Phase4Api):
    response = await phase4_api.client.post(
        "/api/v1/sessions/confirm-parking",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "reservation_id": "RESERVATION-unknown",
            "slot_id": "F1-D01",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_phase4_domain_errors_use_stable_http_codes(phase4_api: Phase4Api):
    missing_user = await phase4_api.client.get(
        "/api/v1/locations/current",
        params={"user_id": "USER-MISSING"},
    )
    assert missing_user.status_code == 404
    assert missing_user.json()["error"]["code"] == "USER_NOT_FOUND"

    missing_reservation = await phase4_api.client.post(
        "/api/v1/sessions/confirm-parking",
        json={
            "user_id": "USER-001",
            "vehicle_id": "VEHICLE-001",
            "reservation_id": "RESERVATION-missing",
        },
    )
    assert missing_reservation.status_code == 404
    assert missing_reservation.json()["error"]["code"] == "RESERVATION_NOT_FOUND"

    invalid_location = await phase4_api.client.post(
        "/api/v1/locations/confirm",
        json={"user_id": "USER-001", "node_id": "F1-A-W"},
    )
    assert invalid_location.status_code == 422
    assert invalid_location.json()["error"]["code"] == "INVALID_LOCATION_NODE_TYPE"


@pytest.mark.asyncio
async def test_cancel_reservation_endpoint_releases_slot(phase4_api: Phase4Api):
    reserved = await phase4_api.client.post(
        "/api/v1/reservations",
        json=_reservation_payload("F1-A01"),
    )
    reservation_id = reserved.json()["data"]["id"]

    cancelled = await phase4_api.client.delete(
        f"/api/v1/reservations/{reservation_id}",
        params={"user_id": "USER-001"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    slot = await phase4_api.client.get("/api/v1/parking/slots/F1-A01")
    assert slot.json()["data"]["status"] == "AVAILABLE"
