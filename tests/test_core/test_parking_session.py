import asyncio
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

import src.core.parking_session as parking_session_module
from src.core.config import Settings, get_settings
from src.core.db_models import (
    Base,
    ParkingEvent,
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.parking_session import ParkingSessionError, ParkingSessionService
from src.core.parking_state import ParkingStateError, ParkingStateService
from src.core.reservation import ReservationService
from src.core.reservation_expiry import ReservationExpiryService
from src.core.seed import seed_if_missing
from src.models.schemas import (
    ErrorCode,
    ParkingEventType,
    ParkingSessionStatus,
    ReservationStatus,
    SlotStatus,
)


@dataclass(slots=True)
class SessionDatabase:
    engine: AsyncEngine


@pytest_asyncio.fixture
async def session_db() -> AsyncGenerator[SessionDatabase, None]:
    database_url = get_settings().database_url
    schema_name = f"test_parking_session_{uuid4().hex}"
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

    try:
        yield SessionDatabase(engine=engine)
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


async def _reserve(
    session,
    slot_id: str,
    *,
    user_id: str = "USER-001",
    vehicle_id: str = "VEHICLE-001",
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ParkingReservation:
    reservation = await ReservationService(session, settings=settings).create_reservation(
        user_id,
        vehicle_id,
        slot_id,
        now=now,
    )
    slot = await session.get(ParkingSlot, slot_id)
    assert slot is not None
    return reservation


@pytest.mark.asyncio
async def test_confirm_valid_reservation_creates_active_session_atomically(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    parked_at = datetime(2026, 8, 12, 6, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F1-D01", now=parked_at - timedelta(seconds=1))
        parking_session = await ParkingSessionService(session, clock=lambda: parked_at).confirm_parking(
            "USER-001",
            "VEHICLE-001",
            reservation.id,
            expected_version=1,
        )

    assert re.fullmatch(r"SESSION-[0-9a-f-]{36}", parking_session.id)
    assert parking_session.slot_id == reservation.slot_id == "F1-D01"
    assert parking_session.status is ParkingSessionStatus.ACTIVE
    assert parking_session.parked_at == parked_at
    assert reservation.status is ReservationStatus.CONFIRMED
    async with factory() as session:
        slot = await session.get(ParkingSlot, "F1-D01")
        parked_event = await session.scalar(
            select(ParkingEvent).where(
                ParkingEvent.slot_id == "F1-D01",
                ParkingEvent.event_type == ParkingEventType.VEHICLE_PARKED,
            )
        )
    assert slot is not None and slot.status is SlotStatus.OCCUPIED
    assert slot.occupied_by_vehicle_id == "VEHICLE-001"
    assert parked_event is not None


@pytest.mark.asyncio
async def test_confirm_rejects_reservation_owned_by_another_user(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await _reserve(
            session,
            "F1-C01",
            user_id="USER-002",
            vehicle_id="VEHICLE-002",
        )
        with pytest.raises(ParkingSessionError, match="does not own") as error:
            await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", reservation.id)
    assert error.value.code is ErrorCode.INVALID_TRANSITION


@pytest.mark.asyncio
async def test_confirm_rejects_expired_reservation_without_occupying_slot(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    created_at = datetime(2026, 8, 12, 7, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        reservation = await _reserve(
            session,
            "F1-C02",
            settings=Settings(reservation_ttl_seconds=1),
            now=created_at,
        )

    async with factory() as session, session.begin():
        with pytest.raises(ParkingSessionError, match="expired") as error:
            await ParkingSessionService(session, clock=lambda: created_at + timedelta(seconds=1)).confirm_parking(
                "USER-001", "VEHICLE-001", reservation.id
            )
    assert error.value.code is ErrorCode.INVALID_TRANSITION
    async with factory() as session:
        slot = await session.get(ParkingSlot, "F1-C02")
        session_count = await session.scalar(select(func.count()).select_from(ParkingSession))
    assert slot is not None and slot.status is SlotStatus.RESERVED
    assert session_count == 0


@pytest.mark.asyncio
async def test_confirm_parking_does_not_require_current_location(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await ReservationService(session).create_reservation("USER-001", "VEHICLE-001", "F2-C09")
        parking_session = await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", reservation.id)

    assert parking_session.slot_id == "F2-C09"


@pytest.mark.asyncio
async def test_unrelated_current_location_does_not_prevent_parking_confirmation(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await ReservationService(session).create_reservation(
            "USER-001", "VEHICLE-001", "F2-C09"
        )
        user = await session.get(ParkingUser, "USER-001")
        assert user is not None
        user.current_node_id = "F2-ELEVATOR"
        parking_session = await ParkingSessionService(session).confirm_parking(
            "USER-001", "VEHICLE-001", reservation.id
        )

    assert parking_session.slot_id == "F2-C09"


@pytest.mark.asyncio
async def test_user_cannot_create_two_active_sessions(session_db: SessionDatabase):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        first_reservation = await _reserve(session, "F1-A01")
        await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", first_reservation.id)
    async with factory() as session, session.begin():
        second_reservation = await _reserve(session, "F1-A02")

    async with factory() as session, session.begin():
        with pytest.raises(ParkingSessionError, match="already exists") as error:
            await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", second_reservation.id)
    assert error.value.code is ErrorCode.INVALID_TRANSITION
    async with factory() as session:
        active_count = await session.scalar(
            select(func.count()).select_from(ParkingSession).where(ParkingSession.status == ParkingSessionStatus.ACTIVE)
        )
        slot = await session.get(ParkingSlot, "F1-A02")
    assert active_count == 1
    assert slot is not None and slot.status is SlotStatus.RESERVED


@pytest.mark.asyncio
async def test_session_insert_failure_rolls_back_slot_reservation_and_event(
    session_db: SessionDatabase,
    monkeypatch: pytest.MonkeyPatch,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    collision_id = "SESSION-duplicate"
    base_time = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F1-B01")
        session.add(
            ParkingSession(
                id=collision_id,
                user_id="USER-002",
                vehicle_id="VEHICLE-002",
                slot_id="F1-B02",
                status=ParkingSessionStatus.COMPLETED,
                parked_at=base_time,
                completed_at=base_time,
            )
        )

    monkeypatch.setattr(parking_session_module, "uuid4", lambda: "duplicate")
    with pytest.raises(IntegrityError):
        async with factory() as session, session.begin():
            await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", reservation.id)

    async with factory() as session:
        stored_reservation = await session.get(ParkingReservation, reservation.id)
        slot = await session.get(ParkingSlot, "F1-B01")
        parked_event_count = await session.scalar(
            select(func.count())
            .select_from(ParkingEvent)
            .where(
                ParkingEvent.slot_id == "F1-B01",
                ParkingEvent.event_type == ParkingEventType.VEHICLE_PARKED,
            )
        )
    assert stored_reservation is not None
    assert stored_reservation.status is ReservationStatus.ACTIVE
    assert slot is not None and slot.status is SlotStatus.RESERVED
    assert parked_event_count == 0


@pytest.mark.asyncio
async def test_find_vehicle_uses_active_session_and_slot_as_destination(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F1-D01")
        parking_session = await ParkingSessionService(session).confirm_parking(
            "USER-001", "VEHICLE-001", reservation.id
        )

    async with factory() as session:
        result = await ParkingSessionService(session).find_parked_vehicle("USER-001")
        slot = await session.get(ParkingSlot, result.slot_id)
    assert result.session_id == parking_session.id
    assert result.vehicle_id == "VEHICLE-001"
    assert result.slot_id == result.destination_node_id == "F1-D01"
    assert slot is not None and slot.node_id != result.destination_node_id


@pytest.mark.asyncio
async def test_complete_session_releases_slot_and_marks_session_completed(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    completed_at = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F1-D02", now=completed_at - timedelta(seconds=1))
        parking_session = await ParkingSessionService(session, clock=lambda: completed_at).confirm_parking(
            "USER-001", "VEHICLE-001", reservation.id
        )
        completed = await ParkingSessionService(session, clock=lambda: completed_at).complete_session(
            parking_session.id, user_id="USER-001"
        )

    assert completed.status is ParkingSessionStatus.COMPLETED
    assert completed.completed_at == completed_at
    async with factory() as session:
        slot = await session.get(ParkingSlot, "F1-D02")
        active = await ParkingSessionService(session).get_active_session("USER-001")
        left_event = await session.scalar(
            select(ParkingEvent).where(
                ParkingEvent.slot_id == "F1-D02",
                ParkingEvent.event_type == ParkingEventType.VEHICLE_LEFT_SLOT,
            )
        )
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
    assert slot.occupied_by_vehicle_id is None
    assert active is None
    assert left_event is not None and left_event.created_at == completed_at


@pytest.mark.asyncio
async def test_other_user_cannot_complete_session(session_db: SessionDatabase):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F1-C03")
        parking_session = await ParkingSessionService(session).confirm_parking(
            "USER-001", "VEHICLE-001", reservation.id
        )

    async with factory() as session, session.begin():
        with pytest.raises(ParkingSessionError, match="does not own") as error:
            await ParkingSessionService(session).complete_session(parking_session.id, user_id="USER-002")
    assert error.value.code is ErrorCode.INVALID_TRANSITION
    async with factory() as session:
        stored_session = await session.get(ParkingSession, parking_session.id)
        slot = await session.get(ParkingSlot, "F1-C03")
    assert stored_session is not None
    assert stored_session.status is ParkingSessionStatus.ACTIVE
    assert slot is not None and slot.status is SlotStatus.OCCUPIED


@pytest.mark.asyncio
async def test_confirm_vs_cancel_has_no_deadlock_and_keeps_valid_state(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F2-C09")

    async def confirm() -> str:
        try:
            async with factory() as session, session.begin():
                await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", reservation.id)
            return "confirmed"
        except (ParkingSessionError, ParkingStateError):
            return "rejected"

    async def cancel() -> str:
        try:
            async with factory() as session, session.begin():
                await ReservationService(session).cancel_reservation(reservation.id, user_id="USER-001")
            return "cancelled"
        except ParkingStateError:
            return "rejected"

    outcomes = await asyncio.wait_for(asyncio.gather(confirm(), cancel()), timeout=5)
    assert outcomes.count("rejected") == 1
    async with factory() as session:
        stored = await session.get(ParkingReservation, reservation.id)
        slot = await session.get(ParkingSlot, "F2-C09")
        sessions = list(await session.scalars(select(ParkingSession)))
    assert stored is not None and slot is not None
    if stored.status is ReservationStatus.CONFIRMED:
        assert slot.status is SlotStatus.OCCUPIED
        assert len(sessions) == 1 and sessions[0].status is ParkingSessionStatus.ACTIVE
    else:
        assert stored.status is ReservationStatus.CANCELLED
        assert slot.status is SlotStatus.AVAILABLE
        assert sessions == []


@pytest.mark.asyncio
async def test_confirm_vs_expiry_has_no_deadlock_and_one_terminal_winner(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    base = datetime(2026, 8, 26, 4, 0, tzinfo=UTC)
    settings = Settings(reservation_ttl_seconds=2)
    async with factory() as session, session.begin():
        reservation = await _reserve(
            session,
            "F2-D09",
            settings=settings,
            now=base,
        )

    async def confirm() -> str:
        try:
            async with factory() as session, session.begin():
                await ParkingSessionService(
                    session,
                    clock=lambda: base + timedelta(seconds=1),
                    settings=settings,
                ).confirm_parking("USER-001", "VEHICLE-001", reservation.id)
            return "confirmed"
        except (ParkingSessionError, ParkingStateError):
            return "rejected"

    async def expire() -> str:
        async with factory() as session, session.begin():
            count = await ReservationExpiryService(session, clock=lambda: base + timedelta(seconds=3)).expire_batch()
        return "expired" if count else "skipped"

    await asyncio.wait_for(asyncio.gather(confirm(), expire()), timeout=5)
    async with factory() as session:
        stored = await session.get(ParkingReservation, reservation.id)
        slot = await session.get(ParkingSlot, "F2-D09")
        active_count = await session.scalar(
            select(func.count()).select_from(ParkingSession).where(ParkingSession.status == ParkingSessionStatus.ACTIVE)
        )
    assert stored is not None and slot is not None
    assert (stored.status, slot.status, active_count) in {
        (ReservationStatus.CONFIRMED, SlotStatus.OCCUPIED, 1),
        (ReservationStatus.EXPIRED, SlotStatus.AVAILABLE, 0),
    }


@pytest.mark.asyncio
async def test_two_confirm_attempts_create_one_active_session_without_deadlock(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F3-A01")

    async def attempt() -> bool:
        try:
            async with factory() as session, session.begin():
                await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", reservation.id)
            return True
        except (ParkingSessionError, ParkingStateError, IntegrityError):
            return False

    results = await asyncio.wait_for(asyncio.gather(attempt(), attempt()), timeout=5)
    assert sorted(results) == [False, True]
    async with factory() as session:
        active_count = await session.scalar(
            select(func.count()).select_from(ParkingSession).where(ParkingSession.status == ParkingSessionStatus.ACTIVE)
        )
        slot = await session.get(ParkingSlot, "F3-A01")
    assert active_count == 1
    assert slot is not None and slot.status is SlotStatus.OCCUPIED


@pytest.mark.asyncio
async def test_complete_vs_admin_slot_mutation_has_no_deadlock(
    session_db: SessionDatabase,
):
    factory = async_sessionmaker(session_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        reservation = await _reserve(session, "F3-B01")
        parked = await ParkingSessionService(session).confirm_parking("USER-001", "VEHICLE-001", reservation.id)
        slot = await session.get(ParkingSlot, "F3-B01")
        assert slot is not None
        expected_version = slot.version

    async def complete() -> bool:
        try:
            async with factory() as session, session.begin():
                await ParkingSessionService(session).complete_session(
                    parked.id,
                    user_id="USER-001",
                    expected_version=expected_version,
                )
            return True
        except (ParkingSessionError, ParkingStateError):
            return False

    async def admin_clear() -> bool:
        try:
            async with factory() as session, session.begin():
                await ParkingStateService(session).set_slot_status_by_admin(
                    "F3-B01",
                    SlotStatus.AVAILABLE,
                    admin_id="ADMIN-001",
                    expected_version=expected_version,
                )
            return True
        except ParkingStateError:
            return False

    results = await asyncio.wait_for(
        asyncio.gather(complete(), admin_clear()),
        timeout=5,
    )
    assert results == [True, False]
    async with factory() as session:
        stored_session = await session.get(ParkingSession, parked.id)
        slot = await session.get(ParkingSlot, "F3-B01")
    assert stored_session is not None
    assert stored_session.status is ParkingSessionStatus.COMPLETED
    assert slot is not None and slot.status is SlotStatus.AVAILABLE
