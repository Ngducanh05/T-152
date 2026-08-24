"""Persistent UTC daily submission quota for wrong-parking reports."""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import ReportDailyUsage


class ReportQuotaClockError(ValueError):
    """The injected quota clock is not timezone-aware UTC."""


class ReportQuotaExceeded(Exception):  # noqa: N818 - contractual domain name
    """The trusted user has no report submissions left for the UTC day."""

    def __init__(self, reset_at: datetime) -> None:
        super().__init__("Wrong-parking report daily limit reached")
        self.reset_at = reset_at


class ReportSubmissionQuotaService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ReportQuotaClockError("Report quota clock must use timezone-aware UTC.")
        return value

    @staticmethod
    def _reset_at(now: datetime) -> datetime:
        return datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=UTC)

    async def preflight(self, user_id: str) -> None:
        limit = self.settings.wrong_parking_report_daily_limit
        if limit == 0:
            return

        now = self._now()
        submission_count = await self.session.scalar(
            select(ReportDailyUsage.submission_count).where(
                ReportDailyUsage.user_id == user_id,
                ReportDailyUsage.usage_date == now.date(),
            )
        )
        if submission_count is not None and submission_count >= limit:
            raise ReportQuotaExceeded(self._reset_at(now))

    async def consume(self, user_id: str) -> int:
        limit = self.settings.wrong_parking_report_daily_limit
        if limit == 0:
            return 0

        now = self._now()
        statement = (
            insert(ReportDailyUsage)
            .values(
                user_id=user_id,
                usage_date=now.date(),
                submission_count=1,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[
                    ReportDailyUsage.user_id,
                    ReportDailyUsage.usage_date,
                ],
                set_={
                    "submission_count": ReportDailyUsage.submission_count + 1,
                    "updated_at": now,
                },
                where=ReportDailyUsage.submission_count < limit,
            )
            .returning(ReportDailyUsage.submission_count)
        )
        submission_count = await self.session.scalar(statement)
        if submission_count is None:
            raise ReportQuotaExceeded(self._reset_at(now))
        return submission_count


__all__ = [
    "ReportQuotaClockError",
    "ReportQuotaExceeded",
    "ReportSubmissionQuotaService",
]
