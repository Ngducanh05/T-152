"""Deterministic, in-memory builder for the canonical F1 parking map.

Section 5 does not define coordinates for the 40 slot destination nodes. This module uses
an explicit display-only formula: each zone has two rows of five slots, with x coordinates
evenly interpolated from its west aisle to its east aisle. For north zones A/B, rows 01-05
and 06-10 use y=22 and y=26; for south zones C/D, they use y=74 and y=78. Edge weights
remain the canonical 4 metres and are not derived from these display coordinates.
"""

from collections import Counter, deque
from dataclasses import dataclass

from src.models.schemas import MapNodeType, SlotStatus

FLOOR_ID = "F1"
ZONE_IDS = ("A", "B", "C", "D")
EXPECTED_SLOT_COUNT = 40
EXPECTED_NODE_COUNT = 54
EXPECTED_EDGE_COUNT = 58


@dataclass(frozen=True, slots=True)
class MapNode:
    id: str
    floor_id: str
    type: MapNodeType
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class MapEdge:
    from_node: str
    to_node: str
    distance_m: float
    bidirectional: bool = True
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ParkingSlot:
    id: str
    floor_id: str
    zone_id: str
    node_id: str
    status: SlotStatus
    has_charger: bool
    is_accessible: bool


@dataclass(frozen=True, slots=True)
class ParkingMap:
    nodes: tuple[MapNode, ...]
    edges: tuple[MapEdge, ...]
    slots: tuple[ParkingSlot, ...]


class ParkingMapValidationError(ValueError):
    """Raised when map data differs from the canonical Section 5 definition."""


_CORE_NODE_SPECS: tuple[tuple[str, MapNodeType, float, float], ...] = (
    ("F1-ENTRANCE", MapNodeType.ENTRANCE, 0, 50),
    ("F1-CP1", MapNodeType.CHECKPOINT, 15, 50),
    ("F1-CP2", MapNodeType.CHECKPOINT, 50, 50),
    ("F1-CP3", MapNodeType.CHECKPOINT, 85, 50),
    ("F1-EXIT", MapNodeType.EXIT, 100, 50),
    ("F1-ELEVATOR", MapNodeType.ELEVATOR, 50, 92),
    ("F1-A-W", MapNodeType.AISLE, 25, 30),
    ("F1-A-E", MapNodeType.AISLE, 42, 30),
    ("F1-B-W", MapNodeType.AISLE, 58, 30),
    ("F1-B-E", MapNodeType.AISLE, 75, 30),
    ("F1-C-W", MapNodeType.AISLE, 25, 70),
    ("F1-C-E", MapNodeType.AISLE, 42, 70),
    ("F1-D-W", MapNodeType.AISLE, 58, 70),
    ("F1-D-E", MapNodeType.AISLE, 75, 70),
)

_CORE_EDGE_SPECS: tuple[tuple[str, str, float], ...] = (
    ("F1-ENTRANCE", "F1-CP1", 15),
    ("F1-CP1", "F1-CP2", 35),
    ("F1-CP2", "F1-CP3", 35),
    ("F1-CP3", "F1-EXIT", 15),
    ("F1-CP1", "F1-A-W", 22),
    ("F1-A-W", "F1-A-E", 17),
    ("F1-A-E", "F1-CP2", 22),
    ("F1-CP2", "F1-B-W", 22),
    ("F1-B-W", "F1-B-E", 17),
    ("F1-B-E", "F1-CP3", 22),
    ("F1-CP1", "F1-C-W", 22),
    ("F1-C-W", "F1-C-E", 17),
    ("F1-C-E", "F1-CP2", 22),
    ("F1-CP2", "F1-D-W", 22),
    ("F1-D-W", "F1-D-E", 17),
    ("F1-D-E", "F1-CP3", 22),
    ("F1-C-E", "F1-ELEVATOR", 23),
    ("F1-D-W", "F1-ELEVATOR", 23),
)

_AISLE_X = {
    "A": (25.0, 42.0),
    "B": (58.0, 75.0),
    "C": (25.0, 42.0),
    "D": (58.0, 75.0),
}
_SLOT_ROW_Y = {
    "A": (22.0, 26.0),
    "B": (22.0, 26.0),
    "C": (74.0, 78.0),
    "D": (74.0, 78.0),
}


def slot_coordinates(zone_id: str, slot_number: int) -> tuple[float, float]:
    """Return the documented deterministic display coordinates for one slot node."""
    if zone_id not in ZONE_IDS or not 1 <= slot_number <= 10:
        raise ValueError("slot coordinates require zone A-D and slot number 1-10")

    row = 0 if slot_number <= 5 else 1
    position = (slot_number - 1) % 5
    west_x, east_x = _AISLE_X[zone_id]
    x = west_x + (east_x - west_x) * position / 4
    return x, _SLOT_ROW_Y[zone_id][row]


def _slot_id(zone_id: str, slot_number: int) -> str:
    return f"F1-{zone_id}{slot_number:02d}"


def _slot_aisle_id(zone_id: str, slot_number: int) -> str:
    position_in_row = (slot_number - 1) % 5 + 1
    side = "W" if position_in_row <= 3 else "E"
    return f"F1-{zone_id}-{side}"


def build_canonical_f1_map() -> ParkingMap:
    """Build a fresh canonical map in stable Section 5 order without I/O."""
    slots: list[ParkingSlot] = []
    slot_nodes: list[MapNode] = []
    slot_edges: list[MapEdge] = []

    for zone_id in ZONE_IDS:
        for slot_number in range(1, 11):
            slot_id = _slot_id(zone_id, slot_number)
            aisle_id = _slot_aisle_id(zone_id, slot_number)
            x, y = slot_coordinates(zone_id, slot_number)
            slots.append(
                ParkingSlot(
                    id=slot_id,
                    floor_id=FLOOR_ID,
                    zone_id=zone_id,
                    node_id=aisle_id,
                    status=SlotStatus.AVAILABLE,
                    has_charger=zone_id in {"C", "D"} and slot_number <= 5,
                    is_accessible=False,
                )
            )
            slot_nodes.append(MapNode(slot_id, FLOOR_ID, MapNodeType.SLOT, x, y))
            slot_edges.append(MapEdge(aisle_id, slot_id, 4))

    core_nodes = tuple(
        MapNode(node_id, FLOOR_ID, node_type, x, y)
        for node_id, node_type, x, y in _CORE_NODE_SPECS
    )
    core_edges = tuple(MapEdge(from_node, to_node, distance) for from_node, to_node, distance in _CORE_EDGE_SPECS)
    return ParkingMap(
        nodes=core_nodes + tuple(slot_nodes),
        edges=core_edges + tuple(slot_edges),
        slots=tuple(slots),
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParkingMapValidationError(message)


def _edge_key(from_node: str, to_node: str) -> frozenset[str]:
    return frozenset((from_node, to_node))


def validate_canonical_f1_map(parking_map: ParkingMap) -> None:
    """Validate counts, canonical content, references, and undirected connectivity."""
    _require(len(parking_map.slots) == EXPECTED_SLOT_COUNT, "map must contain 40 slots")
    _require(len(parking_map.nodes) == EXPECTED_NODE_COUNT, "map must contain 54 nodes")
    _require(len(parking_map.edges) == EXPECTED_EDGE_COUNT, "map must contain 58 edges")

    slot_ids = [slot.id for slot in parking_map.slots]
    node_ids = [node.id for node in parking_map.nodes]
    _require(len(slot_ids) == len(set(slot_ids)), "slot IDs must be unique")
    _require(len(node_ids) == len(set(node_ids)), "node IDs must be unique")

    expected_slot_ids = {_slot_id(zone, number) for zone in ZONE_IDS for number in range(1, 11)}
    expected_core_ids = {node_id for node_id, *_ in _CORE_NODE_SPECS}
    _require(set(slot_ids) == expected_slot_ids, "slot IDs must match F1-A01 through F1-D10")
    _require(set(node_ids) == expected_core_ids | expected_slot_ids, "node IDs are not canonical")

    node_by_id = {node.id: node for node in parking_map.nodes}
    expected_core_nodes = {
        node_id: (node_type, float(x), float(y))
        for node_id, node_type, x, y in _CORE_NODE_SPECS
    }
    for node_id, (node_type, x, y) in expected_core_nodes.items():
        node = node_by_id[node_id]
        _require(
            (node.floor_id, node.type, node.x, node.y) == (FLOOR_ID, node_type, x, y),
            f"canonical node mismatch: {node_id}",
        )

    zone_counts = Counter(slot.zone_id for slot in parking_map.slots)
    _require(zone_counts == Counter({zone: 10 for zone in ZONE_IDS}), "each zone must have 10 slots")
    expected_ev_ids = {
        _slot_id(zone, number) for zone in ("C", "D") for number in range(1, 6)
    }
    actual_ev_ids = {slot.id for slot in parking_map.slots if slot.has_charger}
    _require(actual_ev_ids == expected_ev_ids, "EV allocation must be C01-C05 and D01-D05")

    for slot in parking_map.slots:
        slot_number = int(slot.id[-2:])
        _require(slot.floor_id == FLOOR_ID, f"slot has invalid floor: {slot.id}")
        _require(slot.status is SlotStatus.AVAILABLE, f"slot must start AVAILABLE: {slot.id}")
        _require(not slot.is_accessible, f"slot must start non-accessible: {slot.id}")
        _require(slot.node_id in node_by_id, f"slot aisle reference does not exist: {slot.id}")
        _require(
            slot.node_id == _slot_aisle_id(slot.zone_id, slot_number),
            f"slot has incorrect aisle attachment: {slot.id}",
        )
        slot_node = node_by_id[slot.id]
        expected_x, expected_y = slot_coordinates(slot.zone_id, slot_number)
        _require(
            (slot_node.floor_id, slot_node.type, slot_node.x, slot_node.y)
            == (FLOOR_ID, MapNodeType.SLOT, expected_x, expected_y),
            f"slot node coordinates are not deterministic: {slot.id}",
        )

    edge_keys = [_edge_key(edge.from_node, edge.to_node) for edge in parking_map.edges]
    _require(all(len(key) == 2 for key in edge_keys), "self edges are not allowed")
    _require(len(edge_keys) == len(set(edge_keys)), "bidirectional edges must be stored once")
    _require(
        all(edge.bidirectional and edge.enabled for edge in parking_map.edges),
        "all canonical edges must be enabled and bidirectional",
    )
    _require(
        all(edge.from_node in node_by_id and edge.to_node in node_by_id for edge in parking_map.edges),
        "every edge endpoint must reference an existing node",
    )

    expected_edges = {
        _edge_key(from_node, to_node): float(distance)
        for from_node, to_node, distance in _CORE_EDGE_SPECS
    }
    expected_edges.update(
        {
            _edge_key(_slot_aisle_id(zone, number), _slot_id(zone, number)): 4.0
            for zone in ZONE_IDS
            for number in range(1, 11)
        }
    )
    actual_edges = {
        _edge_key(edge.from_node, edge.to_node): edge.distance_m for edge in parking_map.edges
    }
    _require(actual_edges == expected_edges, "edge endpoints or canonical distances are incorrect")

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in parking_map.edges:
        adjacency[edge.from_node].add(edge.to_node)
        adjacency[edge.to_node].add(edge.from_node)

    _require(
        adjacency["F1-ELEVATOR"] == {"F1-C-E", "F1-D-W"},
        "elevator must connect only to F1-C-E and F1-D-W",
    )
    _require(
        "F1-ELEVATOR" not in adjacency["F1-CP2"],
        "F1-CP2 must not connect directly to the elevator",
    )

    visited = {"F1-CP2"}
    pending = deque(["F1-CP2"])
    while pending:
        current = pending.popleft()
        for neighbor in adjacency[current] - visited:
            visited.add(neighbor)
            pending.append(neighbor)
    _require(visited == set(node_ids), "every node must be connected to F1-CP2")


__all__ = [
    "EXPECTED_EDGE_COUNT",
    "EXPECTED_NODE_COUNT",
    "EXPECTED_SLOT_COUNT",
    "MapEdge",
    "MapNode",
    "ParkingMap",
    "ParkingMapValidationError",
    "ParkingSlot",
    "build_canonical_f1_map",
    "slot_coordinates",
    "validate_canonical_f1_map",
]
