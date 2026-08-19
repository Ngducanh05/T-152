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


def production_settings() -> Settings:
    return Settings(demo_mode=False)


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
async def test_user_cannot_call_admin_api() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = production_settings
    app.dependency_overrides[dependencies.get_optional_current_user] = lambda: USER_A
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/events")

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
