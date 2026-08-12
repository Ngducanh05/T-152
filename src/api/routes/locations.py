"""Confirmed canonical user-location API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.location import LocationError, LocationService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import EntityId, ErrorCode, FloorScopedId

router = APIRouter(prefix="/locations", tags=["Locations"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
ERROR_RESPONSES = {
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class ConfirmLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    node_id: FloorScopedId


class LocationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    node_id: FloorScopedId


def _error(status_code: int, code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message},
    )


def _domain_error(error: LocationError) -> HTTPException:
    message = error.message
    if "Parking user" in message and "not found" in message:
        return _error(404, ErrorCode.USER_NOT_FOUND, message)
    if error.code in {ErrorCode.ROUTE_NODE_NOT_FOUND, ErrorCode.SLOT_NOT_FOUND}:
        return _error(404, ErrorCode.LOCATION_NODE_NOT_FOUND, message)
    if "internal routing aisle" in message:
        return _error(422, ErrorCode.INVALID_LOCATION_NODE_TYPE, message)
    return _error(422, error.code, message)


@router.post(
    "/confirm",
    response_model=SuccessResponse[LocationResponse],
    responses=ERROR_RESPONSES,
)
async def confirm_location(
    request: ConfirmLocationRequest,
    session: SessionDependency,
) -> SuccessResponse[LocationResponse]:
    try:
        async with session.begin():
            node_id = await LocationService(session).confirm_location(
                request.user_id, request.node_id
            )
    except LocationError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=LocationResponse(user_id=request.user_id, node_id=node_id))


@router.get(
    "/current",
    response_model=SuccessResponse[LocationResponse],
    responses=ERROR_RESPONSES,
)
async def current_location(
    session: SessionDependency,
    user_id: Annotated[EntityId, Query()],
) -> SuccessResponse[LocationResponse]:
    try:
        node_id = await LocationService(session).get_current_location(user_id)
    except LocationError as error:
        raise _domain_error(error) from error
    if node_id is None:
        raise _error(
            404,
            ErrorCode.CURRENT_LOCATION_NOT_FOUND,
            f"No confirmed current location exists for user {user_id}",
        )
    return SuccessResponse(data=LocationResponse(user_id=user_id, node_id=node_id))


__all__ = ["router"]
