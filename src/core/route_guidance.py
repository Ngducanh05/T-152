"""Turn a canonical route path into concise Vietnamese driving guidance."""

from __future__ import annotations

import re

_SLOT_ID = re.compile(r"^F[1-3]-([A-D])(\d{2})$")
_AISLE_ID = re.compile(r"^F[1-3]-([A-D])-([WE])$")
_FLOOR_PREFIX = re.compile(r"^(F[1-3])-")
_RAMP_ID = re.compile(r"^F[1-3]-RAMP$")
_ELEVATOR_ID = re.compile(r"^F[1-3]-ELEVATOR$")

_FLOOR_NAMES = {"F1": "tầng 1", "F2": "tầng 2", "F3": "tầng 3"}


def _floor_label(node_id: str) -> str:
    m = _FLOOR_PREFIX.match(node_id)
    return _FLOOR_NAMES.get(m.group(1), m.group(1)) if m else ""


def _detect_floor_transitions(path: list[str]) -> list[str]:
    """Return human-readable floor-change instructions embedded in the path."""
    instructions: list[str] = []
    for i in range(1, len(path)):
        prev_m = _FLOOR_PREFIX.match(path[i - 1])
        curr_m = _FLOOR_PREFIX.match(path[i])
        if not prev_m or not curr_m:
            continue
        prev_floor, curr_floor = prev_m.group(1), curr_m.group(1)
        if prev_floor != curr_floor:
            via = "đường dốc (ramp)" if _RAMP_ID.fullmatch(path[i]) or _RAMP_ID.fullmatch(path[i - 1]) else "thang máy"
            instructions.append(
                f"Di chuyển từ {_FLOOR_NAMES.get(prev_floor, prev_floor)} lên {_FLOOR_NAMES.get(curr_floor, curr_floor)} bằng {via}."
            )
    return instructions


def vietnamese_route_guidance(path: list[str], distance_m: float) -> str:
    """Describe navigation without exposing internal checkpoint or aisle IDs."""
    if not path:
        return "Hiện chưa có tuyến đường hợp lệ."

    destination = path[-1]
    slot_match = _SLOT_ID.fullmatch(destination)
    floor_transitions = _detect_floor_transitions(path)
    transition_copy = " ".join(floor_transitions)

    if not slot_match:
        base = f"Đi theo tuyến được đánh dấu trên bản đồ đến điểm đích."
        if transition_copy:
            base = f"{transition_copy} {base}"
        return f"{base} Quãng đường khoảng {distance_m:g} m."

    zone, number_text = slot_match.groups()
    number = int(number_text)
    dest_floor = _floor_label(destination)
    aisle_match = next(
        (_AISLE_ID.fullmatch(node_id) for node_id in reversed(path[:-1]) if _AISLE_ID.fullmatch(node_id)),
        None,
    )
    side = aisle_match.group(2) if aisle_match else "W"
    is_north = zone in {"A", "B"}
    entry_turn = "trái" if is_north else "phải"
    bay_turn = (
        "phải" if (side == "W" and is_north) or (side == "E" and not is_north) else "trái"
    )
    start_copy = "Từ cổng vào" if path[0] == "F1-ENTRANCE" else "Từ vị trí hiện tại"
    row_copy = "dãy đầu" if number <= 5 else "dãy thứ hai"

    guidance = f"{start_copy}, đi thẳng theo đường chính. "
    if transition_copy:
        guidance += f"{transition_copy} "
    guidance += (
        f"Đến lối vào khu {zone} ({dest_floor}), rẽ {entry_turn} và đi theo đường bao quanh khu. "
        f"Tại {row_copy}, rẽ {bay_turn} vào ô {zone}{number:02d}. "
        f"Quãng đường khoảng {distance_m:g} m."
    )
    return guidance


__all__ = ["vietnamese_route_guidance"]
