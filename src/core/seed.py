"""Idempotent seed for the canonical F1 map and minimal demo identity."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import (
    MapEdge,
    MapNode,
    ParkingSlot,
    ParkingUser,
    Vehicle,
)
from src.core.parking_map import build_canonical_f1_map, validate_canonical_f1_map

DEMO_USER_ID = "USER-001"
DEMO_VEHICLE_ID = "VEHICLE-001"
DEMO_DISPLAY_NAME = "Demo User"
DEMO_PLATE_NUMBER = "51A-00001"
DEMO_START_NODE_ID = "F1-ENTRANCE"


class SeedValidationError(ValueError):
    """Raised when existing seed-owned data conflicts with the canonical contract."""


@dataclass(frozen=True, slots=True)
class SeedResult:
    nodes_created: int = 0
    edges_created: int = 0
    slots_created: int = 0
    users_created: int = 0
    vehicles_created: int = 0

    @property
    def rows_created(self) -> int:
        return sum(
            (
                self.nodes_created,
                self.edges_created,
                self.slots_created,
                self.users_created,
                self.vehicles_created,
            )
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SeedValidationError(message)


async def _seed_if_missing(session: AsyncSession) -> SeedResult:
    canonical_map = build_canonical_f1_map()
    validate_canonical_f1_map(canonical_map)

    canonical_nodes = {node.id: node for node in canonical_map.nodes}
    existing_nodes = {node.id: node for node in await session.scalars(select(MapNode))}
    _require(
        set(existing_nodes) <= set(canonical_nodes),
        "existing map_nodes contain IDs outside the canonical F1 contract",
    )
    for node_id, existing in existing_nodes.items():
        expected = canonical_nodes[node_id]
        _require(
            (existing.floor_id, existing.type, existing.x, existing.y)
            == (expected.floor_id, expected.type, expected.x, expected.y),
            f"existing map node {node_id} does not match the canonical contract",
        )

    missing_nodes = [
        MapNode(id=node.id, floor_id=node.floor_id, type=node.type, x=node.x, y=node.y)
        for node in canonical_map.nodes
        if node.id not in existing_nodes
    ]
    session.add_all(missing_nodes)
    await session.flush()

    canonical_edges = {(edge.from_node, edge.to_node): edge for edge in canonical_map.edges}
    existing_edges = {
        (edge.from_node, edge.to_node): edge for edge in await session.scalars(select(MapEdge))
    }
    _require(
        set(existing_edges) <= set(canonical_edges),
        "existing map_edges contain endpoints outside the canonical F1 contract",
    )
    for edge_key, existing in existing_edges.items():
        expected = canonical_edges[edge_key]
        _require(
            (existing.distance_m, existing.bidirectional)
            == (expected.distance_m, expected.bidirectional),
            f"existing map edge {edge_key} does not match the canonical contract",
        )

    missing_edges = [
        MapEdge(
            from_node=edge.from_node,
            to_node=edge.to_node,
            distance_m=edge.distance_m,
            bidirectional=edge.bidirectional,
            enabled=edge.enabled,
        )
        for edge in canonical_map.edges
        if (edge.from_node, edge.to_node) not in existing_edges
    ]
    session.add_all(missing_edges)

    demo_user = await session.get(ParkingUser, DEMO_USER_ID)
    if demo_user is None:
        session.add(
            ParkingUser(
                id=DEMO_USER_ID,
                display_name=DEMO_DISPLAY_NAME,
                current_node_id=DEMO_START_NODE_ID,
            )
        )
    else:
        _require(
            demo_user.display_name == DEMO_DISPLAY_NAME,
            f"existing {DEMO_USER_ID} does not match the demo contract",
        )

    demo_vehicle = await session.get(Vehicle, DEMO_VEHICLE_ID)
    vehicle_with_demo_plate = await session.scalar(
        select(Vehicle).where(Vehicle.plate_number == DEMO_PLATE_NUMBER)
    )
    _require(
        vehicle_with_demo_plate is None or vehicle_with_demo_plate.id == DEMO_VEHICLE_ID,
        f"plate {DEMO_PLATE_NUMBER} is already assigned to another vehicle",
    )
    if demo_vehicle is None:
        session.add(
            Vehicle(
                id=DEMO_VEHICLE_ID,
                user_id=DEMO_USER_ID,
                plate_number=DEMO_PLATE_NUMBER,
                requires_charging=True,
            )
        )
    else:
        _require(
            (
                demo_vehicle.user_id,
                demo_vehicle.plate_number,
                demo_vehicle.requires_charging,
            )
            == (DEMO_USER_ID, DEMO_PLATE_NUMBER, True),
            f"existing {DEMO_VEHICLE_ID} does not match the demo contract",
        )

    canonical_slots = {slot.id: slot for slot in canonical_map.slots}
    existing_slots = {slot.id: slot for slot in await session.scalars(select(ParkingSlot))}
    _require(
        set(existing_slots) <= set(canonical_slots),
        "existing parking_slots contain IDs outside the canonical F1 contract",
    )
    for slot_id, existing in existing_slots.items():
        expected = canonical_slots[slot_id]
        _require(
            (
                existing.floor_id,
                existing.zone_id,
                existing.node_id,
                existing.has_charger,
                existing.is_accessible,
            )
            == (
                expected.floor_id,
                expected.zone_id,
                expected.node_id,
                expected.has_charger,
                expected.is_accessible,
            ),
            f"existing parking slot {slot_id} does not match the canonical contract",
        )

    missing_slots = [
        ParkingSlot(
            id=slot.id,
            floor_id=slot.floor_id,
            zone_id=slot.zone_id,
            node_id=slot.node_id,
            status=slot.status,
            has_charger=slot.has_charger,
            is_accessible=slot.is_accessible,
            version=0,
            occupied_by_vehicle_id=None,
        )
        for slot in canonical_map.slots
        if slot.id not in existing_slots
    ]
    session.add_all(missing_slots)

    await session.flush()

    return SeedResult(
        nodes_created=len(missing_nodes),
        edges_created=len(missing_edges),
        slots_created=len(missing_slots),
        users_created=int(demo_user is None),
        vehicles_created=int(demo_vehicle is None),
    )


async def seed_if_missing(session: AsyncSession) -> SeedResult:
    """Insert absent canonical rows atomically without resetting mutable parking state.

    When the caller already owns a transaction, this function participates in it. Otherwise,
    it opens and commits one transaction for the complete seed operation.
    """
    if session.in_transaction():
        return await _seed_if_missing(session)

    async with session.begin():
        return await _seed_if_missing(session)


__all__ = [
    "DEMO_START_NODE_ID",
    "DEMO_USER_ID",
    "DEMO_VEHICLE_ID",
    "SeedResult",
    "SeedValidationError",
    "seed_if_missing",
]
