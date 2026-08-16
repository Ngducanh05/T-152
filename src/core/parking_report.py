"""Persistence service for user-submitted wrong-parking reports."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingSlot, ParkingUser, WrongParkingReport
from src.models.schemas import ErrorCode


class ParkingReportError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ParkingReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_wrong_parking_report(
        self,
        *,
        reporter_user_id: str,
        slot_id: str,
        description: str,
        observed_plate_number: str | None,
    ) -> WrongParkingReport:
        if await self.session.get(ParkingUser, reporter_user_id) is None:
            raise ParkingReportError(
                ErrorCode.USER_NOT_FOUND,
                f"Parking user {reporter_user_id} was not found",
            )
        if await self.session.get(ParkingSlot, slot_id) is None:
            raise ParkingReportError(
                ErrorCode.SLOT_NOT_FOUND,
                f"Parking slot {slot_id} was not found",
            )

        report = WrongParkingReport(
            id=f"REPORT-{uuid4()}",
            reporter_user_id=reporter_user_id,
            slot_id=slot_id,
            observed_plate_number=observed_plate_number,
            description=description,
        )
        self.session.add(report)
        await self.session.flush()
        return report


__all__ = ["ParkingReportError", "ParkingReportService"]
