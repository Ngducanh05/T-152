import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema, DropSchema

import src.core.parking_session as parking_session_module
from src.api.dependencies import require_parking_user_or_demo
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
    SlotObservation,
    Vehicle,
)
from src.core.seed import seed_if_missing
from src.models.auth import AppRole, CurrentUser
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
    application: FastAPI


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
            yield Phase4Api(
                client=client,
                session_factory=session_factory,
                application=application,
            )
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
async def test_scan_location_resolves_trusted_marker_and_rejects_invalid_input(
    phase4_api: Phase4Api,
):
    client = phase4_api.client
    success = await client.post(
        "/api/v1/locations/scan",
        json={"user_id": "USER-001", "qr_payload": "parksmart:location:v1:PSLOC-F3-D-W"},
    )
    assert success.status_code == 200
    assert success.json()["data"]["node_id"] == "F3-D-W"
    assert success.json()["data"]["marker_id"] == "PSLOC-F3-D-W"

    malformed = await client.post(
        "/api/v1/locations/scan",
        json={"user_id": "USER-001", "qr_payload": "F3-D-W"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "INVALID_LOCATION_QR"
    current_after_malformed = await client.get("/api/v1/locations/current", params={"user_id": "USER-001"})
    assert current_after_malformed.json()["data"]["node_id"] == "F3-D-W"

    unknown = await client.post(
        "/api/v1/locations/scan",
        json={"user_id": "USER-001", "qr_payload": "parksmart:location:v1:PSLOC-F3-Z-W"},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "LOCATION_MARKER_NOT_FOUND"
    current_after_unknown = await client.get("/api/v1/locations/current", params={"user_id": "USER-001"})
    assert current_after_unknown.json()["data"]["node_id"] == "F3-D-W"

    invalid_suffix = await client.post(
        "/api/v1/locations/scan",
        json={
            "user_id": "USER-001",
            "qr_payload": "parksmart:location:v1:PSLOC-F3-D-W:extra",
        },
    )
    assert invalid_suffix.status_code == 422
    assert invalid_suffix.json()["error"]["code"] == "INVALID_LOCATION_QR"

    extra_field = await client.post(
        "/api/v1/locations/scan",
        json={"user_id": "USER-001", "qr_payload": "F3-D-W", "node_id": "F3-D-W"},
    )
    assert extra_field.status_code == 422

    direct_node = await client.post(
        "/api/v1/locations/scan",
        json={"user_id": "USER-001", "node_id": "F3-D-W"},
    )
    assert direct_node.status_code == 422

    manual_aisle = await client.post(
        "/api/v1/locations/confirm",
        json={"user_id": "USER-001", "node_id": "F3-D-W"},
    )
    assert manual_aisle.status_code == 422
    assert manual_aisle.json()["error"]["code"] == "INVALID_LOCATION_NODE_TYPE"


@pytest.mark.asyncio
async def test_authenticated_user_cannot_change_another_parking_users_location(
    phase4_api: Phase4Api,
):
    async with phase4_api.session_factory() as session, session.begin():
        session.add(ParkingUser(id="USER-002", display_name="Second User"))

    async def authenticated_user() -> CurrentUser:
        return CurrentUser(
            id=uuid4(),
            email="user@example.com",
            role=AppRole.USER,
            parking_user_id="USER-001",
        )

    phase4_api.application.dependency_overrides[require_parking_user_or_demo] = authenticated_user
    try:
        response = await phase4_api.client.post(
            "/api/v1/locations/scan",
            json={
                "user_id": "USER-002",
                "qr_payload": "parksmart:location:v1:PSLOC-F3-D-W",
            },
        )
    finally:
        phase4_api.application.dependency_overrides.pop(require_parking_user_or_demo, None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PARKING_OWNERSHIP_MISMATCH"
    async with phase4_api.session_factory() as session:
        user = await session.get(ParkingUser, "USER-002")
    assert user is not None and user.current_node_id is None


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
            "mode": "VEHICLE",
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
            "mode": "PEDESTRIAN",
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
async def test_parked_user_can_observe_only_adjacent_slots(phase4_api: Phase4Api):
    timestamp = datetime.now(UTC)
    async with phase4_api.session_factory() as session, session.begin():
        own_slot = await session.get(ParkingSlot, "F1-D03")
        assert own_slot is not None
        own_slot.status = SlotStatus.OCCUPIED
        own_slot.occupied_by_vehicle_id = "VEHICLE-001"
        own_slot.version = 2
        session.add(
            ParkingSession(
                id="SESSION-OBSERVE",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F1-D03",
                status=ParkingSessionStatus.ACTIVE,
                parked_at=timestamp,
                completed_at=None,
            )
        )

    observed = await phase4_api.client.post(
        "/api/v1/parking/slots/F1-D02/observation",
        json={
            "user_id": "USER-001",
            "observed_status": "OCCUPIED",
            "expected_slot_version": 0,
        },
    )
    non_adjacent = await phase4_api.client.post(
        "/api/v1/parking/slots/F1-D05/observation",
        json={
            "user_id": "USER-001",
            "observed_status": "OCCUPIED",
            "expected_slot_version": 0,
        },
    )

    assert observed.status_code == 200
    assert observed.json()["data"]["verification_status"] == "PENDING"
    assert observed.json()["data"]["reward_status"] == "PENDING"
    assert observed.json()["data"]["reward_points"] == 10
    assert non_adjacent.status_code == 409
    assert non_adjacent.json()["error"]["code"] == "INVALID_OBSERVATION_TRANSITION"
    async with phase4_api.session_factory() as session:
        event = await session.scalar(select(ParkingEvent).where(ParkingEvent.slot_id == "F1-D02"))
        slot = await session.get(ParkingSlot, "F1-D02")
    assert event is None
    assert slot is not None
    assert slot.status is SlotStatus.AVAILABLE
    assert slot.version == 0


@pytest.mark.asyncio
async def test_adjacent_observation_requires_active_session(phase4_api: Phase4Api):
    response = await phase4_api.client.post(
        "/api/v1/parking/slots/F1-D02/observation",
        json={
            "user_id": "USER-001",
            "observed_status": "OCCUPIED",
            "expected_slot_version": 0,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ACTIVE_SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_observation_changes_slot_and_earns_only_after_admin_verification(
    phase4_api: Phase4Api,
):
    timestamp = datetime.now(UTC)
    async with phase4_api.session_factory() as session, session.begin():
        own_slot = await session.get(ParkingSlot, "F2-D03")
        assert own_slot is not None
        own_slot.status = SlotStatus.OCCUPIED
        own_slot.occupied_by_vehicle_id = "VEHICLE-001"
        session.add(
            ParkingSession(
                id="SESSION-OBSERVE-F2",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F2-D03",
                status=ParkingSessionStatus.ACTIVE,
                parked_at=timestamp,
                completed_at=None,
            )
        )

    created = await phase4_api.client.post(
        "/api/v1/parking/slots/F2-D02/observation",
        json={
            "user_id": "USER-001",
            "observed_status": "OCCUPIED",
            "expected_slot_version": 0,
        },
    )
    assert created.status_code == 200
    observation = created.json()["data"]
    before = await phase4_api.client.get("/api/v1/parking/slots/F2-D02")
    summary_before = await phase4_api.client.get("/api/v1/rewards/users/USER-001/summary")
    assert before.json()["data"]["status"] == "AVAILABLE"
    assert summary_before.json()["data"]["available_points"] == 0
    assert summary_before.json()["data"]["pending_points"] == 10
    contributions = await phase4_api.client.get("/api/v1/contributions/users/USER-001")
    observation_contribution = next(
        item for item in contributions.json()["data"] if item["source_reference"] == observation["id"]
    )
    assert observation_contribution["observer_session_id"] == "SESSION-OBSERVE-F2"

    verified = await phase4_api.client.post(
        f"/api/v1/admin/slot-observations/{observation['id']}/verify",
        json={"expected_version": observation["version"]},
    )
    assert verified.status_code == 200
    assert verified.json()["data"]["verification_status"] == "VERIFIED"
    assert verified.json()["data"]["reward_status"] == "EARNED"
    after = await phase4_api.client.get("/api/v1/parking/slots/F2-D02")
    summary_after = await phase4_api.client.get("/api/v1/rewards/users/USER-001/summary")
    assert after.json()["data"]["status"] == "OCCUPIED"
    assert summary_after.json()["data"]["available_points"] == 10
    assert summary_after.json()["data"]["pending_points"] == 0

    repeated = await phase4_api.client.post(
        f"/api/v1/admin/slot-observations/{observation['id']}/verify",
        json={"expected_version": verified.json()["data"]["version"]},
    )
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "INVALID_OBSERVATION_TRANSITION"


@pytest.mark.asyncio
async def test_rejected_and_expired_observations_cancel_reward_without_slot_change(
    phase4_api: Phase4Api,
):
    timestamp = datetime.now(UTC)
    async with phase4_api.session_factory() as session, session.begin():
        own_slot = await session.get(ParkingSlot, "F3-D03")
        assert own_slot is not None
        own_slot.status = SlotStatus.OCCUPIED
        own_slot.occupied_by_vehicle_id = "VEHICLE-001"
        session.add(
            ParkingSession(
                id="SESSION-OBSERVE-F3",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                slot_id="F3-D03",
                status=ParkingSessionStatus.ACTIVE,
                parked_at=timestamp,
                completed_at=None,
            )
        )

    first = await phase4_api.client.post(
        "/api/v1/parking/slots/F3-D02/observation",
        json={
            "user_id": "USER-001",
            "observed_status": "OCCUPIED",
            "expected_slot_version": 0,
        },
    )
    rejected = await phase4_api.client.post(
        f"/api/v1/admin/slot-observations/{first.json()['data']['id']}/reject",
        json={"expected_version": 0, "reason": "Không khớp kiểm tra hiện trường"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["verification_status"] == "REJECTED"
    assert rejected.json()["data"]["reward_status"] == "CANCELLED"
    unchanged = await phase4_api.client.get("/api/v1/parking/slots/F3-D02")
    assert unchanged.json()["data"]["status"] == "AVAILABLE"

    second = await phase4_api.client.post(
        "/api/v1/parking/slots/F3-D04/observation",
        json={
            "user_id": "USER-001",
            "observed_status": "OCCUPIED",
            "expected_slot_version": 0,
        },
    )
    second_data = second.json()["data"]
    async with phase4_api.session_factory() as session, session.begin():
        observation = await session.get(SlotObservation, second_data["id"])
        assert observation is not None
        observation.created_at = datetime.now(UTC) - timedelta(hours=2)
        observation.expires_at = datetime.now(UTC) - timedelta(hours=1)

    expired = await phase4_api.client.post(
        f"/api/v1/admin/slot-observations/{second_data['id']}/verify",
        json={"expected_version": second_data["version"]},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "OBSERVATION_EXPIRED"
    detail = await phase4_api.client.get(f"/api/v1/admin/slot-observations/{second_data['id']}")
    assert detail.json()["data"]["verification_status"] == "EXPIRED"
    assert detail.json()["data"]["reward_status"] == "CANCELLED"


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
            json=_reservation_payload("F1-D10", user_id="USER-002", vehicle_id="VEHICLE-002"),
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
        if path.startswith(("/api/v1/reservations", "/api/v1/sessions", "/api/v1/locations"))
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
