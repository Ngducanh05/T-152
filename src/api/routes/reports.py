"""User-facing API for reporting vehicles parked in the wrong position."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.parking_report import ParkingReportError, ParkingReportService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import (
    EntityId,
    ErrorCode,
    FloorScopedId,
    WrongParkingReason,
    WrongParkingReport,
)

router = APIRouter(prefix="/reports", tags=["Reports"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
logger = logging.getLogger(__name__)


def _report_response(report: object) -> WrongParkingReport:
    values = vars(report)
    return WrongParkingReport.model_validate(
        {
            field_name: values.get(field_name)
            for field_name in WrongParkingReport.model_fields
        }
    )


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
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_wrong_parking_report(
    request: WrongParkingReportRequest,
    session: SessionDependency,
    http_request: Request,
) -> SuccessResponse[WrongParkingReport]:
    try:
        async with session.begin():
            report = await ParkingReportService(session).create_wrong_parking_report(
                reporter_user_id=request.user_id,
                slot_id=request.slot_id,
                reason_code=request.reason_code,
                description=request.description,
                observed_plate_number=request.observed_plate_number,
            )
            response_report = _report_response(report)
    except ParkingReportError as error:
        logger.warning(
            "wrong_parking_report_action action=create report_id=%s slot_id=%s "
            "actor_id=%s outcome=failure request_id=%s error_code=%s",
            error.report_id or "unknown",
            error.slot_id or request.slot_id,
            request.user_id,
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
        request.user_id,
        getattr(http_request.state, "request_id", "unknown"),
    )
    return SuccessResponse(
        data=response_report,
        message="Wrong-parking report submitted.",
    )


__all__ = ["router"]
