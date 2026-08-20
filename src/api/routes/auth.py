from typing import Annotated

from fastapi import APIRouter, Depends

from src.models.auth import CurrentUser
from src.models.common import SuccessResponse
from src.services.auth_service import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me", response_model=SuccessResponse[CurrentUser])
async def me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SuccessResponse[CurrentUser]:
    return SuccessResponse(data=current_user, message="Current user loaded.")


__all__ = ["router"]
