import asyncio
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import Settings, get_settings
from src.core.db_models import (
    Base,
    ParkingEvent,
    ParkingReservation,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.parking_state import ParkingStateError
from src.core.reservation import ReservationService
from src.core.seed import seed_if_missing
from src.models.schemas import ErrorCode, ParkingEventType, ReservationStatus, SlotStatus


@dataclass(slots=True)
class ReservationDatabase:
    engine: AsyncEngine


@pytest_asyncio.fixture
async def reservation_db() -> AsyncGenerator[ReservationDatabase, None]:
    database_url = get_settings().database_url
    schema_name = f"test_reservation_{uuid4().hex}"
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
    async with factory() as session:
        await seed_if_missing(session)

    try:
        yield ReservationDatabase(engine=engine)
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_create_reservation_uses_server_id_configured_ttl_and_state_service(
    reservation_db: ReservationDatabase,
):
    factory = async_sessionmaker(reservation_db.engine, expire_on_commit=False)
    created_at = datetime(2026, 8, 12, 3, 0, tzinfo=UTC)
    settings = Settings(reservation_ttl_seconds=45)

    async with factory() as session, session.begin():
        reservation = await ReservationService(session, settings=settings).create_reservation(
            "USER-001",
            "VEHICLE-001",
            "F1-C01",
            now=created_at,
        )

    assert re.fullmatch(
        r"RESERVATION-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        reservation.id,
    )
    assert reservation.status is ReservationStatus.ACTIVE
    assert reservation.created_at == created_at
    assert reservation.expires_at == created_at + timedelta(seconds=45)
    async with factory() as session:
        slot = await session.get(ParkingSlot, "F1-C01")
        event = await session.scalar(
            select(ParkingEvent).where(ParkingEvent.slot_id == "F1-C01")
        )
    assert slot is not None and slot.status is SlotStatus.RESERVED
    assert event is not None and event.event_type is ParkingEventType.SLOT_RESERVED


@pytest.mark.asyncio
async def test_create_reservation_validates_user_vehicle_and_active_hold(
    reservation_db: ReservationDatabase,
):
    factory = async_sessionmaker(reservation_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        service = ReservationService(session)
        with pytest.raises(ParkingStateError, match="user") as user_error:
            await service.create_reservation("USER-MISSING", "VEHICLE-001", "F1-A01")
        assert user_error.value.code is ErrorCode.INVALID_TRANSITION

    async with factory() as session, session.begin():
        service = ReservationService(session)
        await service.create_reservation("USER-001", "VEHICLE-001", "F1-A01")
        with pytest.raises(ParkingStateError) as active_error:
            await service.create_reservation("USER-001", "VEHICLE-001", "F1-A02")
        assert active_error.value.code is ErrorCode.ACTIVE_RESERVATION_EXISTS


@pytest.mark.asyncio
async def test_cancel_reservation_updates_reservation_slot_and_event_atomically(
    reservation_db: ReservationDatabase,
):
    factory = async_sessionmaker(reservation_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        service = ReservationService(session)
        reservation = await service.create_reservation(
            "USER-001", "VEHICLE-001", "F1-B01"
        )
        cancelled = await service.cancel_reservation(reservation.id, user_id="USER-001")

    assert cancelled.status is ReservationStatus.CANCELLED
    async with factory() as session:
        slot = await session.get(ParkingSlot, "F1-B01")
        event = await session.scalar(
            select(ParkingEvent).where(
                ParkingEvent.slot_id == "F1-B01",
                ParkingEvent.event_type == ParkingEventType.RESERVATION_CANCELLED,
            )
        )
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert slot.version == 2
    assert event is not None and event.actor_id == "USER-001"


@pytest.mark.asyncio
async def test_get_active_reservation_expires_elapsed_hold(
    reservation_db: ReservationDatabase,
):
    factory = async_sessionmaker(reservation_db.engine, expire_on_commit=False)
    base_time = datetime(2026, 8, 12, 4, 0, tzinfo=UTC)
    settings = Settings(reservation_ttl_seconds=1)
    async with factory() as session, session.begin():
        service = ReservationService(session, settings=settings)
        reservation = await service.create_reservation(
            "USER-001", "VEHICLE-001", "F1-C02", now=base_time
        )
        active = await service.get_active_reservation(
            "USER-001", now=base_time + timedelta(seconds=1)
        )

    assert active is None
    assert reservation.status is ReservationStatus.EXPIRED
    async with factory() as session:
        slot = await session.get(ParkingSlot, "F1-C02")
        expired_events = await session.scalar(
            select(func.count())
            .select_from(ParkingEvent)
            .where(ParkingEvent.event_type == ParkingEventType.RESERVATION_EXPIRED)
        )
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert expired_events == 1


@pytest.mark.asyncio
async def test_create_reservation_replaces_users_expired_hold(
    reservation_db: ReservationDatabase,
):
    factory = async_sessionmaker(reservation_db.engine, expire_on_commit=False)
    base_time = datetime(2026, 8, 12, 5, 0, tzinfo=UTC)
    settings = Settings(reservation_ttl_seconds=1)
    async with factory() as session, session.begin():
        service = ReservationService(session, settings=settings)
        expired = await service.create_reservation(
            "USER-001", "VEHICLE-001", "F1-D01", now=base_time
        )
        current = await service.create_reservation(
            "USER-001",
            "VEHICLE-001",
            "F1-D02",
            now=base_time + timedelta(seconds=2),
        )

    assert expired.status is ReservationStatus.EXPIRED
    assert current.status is ReservationStatus.ACTIVE
    async with factory() as session:
        old_slot = await session.get(ParkingSlot, "F1-D01")
        new_slot = await session.get(ParkingSlot, "F1-D02")
    assert old_slot is not None and old_slot.status is SlotStatus.AVAILABLE
    assert new_slot is not None and new_slot.status is SlotStatus.RESERVED


@pytest.mark.asyncio
async def test_two_sessions_reserving_same_slot_have_exactly_one_winner(
    reservation_db: ReservationDatabase,
):
    factory = async_sessionmaker(reservation_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        session.add(ParkingUser(id="USER-002", display_name="Second User"))
        session.add(
            Vehicle(
                id="VEHICLE-002",
                user_id="USER-002",
                plate_number="51A-00002",
                requires_charging=False,
            )
        )

    start = asyncio.Event()

    async def attempt(user_id: str, vehicle_id: str) -> str | ErrorCode:
        await start.wait()
        try:
            async with factory() as session, session.begin():
                reservation = await ReservationService(session).create_reservation(
                    user_id,
                    vehicle_id,
                    "F1-D10",
                )
            return reservation.id
        except ParkingStateError as error:
            return error.code

    tasks = [
        asyncio.create_task(attempt("USER-001", "VEHICLE-001")),
        asyncio.create_task(attempt("USER-002", "VEHICLE-002")),
    ]
    start.set()
    results = await asyncio.gather(*tasks)

    assert sum(isinstance(result, str) and result.startswith("RESERVATION-") for result in results) == 1
    assert results.count(ErrorCode.SLOT_NOT_AVAILABLE) == 1
    async with factory() as session:
        active_count = await session.scalar(
            select(func.count())
            .select_from(ParkingReservation)
            .where(
                ParkingReservation.slot_id == "F1-D10",
                ParkingReservation.status == ReservationStatus.ACTIVE,
            )
        )
    assert active_count == 1


@pytest.mark.asyncio
async def test_caller_rollback_removes_complete_reservation_transition(
    reservation_db: ReservationDatabase,
):
    factory = async_sessionmaker(reservation_db.engine, expire_on_commit=False)
    with pytest.raises(RuntimeError, match="rollback"):
        async with factory() as session, session.begin():
            await ReservationService(session).create_reservation(
                "USER-001", "VEHICLE-001", "F1-A10"
            )
            raise RuntimeError("rollback")

    async with factory() as session:
        slot = await session.get(ParkingSlot, "F1-A10")
        reservation_count = await session.scalar(
            select(func.count()).select_from(ParkingReservation)
        )
        event_count = await session.scalar(
            select(func.count()).select_from(ParkingEvent).where(ParkingEvent.slot_id == "F1-A10")
        )
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert reservation_count == 0
    assert event_count == 0
