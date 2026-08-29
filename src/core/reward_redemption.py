"""Database-backed voucher catalog and atomic reward redemption services."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingVoucher, RewardCatalogItem, RewardRedemption, RewardTransaction
from src.core.reward import RewardError, RewardService
from src.models.schemas import (
    ErrorCode,
    ParkingVoucherStatus,
    RewardRedemptionStatus,
    RewardSourceType,
    RewardTransactionStatus,
    RewardTransactionType,
)


class RewardCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> list[RewardCatalogItem]:
        return list(
            (
                await self.session.scalars(
                    select(RewardCatalogItem)
                    .where(RewardCatalogItem.is_active.is_(True))
                    .order_by(RewardCatalogItem.points_cost.asc(), RewardCatalogItem.code.asc())
                )
            ).all()
        )

    async def get_for_redemption(self, catalog_item_id: str) -> RewardCatalogItem:
        item = await self.session.scalar(
            select(RewardCatalogItem).where(RewardCatalogItem.id == catalog_item_id).with_for_update()
        )
        if item is None:
            raise RewardError(ErrorCode.REWARD_CATALOG_ITEM_NOT_FOUND, "Reward catalog item was not found.")
        if not item.is_active:
            raise RewardError(ErrorCode.REWARD_CATALOG_ITEM_INACTIVE, "Reward catalog item is inactive.")
        return item


class RewardRedemptionService:
    """Creates debit, redemption, and voucher in the caller-owned transaction."""

    def __init__(self, session: AsyncSession, *, rewards: RewardService | None = None, clock=None) -> None:
        self.session = session
        self.rewards = rewards or RewardService(session)
        self.clock = clock or (lambda: datetime.now(UTC))

    async def redeem(self, *, user_id: str, catalog_item_id: str) -> tuple[RewardRedemption, ParkingVoucher, int]:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() != timedelta(0):
            raise RewardError(ErrorCode.INVALID_TRANSITION, "Reward clock must use UTC.")
        await self.rewards._lock_user(user_id)
        item = await RewardCatalogService(self.session).get_for_redemption(catalog_item_id)
        balance = await self.rewards.finalized_balance(user_id, require_user=False)
        if balance < item.points_cost:
            raise RewardError(
                ErrorCode.INSUFFICIENT_REWARD_POINTS,
                "Insufficient finalized ParkSmart Points.",
                details={"available_points": balance, "points_cost": item.points_cost},
            )
        redemption = RewardRedemption(
            id=f"REDEMPTION-{uuid4()}",
            user_id=user_id,
            catalog_item_id=item.id,
            points_cost_snapshot=item.points_cost,
            free_minutes_snapshot=item.free_minutes,
            validity_days_snapshot=item.validity_days,
            status=RewardRedemptionStatus.COMPLETED,
            created_at=now,
        )
        self.session.add(redemption)
        await self.session.flush()
        debit = RewardTransaction(
            id=f"REWARD-{uuid4()}",
            user_id=user_id,
            source_type=RewardSourceType.VOUCHER_REDEMPTION,
            source_reference=redemption.id,
            transaction_type=RewardTransactionType.VOUCHER_REDEMPTION,
            status=RewardTransactionStatus.POSTED,
            points_delta=-item.points_cost,
            created_at=now,
            settled_at=now,
            transaction_metadata={"catalog_item_id": item.id, "catalog_code": item.code},
        )
        voucher = ParkingVoucher(
            id=f"VOUCHER-{uuid4()}",
            user_id=user_id,
            redemption_id=redemption.id,
            catalog_item_id=item.id,
            catalog_code_snapshot=item.code,
            points_cost_snapshot=item.points_cost,
            free_minutes_snapshot=item.free_minutes,
            validity_days_snapshot=item.validity_days,
            status=ParkingVoucherStatus.ISSUED,
            issued_at=now,
            expires_at=now + timedelta(days=item.validity_days),
        )
        self.session.add_all((debit, voucher))
        await self.session.flush()
        return redemption, voucher, balance - item.points_cost


__all__ = ["RewardCatalogService", "RewardRedemptionService"]
