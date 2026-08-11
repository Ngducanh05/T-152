"""Authenticated-user routes preserved from the application bootstrap."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.models.auth import CurrentUser
from src.models.common import SuccessResponse
from src.services import auth_service

router = APIRouter(tags=["Auth"])


@router.get("/me", response_model=SuccessResponse[CurrentUser])
async def current_user(
    user: Annotated[CurrentUser, Depends(auth_service.get_current_user)],
) -> SuccessResponse[CurrentUser]:
    return SuccessResponse(data=user, message="Current user loaded.")
