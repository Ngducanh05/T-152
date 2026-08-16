"""User-facing API for reporting vehicles parked in the wrong position."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.parking_report import ParkingReportError, ParkingReportService
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import EntityId, FloorScopedId, WrongParkingReport

router = APIRouter(prefix="/reports", tags=["Reports"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


class WrongParkingReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: EntityId
    slot_id: FloorScopedId
    observed_plate_number: str | None = Field(default=None, max_length=32)
    description: str = Field(min_length=5, max_length=500)

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 5:
            raise ValueError("description must contain at least five characters")
        return stripped

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
) -> SuccessResponse[WrongParkingReport]:
    try:
        async with session.begin():
            report = await ParkingReportService(session).create_wrong_parking_report(
                reporter_user_id=request.user_id,
                slot_id=request.slot_id,
                description=request.description,
                observed_plate_number=request.observed_plate_number,
            )
    except ParkingReportError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": error.code.value, "message": error.message},
        ) from error
    return SuccessResponse(
        data=WrongParkingReport.model_validate(report, from_attributes=True),
        message="Wrong-parking report submitted.",
    )


__all__ = ["router"]
