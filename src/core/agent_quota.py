"""Persistent UTC daily request quota for the ParkSmart Agent."""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import AgentDailyUsage, ParkingUser
from src.models.schemas import ErrorCode


class AgentQuotaError(Exception):
    """Domain error raised while validating persistent Agent quota."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AgentQuotaExceeded(Exception):  # noqa: N818 - public domain name is contractual
    """The trusted user has no Agent requests left for the current UTC day."""

    def __init__(self, reset_at: datetime) -> None:
        super().__init__("Agent daily request limit reached")
        self.reset_at = reset_at


class AgentQuotaService:
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
            raise AgentQuotaError(
                ErrorCode.INVALID_TRANSITION,
                "Agent quota clock must use timezone-aware UTC.",
            )
        return value

    async def consume(self, user_id: str) -> None:
        limit = self.settings.agent_daily_request_limit
        if limit == 0:
            return

        now = self._now()
        user = await self.session.scalar(
            select(ParkingUser).where(ParkingUser.id == user_id).with_for_update()
        )
        if user is None:
            raise AgentQuotaError(
                ErrorCode.USER_NOT_FOUND,
                "The parking user was not found.",
            )

        usage = await self.session.scalar(
            select(AgentDailyUsage)
            .where(
                AgentDailyUsage.user_id == user_id,
                AgentDailyUsage.usage_date == now.date(),
            )
            .with_for_update()
        )
        reset_at = datetime.combine(
            now.date() + timedelta(days=1),
            time.min,
            tzinfo=UTC,
        )
        if usage is not None and usage.request_count >= limit:
            raise AgentQuotaExceeded(reset_at)

        if usage is None:
            usage = AgentDailyUsage(
                user_id=user_id,
                usage_date=now.date(),
                request_count=0,
                created_at=now,
                updated_at=now,
            )
            self.session.add(usage)
        usage.request_count += 1
        usage.updated_at = now
        await self.session.flush()


__all__ = ["AgentQuotaError", "AgentQuotaExceeded", "AgentQuotaService"]
