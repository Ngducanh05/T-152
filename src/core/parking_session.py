"""Atomic parking-session lifecycle inside caller-owned transactions."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingReservation, ParkingSession, ParkingUser
from src.core.parking_state import ParkingStateService
from src.models.schemas import (
    ActorType,
    ErrorCode,
    ParkingSessionStatus,
    ReservationStatus,
)


class ParkingSessionError(Exception):
    """Core session error with a stable API-independent error code."""

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


@dataclass(frozen=True, slots=True)
class ParkedVehicle:
    session_id: str
    vehicle_id: str
    slot_id: str
    destination_node_id: str


class ParkingSessionService:
    """Coordinate session records while Parking State owns slot transitions."""

    def __init__(
        self,
        session: AsyncSession,
        parking_state: ParkingStateService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.parking_state = parking_state or ParkingStateService(session)
        self.clock = clock or (lambda: datetime.now(UTC))

    async def confirm_parking(
        self,
        user_id: str,
        vehicle_id: str,
        reservation_id: str,
        *,
        expected_version: int | None = None,
    ) -> ParkingSession:
        current_time = self._utc_now()
        reservation = await self._lock_reservation(reservation_id)
        self._validate_reservation(
            reservation,
            user_id=user_id,
            vehicle_id=vehicle_id,
            now=current_time,
        )

        await self._lock_user(user_id)
        existing = await self.session.scalar(
            select(ParkingSession).where(
                ParkingSession.status == ParkingSessionStatus.ACTIVE,
                or_(
                    ParkingSession.user_id == user_id,
                    ParkingSession.vehicle_id == vehicle_id,
                    ParkingSession.slot_id == reservation.slot_id,
                ),
            )
        )
        if existing is not None:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                f"An active parking session already exists: {existing.id}",
                details={"session_id": existing.id},
            )

        await self.parking_state.occupy_slot(
            reservation.slot_id,
            actor_type=ActorType.USER,
            actor_id=user_id,
            vehicle_id=vehicle_id,
            reservation_id=reservation.id,
            expected_version=expected_version,
            now=current_time,
        )
        parking_session = ParkingSession(
            id=f"SESSION-{uuid4()}",
            user_id=user_id,
            vehicle_id=vehicle_id,
            slot_id=reservation.slot_id,
            status=ParkingSessionStatus.ACTIVE,
            parked_at=current_time,
            completed_at=None,
        )
        self.session.add(parking_session)
        await self.session.flush()
        return parking_session

    async def get_active_session(self, user_id: str) -> ParkingSession | None:
        return await self.session.scalar(
            select(ParkingSession).where(
                ParkingSession.user_id == user_id,
                ParkingSession.status == ParkingSessionStatus.ACTIVE,
            )
        )

    async def find_parked_vehicle(self, user_id: str) -> ParkedVehicle:
        parking_session = await self.get_active_session(user_id)
        if parking_session is None:
            raise ParkingSessionError(
                ErrorCode.ACTIVE_SESSION_NOT_FOUND,
                f"No active parking session exists for user {user_id}",
                details={"user_id": user_id},
            )
        return ParkedVehicle(
            session_id=parking_session.id,
            vehicle_id=parking_session.vehicle_id,
            slot_id=parking_session.slot_id,
            destination_node_id=parking_session.slot_id,
        )

    async def complete_session(
        self,
        session_id: str,
        *,
        user_id: str,
    ) -> ParkingSession:
        current_time = self._utc_now()
        parking_session = await self._lock_session(session_id)
        if parking_session.user_id != user_id:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "User does not own this parking session",
                details={"session_id": session_id, "user_id": user_id},
            )
        if parking_session.status is not ParkingSessionStatus.ACTIVE:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "Only an active parking session can be completed",
                details={"session_id": session_id},
            )

        await self.parking_state.release_slot(
            parking_session.slot_id,
            actor_type=ActorType.USER,
            actor_id=user_id,
            vehicle_id=parking_session.vehicle_id,
            now=current_time,
        )
        parking_session.status = ParkingSessionStatus.COMPLETED
        parking_session.completed_at = current_time
        await self.session.flush()
        return parking_session

    async def _lock_reservation(self, reservation_id: str) -> ParkingReservation:
        reservation = await self.session.scalar(
            select(ParkingReservation)
            .where(ParkingReservation.id == reservation_id)
            .with_for_update()
        )
        if reservation is None:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                f"Reservation {reservation_id} was not found",
                details={"reservation_id": reservation_id},
            )
        return reservation

    async def _lock_user(self, user_id: str) -> None:
        user = await self.session.scalar(
            select(ParkingUser).where(ParkingUser.id == user_id).with_for_update()
        )
        if user is None:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                f"Parking user {user_id} was not found",
                details={"user_id": user_id},
            )

    async def _lock_session(self, session_id: str) -> ParkingSession:
        parking_session = await self.session.scalar(
            select(ParkingSession)
            .where(ParkingSession.id == session_id)
            .with_for_update()
        )
        if parking_session is None:
            raise ParkingSessionError(
                ErrorCode.ACTIVE_SESSION_NOT_FOUND,
                f"Parking session {session_id} was not found",
                details={"session_id": session_id},
            )
        return parking_session

    @staticmethod
    def _validate_reservation(
        reservation: ParkingReservation,
        *,
        user_id: str,
        vehicle_id: str,
        now: datetime,
    ) -> None:
        if reservation.status is not ReservationStatus.ACTIVE:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "Reservation is not active",
                details={"reservation_id": reservation.id},
            )
        if reservation.user_id != user_id or reservation.vehicle_id != vehicle_id:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "User or vehicle does not own this reservation",
                details={"reservation_id": reservation.id},
            )
        if reservation.expires_at <= now:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "Reservation has expired",
                details={"reservation_id": reservation.id},
            )

    def _utc_now(self) -> datetime:
        current_time = self.clock()
        if current_time.utcoffset() != timedelta(0):
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "Session clock must return a timezone-aware UTC datetime",
            )
        return current_time


async def confirm_parking(
    session: AsyncSession,
    user_id: str,
    vehicle_id: str,
    reservation_id: str,
    *,
    expected_version: int | None = None,
    parking_state: ParkingStateService | None = None,
) -> ParkingSession:
    return await ParkingSessionService(session, parking_state).confirm_parking(
        user_id,
        vehicle_id,
        reservation_id,
        expected_version=expected_version,
    )


async def get_active_session(
    session: AsyncSession,
    user_id: str,
) -> ParkingSession | None:
    return await ParkingSessionService(session).get_active_session(user_id)


async def find_parked_vehicle(
    session: AsyncSession,
    user_id: str,
) -> ParkedVehicle:
    return await ParkingSessionService(session).find_parked_vehicle(user_id)


async def complete_session(
    session: AsyncSession,
    session_id: str,
    *,
    user_id: str,
    parking_state: ParkingStateService | None = None,
) -> ParkingSession:
    return await ParkingSessionService(session, parking_state).complete_session(
        session_id,
        user_id=user_id,
    )


__all__ = [
    "ParkedVehicle",
    "ParkingSessionError",
    "ParkingSessionService",
    "complete_session",
    "confirm_parking",
    "find_parked_vehicle",
    "get_active_session",
]
