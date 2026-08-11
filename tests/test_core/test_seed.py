from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import get_settings
from src.core.db_models import (
    LocationCheckpoint,
    MapEdge,
    MapNode,
    ParkingEvent,
    ParkingReservation,
    ParkingSession,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.seed import SeedValidationError, seed_if_missing
from src.models.schemas import SlotStatus


@pytest_asyncio.fixture
async def seed_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as session:
            for model in (
                ParkingEvent,
                ParkingSession,
                ParkingReservation,
                LocationCheckpoint,
                ParkingSlot,
                MapEdge,
                Vehicle,
                ParkingUser,
                MapNode,
            ):
                await session.execute(delete(model))
            await session.commit()
            yield session
        await outer_transaction.rollback()
    await engine.dispose()


async def _count(session: AsyncSession, model: type[object]) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.asyncio
async def test_seed_empty_database_then_second_run_is_idempotent(seed_session: AsyncSession):
    first = await seed_if_missing(seed_session)

    assert first.nodes_created == 54
    assert first.edges_created == 58
    assert first.slots_created == 40
    assert first.checkpoints_created == 3
    assert first.users_created == 1
    assert first.vehicles_created == 1
    assert first.rows_created == 157

    counts_after_first = {
        "nodes": await _count(seed_session, MapNode),
        "edges": await _count(seed_session, MapEdge),
        "slots": await _count(seed_session, ParkingSlot),
        "checkpoints": await _count(seed_session, LocationCheckpoint),
        "users": await _count(seed_session, ParkingUser),
        "vehicles": await _count(seed_session, Vehicle),
    }
    second = await seed_if_missing(seed_session)
    counts_after_second = {
        "nodes": await _count(seed_session, MapNode),
        "edges": await _count(seed_session, MapEdge),
        "slots": await _count(seed_session, ParkingSlot),
        "checkpoints": await _count(seed_session, LocationCheckpoint),
        "users": await _count(seed_session, ParkingUser),
        "vehicles": await _count(seed_session, Vehicle),
    }

    assert counts_after_first == {
        "nodes": 54,
        "edges": 58,
        "slots": 40,
        "checkpoints": 3,
        "users": 1,
        "vehicles": 1,
    }
    assert counts_after_second == counts_after_first
    assert second.rows_created == 0


@pytest.mark.asyncio
async def test_seeded_ids_ev_baseline_and_graph_references(seed_session: AsyncSession):
    await seed_if_missing(seed_session)

    user = await seed_session.get(ParkingUser, "USER-001")
    vehicle = await seed_session.get(Vehicle, "VEHICLE-001")
    slots = list(await seed_session.scalars(select(ParkingSlot)))
    nodes = {node.id for node in await seed_session.scalars(select(MapNode))}
    edges = list(await seed_session.scalars(select(MapEdge)))
    checkpoints = list(await seed_session.scalars(select(LocationCheckpoint)))

    assert user is not None
    assert user.current_node_id == "F1-ENTRANCE"
    assert vehicle is not None
    assert vehicle.user_id == user.id
    assert vehicle.requires_charging is True
    assert {slot.id for slot in slots} == {
        f"F1-{zone}{number:02d}" for zone in "ABCD" for number in range(1, 11)
    }
    assert {slot.id for slot in slots if slot.has_charger} == {
        f"F1-{zone}{number:02d}" for zone in "CD" for number in range(1, 6)
    }
    assert all(slot.node_id in nodes for slot in slots)
    assert all(edge.from_node in nodes and edge.to_node in nodes for edge in edges)
    assert all(edge.bidirectional for edge in edges)
    assert {(checkpoint.id, checkpoint.node_id, checkpoint.qr_payload) for checkpoint in checkpoints} == {
        (checkpoint_id, checkpoint_id, f"PARKSMART:LOCATION:{checkpoint_id}")
        for checkpoint_id in ("F1-CP1", "F1-CP2", "F1-CP3")
    }

    adjacency = {node_id: set() for node_id in nodes}
    for edge in edges:
        adjacency[edge.from_node].add(edge.to_node)
        adjacency[edge.to_node].add(edge.from_node)
    visited = {"F1-CP2"}
    pending = ["F1-CP2"]
    while pending:
        current = pending.pop()
        for neighbor in adjacency[current] - visited:
            visited.add(neighbor)
            pending.append(neighbor)
    assert visited == nodes

    available_ev_ids = {
        slot.id
        for slot in slots
        if slot.has_charger and slot.status is SlotStatus.AVAILABLE
    }
    assert "F1-D01" in available_ev_ids
    assert len(available_ev_ids) >= 2


@pytest.mark.asyncio
async def test_seed_does_not_reset_existing_mutable_state(seed_session: AsyncSession):
    await seed_if_missing(seed_session)
    user = await seed_session.get(ParkingUser, "USER-001")
    slot = await seed_session.get(ParkingSlot, "F1-D02")
    edge = await seed_session.get(MapEdge, ("F1-CP1", "F1-CP2"))
    assert user is not None and slot is not None and edge is not None

    user.current_node_id = "F1-CP3"
    slot.status = SlotStatus.RESERVED
    slot.version = 7
    edge.enabled = False
    await seed_session.flush()

    result = await seed_if_missing(seed_session)

    assert result.rows_created == 0
    assert user.current_node_id == "F1-CP3"
    assert slot.status is SlotStatus.RESERVED
    assert slot.version == 7
    assert edge.enabled is False


@pytest.mark.asyncio
async def test_seed_fails_clearly_for_existing_contract_mismatch(seed_session: AsyncSession):
    await seed_if_missing(seed_session)
    entrance = await seed_session.get(MapNode, "F1-ENTRANCE")
    assert entrance is not None
    entrance.x = 999
    await seed_session.flush()

    with pytest.raises(SeedValidationError, match="F1-ENTRANCE.*canonical contract"):
        await seed_if_missing(seed_session)
