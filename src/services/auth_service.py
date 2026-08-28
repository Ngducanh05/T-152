import asyncio
import hashlib
import time
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from opentelemetry.trace import SpanKind
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.db_models import AppRoleEnum, ParkingUser, Profile, Vehicle
from src.core.observability import get_active_observability
from src.models.auth import AppRole, CurrentUser

bearer_scheme = HTTPBearer(auto_error=False)


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


@dataclass(frozen=True, slots=True)
class _CachedIdentity:
    payload: dict[str, object]
    expires_at: float


class SupabaseTokenVerifier:
    """Remote Supabase verification with one client and a short hash-keyed cache."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._cache: dict[str, _CachedIdentity] = {}
        self._inflight: dict[str, asyncio.Task[dict[str, object]]] = {}
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def verify(self, token: str) -> dict[str, object]:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()
        async with self._lock:
            cached = self._cache.get(token_hash)
            if cached is not None and cached.expires_at > now:
                return dict(cached.payload)
            task = self._inflight.get(token_hash)
            if task is None:
                task = asyncio.create_task(self._verify_remote(token))
                self._inflight[token_hash] = task

        try:
            payload = await task
        finally:
            async with self._lock:
                if self._inflight.get(token_hash) is task:
                    self._inflight.pop(token_hash, None)

        expires_at = now + self.settings.auth_verification_cache_ttl_seconds
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            token_expiry = float(unverified.get("exp", expires_at))
            expires_at = min(expires_at, token_expiry)
        except (jwt.PyJWTError, TypeError, ValueError):
            pass
        async with self._lock:
            if len(self._cache) >= self.settings.auth_verification_cache_max_entries:
                oldest_key = min(self._cache, key=lambda key: self._cache[key].expires_at)
                self._cache.pop(oldest_key, None)
            self._cache[token_hash] = _CachedIdentity(dict(payload), expires_at)
        return payload

    async def _verify_remote(self, token: str) -> dict[str, object]:
        settings = self.settings
        if not settings.supabase_url or not settings.supabase_anon_key:
            raise _auth_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "AUTH_NOT_CONFIGURED",
                "Supabase authentication is not configured.",
            )

        headers = {
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {token}",
        }
        runtime = get_active_observability()
        context_manager = (
            runtime.start_span(
                "external.supabase.auth.verify",
                kind=SpanKind.CLIENT,
                attributes={
                    "external.system": "supabase",
                    "external.operation": "auth.verify",
                    "http.request.method": "GET",
                },
            )
            if runtime is not None
            else nullcontext(None)
        )
        provider_error: httpx.HTTPError | None = None
        with context_manager as span:
            try:
                response = await self.client.get(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                    headers=headers,
                )
            except httpx.HTTPError as error:
                provider_error = error
                if runtime is not None:
                    runtime.mark_span_failed(span, exception=error)
            else:
                if span is not None:
                    span.set_attribute("http.response.status_code", response.status_code)
                    span.set_attribute("outcome", "success" if response.status_code == status.HTTP_200_OK else "error")
                if response.status_code != status.HTTP_200_OK and runtime is not None:
                    runtime.mark_span_failed(span, error_code="INVALID_TOKEN")
        if provider_error is not None:
            raise _auth_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "AUTH_PROVIDER_UNAVAILABLE",
                "Authentication provider is unavailable.",
            ) from provider_error

        if response.status_code != status.HTTP_200_OK:
            raise _auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_TOKEN",
                "The access token is invalid or expired.",
            )

        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("id"):
            raise _auth_error(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_TOKEN",
                "The access token is invalid or expired.",
            )
        return payload


async def verify_supabase_access_token(
    token: str,
    *,
    verifier: SupabaseTokenVerifier | None = None,
) -> dict[str, object]:
    """Verify an access token without logging or retaining the raw credential."""
    if verifier is not None:
        return await verifier.verify(token)
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise _auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_NOT_CONFIGURED",
            "Supabase authentication is not configured.",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        return await SupabaseTokenVerifier(settings, client=client).verify(token)


async def _validate_parking_identity(
    profile: Profile,
    session: AsyncSession,
) -> None:
    """Validate profile-to-business links before exposing a user identity."""
    if profile.app_role is not AppRoleEnum.USER:
        return

    if profile.parking_user_id is None:
        raise _auth_error(
            status.HTTP_403_FORBIDDEN,
            "PARKING_IDENTITY_NOT_LINKED",
            "This user profile is not linked to a parking identity.",
        )

    parking_user = await session.get(ParkingUser, profile.parking_user_id)
    if parking_user is None:
        raise _auth_error(
            status.HTTP_403_FORBIDDEN,
            "PARKING_IDENTITY_INVALID",
            "The linked parking identity is invalid.",
        )

    if profile.default_vehicle_id is None:
        return

    vehicle = await session.get(Vehicle, profile.default_vehicle_id)
    if vehicle is None or vehicle.user_id != profile.parking_user_id:
        raise _auth_error(
            status.HTTP_403_FORBIDDEN,
            "PARKING_IDENTITY_INVALID",
            "The linked default vehicle is invalid.",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
    verifier: SupabaseTokenVerifier | None = None,
) -> CurrentUser:
    """Resolve a verified Supabase UUID to the backend-owned ParkSmart profile."""
    if credentials is None:
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_REQUIRED",
            "Authentication is required.",
        )

    if verifier is None:
        auth_user = await verify_supabase_access_token(credentials.credentials)
    else:
        auth_user = await verify_supabase_access_token(
            credentials.credentials,
            verifier=verifier,
        )
    try:
        auth_user_id = UUID(str(auth_user["id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "The access token is invalid or expired.",
        ) from error

    profile = await session.scalar(select(Profile).where(Profile.id == auth_user_id))
    if profile is None:
        raise _auth_error(
            status.HTTP_403_FORBIDDEN,
            "PROFILE_NOT_FOUND",
            "The ParkSmart profile does not exist.",
        )

    await _validate_parking_identity(profile, session)

    return CurrentUser(
        id=profile.id,
        email=profile.email or str(auth_user.get("email") or "") or None,
        full_name=profile.full_name,
        role=AppRole(profile.app_role.value),
        parking_user_id=profile.parking_user_id,
        default_vehicle_id=profile.default_vehicle_id,
    )


async def get_current_user_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    """FastAPI dependency using the application-scoped token verifier."""
    verifier = getattr(request.app.state, "auth_token_verifier", None)
    return await get_current_user(credentials, session, verifier=verifier)
