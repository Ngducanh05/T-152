from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from src.core.config import Settings
from src.services.auth_service import SupabaseTokenVerifier


class StubClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls = 0

    async def get(self, *_args: object, **_kwargs: object) -> object:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class StubResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> dict[str, object]:
        return self.payload


def settings() -> Settings:
    return Settings(
        _env_file=None,
        debug=False,
        supabase_url="https://project.supabase.co",
        supabase_anon_key="public-anon-key",
        auth_verification_cache_ttl_seconds=15,
    )


def token(*, expires_at: datetime) -> str:
    return jwt.encode(
        {"sub": "11111111-1111-4111-8111-111111111111", "exp": expires_at},
        "test-only-secret",
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_valid_token_identity_is_cached_by_hash() -> None:
    client = StubClient(
        [StubResponse(200, {"id": "11111111-1111-4111-8111-111111111111"})]
    )
    verifier = SupabaseTokenVerifier(settings(), client=client)  # type: ignore[arg-type]
    access_token = token(expires_at=datetime.now(UTC) + timedelta(minutes=5))

    first = await verifier.verify(access_token)
    second = await verifier.verify(access_token)

    assert first == second
    assert client.calls == 1
    assert access_token not in repr(verifier._cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_invalid_or_expired_provider_token_is_rejected(status_code: int) -> None:
    client = StubClient([StubResponse(status_code, {"message": "invalid"})])
    verifier = SupabaseTokenVerifier(settings(), client=client)  # type: ignore[arg-type]
    access_token = token(expires_at=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(Exception) as exc_info:
        await verifier.verify(access_token)

    assert getattr(exc_info.value, "status_code", None) == 401
    assert getattr(exc_info.value, "detail", {}).get("code") == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_auth_provider_unavailable_is_stable_503() -> None:
    client = StubClient([httpx.ConnectError("provider unavailable")])
    verifier = SupabaseTokenVerifier(settings(), client=client)  # type: ignore[arg-type]

    with pytest.raises(Exception) as exc_info:
        await verifier.verify(token(expires_at=datetime.now(UTC) + timedelta(minutes=5)))

    assert getattr(exc_info.value, "status_code", None) == 503
    assert getattr(exc_info.value, "detail", {}).get("code") == "AUTH_PROVIDER_UNAVAILABLE"
