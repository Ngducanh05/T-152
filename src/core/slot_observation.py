"""Guarded status observations for slots adjacent to an active parking session."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingSlot
from src.core.parking_session import ParkingSessionError, ParkingSessionService
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.models.schemas import ErrorCode, SlotStatus

_SLOT_ID = re.compile(r"^F1-([A-D])(0[1-9]|10)$")


def adjacent_slot_ids(slot_id: str) -> tuple[str, ...]:
    """Return physical left/right neighbours within the same five-slot row."""
    match = _SLOT_ID.fullmatch(slot_id)
    if match is None:
        return ()
    zone_id, raw_number = match.groups()
    number = int(raw_number)
    row_start = 1 if number <= 5 else 6
    row_end = row_start + 4
    neighbours = [
        candidate
        for candidate in (number - 1, number + 1)
        if row_start <= candidate <= row_end
    ]
    return tuple(f"F1-{zone_id}{candidate:02d}" for candidate in neighbours)


class SlotObservationService:
    def __init__(
        self,
        session: AsyncSession,
        parking_state: ParkingStateService | None = None,
    ) -> None:
        self.session = session
        self.parking_state = parking_state or ParkingStateService(session)

    async def observe_adjacent_slot(
        self,
        *,
        user_id: str,
        slot_id: str,
        observed_status: SlotStatus,
        expected_version: int,
    ) -> ParkingSlot:
        try:
            active_session = await ParkingSessionService(
                self.session,
                self.parking_state,
            ).get_active_session(user_id)
        except ParkingSessionError as error:
            raise ParkingStateError(
                error.code,
                error.message,
                details=error.details,
            ) from error
        if active_session is None:
            raise ParkingStateError(
                ErrorCode.ACTIVE_SESSION_NOT_FOUND,
                f"No active parking session exists for user {user_id}",
                details={"user_id": user_id},
            )
        if slot_id not in adjacent_slot_ids(active_session.slot_id):
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Parking slot {slot_id} is not adjacent to {active_session.slot_id}",
                details={
                    "slot_id": slot_id,
                    "parked_slot_id": active_session.slot_id,
                },
            )
        return await self.parking_state.apply_user_slot_observation(
            slot_id,
            observed_status=observed_status,
            user_id=user_id,
            observer_session_id=active_session.id,
            expected_version=expected_version,
        )


__all__ = ["SlotObservationService", "adjacent_slot_ids"]
