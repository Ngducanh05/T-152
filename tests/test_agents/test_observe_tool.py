from __future__ import annotations

import json

import pytest
from langchain_core.messages import ToolMessage

from src.agents.nodes.observe_tool import observe_tool_result


def _location_success(call_id: str) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {"ok": True, "data": {"user_id": "USER-001", "node_id": "F1-CP3"}}
        ),
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
