"""Concurrency-safe reservation expiry housekeeping."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.db_models import ParkingReservation, ParkingSlot
from src.core.observability import ObservabilityRuntime, get_active_observability
from src.core.parking_state import ParkingStateService
from src.models.schemas import ReservationStatus

logger = logging.getLogger(__name__)


class ReservationExpiryService:
    """Expire due holds after locking slots in canonical order with SKIP LOCKED."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))
        self.parking_state = ParkingStateService(session)

    async def expire_batch(self, *, batch_size: int = 100) -> int:
        now = self.clock()
        if now.utcoffset() != timedelta(0):
            raise ValueError("Reservation expiry clock must use UTC")

        slots = list(
            await self.session.scalars(
                select(ParkingSlot)
                .join(
                    ParkingReservation,
                    ParkingReservation.slot_id == ParkingSlot.id,
                )
                .where(
                    ParkingReservation.status == ReservationStatus.ACTIVE,
                    ParkingReservation.expires_at <= now,
                )
                .order_by(ParkingSlot.id)
                .limit(batch_size)
                .with_for_update(of=ParkingSlot, skip_locked=True)
            )
        )
        expired = 0
        for slot in slots:
            reservation = await self.session.scalar(
                select(ParkingReservation)
                .where(
                    ParkingReservation.slot_id == slot.id,
                    ParkingReservation.status == ReservationStatus.ACTIVE,
                    ParkingReservation.expires_at <= now,
                )
                .order_by(ParkingReservation.id)
                .limit(1)
            )
            if reservation is None:
                continue
            await self.parking_state.expire_reservation(
                slot.id,
                reservation.id,
                now=now,
            )
            expired += 1
        return expired


async def run_reservation_expiry_worker(
    stop_event: asyncio.Event,
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    observability: ObservabilityRuntime | None = None,
) -> None:
    """Run periodic expiry without making request handlers own global cleanup."""
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.reservation_expiry_interval_seconds,
            )
            continue
        except TimeoutError:
            pass

        try:
            runtime = observability or get_active_observability()
            context = (
                runtime.start_span(
                    "worker.reservation_expiry.batch",
                    attributes={"worker.batch_size": settings.reservation_expiry_batch_size},
                )
                if runtime is not None
                else nullcontext(None)
            )
            with context as span:
                async with session_factory() as session, session.begin():
                    expired_count = await ReservationExpiryService(session).expire_batch(
                        batch_size=settings.reservation_expiry_batch_size
                    )
                if span is not None:
                    span.set_attribute("worker.expired_count", expired_count)
                    span.set_attribute("outcome", "success")
        except Exception as error:  # noqa: BLE001 - worker boundary logs and retries
            logger.error("reservation_expiry_worker_failed exception_type=%s", type(error).__name__)


__all__ = ["ReservationExpiryService", "run_reservation_expiry_worker"]
