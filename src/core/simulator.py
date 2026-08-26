"""Transactional manual parking operations for simulated vehicles."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.db_models import (
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.models.schemas import (
    ActorType,
    ErrorCode,
    ParkingSessionStatus,
    ReservationStatus,
    SlotStatus,
)

SIMULATOR_ACTOR_ID = "SIMULATOR-001"
SIMULATOR_DISPLAY_NAME = "Parking Simulator"
SIMULATED_VEHICLE_ID_PATTERN = re.compile(r"^SIM-CAR-[0-9]{2,}$")
BASELINE_SLOT_ID = "F1-B03"
BASELINE_VEHICLE_ID = "SIM-CAR-02"


class SimulatorAction(StrEnum):
    RESET = "RESET"
    PARK = "PARK"
    LEAVE = "LEAVE"


@dataclass(frozen=True, slots=True)
class SimulatorStep:
    sequence: int
    action: SimulatorAction
    slot_id: str | None
    vehicle_id: str | None
    resulting_status: SlotStatus | None


class SimulatorService:
    """Create simulated vehicles and delegate slot transitions to Parking State."""

    def __init__(
        self,
        session: AsyncSession,
        state_service: ParkingStateService,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.state_service = state_service
        self.settings = settings or get_settings()

    async def ensure_simulated_vehicle(self, vehicle_id: str) -> Vehicle:
        """Return a simulator-owned vehicle, creating it atomically when absent."""
        async with self._mutation_transaction():
            self._require_simulator_demo_mode()
            return await self._ensure_simulated_vehicle(vehicle_id)

    async def manual_park(self, slot_id: str, vehicle_id: str) -> ParkingSlot:
        """Park a simulated vehicle through the Parking State source of truth."""
        async with self._mutation_transaction():
            self._require_simulator_demo_mode()
            return await self._manual_park(slot_id, vehicle_id)

    async def manual_leave(self, slot_id: str, vehicle_id: str) -> ParkingSlot:
        """Release a simulated vehicle through the Parking State source of truth."""
        async with self._mutation_transaction():
            self._require_simulator_demo_mode()
            return await self._manual_leave(slot_id, vehicle_id)

    async def reset_demo(self) -> list[SimulatorStep]:
        """Restore the deterministic demo baseline without touching protected user state."""
        async with self._mutation_transaction():
            self._require_simulator_demo_mode()
            await self._reset_demo()
            return [
                SimulatorStep(
                    sequence=1,
                    action=SimulatorAction.RESET,
                    slot_id=BASELINE_SLOT_ID,
                    vehicle_id=BASELINE_VEHICLE_ID,
                    resulting_status=SlotStatus.OCCUPIED,
                )
            ]

    async def run_fixed_scenario(self) -> list[SimulatorStep]:
        """Run the fixed four-step demo atomically and return its structured steps."""
        async with self._mutation_transaction():
            self._require_simulator_demo_mode()
            await self._reset_demo()
            steps = [
                SimulatorStep(
                    sequence=1,
                    action=SimulatorAction.RESET,
                    slot_id=BASELINE_SLOT_ID,
                    vehicle_id=BASELINE_VEHICLE_ID,
                    resulting_status=SlotStatus.OCCUPIED,
                )
            ]
            parked_a04 = await self._manual_park("F1-A04", "SIM-CAR-01")
            steps.append(self._transition_step(2, SimulatorAction.PARK, parked_a04, "SIM-CAR-01"))
            released_b03 = await self._manual_leave(BASELINE_SLOT_ID, BASELINE_VEHICLE_ID)
            steps.append(
                self._transition_step(
                    3,
                    SimulatorAction.LEAVE,
                    released_b03,
                    BASELINE_VEHICLE_ID,
                )
            )
            parked_d07 = await self._manual_park("F1-D07", "SIM-CAR-03")
            steps.append(self._transition_step(4, SimulatorAction.PARK, parked_d07, "SIM-CAR-03"))
            return steps

    async def _manual_park(self, slot_id: str, vehicle_id: str) -> ParkingSlot:
        vehicle = await self._ensure_simulated_vehicle(vehicle_id)
        return await self.state_service.occupy_slot(
            slot_id,
            actor_type=ActorType.SIMULATOR,
            actor_id=SIMULATOR_ACTOR_ID,
            vehicle_id=vehicle.id,
        )

    async def _manual_leave(self, slot_id: str, vehicle_id: str) -> ParkingSlot:
        vehicle = await self._ensure_simulated_vehicle(vehicle_id)
        return await self.state_service.release_slot(
            slot_id,
            actor_type=ActorType.SIMULATOR,
            actor_id=SIMULATOR_ACTOR_ID,
            vehicle_id=vehicle.id,
        )

    async def _reset_demo(self) -> None:
        slots = list(await self.session.scalars(select(ParkingSlot).order_by(ParkingSlot.id).with_for_update()))
        await self._refuse_protected_state(slots)

        baseline_is_ready = any(
            slot.id == BASELINE_SLOT_ID
            and slot.status is SlotStatus.OCCUPIED
            and slot.occupied_by_vehicle_id == BASELINE_VEHICLE_ID
            for slot in slots
        )
        for slot in slots:
            if slot.status is not SlotStatus.OCCUPIED:
                continue
            if baseline_is_ready and slot.id == BASELINE_SLOT_ID:
                continue
            if slot.occupied_by_vehicle_id is None:
                await self.state_service.clear_user_observed_occupancy(
                    slot.id,
                    actor_id=SIMULATOR_ACTOR_ID,
                )
            else:
                await self._manual_leave(slot.id, slot.occupied_by_vehicle_id)

        if not baseline_is_ready:
            await self._manual_park(BASELINE_SLOT_ID, BASELINE_VEHICLE_ID)

    async def _refuse_protected_state(self, slots: list[ParkingSlot]) -> None:
        active_reservation = await self.session.scalar(
            select(ParkingReservation).where(ParkingReservation.status == ReservationStatus.ACTIVE).with_for_update()
        )
        if active_reservation is not None:
            self._raise_protected(
                "Demo reset cannot run while an active reservation exists",
                reservation_id=active_reservation.id,
            )

        active_session = await self.session.scalar(
            select(ParkingSession).where(ParkingSession.status == ParkingSessionStatus.ACTIVE).with_for_update()
        )
        if active_session is not None:
            self._raise_protected(
                "Demo reset cannot run while an active parking session exists",
                session_id=active_session.id,
            )

        reserved_slot = next(
            (slot for slot in slots if slot.status is SlotStatus.RESERVED),
            None,
        )
        if reserved_slot is not None:
            self._raise_protected(
                "Demo reset cannot change a reserved slot",
                slot_id=reserved_slot.id,
            )

        for slot in slots:
            if slot.status is not SlotStatus.OCCUPIED:
                continue
            vehicle_id = slot.occupied_by_vehicle_id
            if vehicle_id is None and await self.state_service.is_user_observed_occupancy(slot):
                continue
            vehicle = await self.session.get(Vehicle, vehicle_id) if vehicle_id else None
            if (
                vehicle is None
                or vehicle.user_id != SIMULATOR_ACTOR_ID
                or SIMULATED_VEHICLE_ID_PATTERN.fullmatch(vehicle.id) is None
            ):
                self._raise_protected(
                    "Demo reset cannot change a user-owned occupied slot",
                    slot_id=slot.id,
                    vehicle_id=vehicle_id,
                )

    async def _ensure_simulated_vehicle(self, vehicle_id: str) -> Vehicle:
        self._validate_simulated_vehicle_id(vehicle_id)

        simulator_user = await self.session.get(ParkingUser, SIMULATOR_ACTOR_ID)
        if simulator_user is None:
            simulator_user = ParkingUser(
                id=SIMULATOR_ACTOR_ID,
                display_name=SIMULATOR_DISPLAY_NAME,
                current_node_id=None,
            )
            self.session.add(simulator_user)
            await self.session.flush()
        elif simulator_user.display_name != SIMULATOR_DISPLAY_NAME:
            self._raise_invalid("Simulator identity is owned by another user", vehicle_id)

        vehicle = await self.session.get(Vehicle, vehicle_id)
        if vehicle is None:
            vehicle = Vehicle(
                id=vehicle_id,
                user_id=SIMULATOR_ACTOR_ID,
                plate_number=vehicle_id,
                requires_charging=False,
            )
            self.session.add(vehicle)
            await self.session.flush()
        elif vehicle.user_id != SIMULATOR_ACTOR_ID:
            self._raise_invalid("Vehicle is not owned by the simulator", vehicle_id)

        return vehicle

    @asynccontextmanager
    async def _mutation_transaction(self) -> AsyncIterator[None]:
        transaction = self.session.begin_nested() if self.session.in_transaction() else self.session.begin()
        async with transaction:
            yield

    @staticmethod
    def _validate_simulated_vehicle_id(vehicle_id: str) -> None:
        if SIMULATED_VEHICLE_ID_PATTERN.fullmatch(vehicle_id) is None:
            SimulatorService._raise_invalid(
                "Simulated vehicle ID must match SIM-CAR-<number>",
                vehicle_id,
            )

    def _require_simulator_demo_mode(self) -> None:
        if not self.settings.simulator_enabled or not self.settings.demo_mode:
            raise ParkingStateError(
                ErrorCode.INVALID_TRANSITION,
                "Simulator operations require SIMULATOR_ENABLED and DEMO_MODE",
                details={
                    "simulator_enabled": self.settings.simulator_enabled,
                    "demo_mode": self.settings.demo_mode,
                },
            )

    @staticmethod
    def _transition_step(
        sequence: int,
        action: SimulatorAction,
        slot: ParkingSlot,
        vehicle_id: str,
    ) -> SimulatorStep:
        return SimulatorStep(
            sequence=sequence,
            action=action,
            slot_id=slot.id,
            vehicle_id=vehicle_id,
            resulting_status=slot.status,
        )

    @staticmethod
    def _raise_protected(message: str, **details: object) -> None:
        raise ParkingStateError(ErrorCode.INVALID_TRANSITION, message, details=details)

    @staticmethod
    def _raise_invalid(message: str, vehicle_id: str) -> None:
        raise ParkingStateError(
            ErrorCode.INVALID_TRANSITION,
            message,
            details={"vehicle_id": vehicle_id},
        )


async def ensure_simulated_vehicle(
    session: AsyncSession,
    state_service: ParkingStateService,
    vehicle_id: str,
) -> Vehicle:
    return await SimulatorService(session, state_service).ensure_simulated_vehicle(vehicle_id)


async def manual_park(
    session: AsyncSession,
    state_service: ParkingStateService,
    slot_id: str,
    vehicle_id: str,
) -> ParkingSlot:
    return await SimulatorService(session, state_service).manual_park(slot_id, vehicle_id)


async def manual_leave(
    session: AsyncSession,
    state_service: ParkingStateService,
    slot_id: str,
    vehicle_id: str,
) -> ParkingSlot:
    return await SimulatorService(session, state_service).manual_leave(slot_id, vehicle_id)


async def reset_demo(
    session: AsyncSession,
    state_service: ParkingStateService,
) -> list[SimulatorStep]:
    return await SimulatorService(session, state_service).reset_demo()


async def run_fixed_scenario(
    session: AsyncSession,
    state_service: ParkingStateService,
) -> list[SimulatorStep]:
    return await SimulatorService(session, state_service).run_fixed_scenario()


__all__ = [
    "SIMULATED_VEHICLE_ID_PATTERN",
    "SIMULATOR_ACTOR_ID",
    "SimulatorAction",
    "SimulatorService",
    "SimulatorStep",
    "ensure_simulated_vehicle",
    "manual_leave",
    "manual_park",
    "reset_demo",
    "run_fixed_scenario",
]
