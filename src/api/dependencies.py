"""Shared FastAPI dependencies for access-controlled API surfaces."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.models.auth import AppRole, CurrentUser
from src.services import auth_service

SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
CredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(auth_service.bearer_scheme),
]


async def get_optional_current_user(
    credentials: CredentialsDependency,
    session: SessionDependency,
) -> CurrentUser | None:
    """Resolve a bearer identity when supplied without forcing demo login."""
    if credentials is None:
        return None
    return await auth_service.get_current_user(credentials, session)


async def require_admin_or_demo(
    settings: SettingsDependency,
    user: Annotated[CurrentUser | None, Depends(get_optional_current_user)],
) -> CurrentUser | None:
    """Allow the explicit demo surface, otherwise require the existing admin role."""
    if settings.demo_mode:
        return user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."},
        )
    if user.app_role is not AppRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ADMIN_REQUIRED", "message": "Administrator access is required."},
        )
    return user


__all__ = ["get_optional_current_user", "require_admin_or_demo"]
