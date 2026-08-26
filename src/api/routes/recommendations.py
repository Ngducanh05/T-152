"""Parking recommendation API backed by the deterministic core service."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import ParkingUserDependency, resolve_parking_user_id
from src.api.errors import domain_http_error
from src.core.database import get_db_session
from src.core.parking_state import ParkingStateService
from src.core.recommendation import RecommendationError, RecommendationService
from src.core.routing import RoutingService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import RecommendationRequest, RecommendationResult

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


def _domain_error(error: RecommendationError) -> HTTPException:
    return domain_http_error(error)


@router.post(
    "",
    response_model=SuccessResponse[RecommendationResult],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def recommend_parking(
    request: RecommendationRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
) -> SuccessResponse[RecommendationResult]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    trusted_request = request.model_copy(update={"user_id": user_id})
    try:
        async with session.begin():
            result = await RecommendationService(
                session,
                ParkingStateService(session),
                RoutingService(session),
            ).recommend(trusted_request)
    except RecommendationError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=result)


__all__ = ["router"]
