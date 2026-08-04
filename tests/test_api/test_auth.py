from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from src.main import app
from src.models.auth import AppRole, CurrentUser
from src.services import auth_service


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    user_id = uuid4()

    async def override_current_user() -> CurrentUser:
        return CurrentUser(
            id=user_id,
            email="resident@parksmart.demo",
            full_name="Demo Resident",
            app_role=AppRole.RESIDENT,
        )

    app.dependency_overrides[auth_service.get_current_user] = override_current_user
    try:
        response = await client.get("/api/v1/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "id": str(user_id),
            "email": "resident@parksmart.demo",
            "full_name": "Demo Resident",
            "app_role": "resident",
        },
        "message": "Current user loaded.",
    }


@pytest.mark.asyncio
async def test_get_current_user_requires_bearer_token():
    with pytest.raises(HTTPException) as error:
        await auth_service.get_current_user(None, None)  # type: ignore[arg-type]

    assert error.value.status_code == 401
    assert error.value.detail["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_verify_token_rejects_non_200_response(monkeypatch):
    class FakeResponse:
        status_code = 401

        def json(self):
            return {"message": "invalid"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def get(self, url, headers):
            return FakeResponse()

    monkeypatch.setattr(auth_service, "get_settings", lambda: type("Settings", (), {
        "supabase_url": "https://example.supabase.co",
        "supabase_anon_key": "public-anon-key",
    })())
    monkeypatch.setattr(auth_service.httpx, "AsyncClient", lambda **_: FakeClient())

    with pytest.raises(HTTPException) as error:
        await auth_service.verify_supabase_access_token("invalid-token")

    assert error.value.status_code == 401
    assert error.value.detail["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_verify_token_handles_provider_connection_error(monkeypatch):
    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def get(self, url, headers):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(auth_service, "get_settings", lambda: type("Settings", (), {
        "supabase_url": "https://example.supabase.co",
        "supabase_anon_key": "public-anon-key",
    })())
    monkeypatch.setattr(auth_service.httpx, "AsyncClient", lambda **_: FailingClient())

    with pytest.raises(HTTPException) as error:
        await auth_service.verify_supabase_access_token("valid-token")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "AUTH_PROVIDER_UNAVAILABLE"
