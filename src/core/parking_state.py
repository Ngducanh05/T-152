"""Transactional source of truth for ParkSmart parking-slot state."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import (
    ParkingEvent,
    ParkingReservation,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.models.schemas import (
    ActorType,
    ErrorCode,
    ParkingEventType,
    ReservationStatus,
    SlotStatus,
)


class ParkingStateError(Exception):
    """Core domain error with a stable API-independent error code."""

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
class ParkingStatus:
    total: int
    available: int
    reserved: int
    occupied: int
    by_zone: dict[str, dict[SlotStatus, int]]


class ParkingStateService:
    """Apply slot transitions inside the caller's AsyncSession transaction.

    Mutation methods issue ``flush`` but never ``commit`` or ``rollback``. This makes each
    method usable alone inside ``session.begin()`` and composable with Phase 4 reservation
    and parking-session work in the same transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_slot(self, slot_id: str) -> ParkingSlot:
        slot = await self.session.get(ParkingSlot, slot_id)
        if slot is None:
            raise ParkingStateError(
                ErrorCode.SLOT_NOT_FOUND,
                f"Parking slot {slot_id} was not found",
                details={"slot_id": slot_id},
            )
        return slot

    async def list_slots(
        self,
        *,
        zone_id: str | None = None,
        status: SlotStatus | None = None,
        has_charger: bool | None = None,
        is_accessible: bool | None = None,
    ) -> list[ParkingSlot]:
        statement: Select[tuple[ParkingSlot]] = select(ParkingSlot)
        if zone_id is not None:
            statement = statement.where(ParkingSlot.zone_id == zone_id)
        if status is not None:
            statement = statement.where(ParkingSlot.status == status)
        if has_charger is not None:
            statement = statement.where(ParkingSlot.has_charger.is_(has_charger))
        if is_accessible is not None:
            statement = statement.where(ParkingSlot.is_accessible.is_(is_accessible))
        return list(await self.session.scalars(statement.order_by(ParkingSlot.id)))

    async def list_available_slots(
        self,
        *,
        zone_id: str | None = None,
        has_charger: bool | None = None,
        is_accessible: bool | None = None,
    ) -> list[ParkingSlot]:
        return await self.list_slots(
            zone_id=zone_id,
            status=SlotStatus.AVAILABLE,
            has_charger=has_charger,
            is_accessible=is_accessible,
        )

    async def get_parking_status(self) -> ParkingStatus:
        slots = await self.list_slots()
        by_zone: dict[str, dict[SlotStatus, int]] = {}
        for slot in slots:
            zone_counts = by_zone.setdefault(
                slot.zone_id,
                {state: 0 for state in SlotStatus},
            )
            zone_counts[slot.status] += 1
        counts = {state: sum(slot.status is state for slot in slots) for state in SlotStatus}
        return ParkingStatus(
            total=len(slots),
            available=counts[SlotStatus.AVAILABLE],
            reserved=counts[SlotStatus.RESERVED],
            occupied=counts[SlotStatus.OCCUPIED],
            by_zone=by_zone,
        )

    async def reserve_slot(
        self,
        slot_id: str,
        reservation_id: str,
        *,
        user_id: str,
        vehicle_id: str,
        expires_at: datetime,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> ParkingSlot:
        current_time = _utc_now(now)
        _require_aware_utc(expires_at, "expires_at")
        if expires_at <= current_time:
            self._raise_invalid("Reservation expiry must be in the future", slot_id)

        slot = await self._lock_slot(slot_id)
        self._check_expected_version(slot, expected_version)
        if slot.status is SlotStatus.RESERVED:
            active_owner = await self.session.scalar(
                select(ParkingReservation)
                .where(
                    ParkingReservation.slot_id == slot_id,
                    ParkingReservation.status == ReservationStatus.ACTIVE,
                )
                .with_for_update()
            )
            if active_owner is not None and active_owner.expires_at <= current_time:
                active_owner.status = ReservationStatus.EXPIRED
                self._transition_slot(
                    slot,
                    new_status=SlotStatus.AVAILABLE,
                    event_type=ParkingEventType.RESERVATION_EXPIRED,
                    actor_type=ActorType.SYSTEM,
                    actor_id=None,
                    event_metadata={"reservation_id": active_owner.id},
                    now=current_time,
                )
        if slot.status is not SlotStatus.AVAILABLE:
            raise ParkingStateError(
                ErrorCode.SLOT_NOT_AVAILABLE,
                f"Parking slot {slot_id} is not available",
                details={"slot_id": slot_id, "status": slot.status.value},
            )

        user = await self.session.get(ParkingUser, user_id)
        vehicle = await self.session.get(Vehicle, vehicle_id)
        if user is None or vehicle is None or vehicle.user_id != user_id:
            self._raise_invalid("Reservation owner or vehicle is invalid", slot_id)

        existing_reservation = await self.session.get(ParkingReservation, reservation_id)
        if existing_reservation is not None:
            self._raise_invalid(f"Reservation {reservation_id} already exists", slot_id)

        active_reservation = await self.session.scalar(
            select(ParkingReservation).where(
                ParkingReservation.status == ReservationStatus.ACTIVE,
                or_(
                    ParkingReservation.user_id == user_id,
                    ParkingReservation.vehicle_id == vehicle_id,
                ),
            )
        )
        if active_reservation is not None:
            raise ParkingStateError(
                ErrorCode.ACTIVE_RESERVATION_EXISTS,
                f"User or vehicle already has active reservation {active_reservation.id}",
                details={"reservation_id": active_reservation.id},
            )

        reservation = ParkingReservation(
            id=reservation_id,
            user_id=user_id,
            vehicle_id=vehicle_id,
            slot_id=slot_id,
            status=ReservationStatus.ACTIVE,
            expires_at=expires_at,
            created_at=current_time,
        )
        self.session.add(reservation)
        self._transition_slot(
            slot,
            new_status=SlotStatus.RESERVED,
            event_type=ParkingEventType.SLOT_RESERVED,
            actor_type=ActorType.USER,
            actor_id=user_id,
            event_metadata={"reservation_id": reservation_id, "vehicle_id": vehicle_id},
            now=current_time,
        )
        await self.session.flush()
        return slot

    async def occupy_slot(
        self,
        slot_id: str,
        *,
        actor_type: ActorType,
        actor_id: str | None,
        vehicle_id: str,
        reservation_id: str | None = None,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> ParkingSlot:
        current_time = _utc_now(now)
        slot = await self._lock_slot(slot_id)
        self._check_expected_version(slot, expected_version)
        vehicle = await self.session.get(Vehicle, vehicle_id)
        if vehicle is None:
            self._raise_invalid(f"Vehicle {vehicle_id} was not found", slot_id)

        if slot.status is SlotStatus.RESERVED:
            if actor_type is ActorType.SIMULATOR:
                self._raise_invalid("Simulator cannot occupy a reserved slot", slot_id)
            if reservation_id is None:
                self._raise_invalid("Reserved slot requires its reservation reference", slot_id)
            reservation = await self._lock_reservation(reservation_id)
            self._validate_active_reservation(
                reservation,
                slot_id=slot_id,
                vehicle_id=vehicle_id,
                actor_id=actor_id,
                now=current_time,
            )
            reservation.status = ReservationStatus.CONFIRMED
        elif slot.status is not SlotStatus.AVAILABLE:
            self._raise_invalid(
                f"Cannot occupy slot from {slot.status.value}",
                slot_id,
            )

        slot.occupied_by_vehicle_id = vehicle_id
        self._transition_slot(
            slot,
            new_status=SlotStatus.OCCUPIED,
            event_type=ParkingEventType.VEHICLE_PARKED,
            actor_type=actor_type,
            actor_id=actor_id,
            event_metadata={"reservation_id": reservation_id, "vehicle_id": vehicle_id},
            now=current_time,
        )
        await self.session.flush()
        return slot

    async def release_slot(
        self,
        slot_id: str,
        *,
        actor_type: ActorType,
        actor_id: str | None,
        vehicle_id: str,
        expected_version: int | None = None,
    ) -> ParkingSlot:
        slot = await self._lock_slot(slot_id)
        self._check_expected_version(slot, expected_version)
        if slot.status is not SlotStatus.OCCUPIED:
            self._raise_invalid(f"Cannot release slot from {slot.status.value}", slot_id)
        if slot.occupied_by_vehicle_id != vehicle_id:
            self._raise_invalid("Only the occupying vehicle can release this slot", slot_id)

        occupying_vehicle = await self.session.get(Vehicle, vehicle_id)
        if occupying_vehicle is None:
            self._raise_invalid(f"Vehicle {vehicle_id} was not found", slot_id)
        if actor_type is ActorType.USER and actor_id != occupying_vehicle.user_id:
            self._raise_invalid("User does not own the occupying vehicle", slot_id)

        slot.occupied_by_vehicle_id = None
        self._transition_slot(
            slot,
            new_status=SlotStatus.AVAILABLE,
            event_type=ParkingEventType.VEHICLE_LEFT_SLOT,
            actor_type=actor_type,
            actor_id=actor_id,
            event_metadata={"vehicle_id": vehicle_id},
        )
        await self.session.flush()
        return slot

    async def expire_reservation(
        self,
        slot_id: str,
        reservation_id: str,
        *,
        now: datetime | None = None,
        expected_version: int | None = None,
    ) -> ParkingSlot:
        current_time = _utc_now(now)
        slot = await self._lock_slot(slot_id)
        self._check_expected_version(slot, expected_version)
        if slot.status is not SlotStatus.RESERVED:
            self._raise_invalid(f"Cannot expire reservation from {slot.status.value}", slot_id)

        reservation = await self._lock_reservation(reservation_id)
        if reservation.slot_id != slot_id or reservation.status is not ReservationStatus.ACTIVE:
            self._raise_invalid("Reservation does not own this reserved slot", slot_id)
        if reservation.expires_at > current_time:
            self._raise_invalid("Reservation has not expired", slot_id)

        reservation.status = ReservationStatus.EXPIRED
        self._transition_slot(
            slot,
            new_status=SlotStatus.AVAILABLE,
            event_type=ParkingEventType.RESERVATION_EXPIRED,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            event_metadata={"reservation_id": reservation_id},
            now=current_time,
        )
        await self.session.flush()
        return slot

    async def cancel_reservation(
        self,
        slot_id: str,
        reservation_id: str,
        *,
        user_id: str,
        expected_version: int | None = None,
        now: datetime | None = None,
    ) -> ParkingSlot:
        current_time = _utc_now(now)
        slot = await self._lock_slot(slot_id)
        self._check_expected_version(slot, expected_version)
        if slot.status is not SlotStatus.RESERVED:
            self._raise_invalid(f"Cannot cancel reservation from {slot.status.value}", slot_id)

        reservation = await self._lock_reservation(reservation_id)
        if reservation.user_id != user_id:
            self._raise_invalid("User does not own this reservation", slot_id)
        if reservation.slot_id != slot_id:
            self._raise_invalid("Reservation does not own this reserved slot", slot_id)
        if reservation.status is not ReservationStatus.ACTIVE:
            self._raise_invalid("Only an active reservation can be cancelled", slot_id)
        if reservation.expires_at <= current_time:
            reservation.status = ReservationStatus.EXPIRED
            self._transition_slot(
                slot,
                new_status=SlotStatus.AVAILABLE,
                event_type=ParkingEventType.RESERVATION_EXPIRED,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_metadata={"reservation_id": reservation_id},
                now=current_time,
            )
            await self.session.flush()
            return slot

        reservation.status = ReservationStatus.CANCELLED
        self._transition_slot(
            slot,
            new_status=SlotStatus.AVAILABLE,
            event_type=ParkingEventType.RESERVATION_CANCELLED,
            actor_type=ActorType.USER,
            actor_id=user_id,
            event_metadata={
                "reservation_id": reservation_id,
                "vehicle_id": reservation.vehicle_id,
            },
            now=current_time,
        )
        await self.session.flush()
        return slot

    async def _lock_slot(self, slot_id: str) -> ParkingSlot:
        slot = await self.session.scalar(
            select(ParkingSlot).where(ParkingSlot.id == slot_id).with_for_update()
        )
        if slot is None:
            raise ParkingStateError(
                ErrorCode.SLOT_NOT_FOUND,
                f"Parking slot {slot_id} was not found",
                details={"slot_id": slot_id},
            )
        return slot

    async def _lock_reservation(self, reservation_id: str) -> ParkingReservation:
        reservation = await self.session.scalar(
            select(ParkingReservation)
            .where(ParkingReservation.id == reservation_id)
            .with_for_update()
        )
        if reservation is None:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                f"Reservation {reservation_id} was not found",
                details={"reservation_id": reservation_id},
            )
        return reservation

    def _validate_active_reservation(
        self,
        reservation: ParkingReservation,
        *,
        slot_id: str,
        vehicle_id: str,
        actor_id: str | None,
        now: datetime,
    ) -> None:
        if reservation.status is not ReservationStatus.ACTIVE:
            self._raise_invalid("Reservation is not active", slot_id)
        if reservation.slot_id != slot_id or reservation.vehicle_id != vehicle_id:
            self._raise_invalid("Reservation does not own this slot or vehicle", slot_id)
        if actor_id not in {reservation.user_id, reservation.vehicle_id}:
            self._raise_invalid("Actor does not own this reservation", slot_id)
        if reservation.expires_at <= now:
            self._raise_invalid("Reservation has expired", slot_id)

    def _check_expected_version(
        self,
        slot: ParkingSlot,
        expected_version: int | None,
    ) -> None:
        if expected_version is not None and slot.version != expected_version:
            raise ParkingStateError(
                ErrorCode.SLOT_NOT_AVAILABLE,
                f"Parking slot {slot.id} version changed",
                details={"expected_version": expected_version, "actual_version": slot.version},
            )

    def _transition_slot(
        self,
        slot: ParkingSlot,
        *,
        new_status: SlotStatus,
        event_type: ParkingEventType,
        actor_type: ActorType,
        actor_id: str | None,
        event_metadata: dict[str, Any],
        now: datetime | None = None,
    ) -> None:
        old_status = slot.status
        slot.status = new_status
        slot.version += 1
        self.session.add(
            ParkingEvent(
                id=f"EVENT-{uuid4()}",
                event_type=event_type,
                slot_id=slot.id,
                actor_type=actor_type,
                actor_id=actor_id,
                old_status=old_status,
                new_status=new_status,
                created_at=now or datetime.now(UTC),
                event_metadata=event_metadata,
            )
        )

    def _raise_invalid(self, message: str, slot_id: str) -> None:
        raise ParkingStateError(
            ErrorCode.INVALID_TRANSITION,
            message,
            details={"slot_id": slot_id},
        )


def _require_aware_utc(value: datetime, field_name: str) -> None:
    if value.utcoffset() is None or value.utcoffset() != datetime.now(UTC).utcoffset():
        raise ParkingStateError(
            ErrorCode.INVALID_TRANSITION,
            f"{field_name} must be a timezone-aware UTC datetime",
        )


def _utc_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    _require_aware_utc(value, "now")
    return value


async def get_slot(session: AsyncSession, slot_id: str) -> ParkingSlot:
    return await ParkingStateService(session).get_slot(slot_id)


async def list_slots(
    session: AsyncSession,
    *,
    zone_id: str | None = None,
    status: SlotStatus | None = None,
    has_charger: bool | None = None,
    is_accessible: bool | None = None,
) -> list[ParkingSlot]:
    return await ParkingStateService(session).list_slots(
        zone_id=zone_id,
        status=status,
        has_charger=has_charger,
        is_accessible=is_accessible,
    )


async def list_available_slots(
    session: AsyncSession,
    *,
    zone_id: str | None = None,
    has_charger: bool | None = None,
    is_accessible: bool | None = None,
) -> list[ParkingSlot]:
    return await ParkingStateService(session).list_available_slots(
        zone_id=zone_id,
        has_charger=has_charger,
        is_accessible=is_accessible,
    )


async def get_parking_status(session: AsyncSession) -> ParkingStatus:
    return await ParkingStateService(session).get_parking_status()


async def reserve_slot(
    session: AsyncSession,
    slot_id: str,
    reservation_id: str,
    *,
    user_id: str,
    vehicle_id: str,
    expires_at: datetime,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> ParkingSlot:
    return await ParkingStateService(session).reserve_slot(
        slot_id,
        reservation_id,
        user_id=user_id,
        vehicle_id=vehicle_id,
        expires_at=expires_at,
        expected_version=expected_version,
        now=now,
    )


async def occupy_slot(
    session: AsyncSession,
    slot_id: str,
    *,
    actor_type: ActorType,
    actor_id: str | None,
    vehicle_id: str,
    reservation_id: str | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> ParkingSlot:
    return await ParkingStateService(session).occupy_slot(
        slot_id,
        actor_type=actor_type,
        actor_id=actor_id,
        vehicle_id=vehicle_id,
        reservation_id=reservation_id,
        expected_version=expected_version,
        now=now,
    )


async def release_slot(
    session: AsyncSession,
    slot_id: str,
    *,
    actor_type: ActorType,
    actor_id: str | None,
    vehicle_id: str,
    expected_version: int | None = None,
) -> ParkingSlot:
    return await ParkingStateService(session).release_slot(
        slot_id,
        actor_type=actor_type,
        actor_id=actor_id,
        vehicle_id=vehicle_id,
        expected_version=expected_version,
    )


async def expire_reservation(
    session: AsyncSession,
    slot_id: str,
    reservation_id: str,
    *,
    now: datetime | None = None,
    expected_version: int | None = None,
) -> ParkingSlot:
    return await ParkingStateService(session).expire_reservation(
        slot_id,
        reservation_id,
        now=now,
        expected_version=expected_version,
    )


async def cancel_reservation(
    session: AsyncSession,
    slot_id: str,
    reservation_id: str,
    *,
    user_id: str,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> ParkingSlot:
    return await ParkingStateService(session).cancel_reservation(
        slot_id,
        reservation_id,
        user_id=user_id,
        expected_version=expected_version,
        now=now,
    )


__all__ = [
    "cancel_reservation",
    "ParkingStateError",
    "ParkingStateService",
    "ParkingStatus",
    "expire_reservation",
    "get_parking_status",
    "get_slot",
    "list_available_slots",
    "list_slots",
    "occupy_slot",
    "release_slot",
    "reserve_slot",
]
