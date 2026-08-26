"""Deterministic, in-memory builder for the canonical F1-F3 parking maps.

Every floor repeats the same Section 5 layout: four zones of ten slots, three checkpoints,
one elevator and one ramp. Only F1 owns the public entrance and exit of the whole facility.

Section 5 does not define coordinates for the slot destination nodes. This module uses an
explicit display-only formula: each zone has two rows of five slots, with x coordinates
evenly interpolated from its west aisle to its east aisle. For north zones A/B, rows 01-05
and 06-10 use y=22 and y=26; for south zones C/D, they use y=74 and y=78. Floors reuse the
same coordinates because the UI renders one floor at a time. Edge weights remain canonical
metres and are not derived from these display coordinates.

Floors are joined by two mode-restricted connectors so that Phase 11 routing never has to
guess: ramps carry VEHICLE traffic, elevators carry PEDESTRIAN traffic.
"""

from collections import Counter, deque
from dataclasses import dataclass

from src.models.schemas import FLOOR_IDS, MapNodeType, RouteMode, SlotStatus

FLOOR_ID = "F1"
ZONE_IDS = ("A", "B", "C", "D")

SLOTS_PER_FLOOR = 40
EV_SLOTS_PER_FLOOR = 10
NODES_PER_FLOOR_WITH_GATES = 55
NODES_PER_FLOOR_WITHOUT_GATES = 53
EDGES_PER_FLOOR_WITH_GATES = 59
EDGES_PER_FLOOR_WITHOUT_GATES = 57
INTER_FLOOR_EDGE_COUNT = 4

EXPECTED_SLOT_COUNT = SLOTS_PER_FLOOR * len(FLOOR_IDS)
EXPECTED_NODE_COUNT = NODES_PER_FLOOR_WITH_GATES + NODES_PER_FLOOR_WITHOUT_GATES * 2
EXPECTED_EDGE_COUNT = EDGES_PER_FLOOR_WITH_GATES + EDGES_PER_FLOOR_WITHOUT_GATES * 2 + INTER_FLOOR_EDGE_COUNT

RAMP_INTER_FLOOR_DISTANCE_M = 30.0
ELEVATOR_INTER_FLOOR_DISTANCE_M = 12.0


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
    allowed_mode: RouteMode | None = None


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


# Shared per-floor layout. Suffixes are prefixed with the floor ID when a floor is built.
_FLOOR_NODE_SPECS: tuple[tuple[str, MapNodeType, float, float], ...] = (
    ("CP1", MapNodeType.CHECKPOINT, 15, 50),
    ("CP2", MapNodeType.CHECKPOINT, 50, 50),
    ("CP3", MapNodeType.CHECKPOINT, 85, 50),
    ("ELEVATOR", MapNodeType.ELEVATOR, 50, 92),
    ("RAMP", MapNodeType.RAMP, 85, 75),
    ("A-W", MapNodeType.AISLE, 25, 30),
    ("A-E", MapNodeType.AISLE, 42, 30),
    ("B-W", MapNodeType.AISLE, 58, 30),
    ("B-E", MapNodeType.AISLE, 75, 30),
    ("C-W", MapNodeType.AISLE, 25, 70),
    ("C-E", MapNodeType.AISLE, 42, 70),
    ("D-W", MapNodeType.AISLE, 58, 70),
    ("D-E", MapNodeType.AISLE, 75, 70),
)

# Entrance and exit belong to the facility, not to every floor (issue: no fake gates on F2/F3).
_GATE_NODE_SPECS: tuple[tuple[str, MapNodeType, float, float], ...] = (
    ("ENTRANCE", MapNodeType.ENTRANCE, 0, 50),
    ("EXIT", MapNodeType.EXIT, 100, 50),
)

_FLOOR_EDGE_SPECS: tuple[tuple[str, str, float, RouteMode | None], ...] = (
    ("CP1", "CP2", 35, None),
    ("CP2", "CP3", 35, None),
    ("CP1", "A-W", 22, None),
    ("A-W", "A-E", 17, None),
    ("A-E", "CP2", 22, None),
    ("CP2", "B-W", 22, None),
    ("B-W", "B-E", 17, None),
    ("B-E", "CP3", 22, None),
    ("CP1", "C-W", 22, None),
    ("C-W", "C-E", 17, None),
    ("C-E", "CP2", 22, None),
    ("CP2", "D-W", 22, None),
    ("D-W", "D-E", 17, None),
    ("D-E", "CP3", 22, None),
    # Elevator access is pedestrian-only so vehicle routes can never enter it.
    ("C-E", "ELEVATOR", 23, RouteMode.PEDESTRIAN),
    ("D-W", "ELEVATOR", 23, RouteMode.PEDESTRIAN),
    # Ramp access is vehicle-only so pedestrian routes never walk up a vehicle ramp.
    ("CP3", "RAMP", 25, RouteMode.VEHICLE),
)

_GATE_EDGE_SPECS: tuple[tuple[str, str, float, RouteMode | None], ...] = (
    ("ENTRANCE", "CP1", 15, None),
    ("CP3", "EXIT", 15, None),
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


def _slot_id(zone_id: str, slot_number: int, floor_id: str = FLOOR_ID) -> str:
    return f"{floor_id}-{zone_id}{slot_number:02d}"


def _slot_aisle_id(zone_id: str, slot_number: int, floor_id: str = FLOOR_ID) -> str:
    position_in_row = (slot_number - 1) % 5 + 1
    side = "W" if position_in_row <= 3 else "E"
    return f"{floor_id}-{zone_id}-{side}"


def _floor_has_gates(floor_id: str) -> bool:
    return floor_id == FLOOR_ID


def _floor_node_specs(floor_id: str) -> tuple[tuple[str, MapNodeType, float, float], ...]:
    if _floor_has_gates(floor_id):
        return _GATE_NODE_SPECS[:1] + _FLOOR_NODE_SPECS[:3] + _GATE_NODE_SPECS[1:] + _FLOOR_NODE_SPECS[3:]
    return _FLOOR_NODE_SPECS


def _floor_edge_specs(floor_id: str) -> tuple[tuple[str, str, float, RouteMode | None], ...]:
    if _floor_has_gates(floor_id):
        return _GATE_EDGE_SPECS[:1] + _FLOOR_EDGE_SPECS + _GATE_EDGE_SPECS[1:]
    return _FLOOR_EDGE_SPECS


def build_canonical_floor_map(floor_id: str) -> ParkingMap:
    """Build one floor's canonical nodes, edges and slots without inter-floor connectors."""
    if floor_id not in FLOOR_IDS:
        raise ValueError(f"floor {floor_id} is outside the canonical F1-F3 contract")

    slots: list[ParkingSlot] = []
    slot_nodes: list[MapNode] = []
    slot_edges: list[MapEdge] = []

    for zone_id in ZONE_IDS:
        for slot_number in range(1, 11):
            slot_id = _slot_id(zone_id, slot_number, floor_id)
            aisle_id = _slot_aisle_id(zone_id, slot_number, floor_id)
            x, y = slot_coordinates(zone_id, slot_number)
            slots.append(
                ParkingSlot(
                    id=slot_id,
                    floor_id=floor_id,
                    zone_id=zone_id,
                    node_id=aisle_id,
                    status=SlotStatus.AVAILABLE,
                    has_charger=zone_id in {"C", "D"} and slot_number <= 5,
                    is_accessible=False,
                )
            )
            slot_nodes.append(MapNode(slot_id, floor_id, MapNodeType.SLOT, x, y))
            slot_edges.append(MapEdge(aisle_id, slot_id, 4))

    core_nodes = tuple(
        MapNode(f"{floor_id}-{suffix}", floor_id, node_type, x, y)
        for suffix, node_type, x, y in _floor_node_specs(floor_id)
    )
    core_edges = tuple(
        MapEdge(f"{floor_id}-{from_suffix}", f"{floor_id}-{to_suffix}", distance, allowed_mode=mode)
        for from_suffix, to_suffix, distance, mode in _floor_edge_specs(floor_id)
    )
    return ParkingMap(
        nodes=core_nodes + tuple(slot_nodes),
        edges=core_edges + tuple(slot_edges),
        slots=tuple(slots),
    )


def build_inter_floor_edges() -> tuple[MapEdge, ...]:
    """Build the mode-restricted connectors that join adjacent floors."""
    edges: list[MapEdge] = []
    for lower, upper in zip(FLOOR_IDS, FLOOR_IDS[1:], strict=False):
        edges.append(
            MapEdge(
                f"{lower}-RAMP",
                f"{upper}-RAMP",
                RAMP_INTER_FLOOR_DISTANCE_M,
                allowed_mode=RouteMode.VEHICLE,
            )
        )
        edges.append(
            MapEdge(
                f"{lower}-ELEVATOR",
                f"{upper}-ELEVATOR",
                ELEVATOR_INTER_FLOOR_DISTANCE_M,
                allowed_mode=RouteMode.PEDESTRIAN,
            )
        )
    return tuple(edges)


def build_canonical_parking_map() -> ParkingMap:
    """Build the full F1-F3 map in stable floor order without I/O."""
    nodes: list[MapNode] = []
    edges: list[MapEdge] = []
    slots: list[ParkingSlot] = []

    for floor_id in FLOOR_IDS:
        floor_map = build_canonical_floor_map(floor_id)
        nodes.extend(floor_map.nodes)
        edges.extend(floor_map.edges)
        slots.extend(floor_map.slots)

    edges.extend(build_inter_floor_edges())
    return ParkingMap(nodes=tuple(nodes), edges=tuple(edges), slots=tuple(slots))


def build_canonical_f1_map() -> ParkingMap:
    """Build only the F1 floor. Retained for callers that predate multi-floor support."""
    return build_canonical_floor_map(FLOOR_ID)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParkingMapValidationError(message)


def _edge_key(from_node: str, to_node: str) -> frozenset[str]:
    return frozenset((from_node, to_node))


def _expected_floor_edges(floor_id: str) -> dict[frozenset[str], tuple[float, RouteMode | None]]:
    expected = {
        _edge_key(f"{floor_id}-{from_suffix}", f"{floor_id}-{to_suffix}"): (float(distance), mode)
        for from_suffix, to_suffix, distance, mode in _floor_edge_specs(floor_id)
    }
    expected.update(
        {
            _edge_key(
                _slot_aisle_id(zone, number, floor_id),
                _slot_id(zone, number, floor_id),
            ): (4.0, None)
            for zone in ZONE_IDS
            for number in range(1, 11)
        }
    )
    return expected


def _validate_floor_slots(
    parking_map: ParkingMap,
    floor_id: str,
    node_by_id: dict[str, MapNode],
) -> None:
    floor_slots = [slot for slot in parking_map.slots if slot.floor_id == floor_id]
    _require(
        len(floor_slots) == SLOTS_PER_FLOOR,
        f"floor {floor_id} must contain {SLOTS_PER_FLOOR} slots",
    )

    zone_counts = Counter(slot.zone_id for slot in floor_slots)
    _require(
        zone_counts == Counter({zone: 10 for zone in ZONE_IDS}),
        f"each zone on {floor_id} must have 10 slots",
    )

    expected_ev_ids = {_slot_id(zone, number, floor_id) for zone in ("C", "D") for number in range(1, 6)}
    actual_ev_ids = {slot.id for slot in floor_slots if slot.has_charger}
    _require(
        actual_ev_ids == expected_ev_ids,
        f"EV allocation on {floor_id} must be C01-C05 and D01-D05",
    )

    for slot in floor_slots:
        slot_number = int(slot.id[-2:])
        _require(slot.status is SlotStatus.AVAILABLE, f"slot must start AVAILABLE: {slot.id}")
        _require(not slot.is_accessible, f"slot must start non-accessible: {slot.id}")
        _require(slot.node_id in node_by_id, f"slot aisle reference does not exist: {slot.id}")
        _require(
            slot.node_id == _slot_aisle_id(slot.zone_id, slot_number, floor_id),
            f"slot has incorrect aisle attachment: {slot.id}",
        )
        slot_node = node_by_id[slot.id]
        expected_x, expected_y = slot_coordinates(slot.zone_id, slot_number)
        _require(
            (slot_node.floor_id, slot_node.type, slot_node.x, slot_node.y)
            == (floor_id, MapNodeType.SLOT, expected_x, expected_y),
            f"slot node coordinates are not deterministic: {slot.id}",
        )


def _validate_shared_structure(
    parking_map: ParkingMap,
    floor_ids: tuple[str, ...],
    *,
    expected_edges: dict[frozenset[str], tuple[float, RouteMode | None]],
) -> dict[str, set[str]]:
    slot_ids = [slot.id for slot in parking_map.slots]
    node_ids = [node.id for node in parking_map.nodes]
    _require(len(slot_ids) == len(set(slot_ids)), "slot IDs must be unique")
    _require(len(node_ids) == len(set(node_ids)), "node IDs must be unique")

    expected_slot_ids = {
        _slot_id(zone, number, floor_id) for floor_id in floor_ids for zone in ZONE_IDS for number in range(1, 11)
    }
    expected_core_ids = {f"{floor_id}-{suffix}" for floor_id in floor_ids for suffix, *_ in _floor_node_specs(floor_id)}
    _require(set(slot_ids) == expected_slot_ids, "slot IDs are not canonical")
    _require(set(node_ids) == expected_core_ids | expected_slot_ids, "node IDs are not canonical")

    node_by_id = {node.id: node for node in parking_map.nodes}
    for floor_id in floor_ids:
        for suffix, node_type, x, y in _floor_node_specs(floor_id):
            node = node_by_id[f"{floor_id}-{suffix}"]
            _require(
                (node.floor_id, node.type, node.x, node.y) == (floor_id, node_type, float(x), float(y)),
                f"canonical node mismatch: {node.id}",
            )
        _validate_floor_slots(parking_map, floor_id, node_by_id)

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

    actual_edges = {
        _edge_key(edge.from_node, edge.to_node): (edge.distance_m, edge.allowed_mode) for edge in parking_map.edges
    }
    _require(
        actual_edges == expected_edges,
        "edge endpoints, canonical distances or mode restrictions are incorrect",
    )

    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in parking_map.edges:
        adjacency[edge.from_node].add(edge.to_node)
        adjacency[edge.to_node].add(edge.from_node)
    return adjacency


def _require_connected(adjacency: dict[str, set[str]], start_node_id: str) -> None:
    visited = {start_node_id}
    pending = deque([start_node_id])
    while pending:
        current = pending.popleft()
        for neighbor in adjacency[current] - visited:
            visited.add(neighbor)
            pending.append(neighbor)
    _require(visited == set(adjacency), f"every node must be connected to {start_node_id}")


def validate_canonical_parking_map(parking_map: ParkingMap) -> None:
    """Validate the full F1-F3 contract: counts, content, references and connectivity."""
    _require(
        len(parking_map.slots) == EXPECTED_SLOT_COUNT,
        f"map must contain {EXPECTED_SLOT_COUNT} slots",
    )
    _require(
        len(parking_map.nodes) == EXPECTED_NODE_COUNT,
        f"map must contain {EXPECTED_NODE_COUNT} nodes",
    )
    _require(
        len(parking_map.edges) == EXPECTED_EDGE_COUNT,
        f"map must contain {EXPECTED_EDGE_COUNT} edges",
    )

    expected_edges: dict[frozenset[str], tuple[float, RouteMode | None]] = {}
    for floor_id in FLOOR_IDS:
        expected_edges.update(_expected_floor_edges(floor_id))
    for edge in build_inter_floor_edges():
        expected_edges[_edge_key(edge.from_node, edge.to_node)] = (
            edge.distance_m,
            edge.allowed_mode,
        )

    adjacency = _validate_shared_structure(parking_map, FLOOR_IDS, expected_edges=expected_edges)

    for floor_id in FLOOR_IDS:
        _require(
            adjacency[f"{floor_id}-ELEVATOR"] >= {f"{floor_id}-C-E", f"{floor_id}-D-W"},
            f"{floor_id} elevator must connect to its C-E and D-W aisles",
        )
        _require(
            f"{floor_id}-ELEVATOR" not in adjacency[f"{floor_id}-CP2"],
            f"{floor_id}-CP2 must not connect directly to the elevator",
        )
        _require(
            adjacency[f"{floor_id}-RAMP"] >= {f"{floor_id}-CP3"},
            f"{floor_id} ramp must connect to its CP3 checkpoint",
        )

    gate_nodes = {node.id for node in parking_map.nodes if node.type in {MapNodeType.ENTRANCE, MapNodeType.EXIT}}
    _require(
        gate_nodes == {"F1-ENTRANCE", "F1-EXIT"},
        "only F1 may own the public entrance and exit",
    )

    _require_connected(adjacency, "F1-CP2")


def validate_canonical_f1_map(parking_map: ParkingMap) -> None:
    """Validate one standalone F1 floor. Retained for callers that predate multi-floor support."""
    _require(
        len(parking_map.slots) == SLOTS_PER_FLOOR,
        f"map must contain {SLOTS_PER_FLOOR} slots",
    )
    _require(
        len(parking_map.nodes) == NODES_PER_FLOOR_WITH_GATES,
        f"map must contain {NODES_PER_FLOOR_WITH_GATES} nodes",
    )
    _require(
        len(parking_map.edges) == EDGES_PER_FLOOR_WITH_GATES,
        f"map must contain {EDGES_PER_FLOOR_WITH_GATES} edges",
    )

    adjacency = _validate_shared_structure(
        parking_map,
        (FLOOR_ID,),
        expected_edges=_expected_floor_edges(FLOOR_ID),
    )
    _require(
        adjacency["F1-ELEVATOR"] == {"F1-C-E", "F1-D-W"},
        "elevator must connect only to F1-C-E and F1-D-W",
    )
    _require(
        "F1-ELEVATOR" not in adjacency["F1-CP2"],
        "F1-CP2 must not connect directly to the elevator",
    )
    _require_connected(adjacency, "F1-CP2")


__all__ = [
    "ELEVATOR_INTER_FLOOR_DISTANCE_M",
    "EV_SLOTS_PER_FLOOR",
    "EXPECTED_EDGE_COUNT",
    "EXPECTED_NODE_COUNT",
    "EXPECTED_SLOT_COUNT",
    "FLOOR_IDS",
    "MapEdge",
    "MapNode",
    "ParkingMap",
    "ParkingMapValidationError",
    "ParkingSlot",
    "RAMP_INTER_FLOOR_DISTANCE_M",
    "SLOTS_PER_FLOOR",
    "build_canonical_f1_map",
    "build_canonical_floor_map",
    "build_canonical_parking_map",
    "build_inter_floor_edges",
    "slot_coordinates",
    "validate_canonical_f1_map",
    "validate_canonical_parking_map",
]
