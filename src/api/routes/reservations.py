"""Transactional reservation lifecycle API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    ParkingUserDependency,
    resolve_parking_user_id,
    resolve_vehicle_id,
)
from src.api.errors import domain_http_error
from src.core.database import get_db_session
from src.core.errors import DomainError
from src.core.idempotency import IdempotencyService
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.reservation import ReservationService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    EntityId,
    ErrorCode,
    ReservationStatus,
    SlotId,
)
from src.models.schemas import ParkingReservation as ParkingReservationResponse

router = APIRouter(prefix="/reservations", tags=["Reservations"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


class CreateReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    vehicle_id: EntityId
    slot_id: SlotId
    expected_version: int | None = Field(default=None, ge=0)


def _error(status_code: int, code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message},
    )


def _domain_error(error: ParkingStateError) -> HTTPException:
    return domain_http_error(error)


def _response(reservation: object) -> ParkingReservationResponse:
    return ParkingReservationResponse.model_validate(reservation, from_attributes=True)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[ParkingReservationResponse],
    responses=ERROR_RESPONSES,
)
async def create_reservation(
    request: CreateReservationRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = None,
) -> SuccessResponse[ParkingReservationResponse]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    try:
        async with session.begin():
            vehicle_id = await resolve_vehicle_id(
                request.vehicle_id,
                current_user,
                session,
                required=True,
            )
            assert vehicle_id is not None  # required=True guarantees this invariant.
            idempotency = IdempotencyService(session)
            claim = await idempotency.claim(
                user_id=user_id,
                operation="create_reservation",
                key=idempotency_key,
                payload={
                    "vehicle_id": vehicle_id,
                    "slot_id": request.slot_id,
                    "expected_version": request.expected_version,
                },
            )
            replay = idempotency.replay(claim)
            if replay is not None:
                response_data = ParkingReservationResponse.model_validate(replay)
            else:
                reservation = await ReservationService(session, ParkingStateService(session)).create_reservation(
                    user_id,
                    vehicle_id,
                    request.slot_id,
                    expected_version=request.expected_version,
                )
                response_data = _response(reservation)
                await idempotency.complete(
                    claim,
                    response_data.model_dump(mode="json"),
                )
    except ParkingStateError as error:
        raise _domain_error(error) from error
    except DomainError as error:
        raise domain_http_error(error) from error
    return SuccessResponse(data=response_data)


@router.get(
    "/active",
    response_model=SuccessResponse[ParkingReservationResponse],
    responses=ERROR_RESPONSES,
)
async def active_reservation(
    session: SessionDependency,
    current_user: ParkingUserDependency,
    user_id: Annotated[EntityId, Query()],
) -> SuccessResponse[ParkingReservationResponse]:
    user_id = resolve_parking_user_id(user_id, current_user)
    try:
        async with session.begin():
            reservation = await ReservationService(session, ParkingStateService(session)).get_active_reservation(
                user_id
            )
    except ParkingStateError as error:
        raise _domain_error(error) from error
    if reservation is None:
        raise _error(
            404,
            ErrorCode.ACTIVE_RESERVATION_NOT_FOUND,
            f"No active reservation exists for user {user_id}",
        )
    return SuccessResponse(data=_response(reservation))


@router.delete(
    "/{reservation_id}",
    response_model=SuccessResponse[ParkingReservationResponse],
    responses=ERROR_RESPONSES,
)
async def cancel_reservation(
    reservation_id: str,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    user_id: Annotated[EntityId, Query()],
) -> SuccessResponse[ParkingReservationResponse]:
    user_id = resolve_parking_user_id(user_id, current_user)
    try:
        async with session.begin():
            service = ReservationService(session, ParkingStateService(session))
            reservation = await service.get_reservation(reservation_id)
            if reservation.status is not ReservationStatus.EXPIRED:
                reservation = await service.cancel_reservation(reservation_id, user_id=user_id)
    except ParkingStateError as error:
        raise _domain_error(error) from error
    if reservation.status is ReservationStatus.EXPIRED:
        raise _error(409, ErrorCode.RESERVATION_EXPIRED, "Reservation has expired.")
    return SuccessResponse(data=_response(reservation))


__all__ = ["router"]
