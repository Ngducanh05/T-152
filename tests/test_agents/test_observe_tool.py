from __future__ import annotations

import json

import pytest
from langchain_core.messages import ToolMessage

from src.agents.nodes.observe_tool import observe_tool_result


def _location_success(call_id: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"ok": True, "data": {"user_id": "USER-001", "node_id": "F1-CP3"}}),
        tool_call_id=call_id,
        name="set_user_location",
    )


def _missing_location(call_id: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "CURRENT_LOCATION_NOT_FOUND",
                    "message": "Please confirm your current location first.",
                    "retryable": False,
                },
            }
        ),
        tool_call_id=call_id,
        name="recommend_parking_slot",
    )


def _unavailable(call_id: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "AGENT_TOOL_UNAVAILABLE",
                    "message": "Parking service is temporarily unavailable.",
                    "retryable": True,
                },
            }
        ),
        tool_call_id=call_id,
        name="get_parking_status",
    )


def _route_result(call_id: str, *, ok: bool = True) -> ToolMessage:
    content = (
        {
            "ok": True,
            "data": {
                "start_node_id": "F1-CP3",
                "destination_node_id": "F1-D01",
                "path": ["F1-CP3", "F1-D01"],
                "distance_m": 10,
                "polyline": [[85, 50], [58, 70]],
            },
        }
        if ok
        else {
            "ok": False,
            "error": {"code": "ROUTE_NOT_FOUND", "message": "No route."},
        }
    )
    return ToolMessage(
        content=json.dumps(content),
        tool_call_id=call_id,
        name="get_route",
    )


@pytest.mark.parametrize(
    "messages",
    [
        [_missing_location("recommend-1"), _location_success("location-1")],
        [_location_success("location-2"), _missing_location("recommend-2")],
    ],
)
def test_resolved_location_wins_regardless_of_parallel_tool_result_order(messages):
    result = observe_tool_result(
        {
            "messages": messages,
            "missing_fields": ["current_location", "current_location"],
        }
    )

    assert result["current_location"] == "F1-CP3"
    assert result["missing_fields"] == []
    assert result["error"] == ""


@pytest.mark.parametrize(
    "messages",
    [
        [_unavailable("status-1"), _location_success("location-3")],
        [_location_success("location-4"), _unavailable("status-2")],
    ],
)
def test_unresolved_tool_error_is_kept_regardless_of_result_order(messages):
    result = observe_tool_result({"messages": messages, "missing_fields": []})

    assert result["error"].startswith("AGENT_TOOL_UNAVAILABLE:")


def test_successful_route_is_validated_and_stored_without_tool_envelope():
    result = observe_tool_result({"messages": [_route_result("route-1")]})

    assert result["route"].model_dump(mode="json") == {
        "path": ["F1-CP3", "F1-D01"],
        "distance_m": 10.0,
        "polyline": [[85.0, 50.0], [58.0, 70.0]],
    }
    assert result["selected_slot"] == "F1-D01"


@pytest.mark.parametrize(
    "message",
    [
        _route_result("route-failed", ok=False),
        ToolMessage(
            content=json.dumps(
                {
                    "ok": True,
                    "data": {
                        "path": ["invented"],
                        "distance_m": -1,
                        "polyline": [],
                    },
                }
            ),
            tool_call_id="route-invalid",
            name="get_route",
        ),
    ],
)
def test_failed_or_invalid_route_has_no_structured_result(message):
    result = observe_tool_result({"messages": [message]})

    assert "route" not in result
    assert "selected_slot" not in result


def test_recommendations_only_use_valid_ids_from_structured_tool_data():
    message = ToolMessage(
        content=json.dumps(
            {
                "ok": True,
                "data": {
                    "recommendations": [
                        {"slot_id": "F1-C03"},
                        {"slot_id": "F2-A10"},
                        {"slot_id": "F3-D01"},
                        {"slot_id": "not-canonical"},
                        "F1-D01 appears in prose",
                    ]
                },
            }
        ),
        tool_call_id="recommend-valid",
        name="recommend_parking_slot",
    )

    result = observe_tool_result({"messages": [message]})

    assert result["recommended_slot_ids"] == ["F1-C03", "F2-A10", "F3-D01"]
