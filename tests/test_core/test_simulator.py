from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import get_settings
from src.core.db_models import Base, ParkingEvent, ParkingReservation, ParkingSlot, Vehicle
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.seed import seed_if_missing
from src.core.simulator import SIMULATOR_ACTOR_ID, SimulatorService
from src.models.schemas import ActorType, ErrorCode, ParkingEventType, SlotStatus


@dataclass(slots=True)
class SimulatorDatabase:
    engine: AsyncEngine
    factory: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def simulator_db() -> AsyncGenerator[SimulatorDatabase, None]:
    database_url = get_settings().database_url
    schema_name = f"test_simulator_{uuid4().hex}"
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(CreateSchema(schema_name))

    engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as seed_session:
        await seed_if_missing(seed_session)

    try:
        yield SimulatorDatabase(engine=engine, factory=factory)
    finally:
        await engine.dispose()
        async with admin_engine.connect() as admin_connection:
            await admin_connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


async def _service(
    simulator_db: SimulatorDatabase,
) -> tuple[AsyncSession, SimulatorService, ParkingStateService]:
    session = simulator_db.factory()
    parking_state = ParkingStateService(session)
    return session, SimulatorService(session, parking_state), parking_state


@pytest.mark.asyncio
async def test_simulator_uses_state_service(simulator_db: SimulatorDatabase):
    session = simulator_db.factory()
    real_state = ParkingStateService(session)
    state_spy = AsyncMock(wraps=real_state)
    simulator = SimulatorService(session, state_spy)
    try:
        await simulator.manual_park("F1-A01", "SIM-CAR-01")
        await simulator.manual_leave("F1-A01", "SIM-CAR-01")
    finally:
        await session.close()

    state_spy.occupy_slot.assert_awaited_once_with(
        "F1-A01",
        actor_type=ActorType.SIMULATOR,
        actor_id=SIMULATOR_ACTOR_ID,
        vehicle_id="SIM-CAR-01",
    )
    state_spy.release_slot.assert_awaited_once_with(
        "F1-A01",
        actor_type=ActorType.SIMULATOR,
        actor_id=SIMULATOR_ACTOR_ID,
        vehicle_id="SIM-CAR-01",
    )


@pytest.mark.asyncio
async def test_ensure_simulated_vehicle_rejects_non_simulator_id(
    simulator_db: SimulatorDatabase,
):
    session, simulator, _ = await _service(simulator_db)
    try:
        with pytest.raises(ParkingStateError) as error:
            await simulator.ensure_simulated_vehicle("VEHICLE-001")
        await session.rollback()
        vehicle = await session.get(Vehicle, "VEHICLE-001")
    finally:
        await session.close()

    assert error.value.code is ErrorCode.INVALID_TRANSITION
    assert vehicle is not None and vehicle.user_id == "USER-001"


@pytest.mark.asyncio
async def test_manual_park_available_slot(simulator_db: SimulatorDatabase):
    session, simulator, _ = await _service(simulator_db)
    try:
        await simulator.manual_park("F1-A02", "SIM-CAR-02")
        slot = await session.get(ParkingSlot, "F1-A02")
        event = await session.scalar(
            select(ParkingEvent).where(ParkingEvent.slot_id == "F1-A02")
        )
        vehicle = await session.get(Vehicle, "SIM-CAR-02")
    finally:
        await session.close()

    assert slot is not None
    assert slot.status is SlotStatus.OCCUPIED
    assert slot.occupied_by_vehicle_id == "SIM-CAR-02"
    assert slot.version == 1
    assert vehicle is not None and vehicle.user_id == SIMULATOR_ACTOR_ID
    assert event is not None
    assert event.event_type is ParkingEventType.VEHICLE_PARKED
    assert event.actor_type is ActorType.SIMULATOR


@pytest.mark.asyncio
async def test_manual_leave_occupied_slot(simulator_db: SimulatorDatabase):
    session, simulator, _ = await _service(simulator_db)
    try:
        await simulator.manual_park("F1-A03", "SIM-CAR-03")
        await simulator.manual_leave("F1-A03", "SIM-CAR-03")
        slot = await session.get(ParkingSlot, "F1-A03")
        events = list(
            await session.scalars(
                select(ParkingEvent)
                .where(ParkingEvent.slot_id == "F1-A03")
                .order_by(ParkingEvent.created_at)
            )
        )
    finally:
        await session.close()

    assert slot is not None
    assert slot.status is SlotStatus.AVAILABLE
    assert slot.occupied_by_vehicle_id is None
    assert slot.version == 2
    assert [event.event_type for event in events] == [
        ParkingEventType.VEHICLE_PARKED,
        ParkingEventType.VEHICLE_LEFT_SLOT,
    ]


@pytest.mark.asyncio
async def test_simulator_cannot_take_reserved_slot(simulator_db: SimulatorDatabase):
    session, simulator, parking_state = await _service(simulator_db)
    try:
        async with session.begin():
            await parking_state.reserve_slot(
                "F1-C01",
                "RESERVATION-001",
                user_id="USER-001",
                vehicle_id="VEHICLE-001",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        with pytest.raises(ParkingStateError, match="Simulator cannot"):
            await simulator.manual_park("F1-C01", "SIM-CAR-04")
        await session.rollback()
        slot = await session.get(ParkingSlot, "F1-C01")
        reservation = await session.get(ParkingReservation, "RESERVATION-001")
    finally:
        await session.close()

    assert slot is not None and slot.status is SlotStatus.RESERVED
    assert slot.version == 1
    assert reservation is not None


@pytest.mark.asyncio
async def test_cannot_park_occupied_slot(simulator_db: SimulatorDatabase):
    session, simulator, _ = await _service(simulator_db)
    try:
        await simulator.manual_park("F1-B01", "SIM-CAR-05")
        with pytest.raises(ParkingStateError) as error:
            await simulator.manual_park("F1-B01", "SIM-CAR-06")
        await session.rollback()
        slot = await session.get(ParkingSlot, "F1-B01")
    finally:
        await session.close()

    assert error.value.code is ErrorCode.INVALID_TRANSITION
    assert slot is not None
    assert slot.status is SlotStatus.OCCUPIED
    assert slot.occupied_by_vehicle_id == "SIM-CAR-05"
    assert slot.version == 1


@pytest.mark.asyncio
async def test_cannot_leave_available_slot(simulator_db: SimulatorDatabase):
    session, simulator, _ = await _service(simulator_db)
    try:
        with pytest.raises(ParkingStateError) as error:
            await simulator.manual_leave("F1-B02", "SIM-CAR-07")
        await session.rollback()
        slot = await session.get(ParkingSlot, "F1-B02")
        vehicle = await session.get(Vehicle, "SIM-CAR-07")
    finally:
        await session.close()

    assert error.value.code is ErrorCode.INVALID_TRANSITION
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert slot.version == 0
    assert vehicle is None


@pytest.mark.asyncio
async def test_wrong_vehicle_cannot_leave(simulator_db: SimulatorDatabase):
    session, simulator, _ = await _service(simulator_db)
    try:
        await simulator.manual_park("F1-B03", "SIM-CAR-08")
        with pytest.raises(ParkingStateError, match="occupying vehicle"):
            await simulator.manual_leave("F1-B03", "SIM-CAR-09")
        await session.rollback()
        slot = await session.get(ParkingSlot, "F1-B03")
    finally:
        await session.close()

    assert slot is not None
    assert slot.status is SlotStatus.OCCUPIED
    assert slot.occupied_by_vehicle_id == "SIM-CAR-08"
    assert slot.version == 1


@pytest.mark.asyncio
async def test_failed_transition_rolls_back(simulator_db: SimulatorDatabase):
    session = simulator_db.factory()
    real_state = ParkingStateService(session)

    class FailingStateService:
        async def occupy_slot(self, *args: object, **kwargs: object) -> object:
            await real_state.occupy_slot(*args, **kwargs)
            raise RuntimeError("force rollback")

    simulator = SimulatorService(session, FailingStateService())  # type: ignore[arg-type]
    try:
        with pytest.raises(RuntimeError, match="force rollback"):
            await simulator.manual_park("F1-D10", "SIM-CAR-10")
        await session.rollback()
        slot = await session.get(ParkingSlot, "F1-D10")
        vehicle = await session.get(Vehicle, "SIM-CAR-10")
        event_count = await session.scalar(
            select(func.count())
            .select_from(ParkingEvent)
            .where(ParkingEvent.slot_id == "F1-D10")
        )
    finally:
        await session.close()

    assert slot is not None
    assert slot.status is SlotStatus.AVAILABLE
    assert slot.occupied_by_vehicle_id is None
    assert slot.version == 0
    assert vehicle is None
    assert event_count == 0
