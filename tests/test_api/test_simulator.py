from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.dependencies import get_optional_current_user
from src.api.main import REQUEST_ID_HEADER, create_app
from src.api.routes import reports as report_routes
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
from src.core.db_models import WrongParkingReport as WrongParkingReportRow
from src.core.parking_report import ParkingReportError
from src.core.parking_state import ParkingStateService
from src.core.reservation import ReservationService
from src.core.seed import seed_if_missing
from src.models.auth import AppRole, CurrentUser
from src.models.schemas import (
    ActorType,
    ErrorCode,
    ParkingEventType,
    ParkingSessionStatus,
    ReservationStatus,
    SlotStatus,
)
from src.services.report_evidence import StoredReportEvidence


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
        120,
        119,
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
    assert (status["available"], status["reserved"], status["occupied"]) == (118, 0, 2)


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
    (
        "simulator_enabled",
        "demo_mode",
        "expected_status",
        "expected_code",
    ),
    [
        (False, True, 400, "INVALID_TRANSITION"),
        (True, False, 401, "AUTH_REQUIRED"),
    ],
)
async def test_simulator_disabled_rejects_endpoint(
    simulator_api: SimulatorApi,
    simulator_enabled: bool,
    demo_mode: bool,
    expected_status: int,
    expected_code: str,
):
    simulator_api.application.dependency_overrides[get_settings] = lambda: Settings(
        simulator_enabled=simulator_enabled,
        demo_mode=demo_mode,
    )

    response = await simulator_api.client.post("/api/v1/simulator/reset", json={})
    status_response = await simulator_api.client.get("/api/v1/parking/status")

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code

    if demo_mode:
        assert status_response.status_code == 200
        status = status_response.json()["data"]
        assert (
            status["available"],
            status["reserved"],
            status["occupied"],
        ) == (120, 0, 0)
    else:
        assert status_response.status_code == 401
        assert status_response.json()["error"]["code"] == "AUTH_REQUIRED"


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


async def _insert_admin_events(api: SimulatorApi) -> None:
    async with api.session_factory() as session, session.begin():
        session.add_all(
            [
                ParkingEvent(
                    id="EVENT-ADMIN-001",
                    event_type=ParkingEventType.VEHICLE_PARKED,
                    slot_id="F1-A01",
                    actor_type=ActorType.SIMULATOR,
                    actor_id="SIM-CAR-01",
                    old_status=SlotStatus.AVAILABLE,
                    new_status=SlotStatus.OCCUPIED,
                    created_at=datetime(2026, 8, 15, 8, 0, tzinfo=UTC),
                    event_metadata={"source": "test"},
                ),
                ParkingEvent(
                    id="EVENT-ADMIN-002",
                    event_type=ParkingEventType.VEHICLE_LEFT_SLOT,
                    slot_id="F1-A01",
                    actor_type=ActorType.SIMULATOR,
                    actor_id="SIM-CAR-01",
                    old_status=SlotStatus.OCCUPIED,
                    new_status=SlotStatus.AVAILABLE,
                    created_at=datetime(2026, 8, 15, 8, 5, tzinfo=UTC),
                    event_metadata={},
                ),
                ParkingEvent(
                    id="EVENT-ADMIN-003",
                    event_type=ParkingEventType.SLOT_RESERVED,
                    slot_id="F1-D01",
                    actor_type=ActorType.USER,
                    actor_id="USER-001",
                    old_status=SlotStatus.AVAILABLE,
                    new_status=SlotStatus.RESERVED,
                    created_at=datetime(2026, 8, 15, 8, 10, tzinfo=UTC),
                    event_metadata={"reservation_id": "RESERVATION-001"},
                ),
            ]
        )


@pytest.mark.asyncio
async def test_admin_events_are_ordered_and_limited(simulator_api: SimulatorApi):
    await _insert_admin_events(simulator_api)

    response = await simulator_api.client.get("/api/v1/admin/events", params={"limit": 2})

    assert response.status_code == 200
    events = response.json()["data"]
    assert [event["id"] for event in events] == ["EVENT-ADMIN-003", "EVENT-ADMIN-002"]
    assert events[0]["metadata"] == {"reservation_id": "RESERVATION-001"}


@pytest.mark.asyncio
async def test_admin_events_support_zone_type_and_slot_filters(simulator_api: SimulatorApi):
    await _insert_admin_events(simulator_api)

    zone_response = await simulator_api.client.get(
        "/api/v1/admin/events", params={"zone_id": "A"}
    )
    type_response = await simulator_api.client.get(
        "/api/v1/admin/events", params={"event_type": "SLOT_RESERVED"}
    )
    slot_response = await simulator_api.client.get(
        "/api/v1/admin/events", params={"slot_id": "F1-A01"}
    )

    assert [event["id"] for event in zone_response.json()["data"]] == [
        "EVENT-ADMIN-002",
        "EVENT-ADMIN-001",
    ]
    assert [event["id"] for event in type_response.json()["data"]] == [
        "EVENT-ADMIN-003"
    ]
    assert [event["id"] for event in slot_response.json()["data"]] == [
        "EVENT-ADMIN-002",
        "EVENT-ADMIN-001",
    ]


@pytest.mark.asyncio
async def test_admin_events_return_an_empty_list_for_no_match(simulator_api: SimulatorApi):
    await _insert_admin_events(simulator_api)

    response = await simulator_api.client.get(
        "/api/v1/admin/events", params={"slot_id": "F1-C10"}
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_admin_events_validate_limit_bounds(
    simulator_api: SimulatorApi,
    limit: int,
):
    response = await simulator_api.client.get(
        "/api/v1/admin/events", params={"limit": limit}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_admin_events_require_admin_role_outside_demo(simulator_api: SimulatorApi):
    simulator_api.application.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=False
    )
    response = await simulator_api.client.get("/api/v1/admin/events")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"

    async def regular_user() -> CurrentUser:
        return CurrentUser(
            id=uuid4(),
            email="user@example.com",
            full_name="User",
            role=AppRole.USER,
        )

    simulator_api.application.dependency_overrides[get_optional_current_user] = regular_user
    response = await simulator_api.client.get("/api/v1/admin/events")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"

    async def admin_user() -> CurrentUser:
        return CurrentUser(
            id=uuid4(),
            email="admin@example.com",
            full_name="Admin",
            role=AppRole.ADMIN,
        )

    simulator_api.application.dependency_overrides[get_optional_current_user] = admin_user
    response = await simulator_api.client.get("/api/v1/admin/events")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_can_report_wrong_parking_and_admin_can_read_it(
    simulator_api: SimulatorApi,
):
    response = await simulator_api.client.post(
        "/api/v1/reports/wrong-parking",
        json={
            "user_id": "USER-001",
            "slot_id": "F1-D01",
            "reason_code": "CROSSED_LINE",
            "observed_plate_number": "  51a-123.45  ",
            "description": "Xe Ä‘ang Ä‘á»— chĂ©o vĂ  láº¥n sang Ă´ bĂªn cáº¡nh.",
        },
    )

    assert response.status_code == 201
    report = response.json()["data"]
    assert report["id"].startswith("REPORT-")
    assert report["reporter_user_id"] == "USER-001"
    assert report["slot_id"] == "F1-D01"
    assert report["reason_code"] == "CROSSED_LINE"
    assert report["status"] == "OPEN"
    assert report["observed_plate_number"] == "51A-123.45"
    assert report["description"] == "Xe Ä‘ang Ä‘á»— chĂ©o vĂ  láº¥n sang Ă´ bĂªn cáº¡nh."
    assert report["created_at"].endswith("Z")
    assert report["updated_at"].endswith("Z")
    assert report["resolved_at"] is None
    assert report["resolved_by"] is None
    assert report["resolution_note"] is None
    assert report["version"] == 0

    admin_response = await simulator_api.client.get(
        "/api/v1/admin/reports", params={"limit": 1}
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["data"] == [report]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_status", "expected_code"),
    [
        (
            {
                "user_id": "USER-MISSING",
                "slot_id": "F1-D01",
                "reason_code": "OTHER",
                "description": "Xe Ä‘á»— khĂ´ng Ä‘Ăºng vá»‹ trĂ­.",
            },
            404,
            "USER_NOT_FOUND",
        ),
        (
            {
                "user_id": "USER-001",
                "slot_id": "F1-Z99",
                "reason_code": "OTHER",
                "description": "Xe Ä‘á»— khĂ´ng Ä‘Ăºng vá»‹ trĂ­.",
            },
            404,
            "SLOT_NOT_FOUND",
        ),
        (
            {
                "user_id": "USER-001",
                "slot_id": "F1-D01",
                "reason_code": "OTHER",
                "description": "   ",
            },
            422,
            "VALIDATION_ERROR",
        ),
    ],
)
async def test_wrong_parking_report_validates_input(
    simulator_api: SimulatorApi,
    payload: dict[str, object],
    expected_status: int,
    expected_code: str,
):
    response = await simulator_api.client.post(
        "/api/v1/reports/wrong-parking",
        json=payload,
    )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


@pytest.mark.asyncio
async def test_malformed_wrong_parking_json_returns_validation_envelope(
    simulator_api: SimulatorApi,
):
    response = await simulator_api.client.post(
        "/api/v1/reports/wrong-parking",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_uploaded_wrong_parking_evidence_is_cleaned_up_after_db_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    deleted_paths: list[str | None] = []

    class FakeStorage:
        def __init__(self, _settings: Settings) -> None:
            return None

        async def upload(
            self,
            *,
            report_id: str,
            data: bytes,
            content_type: str,
        ) -> StoredReportEvidence:
            return StoredReportEvidence(
                storage_path=f"reports/{report_id}/evidence.jpg",
                content_type=content_type,
                size_bytes=len(data),
            )

        async def delete(self, storage_path: str | None) -> bool:
            deleted_paths.append(storage_path)
            return True

    class FailingReportService:
        def __init__(self, _session: AsyncSession) -> None:
            return None

        async def create_wrong_parking_report(self, **_kwargs: object) -> object:
            raise ParkingReportError(
                ErrorCode.SLOT_NOT_FOUND,
                "Parking slot was not found.",
                slot_id="F1-D01",
            )

    monkeypatch.setitem(
        report_routes.create_wrong_parking_report.__globals__,
        "ReportEvidenceStorage",
        FakeStorage,
    )
    monkeypatch.setitem(
        report_routes.create_wrong_parking_report.__globals__,
        "ParkingReportService",
        FailingReportService,
    )

    class FakeEvidence:
        content_type = "image/jpeg"

        async def read(self) -> bytes:
            return b"fake-image"

    class FakeRequest:
        headers = {"content-type": "multipart/form-data; boundary=test"}
        state = SimpleNamespace(request_id="cleanup-test")

        async def form(self) -> dict[str, object]:
            return {
                "user_id": "USER-001",
                "slot_id": "F1-D01",
                "reason_code": "CROSSED_LINE",
                "evidence": FakeEvidence(),
            }

    class FakeTransaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakeSession:
        def begin(self) -> FakeTransaction:
            return FakeTransaction()

    with pytest.raises(HTTPException) as exc_info:
        await report_routes.create_wrong_parking_report(
            FakeRequest(),  # type: ignore[arg-type]
            FakeSession(),  # type: ignore[arg-type]
            CurrentUser(
                id=UUID("11111111-1111-4111-8111-111111111111"),
                email="user@example.com",
                role=AppRole.USER,
                parking_user_id="USER-001",
                default_vehicle_id="VEHICLE-001",
            ),
            Settings(demo_mode=True),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "code": "SLOT_NOT_FOUND",
        "message": "Parking slot was not found.",
    }
    assert len(deleted_paths) == 1
    assert deleted_paths[0].startswith("reports/REPORT-")


@pytest.mark.asyncio
async def test_standard_wrong_parking_reason_allows_no_description_and_keeps_slot_state(
    simulator_api: SimulatorApi,
):
    before = await simulator_api.client.get("/api/v1/parking/slots/F1-C03")

    response = await simulator_api.client.post(
        "/api/v1/reports/wrong-parking",
        json={
            "user_id": "USER-001",
            "slot_id": "F1-C03",
            "reason_code": "BLOCKING_ACCESS",
            "observed_plate_number": "  30a-000.01 ",
        },
    )
    after = await simulator_api.client.get("/api/v1/parking/slots/F1-C03")

    assert response.status_code == 201
    report = response.json()["data"]
    assert report["description"] is None
    assert report["observed_plate_number"] == "30A-000.01"
    assert report["reason_code"] == "BLOCKING_ACCESS"
    assert report["status"] == "OPEN"
    assert report["version"] == 0
    assert after.json()["data"] == before.json()["data"]


@pytest.mark.asyncio
async def test_other_wrong_parking_reason_requires_meaningful_description(
    simulator_api: SimulatorApi,
):
    response = await simulator_api.client.post(
        "/api/v1/reports/wrong-parking",
        json={
            "user_id": "USER-001",
            "slot_id": "F1-D01",
            "reason_code": "OTHER",
            "description": "  no ",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def _create_lifecycle_report(
    api: SimulatorApi,
    *,
    slot_id: str = "F1-D01",
) -> dict[str, object]:
    response = await api.client.post(
        "/api/v1/reports/wrong-parking",
        json={
            "user_id": "USER-001",
            "slot_id": slot_id,
            "reason_code": "WRONG_SLOT",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.mark.asyncio
async def test_admin_report_lifecycle_filters_conflicts_reopens_and_hard_deletes(
    simulator_api: SimulatorApi,
):
    report = await _create_lifecycle_report(simulator_api)
    report_id = str(report["id"])

    detail = await simulator_api.client.get(f"/api/v1/admin/reports/{report_id}")
    open_reports = await simulator_api.client.get(
        "/api/v1/admin/reports",
        params={"status": "OPEN", "slot_id": "F1-D01", "limit": 1},
    )
    assert detail.status_code == 200
    assert detail.json()["data"] == report
    assert open_reports.json()["data"] == [report]

    resolved_response = await simulator_api.client.patch(
        f"/api/v1/admin/reports/{report_id}",
        json={
            "status": "RESOLVED",
            "resolution_note": "  ÄĂ£ kiá»ƒm tra hiá»‡n trÆ°á»ng.  ",
            "expected_version": 0,
        },
    )
    assert resolved_response.status_code == 200
    resolved = resolved_response.json()["data"]
    assert resolved["status"] == "RESOLVED"
    assert resolved["resolved_at"].endswith("Z")
    assert resolved["resolved_by"] == "DEMO-ADMIN"
    assert resolved["resolution_note"] == "ÄĂ£ kiá»ƒm tra hiá»‡n trÆ°á»ng."
    assert resolved["version"] == 1

    stale_resolve = await simulator_api.client.patch(
        f"/api/v1/admin/reports/{report_id}",
        json={"status": "RESOLVED", "expected_version": 0},
    )
    repeated_resolve = await simulator_api.client.patch(
        f"/api/v1/admin/reports/{report_id}",
        json={"status": "RESOLVED", "expected_version": 1},
    )
    invalid_patch_reopen = await simulator_api.client.patch(
        f"/api/v1/admin/reports/{report_id}",
        json={"status": "OPEN", "expected_version": 1},
    )
    assert stale_resolve.status_code == 409
    assert stale_resolve.json()["error"]["code"] == "REPORT_VERSION_CONFLICT"
    assert repeated_resolve.status_code == 409
    assert repeated_resolve.json()["error"]["code"] == "INVALID_REPORT_TRANSITION"
    assert invalid_patch_reopen.status_code == 422

    reopened_response = await simulator_api.client.post(
        f"/api/v1/admin/reports/{report_id}/reopen",
        json={"expected_version": 1},
    )
    assert reopened_response.status_code == 200
    reopened = reopened_response.json()["data"]
    assert reopened["status"] == "OPEN"
    assert reopened["resolved_at"] is None
    assert reopened["resolved_by"] is None
    assert reopened["resolution_note"] is None
    assert reopened["version"] == 2

    repeated_reopen = await simulator_api.client.post(
        f"/api/v1/admin/reports/{report_id}/reopen",
        json={"expected_version": 2},
    )
    assert repeated_reopen.status_code == 409
    assert repeated_reopen.json()["error"]["code"] == "INVALID_REPORT_TRANSITION"

    stale_delete = await simulator_api.client.delete(
        f"/api/v1/admin/reports/{report_id}",
        params={"expected_version": 1},
    )
    assert stale_delete.status_code == 409
    assert stale_delete.json()["error"]["code"] == "REPORT_VERSION_CONFLICT"

    deleted = await simulator_api.client.delete(
        f"/api/v1/admin/reports/{report_id}",
        params={"expected_version": 2},
    )
    missing = await simulator_api.client.get(f"/api/v1/admin/reports/{report_id}")
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"deleted_report_id": report_id}
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "REPORT_NOT_FOUND"
    async with simulator_api.session_factory() as session:
        assert await session.get(WrongParkingReportRow, report_id) is None


@pytest.mark.asyncio
async def test_non_admin_cannot_resolve_reopen_or_delete_reports_outside_demo(
    simulator_api: SimulatorApi,
):
    report = await _create_lifecycle_report(simulator_api, slot_id="F1-C01")
    report_id = str(report["id"])

    async def regular_user() -> CurrentUser:
        return CurrentUser(
            id=uuid4(),
            email="user@example.com",
            full_name="User",
            role=AppRole.USER,
        )

    simulator_api.application.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=False
    )
    simulator_api.application.dependency_overrides[get_optional_current_user] = (
        regular_user
    )

    responses = [
        await simulator_api.client.patch(
            f"/api/v1/admin/reports/{report_id}",
            json={"status": "RESOLVED", "expected_version": 0},
        ),
        await simulator_api.client.post(
            f"/api/v1/admin/reports/{report_id}/reopen",
            json={"expected_version": 0},
        ),
        await simulator_api.client.delete(
            f"/api/v1/admin/reports/{report_id}",
            params={"expected_version": 0},
        ),
    ]

    assert [response.status_code for response in responses] == [403, 403, 403]
    assert all(
        response.json()["error"]["code"] == "ADMIN_REQUIRED"
        for response in responses
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, 101])
async def test_admin_reports_validate_limit_bounds(
    simulator_api: SimulatorApi,
    limit: int,
):
    response = await simulator_api.client.get(
        "/api/v1/admin/reports",
        params={"limit": limit},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path_suffix", "kwargs"),
    [
        ("GET", "", {}),
        (
            "PATCH",
            "",
            {"json": {"status": "RESOLVED", "expected_version": 0}},
        ),
        ("POST", "/reopen", {"json": {"expected_version": 0}}),
        ("DELETE", "", {"params": {"expected_version": 0}}),
    ],
)
async def test_admin_report_endpoints_return_stable_not_found(
    simulator_api: SimulatorApi,
    method: str,
    path_suffix: str,
    kwargs: dict[str, object],
):
    response = await simulator_api.client.request(
        method,
        f"/api/v1/admin/reports/REPORT-MISSING{path_suffix}",
        **kwargs,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPORT_NOT_FOUND"


@pytest.mark.asyncio
async def test_report_resolution_uses_authenticated_admin_id_in_demo(
    simulator_api: SimulatorApi,
):
    report = await _create_lifecycle_report(simulator_api, slot_id="F1-A01")
    admin_id = uuid4()

    async def admin_user() -> CurrentUser:
        return CurrentUser(
            id=admin_id,
            email="admin@example.com",
            full_name="Admin",
            role=AppRole.ADMIN,
        )

    simulator_api.application.dependency_overrides[get_optional_current_user] = admin_user
    response = await simulator_api.client.patch(
        f"/api/v1/admin/reports/{report['id']}",
        json={"status": "RESOLVED", "expected_version": 0},
    )

    assert response.status_code == 200
    assert response.json()["data"]["resolved_by"] == str(admin_id)


@pytest.mark.asyncio
async def test_report_logs_identifiers_without_sensitive_report_text(
    simulator_api: SimulatorApi,
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level("INFO")
    create_response = await simulator_api.client.post(
        "/api/v1/reports/wrong-parking",
        json={
            "user_id": "USER-001",
            "slot_id": "F1-B01",
            "reason_code": "OTHER",
            "observed_plate_number": "SECRET-PLATE",
            "description": "SECRET-DESCRIPTION",
        },
    )
    report_id = create_response.json()["data"]["id"]
    await simulator_api.client.patch(
        f"/api/v1/admin/reports/{report_id}",
        json={
            "status": "RESOLVED",
            "resolution_note": "SECRET-RESOLUTION-NOTE",
            "expected_version": 0,
        },
    )

    assert "wrong_parking_report_action action=create" in caplog.text
    assert "wrong_parking_report_action action=resolve" in caplog.text
    assert f"report_id={report_id}" in caplog.text
    assert "slot_id=F1-B01" in caplog.text
    assert "request_id=" in caplog.text
    assert "SECRET-PLATE" not in caplog.text
    assert "SECRET-DESCRIPTION" not in caplog.text
    assert "SECRET-RESOLUTION-NOTE" not in caplog.text


def test_admin_report_lifecycle_is_exposed_in_openapi():
    application = create_app()
    openapi = application.openapi()
    paths = openapi["paths"]

    assert "get" in paths["/api/v1/admin/reports"]
    query_parameters = {
        parameter["name"]
        for parameter in paths["/api/v1/admin/reports"]["get"]["parameters"]
    }
    assert {"status", "slot_id", "limit"} <= query_parameters
    detail_operations = paths["/api/v1/admin/reports/{report_id}"]
    assert {"get", "patch", "delete"} <= detail_operations.keys()
    assert "post" in paths["/api/v1/admin/reports/{report_id}/reopen"]
    assert "post" in paths["/api/v1/admin/reports/{report_id}/confirm"]
    assert "post" in paths["/api/v1/admin/reports/{report_id}/reject"]
    assert "get" in paths["/api/v1/admin/reports/{report_id}/evidence-url"]
