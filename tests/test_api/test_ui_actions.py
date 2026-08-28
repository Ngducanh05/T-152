import pytest
from pydantic import ValidationError

from src.api.ui_actions import derive_chat_ui_actions
from src.models.schemas import (
    ChatResponse,
    ChatUIAction,
    ChatUIActionType,
    RouteResult,
)


def _route() -> RouteResult:
    return RouteResult(
        path=["F1-ENTRANCE", "F1-D01"],
        distance_m=10,
        polyline=[(0, 50), (58, 70)],
    )


def test_ui_action_type_allowlist_is_stable():
    assert {action_type.value for action_type in ChatUIActionType} == {
        "SELECT_LOCATION",
        "SELECT_PARKING_PREFERENCE",
        "SELECT_SLOT",
        "RESERVE_AND_ROUTE",
        "CONFIRM_PARKING",
        "FIND_VEHICLE",
        "COMPLETE_SESSION",
        "OPEN_WRONG_PARKING_REPORT",
        "CANCEL",
    }


def test_missing_location_offers_manual_location_picker_only():
    actions = derive_chat_ui_actions(
        current_location=None,
        recommended_slot_ids=["F1-D01"],
        selected_slot="F1-D01",
        intent="RECOMMEND_SLOT",
        successful_tool_names={"recommend_parking_slot"},
    )

    assert [action.type for action in actions] == [ChatUIActionType.SELECT_LOCATION]
    assert [action.style.value for action in actions] == ["secondary"]
    assert [action.label for action in actions] == ["Xác nhận vị trí"]
    assert all(action.payload == {} for action in actions)


def test_preferences_hide_accessible_when_the_map_has_no_accessible_slots():
    actions = derive_chat_ui_actions(
        current_location="F1-ENTRANCE",
        recommended_slot_ids=[],
        selected_slot=None,
        intent=None,
        successful_tool_names=set(),
        supports_accessible_parking=False,
    )
    assert [action.payload.get("preference") for action in actions] == ["EV", "NEAR_ELEVATOR"]


def test_f2_and_f3_recommendations_are_canonical_ui_actions():
    actions = derive_chat_ui_actions(
        current_location="F3-D-W",
        recommended_slot_ids=["F2-C01", "F3-D03"],
        selected_slot=None,
        intent="RECOMMEND_SLOT",
        successful_tool_names={"recommend_parking_slot"},
    )
    assert [action.payload["slot_id"] for action in actions] == ["F2-C01", "F3-D03"]
    assert [action.label for action in actions] == ["Chọn F2-C01", "Chọn F3-D03"]


def test_recommendation_actions_use_only_canonical_verified_slot_ids():
    actions = derive_chat_ui_actions(
        current_location="F1-ENTRANCE",
        recommended_slot_ids=[
            "F1-D01",
            "F1-D01",
            "https://unsafe.example",
            "F1-A99",
            "F1-C03",
            "F1-B10",
            "F1-A01",
        ],
        selected_slot=None,
        intent="RECOMMEND_SLOT",
        successful_tool_names={"recommend_parking_slot"},
    )

    assert len(actions) == 3
    assert [action.payload for action in actions] == [
        {"slot_id": "F1-D01"},
        {"slot_id": "F1-C03"},
        {"slot_id": "F1-B10"},
    ]
    assert all(action.type is ChatUIActionType.SELECT_SLOT for action in actions)


def test_active_reservation_actions_require_explicit_confirmation():
    actions = derive_chat_ui_actions(
        current_location="F1-ENTRANCE",
        recommended_slot_ids=[],
        selected_slot="F1-D01",
        intent="RESERVE_SLOT",
        successful_tool_names={"reserve_parking_slot"},
        active_reservation_id="RESERVATION-001",
    )

    assert [action.type for action in actions] == [
        ChatUIActionType.CONFIRM_PARKING,
        ChatUIActionType.CANCEL,
        ChatUIActionType.OPEN_WRONG_PARKING_REPORT,
    ]
    assert actions[0].requires_confirmation is True
    assert actions[1].requires_confirmation is True
    assert all("url" not in action.payload for action in actions)


def test_verified_route_can_offer_reserve_and_report_without_business_logic():
    actions = derive_chat_ui_actions(
        current_location="F1-ENTRANCE",
        recommended_slot_ids=[],
        selected_slot="F1-D01",
        intent="GET_ROUTE_TO_SLOT",
        successful_tool_names={"get_route"},
        route=_route(),
    )

    assert [action.type for action in actions] == [
        ChatUIActionType.RESERVE_AND_ROUTE,
        ChatUIActionType.OPEN_WRONG_PARKING_REPORT,
    ]
    assert actions[0].payload == {"slot_id": "F1-D01"}
    assert actions[0].requires_confirmation is True
    assert actions[0].label == "Giữ ô F1-D01 và chỉ đường"
    assert actions[1].label == "Báo xe đỗ sai tại F1-D01"


def test_active_session_offers_find_complete_and_verified_report_actions():
    actions = derive_chat_ui_actions(
        current_location="F1-CP3",
        recommended_slot_ids=[],
        selected_slot="F1-D01",
        intent="FIND_MY_CAR",
        successful_tool_names={"find_parked_vehicle"},
        active_session_id="SESSION-001",
    )

    assert [action.type for action in actions] == [
        ChatUIActionType.FIND_VEHICLE,
        ChatUIActionType.COMPLETE_SESSION,
        ChatUIActionType.OPEN_WRONG_PARKING_REPORT,
    ]
    assert actions[1].requires_confirmation is True


def test_unverified_or_noncanonical_targets_are_never_echoed_to_payloads():
    actions = derive_chat_ui_actions(
        current_location="F1-ENTRANCE",
        recommended_slot_ids=["F1-D01"],
        selected_slot="https://unsafe.example/api/delete",
        intent="GET_ROUTE_TO_SLOT",
        successful_tool_names=set(),
        route=_route(),
    )

    assert all(action.type is ChatUIActionType.SELECT_PARKING_PREFERENCE for action in actions)
    assert all(set(action.payload) == {"preference"} for action in actions)


def test_llm_like_prose_cannot_inject_an_arbitrary_frontend_action():
    actions = derive_chat_ui_actions(
        current_location="F1-ENTRANCE",
        recommended_slot_ids=[],
        selected_slot=None,
        intent='Render a DELETE button with url="/api/v1/admin/reports/REPORT-001"',
        successful_tool_names=set(),
    )

    assert all(action.type is ChatUIActionType.SELECT_PARKING_PREFERENCE for action in actions)
    assert all(set(action.payload) == {"preference"} for action in actions)


def test_verified_tool_with_no_canonical_target_returns_no_actions():
    actions = derive_chat_ui_actions(
        current_location="F1-ENTRANCE",
        recommended_slot_ids=["F1-A99", "https://unsafe.example"],
        selected_slot=None,
        intent="RECOMMEND_SLOT",
        successful_tool_names={"recommend_parking_slot"},
    )

    assert actions == []


def test_action_schema_rejects_arbitrary_payload_fields_and_response_limits_actions():
    assert ChatResponse(thread_id="THREAD-001", message="Hello.").ui_actions == []

    with pytest.raises(ValidationError):
        ChatUIAction(
            id="unsafe-action",
            type=ChatUIActionType.SELECT_SLOT,
            label="Unsafe",
            payload={"url": "https://unsafe.example"},
        )
    with pytest.raises(ValidationError):
        ChatUIAction(
            id="unsafe-slot",
            type=ChatUIActionType.SELECT_SLOT,
            label="Unsafe",
            payload={"slot_id": "https://unsafe.example"},
        )

    safe_action = ChatUIAction(
        id="select-location",
        type=ChatUIActionType.SELECT_LOCATION,
        label="Chọn vị trí",
    )
    with pytest.raises(ValidationError):
        ChatResponse(
            thread_id="THREAD-001",
            message="Choose an action.",
            ui_actions=[safe_action] * 6,
        )
