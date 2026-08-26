"""Atomic parking-session lifecycle inside caller-owned transactions."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import (
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.errors import DomainError
from src.core.parking_state import ParkingStateService
from src.models.schemas import (
    ActorType,
    ErrorCode,
    ParkingSessionStatus,
    ReservationStatus,
)


class ParkingSessionError(DomainError):
    """Core session error with a stable API-independent error code."""


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
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.parking_state = parking_state or ParkingStateService(session)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.settings = settings or get_settings()

    async def confirm_parking(
        self,
        user_id: str,
        vehicle_id: str,
        reservation_id: str,
        *,
        expected_version: int | None = None,
    ) -> ParkingSession:
        current_time = self._utc_now()
        reservation = await self.session.get(ParkingReservation, reservation_id)
        if reservation is None:
            raise ParkingSessionError(
                ErrorCode.RESERVATION_NOT_FOUND,
                f"Reservation {reservation_id} was not found",
                details={"reservation_id": reservation_id},
            )
        self._validate_reservation_state(
            reservation,
            now=current_time,
        )

        user = await self._lock_user(user_id)
        vehicle = await self._lock_vehicle(vehicle_id)
        if vehicle.user_id != user_id:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                f"Vehicle {vehicle_id} is not owned by user {user_id}",
                details={"user_id": user_id, "vehicle_id": vehicle_id},
            )
        self._validate_reservation_owner(
            reservation,
            user_id=user_id,
            vehicle_id=vehicle_id,
        )
        slot = await self.session.get(ParkingSlot, reservation.slot_id)
        if slot is None:
            raise ParkingSessionError(
                ErrorCode.SLOT_NOT_FOUND,
                f"Parking slot {reservation.slot_id} was not found",
                details={"slot_id": reservation.slot_id},
            )
        self._validate_verified_arrival(user, slot, now=current_time)
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
                ErrorCode.ACTIVE_SESSION_EXISTS,
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
        if await self.session.get(ParkingUser, user_id) is None:
            self._raise_user_not_found(user_id)
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
        expected_version: int | None = None,
    ) -> ParkingSession:
        current_time = self._utc_now()
        parking_session_snapshot = await self.session.get(ParkingSession, session_id)
        if parking_session_snapshot is None:
            raise ParkingSessionError(
                ErrorCode.ACTIVE_SESSION_NOT_FOUND,
                f"Parking session {session_id} was not found",
                details={"session_id": session_id},
            )
        await self._lock_user(user_id)
        await self._lock_vehicle(parking_session_snapshot.vehicle_id)
        slot = await self.parking_state.lock_slot(parking_session_snapshot.slot_id)
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

        await self.parking_state.release_locked_slot(
            slot,
            actor_type=ActorType.USER,
            actor_id=user_id,
            vehicle_id=parking_session.vehicle_id,
            expected_version=expected_version,
            now=current_time,
        )
        parking_session.status = ParkingSessionStatus.COMPLETED
        parking_session.completed_at = current_time
        await self.session.flush()
        return parking_session

    async def _lock_reservation(self, reservation_id: str) -> ParkingReservation:
        reservation = await self.session.scalar(
            select(ParkingReservation).where(ParkingReservation.id == reservation_id).with_for_update()
        )
        if reservation is None:
            raise ParkingSessionError(
                ErrorCode.RESERVATION_NOT_FOUND,
                f"Reservation {reservation_id} was not found",
                details={"reservation_id": reservation_id},
            )
        return reservation

    async def _lock_user(self, user_id: str) -> ParkingUser:
        user = await self.session.scalar(
            select(ParkingUser)
            .where(ParkingUser.id == user_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if user is None:
            self._raise_user_not_found(user_id)
        return user

    async def _lock_vehicle(self, vehicle_id: str) -> Vehicle:
        vehicle = await self.session.scalar(
            select(Vehicle).where(Vehicle.id == vehicle_id).execution_options(populate_existing=True).with_for_update()
        )
        if vehicle is None:
            raise ParkingSessionError(
                ErrorCode.VEHICLE_NOT_FOUND,
                f"Vehicle {vehicle_id} was not found",
                details={"vehicle_id": vehicle_id},
            )
        return vehicle

    async def _lock_session(self, session_id: str) -> ParkingSession:
        parking_session = await self.session.scalar(
            select(ParkingSession)
            .where(ParkingSession.id == session_id)
            .execution_options(populate_existing=True)
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
    def _validate_reservation_state(
        reservation: ParkingReservation,
        *,
        now: datetime,
    ) -> None:
        if reservation.status is not ReservationStatus.ACTIVE:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "Reservation is not active",
                details={"reservation_id": reservation.id},
            )
        if reservation.expires_at <= now:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "Reservation has expired",
                details={"reservation_id": reservation.id},
            )

    @staticmethod
    def _validate_reservation_owner(
        reservation: ParkingReservation,
        *,
        user_id: str,
        vehicle_id: str,
    ) -> None:
        if reservation.user_id != user_id or reservation.vehicle_id != vehicle_id:
            raise ParkingSessionError(
                ErrorCode.INVALID_TRANSITION,
                "User or vehicle does not own this reservation",
                details={"reservation_id": reservation.id},
            )

    def _validate_verified_arrival(
        self,
        user: ParkingUser,
        slot: ParkingSlot,
        *,
        now: datetime,
    ) -> None:
        expires_before = now - timedelta(seconds=self.settings.parking_arrival_verification_ttl_seconds)
        reason = None
        if user.verified_node_id is None or user.verified_at is None:
            reason = "missing"
        elif user.verified_node_id != slot.node_id:
            reason = "wrong_node"
        elif user.verified_at < expires_before:
            reason = "expired"
        if reason is None:
            return
        raise ParkingSessionError(
            ErrorCode.PARKING_ARRIVAL_NOT_VERIFIED,
            "A fresh QR verification near the reserved slot is required.",
            details={
                "reason": reason,
                "slot_id": slot.id,
                "required_node_id": slot.node_id,
                "verified_node_id": user.verified_node_id,
                "verified_at": user.verified_at.isoformat() if user.verified_at else None,
                "verification_ttl_seconds": (self.settings.parking_arrival_verification_ttl_seconds),
            },
        )

    @staticmethod
    def _raise_user_not_found(user_id: str) -> None:
        raise ParkingSessionError(
            ErrorCode.USER_NOT_FOUND,
            f"Parking user {user_id} was not found",
            details={"user_id": user_id},
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
    expected_version: int | None = None,
    parking_state: ParkingStateService | None = None,
) -> ParkingSession:
    return await ParkingSessionService(session, parking_state).complete_session(
        session_id,
        user_id=user_id,
        expected_version=expected_version,
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
