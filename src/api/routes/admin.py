"""Access-controlled operational APIs for the ParkSmart admin dashboard."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import SettingsDependency, require_admin_or_demo
from src.core.database import get_db_session
from src.core.db_models import ParkingEvent as ParkingEventRecord
from src.core.db_models import ParkingSlot as ParkingSlotRecord
from src.core.parking_report import ParkingReportError, ParkingReportService
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.slot_observation import SlotObservationError, SlotObservationService
from src.models.auth import AppRole, CurrentUser
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    ErrorCode,
    FloorId,
    FloorScopedId,
    ParkingEvent,
    ParkingEventType,
    ParkingSlot,
    SlotId,
    SlotObservation,
    SlotObservationStatus,
    SlotStatus,
    WrongParkingReport,
    WrongParkingReportStatus,
    WrongParkingReportVerificationOutcome,
    ZoneId,
)
from src.services.report_evidence import ReportEvidenceStorage

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
    verification_outcome: Literal[
        WrongParkingReportVerificationOutcome.CONFIRMED,
        WrongParkingReportVerificationOutcome.REJECTED,
        WrongParkingReportVerificationOutcome.DUPLICATE,
        WrongParkingReportVerificationOutcome.UNVERIFIABLE,
    ]
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


class VerifySlotObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class RejectSlotObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class UpdateParkingSlotStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[SlotStatus.AVAILABLE, SlotStatus.OCCUPIED]
    expected_version: int = Field(ge=0)


class DeletedWrongParkingReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted_report_id: str


class ReportEvidenceUrlResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signed_url: str
    expires_in: int


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
    values = vars(report)
    return WrongParkingReport.model_validate(
        {field_name: values.get(field_name) for field_name in WrongParkingReport.model_fields}
    )


def _report_http_error(error: ParkingReportError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if error.code is ErrorCode.REPORT_NOT_FOUND else status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.message},
    )


def _observation_http_error(error: SlotObservationError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND if error.code is ErrorCode.OBSERVATION_NOT_FOUND else status.HTTP_409_CONFLICT
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.message},
    )


def _parking_state_http_error(error: ParkingStateError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if error.code is ErrorCode.SLOT_NOT_FOUND else status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=status_code,
        detail={
            "code": error.code.value,
            "message": error.message,
            "details": error.details,
        },
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


@router.patch(
    "/parking/slots/{slot_id}/status",
    response_model=SuccessResponse[ParkingSlot],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def update_parking_slot_status(
    slot_id: SlotId,
    payload: UpdateParkingSlotStatusRequest,
    session: SessionDependency,
    admin_user: AdminUserDependency,
) -> SuccessResponse[ParkingSlot]:
    try:
        async with session.begin():
            slot = await ParkingStateService(session).set_slot_status_by_admin(
                slot_id,
                payload.status,
                admin_id=_admin_actor_id(admin_user),
                expected_version=payload.expected_version,
            )
    except ParkingStateError as error:
        raise _parking_state_http_error(error) from error
    return SuccessResponse(
        data=ParkingSlot.model_validate(slot, from_attributes=True),
        message="Parking slot status updated.",
    )


@router.get(
    "/slot-observations",
    response_model=SuccessResponse[list[SlotObservation]],
)
async def recent_slot_observations(
    session: SessionDependency,
    observation_status: Annotated[SlotObservationStatus | None, Query(alias="status")] = None,
    floor_id: Annotated[FloorId | None, Query()] = None,
    slot_id: Annotated[FloorScopedId | None, Query()] = None,
    user_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SuccessResponse[list[SlotObservation]]:
    async with session.begin():
        observations = await SlotObservationService(session).list_observations(
            status=observation_status,
            floor_id=floor_id,
            slot_id=slot_id,
            user_id=user_id,
            limit=limit,
        )
    return SuccessResponse(
        data=[SlotObservation.model_validate(observation, from_attributes=True) for observation in observations]
    )


@router.get(
    "/slot-observations/{observation_id}",
    response_model=SuccessResponse[SlotObservation],
)
async def get_slot_observation(
    observation_id: str,
    session: SessionDependency,
) -> SuccessResponse[SlotObservation]:
    service = SlotObservationService(session)
    try:
        async with session.begin():
            await service.expire_pending()
            observation = await service.get_observation(observation_id)
    except SlotObservationError as error:
        raise _observation_http_error(error) from error
    return SuccessResponse(data=SlotObservation.model_validate(observation, from_attributes=True))


@router.post(
    "/slot-observations/{observation_id}/verify",
    response_model=SuccessResponse[SlotObservation],
)
async def verify_slot_observation(
    observation_id: str,
    payload: VerifySlotObservationRequest,
    session: SessionDependency,
    admin_user: AdminUserDependency,
) -> SuccessResponse[SlotObservation]:
    service = SlotObservationService(session)
    try:
        async with session.begin():
            await service.expire_pending()
        async with session.begin():
            observation = await service.verify_observation(
                observation_id,
                verified_by=_admin_actor_id(admin_user),
                expected_version=payload.expected_version,
            )
    except SlotObservationError as error:
        raise _observation_http_error(error) from error
    return SuccessResponse(
        data=SlotObservation.model_validate(observation, from_attributes=True),
        message="Observation verified.",
    )


@router.post(
    "/slot-observations/{observation_id}/reject",
    response_model=SuccessResponse[SlotObservation],
)
async def reject_slot_observation(
    observation_id: str,
    payload: RejectSlotObservationRequest,
    session: SessionDependency,
    admin_user: AdminUserDependency,
) -> SuccessResponse[SlotObservation]:
    service = SlotObservationService(session)
    try:
        async with session.begin():
            await service.expire_pending()
        async with session.begin():
            observation = await service.reject_observation(
                observation_id,
                rejected_by=_admin_actor_id(admin_user),
                reason=payload.reason,
                expected_version=payload.expected_version,
            )
    except SlotObservationError as error:
        raise _observation_http_error(error) from error
    return SuccessResponse(
        data=SlotObservation.model_validate(observation, from_attributes=True),
        message="Observation rejected.",
    )


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


@router.get(
    "/reports/{report_id}/evidence-url",
    response_model=SuccessResponse[ReportEvidenceUrlResponse],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_wrong_parking_report_evidence_url(
    report_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
) -> SuccessResponse[ReportEvidenceUrlResponse]:
    try:
        report = await ParkingReportService(session).get_wrong_parking_report(report_id)
    except ParkingReportError as error:
        raise _report_http_error(error) from error
    if not report.evidence_storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "REPORT_EVIDENCE_NOT_FOUND",
                "message": "Report evidence was not found.",
            },
        )
    expires_in = 300
    signed_url = await ReportEvidenceStorage(settings).create_signed_url(
        report.evidence_storage_path,
        expires_in=expires_in,
    )
    return SuccessResponse(data=ReportEvidenceUrlResponse(signed_url=signed_url, expires_in=expires_in))


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
                verification_outcome=payload.verification_outcome,
                resolution_note=payload.resolution_note,
                expected_version=payload.expected_version,
            )
            response_report = _report_response(report)
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
    return SuccessResponse(data=response_report)


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
            response_report = _report_response(report)
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
    return SuccessResponse(data=response_report)


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
    settings: SettingsDependency,
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
    cleanup_succeeded = False
    try:
        cleanup_succeeded = await ReportEvidenceStorage(settings).delete(report.evidence_storage_path)
    except Exception:  # noqa: BLE001 - cleanup is best effort after DB deletion
        cleanup_succeeded = False
    if not cleanup_succeeded:
        logger.warning(
            "wrong_parking_report_evidence_cleanup report_id=%s outcome=failure request_id=%s",
            report.id,
            getattr(request.state, "request_id", "unknown"),
        )
    return SuccessResponse(data=DeletedWrongParkingReportResponse(deleted_report_id=report.id))


__all__ = ["router"]
