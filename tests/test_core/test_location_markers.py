import pytest

from src.core.location_markers import (
    LOCATION_MARKERS,
    InvalidLocationQrError,
    LocationMarkerNotFoundError,
    resolve_location_qr,
)
from src.core.parking_map import build_canonical_parking_map


@pytest.mark.parametrize(
    ("payload", "node_id"),
    [
        ("parksmart:location:v1:PSLOC-F1-A-W", "F1-A-W"),
        ("parksmart:location:v1:PSLOC-F2-C-E", "F2-C-E"),
        ("parksmart:location:v1:PSLOC-F3-D-W", "F3-D-W"),
    ],
)
def test_resolve_location_qr_returns_allowlisted_aisle_marker(payload: str, node_id: str):
    assert resolve_location_qr(f"  {payload}  ").node_id == node_id


@pytest.mark.parametrize(
    "payload",
    ["", "parksmart:location:v1:", "F3-D-W", "https://evil.example/F3-D-W", "tầng 3 khu D"],
)
def test_invalid_location_qr_payloads_are_rejected(payload: str):
    with pytest.raises(InvalidLocationQrError):
        resolve_location_qr(payload)


def test_unknown_well_formed_marker_is_distinct_from_invalid_qr():
    with pytest.raises(LocationMarkerNotFoundError):
        resolve_location_qr("parksmart:location:v1:PSLOC-F3-Z-W")


def test_marker_catalog_has_unique_ids_and_canonical_aisle_nodes():
    canonical_nodes = {node.id for node in build_canonical_parking_map().nodes}
    assert len(LOCATION_MARKERS) == 24
    assert len(LOCATION_MARKERS) == len({marker.marker_id for marker in LOCATION_MARKERS.values()})
    assert {marker.node_id for marker in LOCATION_MARKERS.values()} <= canonical_nodes
