"""User-facing API for reporting vehicles parked in the wrong position."""

import logging
<<<<<<< HEAD

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
=======
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
>>>>>>> feat/phase11-role-based-auth

from src.api.dependencies import (
    ParkingUserDependency,
    SessionDependency,
<<<<<<< HEAD
=======
    SettingsDependency,
>>>>>>> feat/phase11-role-based-auth
    resolve_parking_user_id,
)
from src.core.parking_report import ParkingReportError, ParkingReportService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    EntityId,
    ErrorCode,
    FloorScopedId,
    WrongParkingReason,
    WrongParkingReport,
)
from src.services.report_evidence import ReportEvidenceStorage, validate_report_image

router = APIRouter(prefix="/reports", tags=["Reports"])
logger = logging.getLogger(__name__)


class WrongParkingReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    slot_id: FloorScopedId
    reason_code: WrongParkingReason
    observed_plate_number: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def other_reason_requires_description(self) -> "WrongParkingReportRequest":
        if self.reason_code is WrongParkingReason.OTHER and len(self.description or "") < 5:
            raise ValueError(
                "description must contain at least five characters for reason OTHER"
            )
        return self

    @field_validator("observed_plate_number")
    @classmethod
    def normalize_plate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


@router.post(
    "/wrong-parking",
    response_model=SuccessResponse[WrongParkingReport],
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_wrong_parking_report(
    http_request: Request,
<<<<<<< HEAD
    current_user: ParkingUserDependency,
) -> SuccessResponse[WrongParkingReport]:
    user_id = resolve_parking_user_id(request.user_id, current_user)
    try:
        async with session.begin():
            report = await ParkingReportService(session).create_wrong_parking_report(
=======
    session: SessionDependency,
    current_user: ParkingUserDependency,
    settings: SettingsDependency,
) -> SuccessResponse[WrongParkingReport]:
    content_type = http_request.headers.get("content-type", "")
    evidence_bytes: bytes | None = None
    evidence_content_type: str | None = None
    try:
        if content_type.startswith("multipart/form-data"):
            form = await http_request.form()
            evidence = form.get("evidence")
            request = WrongParkingReportRequest(
                user_id=str(form.get("user_id") or ""),
                slot_id=str(form.get("slot_id") or ""),
                reason_code=form.get("reason_code"),
                observed_plate_number=(
                    str(form.get("observed_plate_number"))
                    if form.get("observed_plate_number") is not None
                    else None
                ),
                description=(
                    str(form.get("description"))
                    if form.get("description") is not None
                    else None
                ),
            )
            if hasattr(evidence, "read"):
                evidence_bytes = await evidence.read()  # type: ignore[union-attr]
                evidence_content_type = getattr(evidence, "content_type", None)
        else:
            request = WrongParkingReportRequest.model_validate(await http_request.json())
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "VALIDATION_ERROR", "message": "Request validation failed."},
        ) from error

    user_id = resolve_parking_user_id(request.user_id, current_user)
    stored_evidence = None
    report_id = f"REPORT-{uuid4()}"
    if evidence_bytes is not None:
        normalized_content_type = validate_report_image(
            content_type=evidence_content_type,
            size_bytes=len(evidence_bytes),
            max_bytes=settings.report_evidence_max_bytes,
        )
        stored_evidence = await ReportEvidenceStorage(settings).upload(
            report_id=report_id,
            data=evidence_bytes,
            content_type=normalized_content_type,
        )
    elif not settings.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": ErrorCode.REPORT_EVIDENCE_REQUIRED.value,
                "message": "Image evidence is required for wrong-parking reports.",
            },
        )

    try:
        async with session.begin():
            report = await ParkingReportService(session).create_wrong_parking_report(
                report_id=report_id,
>>>>>>> feat/phase11-role-based-auth
                reporter_user_id=user_id,
                slot_id=request.slot_id,
                reason_code=request.reason_code,
                description=request.description,
                observed_plate_number=request.observed_plate_number,
                evidence_storage_path=(
                    stored_evidence.storage_path if stored_evidence is not None else None
                ),
                evidence_content_type=(
                    stored_evidence.content_type if stored_evidence is not None else None
                ),
                evidence_size_bytes=(
                    stored_evidence.size_bytes if stored_evidence is not None else None
                ),
            )
    except ParkingReportError as error:
        if stored_evidence is not None:
            await ReportEvidenceStorage(settings).delete(stored_evidence.storage_path)
        logger.warning(
            "wrong_parking_report_action action=create report_id=%s slot_id=%s "
            "actor_id=%s outcome=failure request_id=%s error_code=%s",
            error.report_id or "unknown",
            error.slot_id or request.slot_id,
            user_id,
            getattr(http_request.state, "request_id", "unknown"),
            error.code.value,
        )
        status_code = (
            status.HTTP_404_NOT_FOUND
            if error.code in {ErrorCode.USER_NOT_FOUND, ErrorCode.SLOT_NOT_FOUND}
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": error.code.value, "message": error.message},
        ) from error
    logger.info(
        "wrong_parking_report_action action=create report_id=%s slot_id=%s "
        "actor_id=%s outcome=success request_id=%s",
        report.id,
        report.slot_id,
        user_id,
        getattr(http_request.state, "request_id", "unknown"),
    )
    return SuccessResponse(
        data=WrongParkingReport.model_validate(report, from_attributes=True),
        message="Wrong-parking report submitted.",
    )


__all__ = ["router"]
