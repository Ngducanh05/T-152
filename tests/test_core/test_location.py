from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from src.core.config import get_settings
from src.core.db_models import Base, ParkingSlot, ParkingUser
from src.core.location import LocationError, LocationService
from src.core.seed import seed_if_missing
from src.models.schemas import ErrorCode


@dataclass(slots=True)
class LocationDatabase:
    engine: AsyncEngine


@pytest_asyncio.fixture
async def location_db() -> AsyncGenerator[LocationDatabase, None]:
    database_url = get_settings().database_url
    schema_name = f"test_location_{uuid4().hex}"
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
        yield LocationDatabase(engine=engine)
    finally:
        await engine.dispose()
        async with admin_engine.connect() as connection:
            await connection.execute(DropSchema(schema_name, cascade=True))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_confirm_entrance(location_db: LocationDatabase):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        confirmed = await LocationService(session).confirm_location(
            "USER-001", "F1-ENTRANCE"
        )
    assert confirmed == "F1-ENTRANCE"


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint_id", ["F1-CP1", "F1-CP2", "F1-CP3"])
async def test_confirm_each_checkpoint(
    location_db: LocationDatabase,
    checkpoint_id: str,
):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        confirmed = await LocationService(session).confirm_location(
            "USER-001", checkpoint_id
        )
    assert confirmed == checkpoint_id


@pytest.mark.asyncio
async def test_confirm_elevator(location_db: LocationDatabase):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        confirmed = await LocationService(session).confirm_location(
            "USER-001", "F1-ELEVATOR"
        )
    assert confirmed == "F1-ELEVATOR"


@pytest.mark.asyncio
async def test_confirm_slot_preserves_slot_node_id_not_aisle_attachment(
    location_db: LocationDatabase,
):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        slot = await session.get(ParkingSlot, "F1-A03")
        assert slot is not None and slot.node_id == "F1-A-W"
        confirmed = await LocationService(session).confirm_location("USER-001", "F1-A03")

    assert confirmed == "F1-A03"
    async with factory() as session:
        user = await session.get(ParkingUser, "USER-001")
    assert user is not None and user.current_node_id == "F1-A03"


@pytest.mark.asyncio
async def test_reject_aisle_node(location_db: LocationDatabase):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        with pytest.raises(LocationError, match="internal routing aisle") as error:
            await LocationService(session).confirm_location("USER-001", "F1-C-W")
    assert error.value.code is ErrorCode.INVALID_TRANSITION


@pytest.mark.asyncio
async def test_scanned_qr_can_confirm_aisle_and_persists_location(location_db: LocationDatabase):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        marker = await LocationService(session).confirm_scanned_location(
            "USER-001", "parksmart:location:v1:PSLOC-F3-D-W"
        )
    assert marker.node_id == "F3-D-W"
    async with factory() as session:
        user = await session.get(ParkingUser, "USER-001")
    assert user is not None and user.current_node_id == "F3-D-W"


@pytest.mark.asyncio
async def test_scanned_qr_rejects_unknown_user_and_rolls_back(location_db: LocationDatabase):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        with pytest.raises(LocationError) as error:
            await LocationService(session).confirm_scanned_location(
                "USER-MISSING", "parksmart:location:v1:PSLOC-F3-D-W"
            )
    assert error.value.code is ErrorCode.INVALID_TRANSITION

    with pytest.raises(RuntimeError, match="rollback"):
        async with factory() as session, session.begin():
            await LocationService(session).confirm_scanned_location(
                "USER-001", "parksmart:location:v1:PSLOC-F3-D-W"
            )
            raise RuntimeError("rollback")
    async with factory() as session:
        assert await LocationService(session).get_current_location("USER-001") == "F1-ENTRANCE"


@pytest.mark.asyncio
async def test_reject_unknown_node(location_db: LocationDatabase):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        with pytest.raises(LocationError, match="was not found") as error:
            await LocationService(session).confirm_location("USER-001", "F1-UNKNOWN")
    assert error.value.code is ErrorCode.ROUTE_NODE_NOT_FOUND


@pytest.mark.asyncio
async def test_reject_unknown_user(location_db: LocationDatabase):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        with pytest.raises(LocationError, match="user") as error:
            await LocationService(session).confirm_location("USER-MISSING", "F1-CP1")
    assert error.value.code is ErrorCode.INVALID_TRANSITION


@pytest.mark.asyncio
async def test_get_current_location_returns_none_when_unconfirmed(
    location_db: LocationDatabase,
):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        user = await session.get(ParkingUser, "USER-001")
        assert user is not None
        user.current_node_id = None

    async with factory() as session:
        current = await LocationService(session).get_current_location("USER-001")
    assert current is None


@pytest.mark.asyncio
async def test_get_current_location_returns_exact_confirmed_id(
    location_db: LocationDatabase,
):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        service = LocationService(session)
        await service.confirm_location("USER-001", "F1-CP3")
        current = await service.get_current_location("USER-001")
    assert current == "F1-CP3"


@pytest.mark.asyncio
async def test_caller_rollback_removes_confirmed_location_change(
    location_db: LocationDatabase,
):
    factory = async_sessionmaker(location_db.engine, expire_on_commit=False)
    with pytest.raises(RuntimeError, match="rollback"):
        async with factory() as session, session.begin():
            await LocationService(session).confirm_location("USER-001", "F1-EXIT")
            raise RuntimeError("rollback")

    async with factory() as session:
        current = await LocationService(session).get_current_location("USER-001")
    assert current == "F1-ENTRANCE"
