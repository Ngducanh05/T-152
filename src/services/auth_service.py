from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.db_models import AppRoleEnum, ParkingUser, Profile, Vehicle
from src.models.auth import AppRole, CurrentUser

bearer_scheme = HTTPBearer(auto_error=False)


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


async def verify_supabase_access_token(token: str) -> dict[str, object]:
    """Verify an access token with Supabase Auth without logging credentials."""
    settings = get_settings()
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
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers=headers,
            )
    except httpx.HTTPError as error:
        raise _auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_PROVIDER_UNAVAILABLE",
            "Authentication provider is unavailable.",
        ) from error

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
) -> CurrentUser:
    """Resolve a verified Supabase UUID to the backend-owned ParkSmart profile."""
    if credentials is None:
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_REQUIRED",
            "Authentication is required.",
        )

    auth_user = await verify_supabase_access_token(credentials.credentials)
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
