"""Voucher wallet and lazy expiry; deliberately no checkout/pricing behaviour."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingSession, ParkingUser, ParkingVoucher
from src.core.reward import RewardError
from src.models.schemas import ErrorCode, ParkingSessionStatus, ParkingVoucherStatus


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

    async def apply_to_session(
        self, *, user_id: str, voucher_id: str, session_id: str
    ) -> ParkingVoucher:
        """Attach one issued voucher to the caller's active parking session.

        The parking session is deliberately locked before the voucher so that
        contenders using different vouchers serialize on the same session.
        """
        now = self.clock()
        parking_session = await self.session.scalar(
            select(ParkingSession)
            .where(ParkingSession.id == session_id)
            .with_for_update()
        )
        if parking_session is None:
            raise RewardError(ErrorCode.SESSION_NOT_FOUND, f"Parking session {session_id} was not found")
        if parking_session.user_id != user_id or parking_session.status is not ParkingSessionStatus.ACTIVE:
            raise RewardError(ErrorCode.INVALID_TRANSITION, "Voucher can only be applied to your active parking session")

        voucher = await self.session.scalar(
            select(ParkingVoucher)
            .where(ParkingVoucher.id == voucher_id, ParkingVoucher.user_id == user_id)
            .with_for_update()
        )
        if voucher is None:
            raise RewardError(ErrorCode.VOUCHER_NOT_FOUND, f"Parking voucher {voucher_id} was not found")
        if voucher.status is not ParkingVoucherStatus.ISSUED or voucher.expires_at <= now:
            raise RewardError(ErrorCode.INVALID_TRANSITION, "Voucher is not available for application")

        applied = await self.session.scalar(
            select(ParkingVoucher).where(ParkingVoucher.applied_session_id == session_id)
        )
        if applied is not None:
            raise RewardError(ErrorCode.INVALID_TRANSITION, "A voucher is already applied to this parking session")

        voucher.status = ParkingVoucherStatus.APPLIED
        voucher.applied_at = now
        voucher.applied_session_id = session_id
        voucher.version += 1
        await self.session.flush()
        return voucher

    async def get_applied_to_session(self, session_id: str) -> ParkingVoucher | None:
        return await self.session.scalar(
            select(ParkingVoucher).where(
                ParkingVoucher.applied_session_id == session_id,
                ParkingVoucher.status == ParkingVoucherStatus.APPLIED,
            )
        )


__all__ = ["VoucherService"]
