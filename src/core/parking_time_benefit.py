"""Duration-only parking voucher benefit calculation; deliberately no pricing."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingSession, ParkingVoucher
from src.core.errors import DomainError
from src.models.schemas import ErrorCode, ParkingSessionStatus


@dataclass(frozen=True, slots=True)
class ParkingTimeBenefit:
    total_minutes: float
    free_minutes: float
    billable_minutes: float
    voucher_id: str | None


class ParkingTimeBenefitService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def calculate(self, parking_session: ParkingSession | str) -> ParkingTimeBenefit:
        session_record = (
            parking_session
            if isinstance(parking_session, ParkingSession)
            else await self.session.get(ParkingSession, parking_session)
        )
        if session_record is None:
            raise DomainError(ErrorCode.SESSION_NOT_FOUND, "Parking session was not found.")
        if session_record.status is not ParkingSessionStatus.COMPLETED or session_record.completed_at is None:
            raise DomainError(ErrorCode.INVALID_TRANSITION, "Parking time benefit requires a completed session.")

        voucher = await self.session.scalar(
            select(ParkingVoucher).where(ParkingVoucher.applied_session_id == session_record.id)
        )
        elapsed_seconds = max(0.0, (session_record.completed_at - session_record.parked_at).total_seconds())
        total_minutes = elapsed_seconds / 60
        free_minutes = min(total_minutes, float(voucher.free_minutes_snapshot)) if voucher is not None else 0.0
        return ParkingTimeBenefit(
            total_minutes=total_minutes,
            free_minutes=free_minutes,
            billable_minutes=max(0.0, total_minutes - free_minutes),
            voucher_id=voucher.id if voucher is not None else None,
        )


__all__ = ["ParkingTimeBenefit", "ParkingTimeBenefitService"]
