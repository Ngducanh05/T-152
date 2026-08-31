"""Apply one owned issued voucher to one active parking session."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingSession, ParkingUser, ParkingVoucher
from src.core.reward import RewardError
from src.models.schemas import ErrorCode, ParkingSessionStatus, ParkingVoucherStatus


class VoucherApplicationService:
    """Voucher application only; pricing and parking lifecycle stay elsewhere."""

    def __init__(self, session: AsyncSession, *, clock=None) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise RewardError(ErrorCode.INVALID_TRANSITION, "Voucher clock must use UTC.")
        return value

    async def apply(
        self,
        *,
        user_id: str,
        voucher_id: str,
        session_id: str | None = None,
    ) -> ParkingVoucher:
        # Lock order intentionally starts with ParkingUser. ParkingSessionService also
        # acquires the user first, so completing and applying cannot form a cycle.
        user = await self.session.scalar(select(ParkingUser).where(ParkingUser.id == user_id).with_for_update())
        if user is None:
            raise RewardError(ErrorCode.USER_NOT_FOUND, f"Parking user {user_id} was not found")

        session_query = select(ParkingSession).where(
            ParkingSession.id == session_id
            if session_id is not None
            else (ParkingSession.user_id == user_id) & (ParkingSession.status == ParkingSessionStatus.ACTIVE)
        ).with_for_update()
        parking_session = await self.session.scalar(session_query)
        if parking_session is None:
            raise RewardError(ErrorCode.ACTIVE_SESSION_NOT_FOUND, "No active parking session exists for this user.")
        if parking_session.user_id != user_id:
            raise RewardError(
                ErrorCode.VOUCHER_OWNERSHIP_MISMATCH,
                "The parking session is not owned by this user.",
            )
        if parking_session.status is not ParkingSessionStatus.ACTIVE:
            raise RewardError(ErrorCode.VOUCHER_NOT_USABLE, "A voucher can only be applied to an active session.")

        voucher = await self.session.scalar(
            select(ParkingVoucher).where(ParkingVoucher.id == voucher_id).with_for_update()
        )
        if voucher is None:
            raise RewardError(ErrorCode.VOUCHER_NOT_FOUND, "Parking voucher was not found.")
        if voucher.user_id != user_id:
            raise RewardError(
                ErrorCode.VOUCHER_OWNERSHIP_MISMATCH,
                "The parking voucher is not owned by this user.",
            )

        now = self._now()
        if voucher.status is ParkingVoucherStatus.ISSUED and voucher.expires_at <= now:
            # The caller owns the transaction.  Do not manufacture an expiry
            # update immediately before raising: that change would be rolled
            # back and suggest persistence that never happened.  Wallet reads
            # use VoucherService.expire_stale as the authoritative lazy path.
            raise RewardError(ErrorCode.VOUCHER_EXPIRED, "Parking voucher has expired.")
        if voucher.status is ParkingVoucherStatus.EXPIRED:
            raise RewardError(ErrorCode.VOUCHER_EXPIRED, "Parking voucher has expired.")
        if voucher.status is ParkingVoucherStatus.APPLIED:
            if voucher.applied_session_id == parking_session.id:
                # Natural idempotency: a retry of the exact already-completed
                # application is successful, without a ledger mutation.
                return voucher
            raise RewardError(ErrorCode.VOUCHER_NOT_USABLE, "Parking voucher is not usable.")
        if voucher.status is not ParkingVoucherStatus.ISSUED:
            raise RewardError(ErrorCode.VOUCHER_NOT_USABLE, "Parking voucher is not usable.")

        applied = await self.session.scalar(
            select(ParkingVoucher)
            .where(ParkingVoucher.applied_session_id == parking_session.id)
            .with_for_update()
        )
        if applied is not None:
            raise RewardError(ErrorCode.VOUCHER_SESSION_CONFLICT, "A voucher is already applied to this session.")

        voucher.status = ParkingVoucherStatus.APPLIED
        voucher.applied_at = now
        voucher.applied_session_id = parking_session.id
        voucher.version += 1
        await self.session.flush()
        return voucher


__all__ = ["VoucherApplicationService"]
