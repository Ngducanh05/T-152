import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.api.main import create_app
from src.api.routes import auth as auth_routes
from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import AppRoleEnum, Base, ParkingUser, Profile, Vehicle
from src.models.auth import AppRole, CurrentUser
from src.services import auth_service


@pytest_asyncio.fixture
async def auth_client_with_db() -> AsyncGenerator[
    tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]],
    None,
]:
    database_url = get_settings().database_url
    schema_name = f"test_auth_api_{uuid4().hex}"
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

    async def override_db_session():
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_auth_me_returns_backend_owned_profile_identity() -> None:
    app = create_app()
    current_user = CurrentUser(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        email="user@example.com",
        full_name="ParkSmart User",
        role=AppRole.USER,
        parking_user_id="USER-101",
        default_vehicle_id="VEHICLE-101",
    )
    app.dependency_overrides[auth_service.get_current_user] = lambda: current_user
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": "11111111-1111-4111-8111-111111111111",
        "email": "user@example.com",
        "full_name": "ParkSmart User",
        "role": "user",
        "parking_user_id": "USER-101",
        "default_vehicle_id": "VEHICLE-101",
    }


@pytest.mark.asyncio
async def test_auth_me_requires_bearer_token() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_supabase_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_service,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-key",
        ),
    )

    class FakeResponse:
        status_code = 401

        def json(self) -> dict[str, object]:
            return {"message": "invalid"}

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(auth_service.httpx, "AsyncClient", lambda **_kwargs: FakeAsyncClient())

    with pytest.raises(Exception) as exc_info:
        await auth_service.verify_supabase_access_token("bad-token")

    error = exc_info.value
    assert getattr(error, "status_code", None) == 401
    assert getattr(error, "detail", {}).get("code") == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_auth_provider_connection_failure_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth_service,
        "get_settings",
        lambda: SimpleNamespace(
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-key",
        ),
    )

    class FailingAsyncClient:
        async def __aenter__(self) -> "FailingAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> object:
            raise httpx.ConnectError("provider unavailable")

    monkeypatch.setattr(
        auth_service.httpx,
        "AsyncClient",
        lambda **_kwargs: FailingAsyncClient(),
    )

    with pytest.raises(Exception) as exc_info:
        await auth_service.verify_supabase_access_token("token")

    error = exc_info.value
    assert getattr(error, "status_code", None) == 503
    assert getattr(error, "detail", {}).get("code") == "AUTH_PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_role_and_parking_identity_come_from_profile_not_token_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    profile = SimpleNamespace(
        id=auth_id,
        email="user@example.com",
        full_name="User A",
        app_role=AppRoleEnum.USER,
        parking_user_id="USER-A",
        default_vehicle_id="VEHICLE-A",
    )

    class FakeSession:
        async def scalar(self, _statement: object) -> object:
            return profile

        async def get(self, model: object, identity: str) -> object | None:
            if model is ParkingUser and identity == "USER-A":
                return SimpleNamespace(id="USER-A")
            if model is Vehicle and identity == "VEHICLE-A":
                return SimpleNamespace(id="VEHICLE-A", user_id="USER-A")
            return None

    async def fake_verify(_token: str) -> dict[str, object]:
        return {
            "id": str(auth_id),
            "email": "user@example.com",
            "user_metadata": {"role": "admin"},
        }

    monkeypatch.setattr(auth_service, "verify_supabase_access_token", fake_verify)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="safe-test-token")

    current_user = await auth_service.get_current_user(
        credentials,
        FakeSession(),  # type: ignore[arg-type]
    )

    assert current_user.role is AppRole.USER
    assert current_user.parking_user_id == "USER-A"
    assert current_user.default_vehicle_id == "VEHICLE-A"


@pytest.mark.asyncio
async def test_onboarding_is_idempotent_under_concurrent_requests(
    auth_client_with_db: tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_factory = auth_client_with_db
    auth_id = UUID("33333333-3333-4333-8333-333333333333")

    async def fake_verify(_token: str) -> dict[str, object]:
        await asyncio.sleep(0)
        return {
            "id": str(auth_id),
            "email": "new@example.com",
            "user_metadata": {"full_name": "New User", "role": "admin"},
        }

    monkeypatch.setattr(auth_routes, "verify_supabase_access_token", fake_verify)
    monkeypatch.setattr(auth_service, "verify_supabase_access_token", fake_verify)

    first, second = await asyncio.gather(
        client.post("/api/v1/auth/onboarding", headers={"Authorization": "Bearer token"}),
        client.post("/api/v1/auth/onboarding", headers={"Authorization": "Bearer token"}),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    assert first.json()["data"]["role"] == "user"
    assert first.json()["data"]["default_vehicle_id"] is None

    async with session_factory() as session:
        profile_count = await session.scalar(select(func.count(Profile.id)))
        parking_user_count = await session.scalar(select(func.count(ParkingUser.id)))
        profile = await session.get(Profile, auth_id)

    assert profile_count == 1
    assert parking_user_count == 1
    assert profile is not None
    assert profile.app_role is AppRoleEnum.USER
