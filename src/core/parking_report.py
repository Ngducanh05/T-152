"""Business lifecycle service for user-submitted wrong-parking reports."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingSlot, ParkingUser, WrongParkingReport
from src.models.schemas import (
    ErrorCode,
    WrongParkingReason,
    WrongParkingReportStatus,
)


class ParkingReportError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        report_id: str | None = None,
        slot_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.report_id = report_id
        self.slot_id = slot_id


class ParkingReportService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _normalize_description(
        reason_code: WrongParkingReason,
        description: str | None,
    ) -> str | None:
        normalized = description.strip() if description is not None else ""
        if reason_code is WrongParkingReason.OTHER and len(normalized) < 5:
            raise ParkingReportError(
                ErrorCode.INVALID_REPORT_TRANSITION,
                "Description must contain at least five characters for reason OTHER.",
            )
        return normalized or None

    @staticmethod
    def _normalize_plate(observed_plate_number: str | None) -> str | None:
        if observed_plate_number is None:
            return None
        normalized = observed_plate_number.strip().upper()
        return normalized or None

    @staticmethod
    def _check_version(
        report: WrongParkingReport,
        expected_version: int,
    ) -> None:
        if report.version != expected_version:
            raise ParkingReportError(
                ErrorCode.REPORT_VERSION_CONFLICT,
                (
                    f"Report {report.id} version changed; expected "
                    f"{expected_version}, found {report.version}."
                ),
                report_id=report.id,
                slot_id=report.slot_id,
            )

    async def create_wrong_parking_report(
        self,
        *,
        reporter_user_id: str,
        slot_id: str,
        reason_code: WrongParkingReason,
        description: str | None,
        observed_plate_number: str | None,
    ) -> WrongParkingReport:
        normalized_description = self._normalize_description(reason_code, description)
        normalized_plate = self._normalize_plate(observed_plate_number)
        if await self.session.get(ParkingUser, reporter_user_id) is None:
            raise ParkingReportError(
                ErrorCode.USER_NOT_FOUND,
                f"Parking user {reporter_user_id} was not found",
                slot_id=slot_id,
            )
        if await self.session.get(ParkingSlot, slot_id) is None:
            raise ParkingReportError(
                ErrorCode.SLOT_NOT_FOUND,
                f"Parking slot {slot_id} was not found",
                slot_id=slot_id,
            )

        report = WrongParkingReport(
            id=f"REPORT-{uuid4()}",
            reporter_user_id=reporter_user_id,
            slot_id=slot_id,
            reason_code=reason_code,
            status=WrongParkingReportStatus.OPEN,
            observed_plate_number=normalized_plate,
            description=normalized_description,
            version=0,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def list_wrong_parking_reports(
        self,
        *,
        status: WrongParkingReportStatus | None = None,
        slot_id: str | None = None,
        limit: int = 20,
    ) -> Sequence[WrongParkingReport]:
        query = select(WrongParkingReport)
        if status is not None:
            query = query.where(WrongParkingReport.status == status)
        if slot_id is not None:
            query = query.where(WrongParkingReport.slot_id == slot_id)
        query = query.order_by(
            WrongParkingReport.created_at.desc(),
            WrongParkingReport.id.desc(),
        ).limit(limit)
        return (await self.session.scalars(query)).all()

    async def get_wrong_parking_report(
        self,
        report_id: str,
        *,
        for_update: bool = False,
    ) -> WrongParkingReport:
        if for_update:
            report = await self.session.scalar(
                select(WrongParkingReport)
                .where(WrongParkingReport.id == report_id)
                .with_for_update()
            )
        else:
            report = await self.session.get(WrongParkingReport, report_id)
        if report is None:
            raise ParkingReportError(
                ErrorCode.REPORT_NOT_FOUND,
                f"Wrong-parking report {report_id} was not found.",
                report_id=report_id,
            )
        return report

    async def resolve_wrong_parking_report(
        self,
        report_id: str,
        *,
        resolved_by: str,
        resolution_note: str | None,
        expected_version: int,
    ) -> WrongParkingReport:
        report = await self.get_wrong_parking_report(report_id, for_update=True)
        self._check_version(report, expected_version)
        if report.status is not WrongParkingReportStatus.OPEN:
            raise ParkingReportError(
                ErrorCode.INVALID_REPORT_TRANSITION,
                f"Report {report.id} is already resolved.",
                report_id=report.id,
                slot_id=report.slot_id,
            )

        current_time = self.clock()
        normalized_resolution_note = (
            resolution_note.strip() if resolution_note is not None else ""
        )
        report.status = WrongParkingReportStatus.RESOLVED
        report.resolved_at = current_time
        report.resolved_by = resolved_by
        report.resolution_note = normalized_resolution_note or None
        report.updated_at = current_time
        report.version += 1
        await self.session.flush()
        return report

    async def reopen_wrong_parking_report(
        self,
        report_id: str,
        *,
        expected_version: int,
    ) -> WrongParkingReport:
        report = await self.get_wrong_parking_report(report_id, for_update=True)
        self._check_version(report, expected_version)
        if report.status is not WrongParkingReportStatus.RESOLVED:
            raise ParkingReportError(
                ErrorCode.INVALID_REPORT_TRANSITION,
                f"Report {report.id} is already open.",
                report_id=report.id,
                slot_id=report.slot_id,
            )

        report.status = WrongParkingReportStatus.OPEN
        report.resolved_at = None
        report.resolved_by = None
        report.resolution_note = None
        report.updated_at = self.clock()
        report.version += 1
        await self.session.flush()
        return report

    async def delete_wrong_parking_report(
        self,
        report_id: str,
        *,
        expected_version: int,
    ) -> WrongParkingReport:
        report = await self.get_wrong_parking_report(report_id, for_update=True)
        self._check_version(report, expected_version)
        await self.session.delete(report)
        await self.session.flush()
        return report


__all__ = ["ParkingReportError", "ParkingReportService"]
