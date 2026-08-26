"""User-facing API for reporting vehicles parked in the wrong position."""

import hashlib
import logging
from datetime import UTC, datetime
from json import JSONDecodeError
from math import ceil
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
from starlette.datastructures import UploadFile

from src.api.dependencies import (
    ParkingUserDependency,
    SessionDependency,
    SettingsDependency,
    resolve_parking_user_id,
)
from src.api.errors import domain_http_error
from src.core.errors import DomainError
from src.core.idempotency import IdempotencyService
from src.core.parking_report import ParkingReportError, ParkingReportService
from src.core.report_quota import ReportQuotaExceeded
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    EntityId,
    ErrorCode,
    SlotId,
    WrongParkingReason,
    WrongParkingReport,
)
from src.services.report_evidence import ReportEvidenceStorage, validate_report_image

EVIDENCE_CHUNK_BYTES = 64 * 1024

router = APIRouter(prefix="/reports", tags=["Reports"])
logger = logging.getLogger(__name__)


def _evidence_too_large(max_bytes: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={
            "code": ErrorCode.REPORT_EVIDENCE_TOO_LARGE.value,
            "message": f"Report evidence must not exceed {max_bytes} bytes.",
        },
    )


def _daily_limit_reached(error: ReportQuotaExceeded) -> HTTPException:
    retry_after = max(
        1,
        ceil((error.reset_at - datetime.now(UTC)).total_seconds()),
    )
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(retry_after)},
        detail={
            "code": ErrorCode.REPORT_DAILY_LIMIT_REACHED.value,
            "message": "The daily wrong-parking report limit has been reached.",
        },
    )


def _report_http_error(error: ParkingReportError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if error.code in {ErrorCode.USER_NOT_FOUND, ErrorCode.SLOT_NOT_FOUND}
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.message},
    )


async def _read_bounded_evidence(evidence: UploadFile, max_bytes: int) -> bytes:
    if evidence.size is not None and evidence.size > max_bytes:
        raise _evidence_too_large(max_bytes)

    content = bytearray()
    while True:
        chunk = await evidence.read(EVIDENCE_CHUNK_BYTES)
        if not chunk:
            return bytes(content)
        content.extend(chunk)
        if len(content) > max_bytes:
            raise _evidence_too_large(max_bytes)


def _report_response(report: object) -> WrongParkingReport:
    values = vars(report)
    return WrongParkingReport.model_validate(
        {field_name: values.get(field_name) for field_name in WrongParkingReport.model_fields}
    )


class WrongParkingReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    slot_id: SlotId
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
            raise ValueError("description must contain at least five characters for reason OTHER")
        return self

    @field_validator("observed_plate_number")
    @classmethod
    def normalize_plate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


_WRONG_PARKING_TEXT_PROPERTIES: dict[str, dict[str, object]] = {
    "user_id": {"type": "string"},
    "slot_id": {"type": "string"},
    "reason_code": {
        "type": "string",
        "enum": [reason.value for reason in WrongParkingReason],
    },
    "observed_plate_number": {"type": "string", "maxLength": 32},
    "description": {"type": "string", "maxLength": 500},
}
_WRONG_PARKING_REQUIRED_FIELDS = ["user_id", "slot_id", "reason_code"]
_WRONG_PARKING_OPENAPI_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": _WRONG_PARKING_TEXT_PROPERTIES,
                "required": _WRONG_PARKING_REQUIRED_FIELDS,
                "additionalProperties": False,
            }
        },
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {
                    **_WRONG_PARKING_TEXT_PROPERTIES,
                    "evidence": {"type": "string", "format": "binary"},
                },
                "required": _WRONG_PARKING_REQUIRED_FIELDS,
                "additionalProperties": False,
            }
        },
    },
}


@router.post(
    "/wrong-parking",
    response_model=SuccessResponse[WrongParkingReport],
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    openapi_extra={"requestBody": _WRONG_PARKING_OPENAPI_REQUEST_BODY},
)
async def create_wrong_parking_report(
    http_request: Request,
    session: SessionDependency,
    current_user: ParkingUserDependency,
    settings: SettingsDependency,
) -> SuccessResponse[WrongParkingReport]:
    content_type = http_request.headers.get("content-type", "")
    content_length = http_request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if declared_length is not None and declared_length > settings.report_evidence_max_bytes + EVIDENCE_CHUNK_BYTES:
            raise _evidence_too_large(settings.report_evidence_max_bytes)

    evidence_bytes: bytes | None = None
    evidence_content_type: str | None = None
    evidence_upload: UploadFile | None = None
    try:
        if content_type.startswith("multipart/form-data"):
            try:
                form = await http_request.form(
                    max_files=1,
                    max_fields=5,
                    max_part_size=2048,
                )
            except Exception as error:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "VALIDATION_ERROR",
                        "message": "Multipart request validation failed.",
                    },
                ) from error
            evidence = form.get("evidence")
            if evidence is not None and not isinstance(evidence, UploadFile):
                raise ValueError("evidence must be an uploaded file")
            evidence_upload = evidence
            request = WrongParkingReportRequest(
                user_id=str(form.get("user_id") or ""),
                slot_id=str(form.get("slot_id") or ""),
                reason_code=form.get("reason_code"),
                observed_plate_number=(
                    str(form.get("observed_plate_number")) if form.get("observed_plate_number") is not None else None
                ),
                description=(str(form.get("description")) if form.get("description") is not None else None),
            )
        else:
            request = WrongParkingReportRequest.model_validate(await http_request.json())
    except (JSONDecodeError, ValidationError, ValueError) as error:
        if evidence_upload is not None:
            await evidence_upload.close()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "VALIDATION_ERROR", "message": "Request validation failed."},
        ) from error

    try:
        user_id = resolve_parking_user_id(request.user_id, current_user)
        stored_evidence = None
        evidence_storage = ReportEvidenceStorage(settings)
        report_service = ParkingReportService(session, settings=settings)

        if evidence_upload is not None:
            evidence_content_type = evidence_upload.content_type
            evidence_bytes = await _read_bounded_evidence(
                evidence_upload,
                settings.report_evidence_max_bytes,
            )
            normalized_content_type = validate_report_image(
                content_type=evidence_content_type,
                data=evidence_bytes,
                max_bytes=settings.report_evidence_max_bytes,
            )
        else:
            normalized_content_type = None

        report_id = f"REPORT-{uuid4()}"

        async def cleanup_uploaded_evidence() -> None:
            if stored_evidence is None:
                return
            if not await evidence_storage.delete(stored_evidence.storage_path):
                logger.warning(
                    "wrong_parking_report_evidence_cleanup_failed report_id=%s request_id=%s",
                    report_id,
                    getattr(http_request.state, "request_id", "unknown"),
                )

        try:
            async with session.begin():
                idempotency = IdempotencyService(session, settings=settings)
                claim = await idempotency.claim(
                    user_id=user_id,
                    operation="create_wrong_parking_report",
                    key=http_request.headers.get("Idempotency-Key"),
                    payload={
                        **request.model_dump(mode="json"),
                        "evidence_sha256": (
                            hashlib.sha256(evidence_bytes).hexdigest() if evidence_bytes is not None else None
                        ),
                    },
                )
                replay = idempotency.replay(claim)
                if replay is not None:
                    response_report = WrongParkingReport.model_validate(replay)
                else:
                    await report_service.preflight_wrong_parking_report(
                        reporter_user_id=user_id,
                        slot_id=request.slot_id,
                    )
                    if evidence_bytes is not None and normalized_content_type is not None:
                        stored_evidence = await evidence_storage.upload(
                            report_id=report_id,
                            data=evidence_bytes,
                            content_type=normalized_content_type,
                            allow_demo_fallback=current_user is None,
                        )
                    report = await report_service.create_wrong_parking_report(
                        report_id=report_id,
                        reporter_user_id=user_id,
                        slot_id=request.slot_id,
                        reason_code=request.reason_code,
                        description=request.description,
                        observed_plate_number=request.observed_plate_number,
                        evidence_storage_path=(stored_evidence.storage_path if stored_evidence is not None else None),
                        evidence_content_type=(stored_evidence.content_type if stored_evidence is not None else None),
                        evidence_size_bytes=(stored_evidence.size_bytes if stored_evidence is not None else None),
                    )
                    response_report = _report_response(report)
                    await idempotency.complete(
                        claim,
                        response_report.model_dump(mode="json"),
                    )
        except ReportQuotaExceeded as error:
            await cleanup_uploaded_evidence()
            raise _daily_limit_reached(error) from error
        except ParkingReportError as error:
            await cleanup_uploaded_evidence()
            logger.warning(
                "wrong_parking_report_action action=create report_id=%s slot_id=%s "
                "actor_id=%s outcome=failure request_id=%s error_code=%s",
                error.report_id or "unknown",
                error.slot_id or request.slot_id,
                user_id,
                getattr(http_request.state, "request_id", "unknown"),
                error.code.value,
            )
            raise _report_http_error(error) from error
        except DomainError as error:
            await cleanup_uploaded_evidence()
            raise domain_http_error(error) from error
        except Exception:
            await cleanup_uploaded_evidence()
            raise
    except ReportQuotaExceeded as error:
        raise _daily_limit_reached(error) from error
    except ParkingReportError as error:
        raise _report_http_error(error) from error
    finally:
        if evidence_upload is not None:
            await evidence_upload.close()
    logger.info(
        "wrong_parking_report_action action=create report_id=%s slot_id=%s actor_id=%s outcome=success request_id=%s",
        response_report.id,
        response_report.slot_id,
        user_id,
        getattr(http_request.state, "request_id", "unknown"),
    )
    return SuccessResponse(
        data=response_report,
        message="Wrong-parking report submitted.",
    )


__all__ = ["router"]
