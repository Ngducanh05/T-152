"""Turn a canonical route path into concise Vietnamese driving guidance."""

from __future__ import annotations

import re

_SLOT_ID = re.compile(r"^F1-([A-D])(\d{2})$")
_AISLE_ID = re.compile(r"^F1-([A-D])-([WE])$")


def vietnamese_route_guidance(path: list[str], distance_m: float) -> str:
    """Describe navigation without exposing internal checkpoint or aisle IDs."""
    if not path:
        return "Hiện chưa có tuyến đường hợp lệ."

    destination = path[-1]
    slot_match = _SLOT_ID.fullmatch(destination)
    if not slot_match:
        return f"Đi theo tuyến được đánh dấu trên bản đồ đến điểm đích. Quãng đường khoảng {distance_m:g} m."

    zone, number_text = slot_match.groups()
    number = int(number_text)
    aisle_match = next(
        (_AISLE_ID.fullmatch(node_id) for node_id in reversed(path[:-1]) if _AISLE_ID.fullmatch(node_id)),
        None,
    )
    side = aisle_match.group(2) if aisle_match else "W"
    is_north = zone in {"A", "B"}
    entry_turn = "trái" if is_north else "phải"
    # From the west edge, northbound traffic turns right into an east-facing bay
    # and southbound traffic turns left. The east edge is the mirror image.
    bay_turn = (
        "phải" if (side == "W" and is_north) or (side == "E" and not is_north) else "trái"
    )
    start_copy = "Từ cổng vào" if path[0] == "F1-ENTRANCE" else "Từ vị trí hiện tại"
    row_copy = "dãy đầu" if number <= 5 else "dãy thứ hai"

    return (
        f"{start_copy}, đi thẳng theo đường chính. "
        f"Đến lối vào khu {zone}, rẽ {entry_turn} và đi theo đường bao quanh khu. "
        f"Tại {row_copy}, rẽ {bay_turn} vào ô {zone}{number:02d}. "
        f"Quãng đường khoảng {distance_m:g} m."
    )


__all__ = ["vietnamese_route_guidance"]
