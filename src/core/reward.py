"""Authoritative signed ParkSmart Points ledger and contribution lifecycle."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import ParkingUser, RewardTransaction
from src.core.errors import DomainError
from src.models.schemas import (
    ErrorCode,
    RewardSourceType,
    RewardSummary,
    RewardTransactionStatus,
    RewardTransactionType,
)


class RewardError(DomainError):
    """Reward-domain failure with the shared API error protocol."""


class RewardService:
    def __init__(
        self, session: AsyncSession, *, settings: Settings | None = None, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise RewardError(ErrorCode.INVALID_TRANSITION, "Reward clock must use UTC.")
        return value

    def business_day_bounds(self, value: datetime | None = None) -> tuple[datetime, datetime]:
        now = value or self._now()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise RewardError(ErrorCode.INVALID_TRANSITION, "Reward clock must use UTC.")
        timezone = ZoneInfo(self.settings.reward_business_timezone)
        local = now.astimezone(timezone)
        start_local = datetime.combine(local.date(), time.min, tzinfo=timezone)
        return start_local.astimezone(UTC), (start_local + timedelta(days=1)).astimezone(UTC)

    async def _lock_user(self, user_id: str) -> ParkingUser:
        user = await self.session.scalar(select(ParkingUser).where(ParkingUser.id == user_id).with_for_update())
        if user is None:
            raise RewardError(
                ErrorCode.USER_NOT_FOUND, f"Parking user {user_id} was not found", details={"user_id": user_id}
            )
        return user

    async def finalized_balance(self, user_id: str, *, require_user: bool = True) -> int:
        """Return the signed available balance; never conceal a negative ledger."""
        if require_user and await self.session.get(ParkingUser, user_id) is None:
            raise RewardError(ErrorCode.USER_NOT_FOUND, f"Parking user {user_id} was not found")
        finalized = (
            (RewardTransaction.transaction_type == RewardTransactionType.CONTRIBUTION_REWARD)
            & (RewardTransaction.status == RewardTransactionStatus.EARNED)
        ) | (
            (RewardTransaction.transaction_type != RewardTransactionType.CONTRIBUTION_REWARD)
            & (RewardTransaction.status == RewardTransactionStatus.POSTED)
        )
        balance = int(
            await self.session.scalar(
                select(func.coalesce(func.sum(RewardTransaction.points_delta), 0)).where(
                    RewardTransaction.user_id == user_id, finalized
                )
            )
            or 0
        )
        if balance < 0:
            raise RewardError(
                ErrorCode.INVALID_TRANSITION, "Reward ledger balance is negative.", details={"user_id": user_id}
            )
        return balance

    async def reserve_contribution_reward(
        self,
        *,
        user_id: str,
        source_type: RewardSourceType,
        source_reference: str,
        requested_points: int,
        metadata: dict[str, object],
    ) -> RewardTransaction | None:
        now = self._now()
        await self._lock_user(user_id)
        existing = await self.get_source_transaction(
            source_type, source_reference, transaction_type=RewardTransactionType.CONTRIBUTION_REWARD
        )
        if existing is not None:
            return existing
        if requested_points <= 0:
            return None
        start, end = self.business_day_bounds(now)
        reserved = int(
            await self.session.scalar(
                select(func.coalesce(func.sum(RewardTransaction.points_delta), 0)).where(
                    RewardTransaction.user_id == user_id,
                    RewardTransaction.transaction_type == RewardTransactionType.CONTRIBUTION_REWARD,
                    RewardTransaction.points_delta > 0,
                    RewardTransaction.status.in_((RewardTransactionStatus.PENDING, RewardTransactionStatus.EARNED)),
                    RewardTransaction.created_at >= start,
                    RewardTransaction.created_at < end,
                )
            )
            or 0
        )
        granted = min(requested_points, max(0, self.settings.contribution_daily_points_limit - reserved))
        if granted == 0:
            return None
        transaction = RewardTransaction(
            id=f"REWARD-{uuid4()}",
            user_id=user_id,
            source_type=source_type,
            source_reference=source_reference,
            transaction_type=RewardTransactionType.CONTRIBUTION_REWARD,
            status=RewardTransactionStatus.PENDING,
            points_delta=granted,
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
        transaction_type: RewardTransactionType | None = None,
        for_update: bool = False,
    ) -> RewardTransaction | None:
        query = select(RewardTransaction).where(
            RewardTransaction.source_type == source_type, RewardTransaction.source_reference == source_reference
        )
        if transaction_type is not None:
            query = query.where(RewardTransaction.transaction_type == transaction_type)
        if for_update:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def settle_pending(self, source_type: RewardSourceType, source_reference: str) -> RewardTransaction | None:
        transaction = await self.get_source_transaction(
            source_type, source_reference, transaction_type=RewardTransactionType.CONTRIBUTION_REWARD, for_update=True
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

    async def cancel_pending(self, source_type: RewardSourceType, source_reference: str) -> RewardTransaction | None:
        transaction = await self.get_source_transaction(
            source_type, source_reference, transaction_type=RewardTransactionType.CONTRIBUTION_REWARD, for_update=True
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
                    RewardTransaction.transaction_type == RewardTransactionType.CONTRIBUTION_REWARD,
                )
                .order_by(RewardTransaction.created_at.desc(), RewardTransaction.id.desc())
            )
        ).all()

    async def list_user_ledger(self, user_id: str) -> Sequence[RewardTransaction]:
        if await self.session.get(ParkingUser, user_id) is None:
            raise RewardError(ErrorCode.USER_NOT_FOUND, f"Parking user {user_id} was not found")
        return (
            await self.session.scalars(
                select(RewardTransaction)
                .where(RewardTransaction.user_id == user_id)
                .order_by(RewardTransaction.created_at.desc(), RewardTransaction.id.desc())
            )
        ).all()

    async def get_summary(self, user_id: str) -> RewardSummary:
        transactions = list(await self.list_user_transactions(user_id))
        start, end = self.business_day_bounds()
        earned = [tx for tx in transactions if tx.status is RewardTransactionStatus.EARNED]
        pending = [tx for tx in transactions if tx.status is RewardTransactionStatus.PENDING]
        return RewardSummary(
            available_points=await self.finalized_balance(user_id, require_user=False),
            pending_points=sum(tx.points_delta for tx in pending),
            verified_contributions=len(earned),
            daily_pending_points=sum(tx.points_delta for tx in pending if start <= tx.created_at < end),
            daily_earned_points=sum(tx.points_delta for tx in earned if start <= tx.created_at < end),
            daily_limit_points=self.settings.contribution_daily_points_limit,
        )


__all__ = ["RewardError", "RewardService"]
