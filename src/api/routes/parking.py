"""Read-only ParkSmart parking-state and canonical-map routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.parking_map import build_canonical_f1_map
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.models.common import SuccessResponse
from src.models.schemas import (
    ErrorCode,
    MapEdge,
    MapNode,
    ParkingSlot,
    SlotStatus,
    ZoneId,
)

router = APIRouter(prefix="/parking", tags=["Parking"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


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


def _slot_response(slot: object) -> ParkingSlot:
    return ParkingSlot.model_validate(slot, from_attributes=True)


def _domain_error(error: ParkingStateError) -> HTTPException:
    return HTTPException(
        status_code=404 if error.code is ErrorCode.SLOT_NOT_FOUND else 409,
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


@router.get("/map", response_model=SuccessResponse[ParkingMapResponse])
async def parking_map(session: SessionDependency) -> SuccessResponse[ParkingMapResponse]:
    canonical_map = build_canonical_f1_map()
    slots = await ParkingStateService(session).list_slots()
    return SuccessResponse(
        data=ParkingMapResponse(
            nodes=[MapNode.model_validate(node, from_attributes=True) for node in canonical_map.nodes],
            edges=[MapEdge.model_validate(edge, from_attributes=True) for edge in canonical_map.edges],
            slots=[_slot_response(slot) for slot in slots],
        )
    )
