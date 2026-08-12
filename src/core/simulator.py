"""Transactional manual parking operations for simulated vehicles."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import ParkingSlot, ParkingUser, Vehicle
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.models.schemas import ActorType, ErrorCode

SIMULATOR_ACTOR_ID = "SIMULATOR-001"
SIMULATOR_DISPLAY_NAME = "Parking Simulator"
SIMULATED_VEHICLE_ID_PATTERN = re.compile(r"^SIM-CAR-[0-9]{2,}$")


class SimulatorService:
    """Create simulated vehicles and delegate slot transitions to Parking State."""

    def __init__(
        self,
        session: AsyncSession,
        state_service: ParkingStateService,
    ) -> None:
        self.session = session
        self.state_service = state_service

    async def ensure_simulated_vehicle(self, vehicle_id: str) -> Vehicle:
        """Return a simulator-owned vehicle, creating it atomically when absent."""
        async with self._mutation_transaction():
            return await self._ensure_simulated_vehicle(vehicle_id)

    async def manual_park(self, slot_id: str, vehicle_id: str) -> ParkingSlot:
        """Park a simulated vehicle through the Parking State source of truth."""
        async with self._mutation_transaction():
            vehicle = await self._ensure_simulated_vehicle(vehicle_id)
            return await self.state_service.occupy_slot(
                slot_id,
                actor_type=ActorType.SIMULATOR,
                actor_id=SIMULATOR_ACTOR_ID,
                vehicle_id=vehicle.id,
            )

    async def manual_leave(self, slot_id: str, vehicle_id: str) -> ParkingSlot:
        """Release a simulated vehicle through the Parking State source of truth."""
        async with self._mutation_transaction():
            vehicle = await self._ensure_simulated_vehicle(vehicle_id)
            return await self.state_service.release_slot(
                slot_id,
                actor_type=ActorType.SIMULATOR,
                actor_id=SIMULATOR_ACTOR_ID,
                vehicle_id=vehicle.id,
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
        transaction = (
            self.session.begin_nested()
            if self.session.in_transaction()
            else self.session.begin()
        )
        async with transaction:
            yield

    @staticmethod
    def _validate_simulated_vehicle_id(vehicle_id: str) -> None:
        if SIMULATED_VEHICLE_ID_PATTERN.fullmatch(vehicle_id) is None:
            SimulatorService._raise_invalid(
                "Simulated vehicle ID must match SIM-CAR-<number>",
                vehicle_id,
            )

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


__all__ = [
    "SIMULATED_VEHICLE_ID_PATTERN",
    "SIMULATOR_ACTOR_ID",
    "SimulatorService",
    "ensure_simulated_vehicle",
    "manual_leave",
    "manual_park",
]
