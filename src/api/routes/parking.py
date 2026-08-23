"""Read-only ParkSmart parking-state and canonical-map routes."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.parking_map import build_canonical_parking_map
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.slot_observation import SlotObservationError, SlotObservationService
from src.models.common import SuccessResponse
from src.models.schemas import (
    ErrorCode,
    FloorId,
    MapEdge,
    MapNode,
    ParkingSlot,
    SlotObservation,
    SlotStatus,
    ZoneId,
)

router = APIRouter(prefix="/parking", tags=["Parking"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
logger = logging.getLogger(__name__)


class ParkingStatusResponse(BaseModel):
    total: int
    available: int
    reserved: int
    occupied: int
    by_zone: dict[str, dict[SlotStatus, int]]


class ParkingMapResponse(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]
    slots: list[ParkingSlot]


class AdjacentSlotObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    observed_status: Literal[SlotStatus.AVAILABLE, SlotStatus.OCCUPIED]
    expected_slot_version: int = Field(ge=0)


def _slot_response(slot: object) -> ParkingSlot:
    return ParkingSlot.model_validate(slot, from_attributes=True)


def _domain_error(error: ParkingStateError) -> HTTPException:
    return HTTPException(
        status_code=404 if error.code is ErrorCode.SLOT_NOT_FOUND else 409,
        detail={"code": error.code.value, "message": error.message},
    )


def _observation_error(error: SlotObservationError) -> HTTPException:
    if error.code in {ErrorCode.SLOT_NOT_FOUND, ErrorCode.USER_NOT_FOUND}:
        status_code = 404
    elif error.code is ErrorCode.ACTIVE_SESSION_NOT_FOUND:
        status_code = 409
    else:
        status_code = 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.message},
    )


@router.get("/status", response_model=SuccessResponse[ParkingStatusResponse])
async def parking_status(
    session: SessionDependency,
) -> SuccessResponse[ParkingStatusResponse]:
    status = await ParkingStateService(session).get_parking_status()
    return SuccessResponse(data=ParkingStatusResponse.model_validate(status, from_attributes=True))


@router.get("/slots", response_model=SuccessResponse[list[ParkingSlot]])
async def parking_slots(
    session: SessionDependency,
    floor_id: Annotated[FloorId | None, Query()] = None,
    zone_id: Annotated[ZoneId | None, Query()] = None,
    status: Annotated[SlotStatus | None, Query()] = None,
    has_charger: Annotated[bool | None, Query()] = None,
    is_accessible: Annotated[bool | None, Query()] = None,
) -> SuccessResponse[list[ParkingSlot]]:
    slots = await ParkingStateService(session).list_slots(
        zone_id=zone_id,
        status=status,
        has_charger=has_charger,
        is_accessible=is_accessible,
    )
    if floor_id is not None:
        slots = [slot for slot in slots if slot.floor_id == floor_id]
    return SuccessResponse(data=[_slot_response(slot) for slot in slots])


@router.get("/slots/{slot_id}", response_model=SuccessResponse[ParkingSlot])
async def parking_slot(
    slot_id: str,
    session: SessionDependency,
) -> SuccessResponse[ParkingSlot]:
    try:
        slot = await ParkingStateService(session).get_slot(slot_id)
    except ParkingStateError as error:
        raise _domain_error(error) from error
    return SuccessResponse(data=_slot_response(slot))


@router.post(
    "/slots/{slot_id}/observation",
    response_model=SuccessResponse[SlotObservation],
)
async def observe_adjacent_parking_slot(
    slot_id: str,
    request: AdjacentSlotObservationRequest,
    session: SessionDependency,
) -> SuccessResponse[SlotObservation]:
    try:
        async with session.begin():
            observation = await SlotObservationService(session).create_observation(
                user_id=request.user_id,
                slot_id=slot_id,
                observed_status=request.observed_status,
                expected_slot_version=request.expected_slot_version,
            )
    except SlotObservationError as error:
        raise _observation_error(error) from error
    logger.info(
        "adjacent_slot_observation slot_id=%s actor_id=%s observed_status=%s outcome=success",
        slot_id,
        request.user_id,
        request.observed_status.value,
    )
    return SuccessResponse(
        data=SlotObservation.model_validate(observation, from_attributes=True),
        message="Observation submitted for verification.",
    )


@router.get("/map", response_model=SuccessResponse[ParkingMapResponse])
async def parking_map(session: SessionDependency) -> SuccessResponse[ParkingMapResponse]:
    canonical_map = build_canonical_parking_map()
    slots = await ParkingStateService(session).list_slots()
    return SuccessResponse(
        data=ParkingMapResponse(
            nodes=[MapNode.model_validate(node, from_attributes=True) for node in canonical_map.nodes],
            edges=[MapEdge.model_validate(edge, from_attributes=True) for edge in canonical_map.edges],
            slots=[_slot_response(slot) for slot in slots],
        )
    )
