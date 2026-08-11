import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from src.core.db_models import (
    Base,
    ParkingEvent,
    ParkingReservation,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.seed import seed_if_missing
from src.models.schemas import (
    ActorType,
    ErrorCode,
    ParkingEventType,
    ReservationStatus,
    SlotStatus,
)


@dataclass(slots=True)
class StateDatabase:
    engine: AsyncEngine
    session: AsyncSession


@pytest_asyncio.fixture
async def state_db() -> AsyncGenerator[StateDatabase, None]:
    database_url = get_settings().database_url
    schema_name = f"test_parking_state_{uuid4().hex}"
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

    connection = await engine.connect()
    outer_transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield StateDatabase(engine=engine, session=session)
    finally:
        await session.close()
        await outer_transaction.rollback()
        await connection.close()
        await engine.dispose()
        async with admin_engine.connect() as admin_connection:
            await admin_connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


def _future(minutes: int = 5) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


async def _reserve(
    service: ParkingStateService,
    slot_id: str,
    reservation_id: str = "RESERVATION-001",
    *,
    user_id: str = "USER-001",
    vehicle_id: str = "VEHICLE-001",
    expires_at: datetime | None = None,
) -> ParkingSlot:
    return await service.reserve_slot(
        slot_id,
        reservation_id,
        user_id=user_id,
        vehicle_id=vehicle_id,
        expires_at=expires_at or _future(),
    )


@pytest.mark.asyncio
async def test_read_interfaces_return_deterministic_current_state(state_db: StateDatabase):
    service = ParkingStateService(state_db.session)

    slot = await service.get_slot("F1-D01")
    all_slots = await service.list_slots()
    ev_slots = await service.list_available_slots(has_charger=True)
    status = await service.get_parking_status()

    assert slot.id == "F1-D01"
    assert [item.id for item in all_slots] == sorted(item.id for item in all_slots)
    assert len(all_slots) == 40
    assert len(ev_slots) == 10
    assert status.total == status.available == 40
    assert status.reserved == status.occupied == 0
    assert all(zone_counts[SlotStatus.AVAILABLE] == 10 for zone_counts in status.by_zone.values())

    with pytest.raises(ParkingStateError) as error:
        await service.get_slot("F1-Z99")
    assert error.value.code is ErrorCode.SLOT_NOT_FOUND


@pytest.mark.asyncio
async def test_reserve_available_slot_increments_version_and_creates_event(
    state_db: StateDatabase,
):
    service = ParkingStateService(state_db.session)
    slot = await _reserve(service, "F1-D01")

    reservation = await state_db.session.get(ParkingReservation, "RESERVATION-001")
    event = await state_db.session.scalar(
        select(ParkingEvent).where(ParkingEvent.slot_id == "F1-D01")
    )
    assert slot.status is SlotStatus.RESERVED
    assert slot.version == 1
    assert reservation is not None
    assert reservation.status is ReservationStatus.ACTIVE
    assert event is not None
    assert event.event_type is ParkingEventType.SLOT_RESERVED
    assert (event.old_status, event.new_status) == (
        SlotStatus.AVAILABLE,
        SlotStatus.RESERVED,
    )
    assert event.event_metadata["reservation_id"] == reservation.id


@pytest.mark.asyncio
async def test_direct_occupy_and_owner_release_are_valid_transitions(state_db: StateDatabase):
    service = ParkingStateService(state_db.session)

    occupied = await service.occupy_slot(
        "F1-A01",
        actor_type=ActorType.USER,
        actor_id="USER-001",
        vehicle_id="VEHICLE-001",
    )
    released = await service.release_slot(
        "F1-A01",
        actor_type=ActorType.USER,
        actor_id="USER-001",
        vehicle_id="VEHICLE-001",
    )

    assert occupied is released
    assert released.status is SlotStatus.AVAILABLE
    assert released.occupied_by_vehicle_id is None
    assert released.version == 2
    events = list(
        await state_db.session.scalars(
            select(ParkingEvent)
            .where(ParkingEvent.slot_id == "F1-A01")
            .order_by(ParkingEvent.created_at)
        )
    )
    assert [event.event_type for event in events] == [
        ParkingEventType.VEHICLE_PARKED,
        ParkingEventType.VEHICLE_LEFT_SLOT,
    ]


@pytest.mark.asyncio
async def test_reservation_owner_can_occupy_and_reservation_is_confirmed(
    state_db: StateDatabase,
):
    service = ParkingStateService(state_db.session)
    await _reserve(service, "F1-C01")

    slot = await service.occupy_slot(
        "F1-C01",
        actor_type=ActorType.USER,
        actor_id="USER-001",
        vehicle_id="VEHICLE-001",
        reservation_id="RESERVATION-001",
    )

    reservation = await state_db.session.get(ParkingReservation, "RESERVATION-001")
    assert slot.status is SlotStatus.OCCUPIED
    assert slot.occupied_by_vehicle_id == "VEHICLE-001"
    assert slot.version == 2
    assert reservation is not None
    assert reservation.status is ReservationStatus.CONFIRMED
    assert await state_db.session.scalar(
        select(func.count()).select_from(ParkingEvent).where(ParkingEvent.slot_id == slot.id)
    ) == 2


@pytest.mark.asyncio
async def test_invalid_transitions_and_version_conflict_use_domain_errors(
    state_db: StateDatabase,
):
    service = ParkingStateService(state_db.session)
    await service.occupy_slot(
        "F1-A02",
        actor_type=ActorType.USER,
        actor_id="USER-001",
        vehicle_id="VEHICLE-001",
    )

    with pytest.raises(ParkingStateError) as reserve_error:
        await _reserve(service, "F1-A02")
    assert reserve_error.value.code is ErrorCode.SLOT_NOT_AVAILABLE

    with pytest.raises(ParkingStateError) as occupy_error:
        await service.occupy_slot(
            "F1-A02",
            actor_type=ActorType.USER,
            actor_id="USER-001",
            vehicle_id="VEHICLE-001",
        )
    assert occupy_error.value.code is ErrorCode.INVALID_TRANSITION

    with pytest.raises(ParkingStateError) as version_error:
        await service.release_slot(
            "F1-A02",
            actor_type=ActorType.USER,
            actor_id="USER-001",
            vehicle_id="VEHICLE-001",
            expected_version=0,
        )
    assert version_error.value.code is ErrorCode.SLOT_NOT_AVAILABLE


@pytest.mark.asyncio
async def test_wrong_owner_and_simulator_cannot_occupy_reserved_slot(
    state_db: StateDatabase,
):
    service = ParkingStateService(state_db.session)
    await _reserve(service, "F1-C02")

    with pytest.raises(ParkingStateError, match="does not own") as owner_error:
        await service.occupy_slot(
            "F1-C02",
            actor_type=ActorType.USER,
            actor_id="USER-OTHER",
            vehicle_id="VEHICLE-001",
            reservation_id="RESERVATION-001",
        )
    assert owner_error.value.code is ErrorCode.INVALID_TRANSITION

    with pytest.raises(ParkingStateError, match="Simulator cannot") as simulator_error:
        await service.occupy_slot(
            "F1-C02",
            actor_type=ActorType.SIMULATOR,
            actor_id="SIMULATOR-001",
            vehicle_id="VEHICLE-001",
            reservation_id="RESERVATION-001",
        )
    assert simulator_error.value.code is ErrorCode.INVALID_TRANSITION
    slot = await service.get_slot("F1-C02")
    assert slot.status is SlotStatus.RESERVED
    assert slot.version == 1


@pytest.mark.asyncio
async def test_expired_reservation_cannot_occupy_and_can_be_expired(
    state_db: StateDatabase,
):
    service = ParkingStateService(state_db.session)
    base_time = datetime.now(UTC)
    await service.reserve_slot(
        "F1-C03",
        "RESERVATION-001",
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        expires_at=base_time + timedelta(seconds=1),
        now=base_time,
    )
    expired_time = base_time + timedelta(seconds=2)

    with pytest.raises(ParkingStateError, match="has expired") as occupy_error:
        await service.occupy_slot(
            "F1-C03",
            actor_type=ActorType.USER,
            actor_id="USER-001",
            vehicle_id="VEHICLE-001",
            reservation_id="RESERVATION-001",
            now=expired_time,
        )
    assert occupy_error.value.code is ErrorCode.INVALID_TRANSITION

    slot = await service.expire_reservation(
        "F1-C03",
        "RESERVATION-001",
        now=expired_time,
    )
    reservation = await state_db.session.get(ParkingReservation, "RESERVATION-001")
    assert slot.status is SlotStatus.AVAILABLE
    assert slot.version == 2
    assert reservation is not None
    assert reservation.status is ReservationStatus.EXPIRED
    event = await state_db.session.scalar(
        select(ParkingEvent).where(
            ParkingEvent.slot_id == slot.id,
            ParkingEvent.event_type == ParkingEventType.RESERVATION_EXPIRED,
        )
    )
    assert event is not None


@pytest.mark.asyncio
async def test_transaction_rollback_removes_slot_reservation_and_event_changes(
    state_db: StateDatabase,
):
    factory = async_sessionmaker(state_db.engine, expire_on_commit=False)

    with pytest.raises(RuntimeError, match="force rollback"):
        async with factory() as session, session.begin():
            await _reserve(ParkingStateService(session), "F1-B01")
            raise RuntimeError("force rollback")

    async with factory() as verification_session:
        slot = await verification_session.get(ParkingSlot, "F1-B01")
        reservation = await verification_session.get(ParkingReservation, "RESERVATION-001")
        event_count = await verification_session.scalar(
            select(func.count()).select_from(ParkingEvent).where(ParkingEvent.slot_id == "F1-B01")
        )
    assert slot is not None
    assert slot.status is SlotStatus.AVAILABLE
    assert slot.version == 0
    assert reservation is None
    assert event_count == 0


@pytest.mark.asyncio
async def test_concurrent_reserve_allows_exactly_one_winner(state_db: StateDatabase):
    factory = async_sessionmaker(state_db.engine, expire_on_commit=False)
    async with factory() as setup_session, setup_session.begin():
        setup_session.add(ParkingUser(id="USER-002", display_name="Second User"))
        setup_session.add(
            Vehicle(
                id="VEHICLE-002",
                user_id="USER-002",
                plate_number="51A-00002",
                requires_charging=False,
            )
        )

    start = asyncio.Event()

    async def attempt(reservation_id: str, user_id: str, vehicle_id: str) -> str | ErrorCode:
        await start.wait()
        try:
            async with factory() as session, session.begin():
                await ParkingStateService(session).reserve_slot(
                    "F1-D10",
                    reservation_id,
                    user_id=user_id,
                    vehicle_id=vehicle_id,
                    expires_at=_future(),
                )
            return reservation_id
        except ParkingStateError as exc:
            return exc.code

    attempts = [
        asyncio.create_task(attempt("RESERVATION-001", "USER-001", "VEHICLE-001")),
        asyncio.create_task(attempt("RESERVATION-002", "USER-002", "VEHICLE-002")),
    ]
    start.set()
    results = await asyncio.gather(*attempts)

    assert sum(result in {"RESERVATION-001", "RESERVATION-002"} for result in results) == 1
    assert results.count(ErrorCode.SLOT_NOT_AVAILABLE) == 1
    async with factory() as verification_session:
        slot = await verification_session.get(ParkingSlot, "F1-D10")
        reservation_count = await verification_session.scalar(
            select(func.count())
            .select_from(ParkingReservation)
            .where(ParkingReservation.slot_id == "F1-D10")
        )
        event_count = await verification_session.scalar(
            select(func.count()).select_from(ParkingEvent).where(ParkingEvent.slot_id == "F1-D10")
        )
    assert slot is not None
    assert slot.status is SlotStatus.RESERVED
    assert slot.version == 1
    assert reservation_count == 1
    assert event_count == 1
