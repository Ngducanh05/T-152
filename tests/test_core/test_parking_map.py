from dataclasses import replace

import pytest

from src.core.parking_map import (
    MapEdge,
    ParkingMapValidationError,
    build_canonical_f1_map,
    slot_coordinates,
    validate_canonical_f1_map,
)
from src.models.schemas import MapNodeType


def test_builder_is_deterministic_and_canonical_map_validates():
    first = build_canonical_f1_map()
    second = build_canonical_f1_map()

    assert first == second
    assert first is not second
    assert len(first.slots) == 40
    assert len(first.nodes) == 54
    assert len(first.edges) == 58
    validate_canonical_f1_map(first)


def test_slot_ids_ev_allocation_and_aisle_attachments_are_exact():
    parking_map = build_canonical_f1_map()
    slots = {slot.id: slot for slot in parking_map.slots}

    assert set(slots) == {
        f"F1-{zone}{number:02d}" for zone in "ABCD" for number in range(1, 11)
    }
    assert {slot.id for slot in parking_map.slots if slot.has_charger} == {
        f"F1-{zone}{number:02d}" for zone in "CD" for number in range(1, 6)
    }
    for zone in "ABCD":
        for number in range(1, 11):
            position_in_row = (number - 1) % 5 + 1
            expected_side = "W" if position_in_row <= 3 else "E"
            assert slots[f"F1-{zone}{number:02d}"].node_id == f"F1-{zone}-{expected_side}"


def test_core_and_assumed_slot_coordinates_are_exact():
    parking_map = build_canonical_f1_map()
    nodes = {node.id: node for node in parking_map.nodes}

    assert (nodes["F1-ENTRANCE"].x, nodes["F1-ENTRANCE"].y) == (0, 50)
    assert (nodes["F1-CP2"].x, nodes["F1-CP2"].y) == (50, 50)
    assert (nodes["F1-ELEVATOR"].x, nodes["F1-ELEVATOR"].y) == (50, 92)
    assert nodes["F1-A-W"].type is MapNodeType.AISLE
    assert nodes["F1-D10"].type is MapNodeType.SLOT

    for zone in "ABCD":
        for number in range(1, 11):
            node = nodes[f"F1-{zone}{number:02d}"]
            assert (node.x, node.y) == slot_coordinates(zone, number)


def test_edges_are_bidirectional_stored_once_with_canonical_distances():
    parking_map = build_canonical_f1_map()
    edges = {
        frozenset((edge.from_node, edge.to_node)): edge for edge in parking_map.edges
    }

    assert len(edges) == len(parking_map.edges) == 58
    assert all(edge.bidirectional and edge.enabled for edge in parking_map.edges)
    assert edges[frozenset(("F1-CP1", "F1-CP2"))].distance_m == 35
    assert edges[frozenset(("F1-C-E", "F1-ELEVATOR"))].distance_m == 23
    assert edges[frozenset(("F1-D-W", "F1-ELEVATOR"))].distance_m == 23
    assert frozenset(("F1-CP2", "F1-ELEVATOR")) not in edges

    slot_edges = [
        edge
        for edge in parking_map.edges
        if edge.from_node.endswith(("-W", "-E")) and edge.to_node[-2:].isdigit()
    ]
    assert len(slot_edges) == 40
    assert all(edge.distance_m == 4 for edge in slot_edges)


def test_all_nodes_are_connected_and_elevator_has_only_canonical_neighbors():
    parking_map = build_canonical_f1_map()
    adjacency = {node.id: set() for node in parking_map.nodes}
    for edge in parking_map.edges:
        adjacency[edge.from_node].add(edge.to_node)
        adjacency[edge.to_node].add(edge.from_node)

    assert adjacency["F1-ELEVATOR"] == {"F1-C-E", "F1-D-W"}
    visited = {"F1-CP2"}
    pending = ["F1-CP2"]
    while pending:
        current = pending.pop()
        for neighbor in adjacency[current] - visited:
            visited.add(neighbor)
            pending.append(neighbor)
    assert visited == set(adjacency)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda parking_map: replace(
                parking_map, nodes=parking_map.nodes[:-1] + (parking_map.nodes[0],)
            ),
            "node IDs must be unique",
        ),
        (
            lambda parking_map: replace(
                parking_map,
                slots=(replace(parking_map.slots[0], node_id="F1-MISSING"),)
                + parking_map.slots[1:],
            ),
            "slot aisle reference does not exist",
        ),
        (
            lambda parking_map: replace(
                parking_map,
                slots=parking_map.slots[:20]
                + (replace(parking_map.slots[20], has_charger=False),)
                + parking_map.slots[21:],
            ),
            "EV allocation",
        ),
        (
            lambda parking_map: replace(
                parking_map,
                edges=parking_map.edges[:-1]
                + (MapEdge("F1-CP2", "F1-ELEVATOR", 1),),
            ),
            "edge endpoints or canonical distances",
        ),
        (
            lambda parking_map: replace(
                parking_map,
                edges=parking_map.edges[:-1]
                + (MapEdge("F1-D-E", "F1-MISSING", 4),),
            ),
            "every edge endpoint",
        ),
    ],
)
def test_validator_rejects_invalid_canonical_maps(mutation, message):
    with pytest.raises(ParkingMapValidationError, match=message):
        validate_canonical_f1_map(mutation(build_canonical_f1_map()))
