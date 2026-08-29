"""Voucher wallet and lazy expiry; deliberately no checkout/pricing behaviour."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingUser, ParkingVoucher
from src.core.reward import RewardError
from src.models.schemas import ErrorCode, ParkingVoucherStatus


class VoucherService:
    def __init__(self, session: AsyncSession, *, clock=None) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))

    async def list_user_vouchers(self, user_id: str) -> list[ParkingVoucher]:
        if await self.session.get(ParkingUser, user_id) is None:
            raise RewardError(ErrorCode.USER_NOT_FOUND, f"Parking user {user_id} was not found")
        return list(
            (
                await self.session.scalars(
                    select(ParkingVoucher)
                    .where(ParkingVoucher.user_id == user_id)
                    .order_by(ParkingVoucher.issued_at.desc(), ParkingVoucher.id.desc())
                )
            ).all()
        )

    async def expire_stale(self, user_id: str | None = None) -> int:
        now = self.clock()
        query = (
            select(ParkingVoucher)
            .where(ParkingVoucher.status == ParkingVoucherStatus.ISSUED, ParkingVoucher.expires_at <= now)
            .with_for_update()
        )
        if user_id is not None:
            query = query.where(ParkingVoucher.user_id == user_id)
        vouchers = list((await self.session.scalars(query)).all())
        for voucher in vouchers:
            voucher.status = ParkingVoucherStatus.EXPIRED
        if vouchers:
            await self.session.flush()
        return len(vouchers)


__all__ = ["VoucherService"]
