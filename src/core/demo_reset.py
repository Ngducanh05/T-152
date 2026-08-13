"""Transactional orchestration for restoring the repeatable demo baseline."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.location import LocationService
from src.core.parking_session import ParkingSessionService
from src.core.parking_state import ParkingStateService
from src.core.reservation import ReservationService
from src.core.seed import DEMO_START_NODE_ID, DEMO_USER_ID
from src.core.simulator import SimulatorService, SimulatorStep


class DemoResetService:
    """Close demo-user state before delegating baseline reset to the simulator.

    The caller owns the database transaction. This keeps session completion,
    reservation cancellation, location confirmation, and simulator reset atomic.
    """

    def __init__(self, session: AsyncSession, *, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def reset_demo(self) -> list[SimulatorStep]:
        if not self.session.in_transaction():
            raise RuntimeError("DemoResetService requires a caller-owned transaction")

        parking_state = ParkingStateService(self.session)
        session_service = ParkingSessionService(self.session, parking_state)
        reservation_service = ReservationService(self.session, parking_state)

        active_session = await session_service.get_active_session(DEMO_USER_ID)
        if active_session is not None:
            await session_service.complete_session(
                active_session.id,
                user_id=DEMO_USER_ID,
            )

        active_reservation = await reservation_service.get_active_reservation(DEMO_USER_ID)
        if active_reservation is not None:
            await reservation_service.cancel_reservation(
                active_reservation.id,
                user_id=DEMO_USER_ID,
            )

        await LocationService(self.session).confirm_location(
            DEMO_USER_ID,
            DEMO_START_NODE_ID,
        )

        return await SimulatorService(
            self.session,
            parking_state,
            settings=self.settings,
        ).reset_demo()


__all__ = ["DemoResetService"]
