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

from src.core.config import Settings, get_settings
from src.core.db_models import (
    Base,
    ParkingEvent,
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    Vehicle,
)
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.seed import seed_if_missing
from src.core.simulator import SIMULATOR_ACTOR_ID, SimulatorAction, SimulatorService
from src.models.schemas import (
    ActorType,
    ErrorCode,
    ParkingEventType,
    ParkingSessionStatus,
    SlotStatus,
)


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


@pytest.mark.asyncio
async def test_reset_is_idempotent(simulator_db: SimulatorDatabase):
    session, simulator, _ = await _service(simulator_db)
    try:
        first_steps = await simulator.reset_demo()
        first_slot = await session.get(ParkingSlot, "F1-B03")
        first_version = first_slot.version if first_slot is not None else None
        first_event_count = await session.scalar(
            select(func.count())
            .select_from(ParkingEvent)
            .where(ParkingEvent.slot_id == "F1-B03")
        )
        await session.rollback()

        second_steps = await simulator.reset_demo()
        second_slot = await session.get(ParkingSlot, "F1-B03")
        second_event_count = await session.scalar(
            select(func.count())
            .select_from(ParkingEvent)
            .where(ParkingEvent.slot_id == "F1-B03")
        )
    finally:
        await session.close()

    assert first_steps == second_steps
    assert first_version == 1
    assert second_slot is not None and second_slot.version == first_version
    assert second_event_count == first_event_count == 1


@pytest.mark.asyncio
async def test_reset_produces_expected_baseline(simulator_db: SimulatorDatabase):
    session, simulator, state_service = await _service(simulator_db)
    try:
        await simulator.manual_park("F1-A04", "SIM-CAR-01")
        await simulator.manual_park("F1-D07", "SIM-CAR-03")
        await state_service.apply_user_slot_observation(
            "F1-A02",
            observed_status=SlotStatus.OCCUPIED,
            user_id="USER-001",
            observer_session_id="SESSION-OBSERVE",
            expected_version=0,
        )
        await simulator.reset_demo()
        status = await state_service.get_parking_status()
        slots = {slot.id: slot for slot in await state_service.list_slots()}
    finally:
        await session.close()

    assert (status.available, status.reserved, status.occupied) == (39, 0, 1)
    assert slots["F1-B03"].status is SlotStatus.OCCUPIED
    assert slots["F1-B03"].occupied_by_vehicle_id == "SIM-CAR-02"
    assert slots["F1-A04"].status is SlotStatus.AVAILABLE
    assert slots["F1-A02"].status is SlotStatus.AVAILABLE
    assert slots["F1-D07"].status is SlotStatus.AVAILABLE
    assert slots["F1-D01"].status is SlotStatus.AVAILABLE
    assert all(
        slot.status is SlotStatus.AVAILABLE
        for slot_id, slot in slots.items()
        if slot_id != "F1-B03"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("protected_kind", ["reservation", "session"])
async def test_reset_refuses_protected_state(
    simulator_db: SimulatorDatabase,
    protected_kind: str,
):
    session, simulator, state_service = await _service(simulator_db)
    try:
        async with session.begin():
            if protected_kind == "reservation":
                await state_service.reserve_slot(
                    "F1-C01",
                    "RESERVATION-001",
                    user_id="USER-001",
                    vehicle_id="VEHICLE-001",
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                )
            else:
                await state_service.occupy_slot(
                    "F1-C01",
                    actor_type=ActorType.USER,
                    actor_id="USER-001",
                    vehicle_id="VEHICLE-001",
                )
                session.add(
                    ParkingSession(
                        id="SESSION-001",
                        user_id="USER-001",
                        vehicle_id="VEHICLE-001",
                        slot_id="F1-C01",
                        status=ParkingSessionStatus.ACTIVE,
                    )
                )

        with pytest.raises(ParkingStateError, match="active"):
            await simulator.reset_demo()
        await session.rollback()
        protected_slot = await session.get(ParkingSlot, "F1-C01")
        baseline_slot = await session.get(ParkingSlot, "F1-B03")
    finally:
        await session.close()

    assert protected_slot is not None
    assert protected_slot.status is (
        SlotStatus.RESERVED if protected_kind == "reservation" else SlotStatus.OCCUPIED
    )
    assert baseline_slot is not None and baseline_slot.status is SlotStatus.AVAILABLE


@pytest.mark.asyncio
async def test_fixed_scenario_is_repeatable(simulator_db: SimulatorDatabase):
    session, simulator, state_service = await _service(simulator_db)
    try:
        first_steps = await simulator.run_fixed_scenario()
        first_state = {
            slot.id: (slot.status, slot.occupied_by_vehicle_id)
            for slot in await state_service.list_slots()
        }
        await session.rollback()

        second_steps = await simulator.run_fixed_scenario()
        second_state = {
            slot.id: (slot.status, slot.occupied_by_vehicle_id)
            for slot in await state_service.list_slots()
        }
    finally:
        await session.close()

    assert first_steps == second_steps
    assert first_state == second_state


@pytest.mark.asyncio
async def test_fixed_scenario_final_state(simulator_db: SimulatorDatabase):
    session, simulator, state_service = await _service(simulator_db)
    try:
        steps = await simulator.run_fixed_scenario()
        status = await state_service.get_parking_status()
        slots = {slot.id: slot for slot in await state_service.list_slots()}
    finally:
        await session.close()

    assert [step.action for step in steps] == [
        SimulatorAction.RESET,
        SimulatorAction.PARK,
        SimulatorAction.LEAVE,
        SimulatorAction.PARK,
    ]
    assert [(step.slot_id, step.vehicle_id) for step in steps] == [
        ("F1-B03", "SIM-CAR-02"),
        ("F1-A04", "SIM-CAR-01"),
        ("F1-B03", "SIM-CAR-02"),
        ("F1-D07", "SIM-CAR-03"),
    ]
    assert (status.available, status.reserved, status.occupied) == (38, 0, 2)
    assert slots["F1-A04"].occupied_by_vehicle_id == "SIM-CAR-01"
    assert slots["F1-B03"].status is SlotStatus.AVAILABLE
    assert slots["F1-D07"].occupied_by_vehicle_id == "SIM-CAR-03"


@pytest.mark.asyncio
async def test_scenario_failure_rolls_back(simulator_db: SimulatorDatabase):
    session = simulator_db.factory()
    real_state = ParkingStateService(session)

    class FailingScenarioStateService:
        async def occupy_slot(self, slot_id: str, **kwargs: object) -> object:
            slot = await real_state.occupy_slot(slot_id, **kwargs)
            if slot_id == "F1-D07":
                raise RuntimeError("force scenario rollback")
            return slot

        async def release_slot(self, slot_id: str, **kwargs: object) -> object:
            return await real_state.release_slot(slot_id, **kwargs)

    simulator = SimulatorService(
        session,
        FailingScenarioStateService(),  # type: ignore[arg-type]
    )
    try:
        with pytest.raises(RuntimeError, match="force scenario rollback"):
            await simulator.run_fixed_scenario()
        await session.rollback()
        slots = list(await session.scalars(select(ParkingSlot)))
        simulated_vehicle_count = await session.scalar(
            select(func.count())
            .select_from(Vehicle)
            .where(Vehicle.id.like("SIM-CAR-%"))
        )
        event_count = await session.scalar(select(func.count()).select_from(ParkingEvent))
    finally:
        await session.close()

    assert all(slot.status is SlotStatus.AVAILABLE for slot in slots)
    assert all(slot.occupied_by_vehicle_id is None for slot in slots)
    assert all(slot.version == 0 for slot in slots)
    assert simulated_vehicle_count == 0
    assert event_count == 0


@pytest.mark.asyncio
async def test_reset_requires_simulator_demo_mode(simulator_db: SimulatorDatabase):
    session = simulator_db.factory()
    disabled_settings = Settings(simulator_enabled=False, demo_mode=True)
    simulator = SimulatorService(
        session,
        ParkingStateService(session),
        settings=disabled_settings,
    )
    try:
        with pytest.raises(ParkingStateError, match="SIMULATOR_ENABLED"):
            await simulator.reset_demo()
        await session.rollback()
        status = await ParkingStateService(session).get_parking_status()
    finally:
        await session.close()

    assert (status.available, status.reserved, status.occupied) == (40, 0, 0)
