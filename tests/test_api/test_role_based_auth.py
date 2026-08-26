from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from src.api import dependencies
from src.api.dependencies import resolve_vehicle_id
from src.api.main import create_app
from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.db_models import Vehicle
from src.models.auth import AppRole, CurrentUser

USER_A = CurrentUser(
    id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    email="user-a@example.com",
    role=AppRole.USER,
    parking_user_id="USER-A",
    default_vehicle_id="VEHICLE-A",
)
ADMIN = CurrentUser(
    id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    email="admin@example.com",
    role=AppRole.ADMIN,
)

ADMIN_ROUTE_CASES = [
    pytest.param("GET", "/api/v1/admin/events", None, id="events-list"),
    pytest.param(
        "PATCH",
        "/api/v1/admin/parking/slots/F1-A01/status",
        {"status": "AVAILABLE", "expected_version": 0},
        id="slot-status-mutation",
    ),
    pytest.param(
        "GET",
        "/api/v1/admin/slot-observations",
        None,
        id="observations-list",
    ),
    pytest.param(
        "GET",
        "/api/v1/admin/slot-observations/OBSERVATION-001",
        None,
        id="observation-detail",
    ),
    pytest.param(
        "POST",
        "/api/v1/admin/slot-observations/OBSERVATION-001/verify",
        {"expected_version": 0},
        id="observation-verify",
    ),
    pytest.param(
        "POST",
        "/api/v1/admin/slot-observations/OBSERVATION-001/reject",
        {"expected_version": 0, "reason": "invalid observation"},
        id="observation-reject",
    ),
    pytest.param("GET", "/api/v1/admin/reports", None, id="reports-list"),
    pytest.param(
        "GET",
        "/api/v1/admin/reports/REPORT-001",
        None,
        id="report-detail",
    ),
    pytest.param(
        "GET",
        "/api/v1/admin/reports/REPORT-001/evidence-url",
        None,
        id="report-evidence-url",
    ),
    pytest.param(
        "PATCH",
        "/api/v1/admin/reports/REPORT-001",
        {
            "status": "RESOLVED",
            "verification_outcome": "CONFIRMED",
            "expected_version": 0,
        },
        id="report-resolve",
    ),
    pytest.param(
        "POST",
        "/api/v1/admin/reports/REPORT-001/reopen",
        {"expected_version": 0},
        id="report-reopen",
    ),
    pytest.param(
        "DELETE",
        "/api/v1/admin/reports/REPORT-001?expected_version=0",
        None,
        id="report-delete",
    ),
]

SIMULATOR_ROUTE_CASES = [
    pytest.param(
        "/api/v1/simulator/park",
        {"slot_id": "F1-A01", "vehicle_id": "SIM-CAR-01"},
        id="simulator-park",
    ),
    pytest.param(
        "/api/v1/simulator/leave",
        {"slot_id": "F1-A01", "vehicle_id": "SIM-CAR-01"},
        id="simulator-leave",
    ),
    pytest.param("/api/v1/simulator/reset", {}, id="simulator-reset"),
    pytest.param(
        "/api/v1/simulator/run-scenario",
        {},
        id="simulator-run-scenario",
    ),
]


def production_settings() -> Settings:
    return Settings(
        app_env="production",
        database_url="postgresql+asyncpg://unit:unit@database/parksmart_test",
        demo_mode=False,
        simulator_enabled=False,
        agent_enabled=False,
        speech_enabled=False,
        supabase_url="https://unit-test.supabase.co",
        supabase_anon_key="unit-test-anon",
        supabase_service_role_key="unit-test-server-key",
    )


def demo_settings() -> Settings:
    return Settings(demo_mode=True)


@pytest.mark.asyncio
async def test_demo_mode_false_requires_auth_for_user_api() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/reservations/active?user_id=USER-A")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "json_body"), ADMIN_ROUTE_CASES)
async def test_regular_user_is_rejected_before_admin_business_dependency(
    method: str,
    path: str,
    json_body: dict[str, object] | None,
) -> None:
    business_db_requested = False

    async def forbidden_db_session():
        nonlocal business_db_requested
        business_db_requested = True
        yield object()

    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: USER_A
    app.dependency_overrides[get_db_session] = forbidden_db_session
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        if json_body is None:
            response = await client.request(method, path)
        else:
            response = await client.request(method, path, json=json_body)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"
    assert business_db_requested is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "json_body"), ADMIN_ROUTE_CASES)
async def test_anonymous_production_request_is_rejected_before_admin_business_dependency(
    method: str,
    path: str,
    json_body: dict[str, object] | None,
) -> None:
    business_db_requested = False

    async def forbidden_db_session():
        nonlocal business_db_requested
        business_db_requested = True
        yield object()

    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: None
    app.dependency_overrides[get_db_session] = forbidden_db_session
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        if json_body is None:
            response = await client.request(method, path)
        else:
            response = await client.request(method, path, json=json_body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert business_db_requested is False


@pytest.mark.asyncio
async def test_authenticated_user_does_not_inherit_anonymous_demo_admin_access() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = demo_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: USER_A
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/events")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "json_body"),
    [
        pytest.param("/api/v1/admin/events", None, id="admin-route"),
        pytest.param("/api/v1/simulator/reset", {}, id="simulator-route"),
    ],
)
async def test_authenticated_regular_user_stays_non_admin_in_demo_mode(
    path: str,
    json_body: dict[str, object] | None,
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = demo_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: USER_A
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        if json_body is None:
            response = await client.get(path)
        else:
            response = await client.post(path, json=json_body)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "json_body"), SIMULATOR_ROUTE_CASES)
async def test_anonymous_production_request_cannot_mutate_simulator(
    path: str,
    json_body: dict[str, object],
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: None
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(path, json=json_body)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "json_body"), SIMULATOR_ROUTE_CASES)
async def test_regular_user_cannot_mutate_simulator_in_production(
    path: str,
    json_body: dict[str, object],
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: USER_A
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(path, json=json_body)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


@pytest.mark.asyncio
async def test_admin_can_call_admin_api() -> None:
    class FakeScalarResult:
        def all(self) -> list[object]:
            return []

    class FakeSession:
        async def scalars(self, *_args: object, **_kwargs: object) -> FakeScalarResult:
            return FakeScalarResult()

    async def fake_db_session():
        yield FakeSession()

    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: ADMIN
    app.dependency_overrides[get_db_session] = fake_db_session
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/events?limit=5")

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        (
            "POST",
            "/api/v1/reservations",
            {
                "user_id": "USER-B",
                "vehicle_id": "VEHICLE-A",
                "slot_id": "F1-A01",
            },
        ),
        (
            "POST",
            "/api/v1/sessions/SESSION-B/complete",
            {"user_id": "USER-B"},
        ),
        (
            "POST",
            "/api/v1/reports/wrong-parking",
            {
                "user_id": "USER-B",
                "slot_id": "F1-A01",
                "reason_code": "CROSSED_LINE",
            },
        ),
    ],
)
async def test_user_cannot_operate_on_another_users_business_resources(
    method: str,
    path: str,
    json_body: dict[str, object],
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: USER_A
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(method, path, json=json_body)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PARKING_OWNERSHIP_MISMATCH"


@pytest.mark.asyncio
async def test_selected_vehicle_must_belong_to_authenticated_parking_user() -> None:
    class FakeSession:
        async def get(self, model: object, identity: str) -> object | None:
            if model is Vehicle and identity == "VEHICLE-B":
                return SimpleNamespace(id="VEHICLE-B", user_id="USER-B")
            return None

    with pytest.raises(Exception) as exc_info:
        await resolve_vehicle_id(
            "VEHICLE-B",
            USER_A,
            FakeSession(),  # type: ignore[arg-type]
            required=True,
        )

    error = exc_info.value
    assert getattr(error, "status_code", None) == 403
    assert getattr(error, "detail", {}).get("code") == "PARKING_VEHICLE_MISMATCH"
