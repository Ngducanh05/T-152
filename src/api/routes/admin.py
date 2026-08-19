"""Access-controlled operational APIs for the ParkSmart admin dashboard."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import require_admin_or_demo
from src.core.database import get_db_session
from src.core.db_models import ParkingEvent as ParkingEventRecord
from src.core.db_models import ParkingSlot as ParkingSlotRecord
from src.core.parking_report import ParkingReportError, ParkingReportService
from src.models.auth import AppRole, CurrentUser
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    ErrorCode,
    FloorScopedId,
    ParkingEvent,
    ParkingEventType,
    WrongParkingReport,
    WrongParkingReportStatus,
    ZoneId,
)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin_or_demo)],
)
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
AdminUserDependency = Annotated[CurrentUser | None, Depends(require_admin_or_demo)]
logger = logging.getLogger(__name__)


class ResolveWrongParkingReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[WrongParkingReportStatus.RESOLVED]
    resolution_note: str | None = Field(default=None, max_length=500)
    expected_version: int = Field(ge=0)

    @field_validator("resolution_note")
    @classmethod
    def normalize_resolution_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ReopenWrongParkingReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class DeletedWrongParkingReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted_report_id: str


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


def _report_response(report: object) -> WrongParkingReport:
    return WrongParkingReport.model_validate(report, from_attributes=True)


def _report_http_error(error: ParkingReportError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if error.code is ErrorCode.REPORT_NOT_FOUND
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.message},
    )


def _admin_actor_id(user: CurrentUser | None) -> str:
    if user is not None and user.app_role is AppRole.ADMIN:
        return str(user.id)
    return "DEMO-ADMIN"


def _log_report_action(
    *,
    action: str,
    request: Request,
    report_id: str,
    slot_id: str | None,
    actor_id: str,
    outcome: str,
    error_code: ErrorCode | None = None,
) -> None:
    log = logger.warning if outcome == "failure" else logger.info
    log(
        "wrong_parking_report_action action=%s report_id=%s slot_id=%s "
        "actor_id=%s outcome=%s request_id=%s error_code=%s",
        action,
        report_id,
        slot_id or "unknown",
        actor_id,
        outcome,
        getattr(request.state, "request_id", "unknown"),
        error_code.value if error_code is not None else "none",
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
    request: Request,
    admin_user: AdminUserDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    report_status: Annotated[
        WrongParkingReportStatus | None,
        Query(alias="status"),
    ] = None,
    slot_id: Annotated[FloorScopedId | None, Query()] = None,
) -> SuccessResponse[list[WrongParkingReport]]:
    reports = await ParkingReportService(session).list_wrong_parking_reports(
        status=report_status,
        slot_id=slot_id,
        limit=limit,
    )
    _log_report_action(
        action="list",
        request=request,
        report_id="multiple",
        slot_id=slot_id,
        actor_id=_admin_actor_id(admin_user),
        outcome="success",
    )
    return SuccessResponse(data=[_report_response(report) for report in reports])


@router.get(
    "/reports/{report_id}",
    response_model=SuccessResponse[WrongParkingReport],
    responses={404: {"model": ErrorResponse}},
)
async def get_wrong_parking_report(
    report_id: str,
    session: SessionDependency,
    request: Request,
    admin_user: AdminUserDependency,
) -> SuccessResponse[WrongParkingReport]:
    actor_id = _admin_actor_id(admin_user)
    try:
        report = await ParkingReportService(session).get_wrong_parking_report(report_id)
    except ParkingReportError as error:
        _log_report_action(
            action="get",
            request=request,
            report_id=report_id,
            slot_id=error.slot_id,
            actor_id=actor_id,
            outcome="failure",
            error_code=error.code,
        )
        raise _report_http_error(error) from error
    _log_report_action(
        action="get",
        request=request,
        report_id=report.id,
        slot_id=report.slot_id,
        actor_id=actor_id,
        outcome="success",
    )
    return SuccessResponse(data=_report_response(report))


@router.patch(
    "/reports/{report_id}",
    response_model=SuccessResponse[WrongParkingReport],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def resolve_wrong_parking_report(
    report_id: str,
    payload: ResolveWrongParkingReportRequest,
    session: SessionDependency,
    request: Request,
    admin_user: AdminUserDependency,
) -> SuccessResponse[WrongParkingReport]:
    actor_id = _admin_actor_id(admin_user)
    try:
        async with session.begin():
            report = await ParkingReportService(session).resolve_wrong_parking_report(
                report_id,
                resolved_by=actor_id,
                resolution_note=payload.resolution_note,
                expected_version=payload.expected_version,
            )
    except ParkingReportError as error:
        _log_report_action(
            action="resolve",
            request=request,
            report_id=report_id,
            slot_id=error.slot_id,
            actor_id=actor_id,
            outcome="failure",
            error_code=error.code,
        )
        raise _report_http_error(error) from error
    _log_report_action(
        action="resolve",
        request=request,
        report_id=report.id,
        slot_id=report.slot_id,
        actor_id=actor_id,
        outcome="success",
    )
    return SuccessResponse(data=_report_response(report))


@router.post(
    "/reports/{report_id}/reopen",
    response_model=SuccessResponse[WrongParkingReport],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def reopen_wrong_parking_report(
    report_id: str,
    payload: ReopenWrongParkingReportRequest,
    session: SessionDependency,
    request: Request,
    admin_user: AdminUserDependency,
) -> SuccessResponse[WrongParkingReport]:
    actor_id = _admin_actor_id(admin_user)
    try:
        async with session.begin():
            report = await ParkingReportService(session).reopen_wrong_parking_report(
                report_id,
                expected_version=payload.expected_version,
            )
    except ParkingReportError as error:
        _log_report_action(
            action="reopen",
            request=request,
            report_id=report_id,
            slot_id=error.slot_id,
            actor_id=actor_id,
            outcome="failure",
            error_code=error.code,
        )
        raise _report_http_error(error) from error
    _log_report_action(
        action="reopen",
        request=request,
        report_id=report.id,
        slot_id=report.slot_id,
        actor_id=actor_id,
        outcome="success",
    )
    return SuccessResponse(data=_report_response(report))


@router.delete(
    "/reports/{report_id}",
    response_model=SuccessResponse[DeletedWrongParkingReportResponse],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def delete_wrong_parking_report(
    report_id: str,
    session: SessionDependency,
    request: Request,
    admin_user: AdminUserDependency,
    expected_version: Annotated[int, Query(ge=0)],
) -> SuccessResponse[DeletedWrongParkingReportResponse]:
    actor_id = _admin_actor_id(admin_user)
    try:
        async with session.begin():
            report = await ParkingReportService(session).delete_wrong_parking_report(
                report_id,
                expected_version=expected_version,
            )
    except ParkingReportError as error:
        _log_report_action(
            action="delete",
            request=request,
            report_id=report_id,
            slot_id=error.slot_id,
            actor_id=actor_id,
            outcome="failure",
            error_code=error.code,
        )
        raise _report_http_error(error) from error
    _log_report_action(
        action="delete",
        request=request,
        report_id=report.id,
        slot_id=report.slot_id,
        actor_id=actor_id,
        outcome="success",
    )
    return SuccessResponse(
        data=DeletedWrongParkingReportResponse(deleted_report_id=report.id)
    )


__all__ = ["router"]
