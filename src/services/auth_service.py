from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.auth import AppRole, CurrentUser
from src.services.database import get_db_session
from src.services.db_models import Profile

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_supabase_access_token(token: str) -> dict[str, object]:
    """Verify a Supabase access token through the Auth user endpoint.

    This is the Stage 1 MVP approach. It keeps the JWT verification authority in
    Supabase and can later be replaced by local JWKS verification if needed.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Supabase authentication is not configured.",
            },
        )

    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {token}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers=headers,
            )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AUTH_PROVIDER_UNAVAILABLE",
                "message": "Authentication provider is unavailable.",
            },
        )

    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": "The access token is invalid or expired.",
            },
        )

    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": "The access token is invalid or expired.",
            },
        )
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    """Resolve a verified Supabase user to a ParkSmart profile and role."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_REQUIRED",
                "message": "Authentication is required.",
            },
        )

    auth_user = await verify_supabase_access_token(credentials.credentials)
    try:
        user_id = UUID(str(auth_user["id"]))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": "The access token is invalid or expired.",
            },
        )

    result = await session.execute(select(Profile).where(Profile.id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PROFILE_NOT_FOUND",
                "message": "The ParkSmart profile does not exist.",
            },
        )

    return CurrentUser(
        id=profile.id,
        email=profile.email or str(auth_user.get("email") or "") or None,
        full_name=profile.full_name,
        app_role=AppRole(profile.app_role.value),
    )
