"""Reservation lifecycle orchestration inside caller-owned transactions."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import ParkingReservation, ParkingUser, Vehicle
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.models.schemas import ErrorCode, ReservationStatus

_ACTIVE_USER_CONSTRAINT = "uq_parking_reservations_active_user"
_ACTIVE_VEHICLE_CONSTRAINT = "uq_parking_reservations_active_vehicle"
_ACTIVE_SLOT_CONSTRAINT = "uq_parking_reservations_active_slot"


class ReservationService:
    """Coordinate reservation rules while Parking State owns every slot change."""

    def __init__(
        self,
        session: AsyncSession,
        parking_state: ParkingStateService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.parking_state = parking_state or ParkingStateService(session)
        self.settings = settings or get_settings()

    async def create_reservation(
        self,
        user_id: str,
        vehicle_id: str,
        slot_id: str,
        *,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> ParkingReservation:
        current_time = _utc_now(now)
        await self._validate_and_lock_owner(user_id, vehicle_id)

        existing = await self._find_active_reservation(user_id=user_id)
        if existing is not None:
            if not await self.expire_reservation_if_needed(existing, now=current_time):
                raise ParkingStateError(
                    ErrorCode.ACTIVE_RESERVATION_EXISTS,
                    f"User already has active reservation {existing.id}",
                    details={"reservation_id": existing.id},
                )

        reservation_id = f"RESERVATION-{uuid4()}"
        expires_at = current_time + timedelta(seconds=self.settings.reservation_ttl_seconds)
        try:
            await self.parking_state.reserve_slot(
                slot_id,
                reservation_id,
                user_id=user_id,
                vehicle_id=vehicle_id,
                expires_at=expires_at,
                expected_version=expected_version,
                now=current_time,
            )
        except IntegrityError as error:
            self._raise_concurrency_error(error, slot_id)

        reservation = await self.session.get(ParkingReservation, reservation_id)
        if reservation is None:  # pragma: no cover - guards an internal invariant
            raise RuntimeError(f"Reservation {reservation_id} was not persisted")
        return reservation

    async def get_active_reservation(
        self,
        user_id: str,
        *,
        now: datetime | None = None,
    ) -> ParkingReservation | None:
        current_time = _utc_now(now)
        await self._validate_user_exists(user_id)
        reservation = await self._find_active_reservation(user_id=user_id)
        if reservation is None:
            return None
        if await self.expire_reservation_if_needed(reservation, now=current_time):
            return None
        return reservation

    async def get_reservation(self, reservation_id: str) -> ParkingReservation:
        reservation = await self.session.get(ParkingReservation, reservation_id)
        if reservation is None:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Reservation {reservation_id} was not found",
                details={"reservation_id": reservation_id},
            )
        return reservation

    async def cancel_reservation(
        self,
        reservation_id: str,
        *,
        user_id: str,
        now: datetime | None = None,
    ) -> ParkingReservation:
        current_time = _utc_now(now)
        reservation = await self.session.get(ParkingReservation, reservation_id)
        if reservation is None:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Reservation {reservation_id} was not found",
                details={"reservation_id": reservation_id},
            )
        await self._validate_user_exists(user_id)
        if reservation.user_id != user_id:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                "User does not own this reservation",
                details={"reservation_id": reservation_id, "user_id": user_id},
            )
        await self.parking_state.cancel_reservation(
            reservation.slot_id,
            reservation.id,
            user_id=user_id,
            now=current_time,
        )
        return reservation

    async def expire_reservation_if_needed(
        self,
        reservation: ParkingReservation | str,
        *,
        now: datetime | None = None,
    ) -> bool:
        current_time = _utc_now(now)
        if isinstance(reservation, str):
            loaded = await self.session.get(ParkingReservation, reservation)
            if loaded is None:
                raise ParkingStateError(
                    ErrorCode.INVALID_TRANSITION,
                    f"Reservation {reservation} was not found",
                    details={"reservation_id": reservation},
                )
            reservation = loaded
        if reservation.status is not ReservationStatus.ACTIVE:
            return False
        if reservation.expires_at > current_time:
            return False
        await self.parking_state.expire_reservation(
            reservation.slot_id,
            reservation.id,
            now=current_time,
        )
        return True

    async def _validate_and_lock_owner(self, user_id: str, vehicle_id: str) -> None:
        user = await self.session.scalar(
            select(ParkingUser).where(ParkingUser.id == user_id).with_for_update()
        )
        if user is None:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Parking user {user_id} was not found",
                details={"user_id": user_id},
            )
        vehicle = await self.session.scalar(
            select(Vehicle).where(Vehicle.id == vehicle_id).with_for_update()
        )
        if vehicle is None:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Vehicle {vehicle_id} was not found",
                details={"vehicle_id": vehicle_id},
            )
        if vehicle.user_id != user_id:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Vehicle {vehicle_id} is not owned by user {user_id}",
                details={"user_id": user_id, "vehicle_id": vehicle_id},
            )

    async def _validate_user_exists(self, user_id: str) -> None:
        if await self.session.get(ParkingUser, user_id) is None:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Parking user {user_id} was not found",
                details={"user_id": user_id},
            )

    async def _find_active_reservation(self, *, user_id: str) -> ParkingReservation | None:
        return await self.session.scalar(
            select(ParkingReservation).where(
                ParkingReservation.user_id == user_id,
                ParkingReservation.status == ReservationStatus.ACTIVE,
            )
        )

    @staticmethod
    def _raise_concurrency_error(error: IntegrityError, slot_id: str) -> None:
        constraint_name = _constraint_name(error)
        if constraint_name == _ACTIVE_SLOT_CONSTRAINT:
            raise ParkingStateError(
                ErrorCode.SLOT_NOT_AVAILABLE,
                f"Parking slot {slot_id} is not available",
                details={"slot_id": slot_id},
            ) from error
        if constraint_name in {_ACTIVE_USER_CONSTRAINT, _ACTIVE_VEHICLE_CONSTRAINT}:
            raise ParkingStateError(
                ErrorCode.ACTIVE_RESERVATION_EXISTS,
                "User or vehicle already has an active reservation",
            ) from error
        raise error


def _constraint_name(error: IntegrityError) -> str | None:
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        name = getattr(current, "constraint_name", None)
        if isinstance(name, str):
            return name
        for related in (getattr(current, "orig", None), current.__cause__, current.__context__):
            if isinstance(related, BaseException):
                pending.append(related)
    message = str(error)
    for name in (
        _ACTIVE_USER_CONSTRAINT,
        _ACTIVE_VEHICLE_CONSTRAINT,
        _ACTIVE_SLOT_CONSTRAINT,
    ):
        if name in message:
            return name
    return None


def _utc_now(value: datetime | None) -> datetime:
    current_time = value or datetime.now(UTC)
    if current_time.utcoffset() != timedelta(0):
        raise ParkingStateError(
            ErrorCode.INVALID_TRANSITION,
            "now must be a timezone-aware UTC datetime",
        )
    return current_time


async def create_reservation(
    session: AsyncSession,
    user_id: str,
    vehicle_id: str,
    slot_id: str,
    *,
    parking_state: ParkingStateService | None = None,
    settings: Settings | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> ParkingReservation:
    return await ReservationService(session, parking_state, settings).create_reservation(
        user_id,
        vehicle_id,
        slot_id,
        expected_version=expected_version,
        now=now,
    )


async def get_active_reservation(
    session: AsyncSession,
    user_id: str,
    *,
    parking_state: ParkingStateService | None = None,
    now: datetime | None = None,
) -> ParkingReservation | None:
    return await ReservationService(session, parking_state).get_active_reservation(
        user_id,
        now=now,
    )


async def get_reservation(
    session: AsyncSession,
    reservation_id: str,
) -> ParkingReservation:
    return await ReservationService(session).get_reservation(reservation_id)


async def cancel_reservation(
    session: AsyncSession,
    reservation_id: str,
    *,
    user_id: str,
    parking_state: ParkingStateService | None = None,
    now: datetime | None = None,
) -> ParkingReservation:
    return await ReservationService(session, parking_state).cancel_reservation(
        reservation_id,
        user_id=user_id,
        now=now,
    )


async def expire_reservation_if_needed(
    session: AsyncSession,
    reservation: ParkingReservation | str,
    *,
    parking_state: ParkingStateService | None = None,
    now: datetime | None = None,
) -> bool:
    return await ReservationService(session, parking_state).expire_reservation_if_needed(
        reservation,
        now=now,
    )


__all__ = [
    "ReservationService",
    "cancel_reservation",
    "create_reservation",
    "expire_reservation_if_needed",
    "get_active_reservation",
    "get_reservation",
]
