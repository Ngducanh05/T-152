"""Transactional parking-session lifecycle API."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    ParkingUserDependency,
    resolve_parking_user_id,
    resolve_vehicle_id,
)
from src.core.database import get_db_session
from src.core.parking_session import ParkingSessionError, ParkingSessionService
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.reservation import ReservationService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import EntityId, ErrorCode, ReservationStatus
from src.models.schemas import ParkingSession as ParkingSessionResponse

router = APIRouter(prefix="/sessions", tags=["Parking Sessions"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class ConfirmParkingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    vehicle_id: EntityId
    reservation_id: EntityId
    expected_version: int | None = Field(default=None, ge=0)


class CompleteSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    expected_version: int | None = Field(default=None, ge=0)


class ParkedVehicleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: EntityId
    vehicle_id: EntityId
    slot_id: str
    destination_node_id: str


def _error(status_code: int, code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message},
    )


def _session_error(error: ParkingSessionError, *, completing: bool = False) -> HTTPException:
    message = error.message
    if "Reservation" in message and "not found" in message:
        return _error(404, ErrorCode.RESERVATION_NOT_FOUND, message)
    if "Parking user" in message and "not found" in message:
        return _error(404, ErrorCode.USER_NOT_FOUND, message)
    if "Vehicle" in message and "not found" in message:
        return _error(404, ErrorCode.VEHICLE_NOT_FOUND, message)
    if "active parking session already exists" in message:
        return _error(409, ErrorCode.ACTIVE_SESSION_EXISTS, message)
    if error.code is ErrorCode.ACTIVE_SESSION_NOT_FOUND:
        code = ErrorCode.SESSION_NOT_FOUND if completing else error.code
        return _error(404, code, message)
    return _error(409, error.code, message)


def _state_error(error: ParkingStateError) -> HTTPException:
    if "Reservation" in error.message and "not found" in error.message:
        return _error(404, ErrorCode.RESERVATION_NOT_FOUND, error.message)
    status_code = 404 if error.code is ErrorCode.SLOT_NOT_FOUND else 409
    return _error(status_code, error.code, error.message)


def _response(parking_session: object) -> ParkingSessionResponse:
    return ParkingSessionResponse.model_validate(parking_session, from_attributes=True)


@router.post(
    "/confirm-parking",
    response_model=SuccessResponse[ParkingSessionResponse],
    responses=ERROR_RESPONSES,
)
async def confirm_parking(
    request: ConfirmParkingRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
) -> SuccessResponse[ParkingSessionResponse]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    expired = False
    try:
        async with session.begin():
            vehicle_id = await resolve_vehicle_id(
                request.vehicle_id,
                current_user,
                session,
                required=True,
            )
            assert vehicle_id is not None
            current_time = datetime.now(UTC)
            state_service = ParkingStateService(session)
            reservation_service = ReservationService(session, state_service)
            reservation = await reservation_service.get_reservation(request.reservation_id)
            expired = reservation.status is ReservationStatus.EXPIRED
            if not expired:
                expired = await reservation_service.expire_reservation_if_needed(
                    reservation,
                    now=current_time,
                )
            if not expired:
                parking_session = await ParkingSessionService(
                    session,
                    state_service,
                    clock=lambda: current_time,
                ).confirm_parking(
                    user_id,
                    vehicle_id,
                    request.reservation_id,
                    expected_version=request.expected_version,
                )
    except ParkingSessionError as error:
        raise _session_error(error) from error
    except ParkingStateError as error:
        raise _state_error(error) from error
    if expired:
        raise _error(409, ErrorCode.RESERVATION_EXPIRED, "Reservation has expired.")
    return SuccessResponse(data=_response(parking_session))


@router.get(
    "/active",
    response_model=SuccessResponse[ParkedVehicleResponse],
    responses=ERROR_RESPONSES,
)
async def active_vehicle(
    session: SessionDependency,
    current_user: ParkingUserDependency,
    user_id: Annotated[EntityId, Query()],
) -> SuccessResponse[ParkedVehicleResponse]:
    user_id = resolve_parking_user_id(user_id, current_user)
    try:
        vehicle = await ParkingSessionService(session).find_parked_vehicle(user_id)
    except ParkingSessionError as error:
        raise _session_error(error) from error
    return SuccessResponse(
        data=ParkedVehicleResponse.model_validate(vehicle, from_attributes=True)
    )


@router.post(
    "/{session_id}/complete",
    response_model=SuccessResponse[ParkingSessionResponse],
    responses=ERROR_RESPONSES,
)
async def complete_session(
    session_id: str,
    request: CompleteSessionRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
) -> SuccessResponse[ParkingSessionResponse]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    try:
        async with session.begin():
            parking_session = await ParkingSessionService(
                session, ParkingStateService(session)
            ).complete_session(
                session_id,
                user_id=user_id,
                expected_version=request.expected_version,
            )
    except ParkingSessionError as error:
        raise _session_error(error, completing=True) from error
    except ParkingStateError as error:
        raise _state_error(error) from error
    return SuccessResponse(data=_response(parking_session))


__all__ = ["router"]
