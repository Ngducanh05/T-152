"""Transactional ParkSmart Points ledger and shared daily contribution cap."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import ParkingUser, RewardTransaction
from src.models.schemas import (
    ErrorCode,
    RewardSourceType,
    RewardSummary,
    RewardTransactionStatus,
    RewardTransactionType,
)


class RewardError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RewardService:
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
        if value.utcoffset() != timedelta(0):
            raise RewardError(ErrorCode.INVALID_TRANSITION, "Reward clock must use UTC.")
        return value

    @staticmethod
    def _day_bounds(value: datetime) -> tuple[datetime, datetime]:
        start = datetime.combine(value.date(), time.min, tzinfo=UTC)
        return start, start + timedelta(days=1)

    async def _lock_user(self, user_id: str) -> ParkingUser:
        user = await self.session.scalar(
            select(ParkingUser).where(ParkingUser.id == user_id).with_for_update()
        )
        if user is None:
            raise RewardError(
                ErrorCode.USER_NOT_FOUND,
                f"Parking user {user_id} was not found",
                details={"user_id": user_id},
            )
        return user

    async def reserve_contribution_reward(
        self,
        *,
        user_id: str,
        source_type: RewardSourceType,
        source_reference: str,
        requested_points: int,
        metadata: dict[str, object],
    ) -> RewardTransaction | None:
        """Serialize eligibility on the user row and reserve at most one reward."""
        now = self._now()
        await self._lock_user(user_id)
        existing = await self.session.scalar(
            select(RewardTransaction).where(
                RewardTransaction.source_type == source_type,
                RewardTransaction.source_reference == source_reference,
            )
        )
        if existing is not None:
            return existing
        if requested_points <= 0:
            return None

        start, end = self._day_bounds(now)
        used_points = int(
            await self.session.scalar(
                select(func.coalesce(func.sum(RewardTransaction.points), 0)).where(
                    RewardTransaction.user_id == user_id,
                    RewardTransaction.transaction_type
                    == RewardTransactionType.CONTRIBUTION_REWARD,
                    RewardTransaction.status.in_(
                        (
                            RewardTransactionStatus.PENDING,
                            RewardTransactionStatus.EARNED,
                        )
                    ),
                    RewardTransaction.created_at >= start,
                    RewardTransaction.created_at < end,
                )
            )
            or 0
        )
        if used_points + requested_points > self.settings.contribution_daily_points_limit:
            return None

        transaction = RewardTransaction(
            id=f"REWARD-{uuid4()}",
            user_id=user_id,
            source_type=source_type,
            source_reference=source_reference,
            transaction_type=RewardTransactionType.CONTRIBUTION_REWARD,
            status=RewardTransactionStatus.PENDING,
            points=requested_points,
            created_at=now,
            settled_at=None,
            transaction_metadata=dict(metadata),
        )
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def get_source_transaction(
        self,
        source_type: RewardSourceType,
        source_reference: str,
        *,
        for_update: bool = False,
    ) -> RewardTransaction | None:
        query = select(RewardTransaction).where(
            RewardTransaction.source_type == source_type,
            RewardTransaction.source_reference == source_reference,
        )
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def settle_pending(
        self,
        source_type: RewardSourceType,
        source_reference: str,
    ) -> RewardTransaction | None:
        transaction = await self.get_source_transaction(
            source_type, source_reference, for_update=True
        )
        if transaction is None:
            return None
        if transaction.status is not RewardTransactionStatus.PENDING:
            raise RewardError(
                ErrorCode.REWARD_ALREADY_SETTLED,
                f"Reward for {source_reference} is already {transaction.status.value}.",
                details={"source_reference": source_reference},
            )
        transaction.status = RewardTransactionStatus.EARNED
        transaction.settled_at = self._now()
        await self.session.flush()
        return transaction

    async def cancel_pending(
        self,
        source_type: RewardSourceType,
        source_reference: str,
    ) -> RewardTransaction | None:
        transaction = await self.get_source_transaction(
            source_type, source_reference, for_update=True
        )
        if transaction is None:
            return None
        if transaction.status is RewardTransactionStatus.CANCELLED:
            return transaction
        if transaction.status is RewardTransactionStatus.EARNED:
            raise RewardError(
                ErrorCode.REWARD_ALREADY_SETTLED,
                f"Earned reward for {source_reference} cannot be cancelled.",
                details={"source_reference": source_reference},
            )
        transaction.status = RewardTransactionStatus.CANCELLED
        transaction.settled_at = self._now()
        await self.session.flush()
        return transaction

    async def list_user_transactions(self, user_id: str) -> Sequence[RewardTransaction]:
        if await self.session.get(ParkingUser, user_id) is None:
            raise RewardError(ErrorCode.USER_NOT_FOUND, f"Parking user {user_id} was not found")
        return (
            await self.session.scalars(
                select(RewardTransaction)
                .where(
                    RewardTransaction.user_id == user_id,
                    RewardTransaction.transaction_type
                    == RewardTransactionType.CONTRIBUTION_REWARD,
                )
                .order_by(
                    RewardTransaction.created_at.desc(),
                    RewardTransaction.id.desc(),
                )
            )
        ).all()

    async def get_summary(self, user_id: str) -> RewardSummary:
        transactions = list(await self.list_user_transactions(user_id))
        now = self._now()
        start, end = self._day_bounds(now)
        earned = [tx for tx in transactions if tx.status is RewardTransactionStatus.EARNED]
        pending = [tx for tx in transactions if tx.status is RewardTransactionStatus.PENDING]
        return RewardSummary(
            available_points=sum(tx.points for tx in earned),
            pending_points=sum(tx.points for tx in pending),
            verified_contributions=len(earned),
            daily_pending_points=sum(
                tx.points for tx in pending if start <= tx.created_at < end
            ),
            daily_earned_points=sum(
                tx.points for tx in earned if start <= tx.created_at < end
            ),
            daily_limit_points=self.settings.contribution_daily_points_limit,
        )


__all__ = ["RewardError", "RewardService"]
