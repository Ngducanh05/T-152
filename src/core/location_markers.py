"""Trusted static QR markers for indoor location confirmation."""

import re
from dataclasses import dataclass

from src.models.schemas import FLOOR_IDS

LOCATION_QR_PREFIX = "parksmart:location:v1:"
MAX_LOCATION_QR_PAYLOAD_LENGTH = 256
_ZONE_IDS = ("A", "B", "C", "D")
_SIDES = (("W", "Tây"), ("E", "Đông"))
_MARKER_ID_PATTERN = re.compile(r"^PSLOC-F[1-3]-[A-Z]-[WE]$")


class InvalidLocationQrError(ValueError):
    """Raised when a value is not a ParkSmart v1 location QR payload."""


class LocationMarkerNotFoundError(LookupError):
    """Raised when a well-formed ParkSmart marker is not allowlisted."""


@dataclass(frozen=True, slots=True)
class LocationMarker:
    marker_id: str
    node_id: str
    floor_id: str
    zone_id: str
    label: str


def _marker(floor_id: str, zone_id: str, side: str, side_label: str) -> LocationMarker:
    marker_id = f"PSLOC-{floor_id}-{zone_id}-{side}"
    return LocationMarker(
        marker_id=marker_id,
        node_id=f"{floor_id}-{zone_id}-{side}",
        floor_id=floor_id,
        zone_id=zone_id,
        label=f"Tầng {floor_id[1:]} · Khu {zone_id} · lối {side_label}",
    )


LOCATION_MARKERS = {
    marker.marker_id: marker
    for floor_id in FLOOR_IDS
    for zone_id in _ZONE_IDS
    for side, side_label in _SIDES
    for marker in (_marker(floor_id, zone_id, side, side_label),)
}


def get_location_marker(marker_id: str) -> LocationMarker:
    marker = LOCATION_MARKERS.get(marker_id)
    if marker is None:
        raise LocationMarkerNotFoundError(f"Location marker {marker_id!r} was not found")
    return marker


def resolve_location_qr(qr_payload: str) -> LocationMarker:
    """Resolve a bounded ParkSmart v1 QR payload through the marker allowlist."""
    payload = qr_payload.strip()
    if (
        not payload
        or len(payload) > MAX_LOCATION_QR_PAYLOAD_LENGTH
        or not payload.startswith(LOCATION_QR_PREFIX)
    ):
        raise InvalidLocationQrError("QR payload is not a valid ParkSmart location QR")
    marker_id = payload.removeprefix(LOCATION_QR_PREFIX)
    if not _MARKER_ID_PATTERN.fullmatch(marker_id):
        raise InvalidLocationQrError("QR payload does not include a location marker ID")
    return get_location_marker(marker_id)


__all__ = [
    "LOCATION_MARKERS",
    "LOCATION_QR_PREFIX",
    "MAX_LOCATION_QR_PAYLOAD_LENGTH",
    "InvalidLocationQrError",
    "LocationMarker",
    "LocationMarkerNotFoundError",
    "get_location_marker",
    "resolve_location_qr",
]
