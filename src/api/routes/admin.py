"""Read-only operational data for the ParkSmart admin dashboard."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import require_admin_or_demo
from src.core.database import get_db_session
from src.core.db_models import ParkingEvent as ParkingEventRecord
from src.core.db_models import ParkingSlot as ParkingSlotRecord
from src.core.db_models import WrongParkingReport as WrongParkingReportRecord
from src.models.common import SuccessResponse
from src.models.schemas import (
    FloorScopedId,
    ParkingEvent,
    ParkingEventType,
    WrongParkingReport,
    ZoneId,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin_or_demo)],
)
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


def _event_response(event: ParkingEventRecord) -> ParkingEvent:
    return ParkingEvent(
        id=event.id,
        event_type=event.event_type,
        slot_id=event.slot_id,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        old_status=event.old_status,
        new_status=event.new_status,
        created_at=event.created_at,
        metadata=event.event_metadata,
    )


@router.get("/events", response_model=SuccessResponse[list[ParkingEvent]])
async def recent_parking_events(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    zone_id: Annotated[ZoneId | None, Query()] = None,
    event_type: Annotated[ParkingEventType | None, Query()] = None,
    slot_id: Annotated[FloorScopedId | None, Query()] = None,
) -> SuccessResponse[list[ParkingEvent]]:
    query = select(ParkingEventRecord)
    if zone_id is not None:
        query = query.join(
            ParkingSlotRecord,
            ParkingEventRecord.slot_id == ParkingSlotRecord.id,
        ).where(ParkingSlotRecord.zone_id == zone_id)
    if event_type is not None:
        query = query.where(ParkingEventRecord.event_type == event_type)
    if slot_id is not None:
        query = query.where(ParkingEventRecord.slot_id == slot_id)
    query = query.order_by(
        ParkingEventRecord.created_at.desc(),
        ParkingEventRecord.id.desc(),
    ).limit(limit)
    events = (await session.scalars(query)).all()
    return SuccessResponse(data=[_event_response(event) for event in events])


@router.get("/reports", response_model=SuccessResponse[list[WrongParkingReport]])
async def recent_wrong_parking_reports(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SuccessResponse[list[WrongParkingReport]]:
    query = select(WrongParkingReportRecord).order_by(
        WrongParkingReportRecord.created_at.desc(),
        WrongParkingReportRecord.id.desc(),
    ).limit(limit)
    reports = (await session.scalars(query)).all()
    return SuccessResponse(
        data=[
            WrongParkingReport.model_validate(report, from_attributes=True)
            for report in reports
        ]
    )


__all__ = ["router"]
