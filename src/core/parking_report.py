"""Verified lifecycle and reward rules for wrong-parking reports."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import ParkingSlot, ParkingUser, RewardTransaction, WrongParkingReport
from src.core.reward import RewardError, RewardService
from src.models.schemas import (
    ErrorCode,
    RewardSourceType,
    RewardTransactionStatus,
    WrongParkingReason,
    WrongParkingReportStatus,
    WrongParkingReportVerificationOutcome,
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
        settings: Settings | None = None,
        reward_service: RewardService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.rewards = reward_service or RewardService(
            session, settings=self.settings, clock=self.clock
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.utcoffset() != timedelta(0):
            raise ParkingReportError(
                ErrorCode.INVALID_REPORT_TRANSITION,
                "Report clock must use UTC.",
            )
        return value

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
        return observed_plate_number.strip().upper() or None

    @staticmethod
    def _check_version(report: WrongParkingReport, expected_version: int) -> None:
        if report.version != expected_version:
            raise ParkingReportError(
                ErrorCode.REPORT_VERSION_CONFLICT,
                f"Report {report.id} version changed; expected {expected_version}, found {report.version}.",
                report_id=report.id,
                slot_id=report.slot_id,
            )

    async def _attach_reward_status(self, reports: Sequence[WrongParkingReport]) -> None:
        ids = [report.id for report in reports]
        if not ids:
            return
        transactions = list(
            await self.session.scalars(
                select(RewardTransaction).where(
                    RewardTransaction.source_type == RewardSourceType.WRONG_PARKING_REPORT,
                    RewardTransaction.source_reference.in_(ids),
                )
            )
        )
        by_source = {transaction.source_reference: transaction for transaction in transactions}
        for report in reports:
            reward = by_source.get(report.id)
            report.reward_status = reward.status if reward is not None else None

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
        slot = await self.session.scalar(
            select(ParkingSlot).where(ParkingSlot.id == slot_id).with_for_update()
        )
        if slot is None:
            raise ParkingReportError(
                ErrorCode.SLOT_NOT_FOUND,
                f"Parking slot {slot_id} was not found",
                slot_id=slot_id,
            )

        now = self._now()
        cooldown_start = now - timedelta(seconds=self.settings.report_reward_cooldown_seconds)
        duplicate = await self.session.scalar(
            select(WrongParkingReport)
            .where(
                WrongParkingReport.slot_id == slot_id,
                WrongParkingReport.reason_code == reason_code,
                WrongParkingReport.status == WrongParkingReportStatus.OPEN,
                WrongParkingReport.created_at >= cooldown_start,
            )
            .order_by(WrongParkingReport.created_at.desc(), WrongParkingReport.id.desc())
            .limit(1)
        )
        report = WrongParkingReport(
            id=f"REPORT-{uuid4()}",
            reporter_user_id=reporter_user_id,
            slot_id=slot_id,
            reason_code=reason_code,
            status=WrongParkingReportStatus.OPEN,
            observed_plate_number=normalized_plate,
            description=normalized_description,
            created_at=now,
            updated_at=now,
            resolved_at=None,
            resolved_by=None,
            resolution_note=None,
            verification_outcome=WrongParkingReportVerificationOutcome.PENDING,
            reward_points=0,
            duplicate_candidate_of_id=duplicate.id if duplicate is not None else None,
            version=0,
        )
        self.session.add(report)
        reward = await self.rewards.reserve_contribution_reward(
            user_id=reporter_user_id,
            source_type=RewardSourceType.WRONG_PARKING_REPORT,
            source_reference=report.id,
            requested_points=(
                0 if duplicate is not None else self.settings.wrong_parking_report_reward_points
            ),
            metadata={"slot_id": slot.id, "floor_id": slot.floor_id},
        )
        report.reward_points = reward.points if reward is not None else 0
        report.reward_status = reward.status if reward is not None else None
        # The reward reservation can autoflush the initial INSERT. Reasserting
        # updated_at prevents SQLAlchemy's server-side onupdate from expiring it
        # during the reward_points UPDATE, keeping the response snapshot async-safe.
        report.updated_at = now
        await self.session.flush()
        await self.session.refresh(report)
        report.reward_status = reward.status if reward is not None else None
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
        reports = (
            await self.session.scalars(
                query.order_by(
                    WrongParkingReport.created_at.desc(),
                    WrongParkingReport.id.desc(),
                ).limit(limit)
            )
        ).all()
        await self._attach_reward_status(reports)
        return reports

    async def get_wrong_parking_report(
        self,
        report_id: str,
        *,
        for_update: bool = False,
    ) -> WrongParkingReport:
        query = select(WrongParkingReport).where(WrongParkingReport.id == report_id)
        if for_update:
            query = query.with_for_update()
        report = await self.session.scalar(query)
        if report is None:
            raise ParkingReportError(
                ErrorCode.REPORT_NOT_FOUND,
                f"Wrong-parking report {report_id} was not found.",
                report_id=report_id,
            )
        await self._attach_reward_status([report])
        return report

    async def resolve_wrong_parking_report(
        self,
        report_id: str,
        *,
        resolved_by: str,
        verification_outcome: WrongParkingReportVerificationOutcome,
        resolution_note: str | None,
        expected_version: int,
    ) -> WrongParkingReport:
        if verification_outcome is WrongParkingReportVerificationOutcome.PENDING:
            raise ParkingReportError(
                ErrorCode.INVALID_REPORT_TRANSITION,
                "Resolving a report requires a non-PENDING verification outcome.",
                report_id=report_id,
            )
        report = await self.get_wrong_parking_report(report_id, for_update=True)
        self._check_version(report, expected_version)
        if report.status is not WrongParkingReportStatus.OPEN:
            raise ParkingReportError(
                ErrorCode.INVALID_REPORT_TRANSITION,
                f"Report {report.id} is already resolved.",
                report_id=report.id,
                slot_id=report.slot_id,
            )

        now = self._now()
        report.status = WrongParkingReportStatus.RESOLVED
        report.verification_outcome = verification_outcome
        report.resolved_at = now
        report.resolved_by = resolved_by
        report.resolution_note = resolution_note.strip() if resolution_note else None
        report.updated_at = now
        report.version += 1

        reward = await self.rewards.get_source_transaction(
            RewardSourceType.WRONG_PARKING_REPORT, report.id, for_update=True
        )
        try:
            if reward is not None and reward.status is RewardTransactionStatus.PENDING:
                if verification_outcome is WrongParkingReportVerificationOutcome.CONFIRMED:
                    reward = await self.rewards.settle_pending(
                        RewardSourceType.WRONG_PARKING_REPORT, report.id
                    )
                else:
                    reward = await self.rewards.cancel_pending(
                        RewardSourceType.WRONG_PARKING_REPORT, report.id
                    )
        except RewardError as error:
            raise ParkingReportError(
                error.code,
                error.message,
                report_id=report.id,
                slot_id=report.slot_id,
            ) from error
        report.reward_status = reward.status if reward is not None else None
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
        report.updated_at = self._now()
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
        reward = await self.rewards.get_source_transaction(
            RewardSourceType.WRONG_PARKING_REPORT, report.id, for_update=True
        )
        if reward is not None and reward.status is RewardTransactionStatus.PENDING:
            await self.rewards.cancel_pending(
                RewardSourceType.WRONG_PARKING_REPORT, report.id
            )
        await self.session.delete(report)
        await self.session.flush()
        return report


__all__ = ["ParkingReportError", "ParkingReportService"]
