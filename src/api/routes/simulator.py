"""Transactional control endpoints for the deterministic parking simulator."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.database import get_db_session
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.simulator import (
    SIMULATED_VEHICLE_ID_PATTERN,
    SimulatorAction,
    SimulatorService,
    SimulatorStep,
)
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import ErrorCode, FloorScopedId, ParkingSlot, SlotStatus

router = APIRouter(prefix="/simulator", tags=["Simulator"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


class ManualSimulatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: FloorScopedId
    vehicle_id: str = Field(pattern=SIMULATED_VEHICLE_ID_PATTERN.pattern)


class SimulatorControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SimulatorStepResponse(BaseModel):
    sequence: int = Field(ge=1)
    action: SimulatorAction
    slot_id: FloorScopedId | None
    vehicle_id: str | None
    resulting_status: SlotStatus | None


def _step_response(step: SimulatorStep) -> SimulatorStepResponse:
    return SimulatorStepResponse.model_validate(step, from_attributes=True)


def _domain_error(error: ParkingStateError) -> HTTPException:
    status_code = {
        ErrorCode.INVALID_TRANSITION: 400,
        ErrorCode.SLOT_NOT_FOUND: 404,
        ErrorCode.SLOT_NOT_AVAILABLE: 409,
    }.get(error.code, 409)
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.message},
    )


@router.post(
    "/park",
    response_model=SuccessResponse[ParkingSlot],
    responses=ERROR_RESPONSES,
)
async def simulator_park(
    request: ManualSimulatorRequest,
    session: SessionDependency,
    settings: SettingsDependency,
) -> SuccessResponse[ParkingSlot]:
    try:
        async with session.begin():
            slot = await SimulatorService(
                session,
                ParkingStateService(session),
                settings=settings,
            ).manual_park(request.slot_id, request.vehicle_id)
    except ParkingStateError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=ParkingSlot.model_validate(slot, from_attributes=True))


@router.post(
    "/leave",
    response_model=SuccessResponse[ParkingSlot],
    responses=ERROR_RESPONSES,
)
async def simulator_leave(
    request: ManualSimulatorRequest,
    session: SessionDependency,
    settings: SettingsDependency,
) -> SuccessResponse[ParkingSlot]:
    try:
        async with session.begin():
            slot = await SimulatorService(
                session,
                ParkingStateService(session),
                settings=settings,
            ).manual_leave(request.slot_id, request.vehicle_id)
    except ParkingStateError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=ParkingSlot.model_validate(slot, from_attributes=True))


@router.post(
    "/reset",
    response_model=SuccessResponse[list[SimulatorStepResponse]],
    responses=ERROR_RESPONSES,
)
async def simulator_reset(
    session: SessionDependency,
    settings: SettingsDependency,
    _request: SimulatorControlRequest | None = None,
) -> SuccessResponse[list[SimulatorStepResponse]]:
    try:
        async with session.begin():
            steps = await SimulatorService(
                session,
                ParkingStateService(session),
                settings=settings,
            ).reset_demo()
    except ParkingStateError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=[_step_response(step) for step in steps])


@router.post(
    "/run-scenario",
    response_model=SuccessResponse[list[SimulatorStepResponse]],
    responses=ERROR_RESPONSES,
)
async def simulator_run_scenario(
    session: SessionDependency,
    settings: SettingsDependency,
    _request: SimulatorControlRequest | None = None,
) -> SuccessResponse[list[SimulatorStepResponse]]:
    try:
        async with session.begin():
            steps = await SimulatorService(
                session,
                ParkingStateService(session),
                settings=settings,
            ).run_fixed_scenario()
    except ParkingStateError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=[_step_response(step) for step in steps])


__all__ = ["router"]
