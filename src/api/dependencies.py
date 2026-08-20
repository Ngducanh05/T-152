"""Shared FastAPI dependencies for authenticated ParkSmart API surfaces."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.database import get_db_session, get_session_factory
from src.core.db_models import Vehicle
from src.models.auth import AppRole, CurrentUser
from src.services import auth_service

SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
CredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(auth_service.bearer_scheme),
]


def _access_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


async def get_optional_current_user(
    credentials: CredentialsDependency,
) -> CurrentUser | None:
    """Resolve an optional bearer identity in an isolated auth DB session.

    Business routes intentionally use a different AsyncSession.  Profile lookup
    starts an implicit SQLAlchemy transaction, so sharing that session with a
    route that later enters ``session.begin()`` would cause a nested-transaction
    failure before the business operation runs.
    """
    if credentials is None:
        return None
    async with get_session_factory()() as auth_session:
        return await auth_service.get_current_user(credentials, auth_session)


async def require_authenticated_or_demo(
    settings: SettingsDependency,
    user: Annotated[CurrentUser | None, Depends(get_optional_current_user)],
) -> CurrentUser | None:
    """Require a valid bearer identity outside explicit demo mode."""
    if settings.demo_mode:
        return user
    if user is None:
        raise _access_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_REQUIRED",
            "Authentication is required.",
        )
    return user


async def require_parking_user_or_demo(
    user: Annotated[CurrentUser | None, Depends(require_authenticated_or_demo)],
    settings: SettingsDependency,
) -> CurrentUser | None:
    """Require the regular user role and a linked ParkingUser outside demo mode."""
    if settings.demo_mode:
        return user
    if user is None:  # pragma: no cover - enforced by require_authenticated_or_demo
        raise _access_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_REQUIRED",
            "Authentication is required.",
        )
    if user.role is not AppRole.USER:
        raise _access_error(
            status.HTTP_403_FORBIDDEN,
            "USER_REQUIRED",
            "A parking user account is required for this operation.",
        )
    if user.parking_user_id is None:
        raise _access_error(
            status.HTTP_403_FORBIDDEN,
            "PARKING_IDENTITY_NOT_LINKED",
            "This user profile is not linked to a parking identity.",
        )
    return user


async def require_admin_or_demo(
    settings: SettingsDependency,
    user: Annotated[CurrentUser | None, Depends(get_optional_current_user)],
) -> CurrentUser | None:
    """Allow demo operations, otherwise require the backend-owned admin role."""
    if settings.demo_mode:
        return user
    if user is None:
        raise _access_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_REQUIRED",
            "Authentication is required.",
        )
    if user.role is not AppRole.ADMIN:
        raise _access_error(
            status.HTTP_403_FORBIDDEN,
            "ADMIN_REQUIRED",
            "Administrator access is required.",
        )
    return user


ParkingUserDependency = Annotated[
    CurrentUser | None,
    Depends(require_parking_user_or_demo),
]
AuthenticatedDependency = Annotated[
    CurrentUser | None,
    Depends(require_authenticated_or_demo),
]


def resolve_parking_user_id(
    requested_user_id: str,
    current_user: CurrentUser | None,
) -> str:
    """Return the trusted business user id, rejecting cross-user impersonation."""
    if current_user is None:
        return requested_user_id
    if current_user.parking_user_id != requested_user_id:
        raise _access_error(
            status.HTTP_403_FORBIDDEN,
            "PARKING_OWNERSHIP_MISMATCH",
            "The authenticated account does not own the requested parking identity.",
        )
    return requested_user_id


async def resolve_vehicle_id(
    requested_vehicle_id: str | None,
    current_user: CurrentUser | None,
    session: AsyncSession,
    *,
    required: bool = False,
) -> str | None:
    """Resolve a default/selected vehicle and verify it belongs to the current user."""
    if current_user is None:
        if required and requested_vehicle_id is None:
            raise _access_error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "VEHICLE_REQUIRED",
                "A vehicle is required for this operation.",
            )
        return requested_vehicle_id

    vehicle_id = requested_vehicle_id or current_user.default_vehicle_id
    if vehicle_id is None:
        if required:
            raise _access_error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "VEHICLE_REQUIRED",
                "Select a vehicle before continuing.",
            )
        return None

    vehicle = await session.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise _access_error(
            status.HTTP_404_NOT_FOUND,
            "VEHICLE_NOT_FOUND",
            "The selected vehicle does not exist.",
        )
    if vehicle.user_id != current_user.parking_user_id:
        raise _access_error(
            status.HTTP_403_FORBIDDEN,
            "PARKING_VEHICLE_MISMATCH",
            "The authenticated account does not own the selected vehicle.",
        )
    return vehicle_id


__all__ = [
    "AuthenticatedDependency",
    "ParkingUserDependency",
    "get_optional_current_user",
    "require_admin_or_demo",
    "require_authenticated_or_demo",
    "require_parking_user_or_demo",
    "resolve_parking_user_id",
    "resolve_vehicle_id",
]
