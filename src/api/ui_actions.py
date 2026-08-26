"""Deterministic, allowlisted UI actions derived from verified Agent state."""

import re
from collections.abc import Sequence, Set

from src.models.schemas import (
    ChatUIAction,
    ChatUIActionStyle,
    ChatUIActionType,
    RouteResult,
)

_CANONICAL_SLOT_ID = re.compile(r"^F[1-3]-[A-D](?:0[1-9]|10)$")
_MAX_UI_ACTIONS = 5


def _slot_ids(values: Sequence[str]) -> list[str]:
    return [
        slot_id
        for slot_id in dict.fromkeys(values)
        if _CANONICAL_SLOT_ID.fullmatch(slot_id)
    ]


def _action(
    *,
    action_id: str,
    action_type: ChatUIActionType,
    label: str,
    payload: dict[str, str] | None = None,
    style: ChatUIActionStyle = ChatUIActionStyle.SECONDARY,
    requires_confirmation: bool = False,
) -> ChatUIAction:
    if action_type is ChatUIActionType.SELECT_LOCATION:
        style = ChatUIActionStyle.SECONDARY
    return ChatUIAction(
        id=action_id,
        type=action_type,
        label=label,
        payload=payload or {},
        style=style,
        requires_confirmation=requires_confirmation,
    )


def derive_chat_ui_actions(
    *,
    current_location: str | None,
    recommended_slot_ids: Sequence[str],
    selected_slot: str | None,
    intent: str | None,
    successful_tool_names: Set[str],
    active_reservation_id: str | None = None,
    active_session_id: str | None = None,
    route: RouteResult | None = None,
) -> list[ChatUIAction]:
    """Build safe actions without inspecting LLM text or accepting arbitrary targets."""
    actions: list[ChatUIAction] = []
    canonical_selected_slot = (
        selected_slot
        if selected_slot is not None and _CANONICAL_SLOT_ID.fullmatch(selected_slot)
        else None
    )

    if not current_location:
        return [
            _action(
                action_id="scan-location-qr",
                action_type=ChatUIActionType.SCAN_LOCATION_QR,
                label="Quét QR vị trí",
                style=ChatUIActionStyle.PRIMARY,
            ),
            _action(
                action_id="select-location",
                action_type=ChatUIActionType.SELECT_LOCATION,
                label="Chọn vị trí thủ công",
                style=ChatUIActionStyle.SECONDARY,
            )
        ]

    if (
        "recommend_parking_slot" in successful_tool_names
        and recommended_slot_ids
    ):
        for slot_id in _slot_ids(recommended_slot_ids)[:3]:
            actions.append(
                _action(
                    action_id=f"select-slot:{slot_id.lower()}",
                    action_type=ChatUIActionType.SELECT_SLOT,
                    label=f"Chọn {slot_id}",
                    payload={"slot_id": slot_id},
                    style=ChatUIActionStyle.PRIMARY,
                )
            )
        return actions[:_MAX_UI_ACTIONS]

    if active_reservation_id:
        actions.append(
            _action(
                action_id="confirm-parking",
                action_type=ChatUIActionType.CONFIRM_PARKING,
                label="Xác nhận đã đỗ",
                style=ChatUIActionStyle.PRIMARY,
                requires_confirmation=True,
            )
        )
        actions.append(
            _action(
                action_id="cancel-reservation",
                action_type=ChatUIActionType.CANCEL,
                label="Hủy chỗ đã giữ",
                payload=(
                    {"slot_id": canonical_selected_slot}
                    if canonical_selected_slot is not None
                    else None
                ),
                style=ChatUIActionStyle.DANGER,
                requires_confirmation=True,
            )
        )
    elif active_session_id:
        actions.extend(
            [
                _action(
                    action_id="find-vehicle",
                    action_type=ChatUIActionType.FIND_VEHICLE,
                    label="Chỉ đường tới xe",
                    style=ChatUIActionStyle.PRIMARY,
                ),
                _action(
                    action_id="complete-session",
                    action_type=ChatUIActionType.COMPLETE_SESSION,
                    label="Kết thúc phiên đỗ",
                    style=ChatUIActionStyle.DANGER,
                    requires_confirmation=True,
                ),
            ]
        )
    elif (
        canonical_selected_slot is not None
        and route is not None
        and "get_route" in successful_tool_names
        and intent == "GET_ROUTE_TO_SLOT"
    ):
        actions.append(
            _action(
                action_id=f"reserve-and-route:{canonical_selected_slot.lower()}",
                action_type=ChatUIActionType.RESERVE_AND_ROUTE,
                label=f"Giữ ô {canonical_selected_slot} và chỉ đường",
                payload={"slot_id": canonical_selected_slot},
                style=ChatUIActionStyle.PRIMARY,
                requires_confirmation=True,
            )
        )

    if canonical_selected_slot is not None and (
        successful_tool_names
        & {
            "get_route",
            "reserve_parking_slot",
            "confirm_parking",
            "find_parked_vehicle",
        }
    ):
        actions.append(
            _action(
                action_id=f"report-wrong-parking:{canonical_selected_slot.lower()}",
                action_type=ChatUIActionType.OPEN_WRONG_PARKING_REPORT,
                label=f"Báo xe đỗ sai tại {canonical_selected_slot}",
                payload={"slot_id": canonical_selected_slot},
            )
        )

    if not actions:
        preferences = (
            ("EV", "Tìm ô có sạc"),
            ("ACCESSIBLE", "Tìm ô dễ tiếp cận"),
            ("NEAR_ELEVATOR", "Tìm ô gần thang máy"),
        )
        for preference, label in preferences:
            actions.append(
                _action(
                    action_id=f"parking-preference:{preference.lower().replace('_', '-')}",
                    action_type=ChatUIActionType.SELECT_PARKING_PREFERENCE,
                    label=label,
                    payload={"preference": preference},
                )
            )

    return actions[:_MAX_UI_ACTIONS]


__all__ = ["derive_chat_ui_actions"]
