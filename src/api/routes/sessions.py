"""Transactional parking-session lifecycle API."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    ParkingUserDependency,
    resolve_parking_user_id,
    resolve_vehicle_id,
)
from src.api.errors import domain_http_error
from src.core.database import get_db_session
from src.core.db_models import ParkingSession as ParkingSessionRecord
from src.core.errors import DomainError
from src.core.idempotency import IdempotencyService
from src.core.parking_session import ParkingSessionError, ParkingSessionService
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.parking_time_benefit import ParkingTimeBenefitService
from src.core.reservation import ReservationService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    EntityId,
    ErrorCode,
    ParkingSessionCompletion,
    ParkingSessionStatus,
    ParkingTimeBenefit,
    ReservationStatus,
)
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


def _error(
    status_code: int,
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, object] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message, "details": details},
    )


def _session_error(error: ParkingSessionError, *, completing: bool = False) -> HTTPException:
    if error.code is ErrorCode.ACTIVE_SESSION_NOT_FOUND:
        return domain_http_error(
            error,
            code=ErrorCode.SESSION_NOT_FOUND if completing else error.code,
        )
    return domain_http_error(error)


def _state_error(error: ParkingStateError) -> HTTPException:
    return domain_http_error(error)


def _response(parking_session: object) -> ParkingSessionResponse:
    return ParkingSessionResponse.model_validate(parking_session, from_attributes=True)


def _completion_response(parking_session: object, benefit: object) -> ParkingSessionCompletion:
    session_response = _response(parking_session)
    return ParkingSessionCompletion(
        **session_response.model_dump(),
        time_benefit=ParkingTimeBenefit.model_validate(benefit, from_attributes=True),
    )


async def _completion_replay_response(
    *,
    replay: dict[str, object],
    session: AsyncSession,
    user_id: str,
    session_id: str,
) -> ParkingSessionCompletion:
    """Adapt only a validated pre-time-benefit completion replay in place."""
    if "time_benefit" in replay:
        return ParkingSessionCompletion.model_validate(replay)

    # A legacy response must still be a valid old completion response and must
    # identify this exact caller/session.  Anything else remains corrupt data,
    # not a shape we silently reinterpret.
    legacy = ParkingSessionResponse.model_validate(replay)
    if legacy.id != session_id or legacy.user_id != user_id:
        raise RuntimeError("Legacy idempotency completion replay does not match the requested session.")
    parking_session = await session.get(ParkingSessionRecord, session_id)
    if (
        parking_session is None
        or parking_session.user_id != user_id
        or parking_session.status is not ParkingSessionStatus.COMPLETED
    ):
        raise RuntimeError("Legacy idempotency completion replay has no matching completed session.")
    benefit = await ParkingTimeBenefitService(session).calculate(parking_session)
    return _completion_response(parking_session, benefit)


@router.post(
    "/confirm-parking",
    response_model=SuccessResponse[ParkingSessionResponse],
    responses=ERROR_RESPONSES,
)
async def confirm_parking(
    request: ConfirmParkingRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = None,
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
            idempotency = IdempotencyService(session)
            claim = await idempotency.claim(
                user_id=user_id,
                operation="confirm_parking",
                key=idempotency_key,
                payload={
                    "vehicle_id": vehicle_id,
                    "reservation_id": request.reservation_id,
                    "expected_version": request.expected_version,
                },
            )
            replay = idempotency.replay(claim)
            if replay is not None:
                response_data = ParkingSessionResponse.model_validate(replay)
                parking_session = None
                expired = False
            else:
                response_data = None
            current_time = datetime.now(UTC)
            if response_data is None:
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
                    response_data = _response(parking_session)
                    await idempotency.complete(
                        claim,
                        response_data.model_dump(mode="json"),
                    )
    except ParkingSessionError as error:
        raise _session_error(error) from error
    except ParkingStateError as error:
        raise _state_error(error) from error
    except DomainError as error:
        raise domain_http_error(error) from error
    if expired:
        raise _error(409, ErrorCode.RESERVATION_EXPIRED, "Reservation has expired.")
    assert response_data is not None
    return SuccessResponse(data=response_data)


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
    return SuccessResponse(data=ParkedVehicleResponse.model_validate(vehicle, from_attributes=True))


@router.post(
    "/{session_id}/complete",
    response_model=SuccessResponse[ParkingSessionCompletion],
    responses=ERROR_RESPONSES,
)
async def complete_session(
    session_id: str,
    request: CompleteSessionRequest,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=1, max_length=128),
    ] = None,
) -> SuccessResponse[ParkingSessionCompletion]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    try:
        async with session.begin():
            idempotency = IdempotencyService(session)
            claim = await idempotency.claim(
                user_id=user_id,
                operation="complete_parking_session",
                key=idempotency_key,
                payload={
                    "session_id": session_id,
                    "expected_version": request.expected_version,
                },
            )
            replay = idempotency.replay(claim)
            if replay is not None:
                response_data = await _completion_replay_response(
                    replay=replay,
                    session=session,
                    user_id=user_id,
                    session_id=session_id,
                )
                # The existing claim is locked.  Upgrade only the validated
                # legacy body so every later replay uses the current contract.
                if "time_benefit" not in replay:
                    await idempotency.complete(claim, response_data.model_dump(mode="json"))
            else:
                parking_session = await ParkingSessionService(session, ParkingStateService(session)).complete_session(
                    session_id,
                    user_id=user_id,
                    expected_version=request.expected_version,
                )
                benefit = await ParkingTimeBenefitService(session).calculate(parking_session)
                response_data = _completion_response(parking_session, benefit)
                await idempotency.complete(
                    claim,
                    response_data.model_dump(mode="json"),
                )
    except ParkingSessionError as error:
        raise _session_error(error, completing=True) from error
    except ParkingStateError as error:
        raise _state_error(error) from error
    except DomainError as error:
        raise domain_http_error(error) from error
    return SuccessResponse(data=response_data)


__all__ = ["router"]
