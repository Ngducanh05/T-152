from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import ToolMessage

from src.agents.state import AgentState


def _tool_messages(state: AgentState) -> list[ToolMessage]:
    messages: list[ToolMessage] = []
    for message in reversed(state.get("messages", [])):
        if not isinstance(message, ToolMessage):
            break
        messages.append(message)
    return list(reversed(messages))


def _parse_tool_content(content: object) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": {
                    "code": "AGENT_TOOL_UNAVAILABLE",
                    "message": "Tool returned an invalid response.",
                    "retryable": True,
                },
            }
        if isinstance(parsed, dict):
            return parsed
    return {
        "ok": False,
        "error": {
            "code": "AGENT_TOOL_UNAVAILABLE",
            "message": "Tool returned an invalid response.",
            "retryable": True,
        },
    }


def _remove_missing(fields: list[str], field: str) -> list[str]:
    return [value for value in fields if value != field]


def _apply_success(
    update: dict[str, object],
    tool_name: str | None,
    data: object,
    missing_fields: list[str],
) -> list[str]:
    if not isinstance(data, dict):
        return missing_fields

    if tool_name == "recommend_parking_slot":
        recommendations = data.get("recommendations", [])
        if isinstance(recommendations, list):
            update["recommended_slot_ids"] = [
                candidate["slot_id"]
                for candidate in recommendations
                if isinstance(candidate, dict) and isinstance(candidate.get("slot_id"), str)
            ]
    elif tool_name == "reserve_parking_slot":
        if isinstance(data.get("slot_id"), str):
            update["selected_slot"] = data["slot_id"]
        if isinstance(data.get("id"), str):
            update["active_reservation_id"] = data["id"]
    elif tool_name == "set_user_location":
        if isinstance(data.get("node_id"), str):
            update["current_location"] = data["node_id"]
            missing_fields = _remove_missing(missing_fields, "current_location")
    elif tool_name == "confirm_parking":
        if isinstance(data.get("id"), str):
            update["active_session_id"] = data["id"]
    elif tool_name == "find_parked_vehicle":
        if isinstance(data.get("session_id"), str):
            update["active_session_id"] = data["session_id"]
        if isinstance(data.get("slot_id"), str):
            update["selected_slot"] = data["slot_id"]
    elif tool_name == "cancel_reservation":
        update["active_reservation_id"] = ""
    elif tool_name == "complete_parking_session":
        update["active_session_id"] = ""
    return missing_fields


def observe_tool_result(state: AgentState) -> dict[str, object]:
    """Parse structured tool observations into the durable agent state contract."""
    messages = _tool_messages(state)
    if not messages:
        return {}

    update: dict[str, object] = {
        "tool_call_count": state.get("tool_call_count", 0) + len(messages),
        "agent_step_count": state.get("agent_step_count", 0) + len(messages),
    }
    missing_fields = list(state.get("missing_fields", []))
    for message in messages:
        result = _parse_tool_content(message.content)
        update["tool_result"] = result
        if result.get("ok") is True:
            update["error"] = ""
            missing_fields = _apply_success(
                update,
                message.name,
                result.get("data"),
                missing_fields,
            )
            continue

        error = result.get("error", {})
        if isinstance(error, dict):
            code = str(error.get("code", "AGENT_TOOL_UNAVAILABLE"))
            message_text = str(error.get("message", "Tool request failed."))
        else:
            code = "AGENT_TOOL_UNAVAILABLE"
            message_text = "Tool request failed."
        update["error"] = f"{code}: {message_text}"
        if code == "CURRENT_LOCATION_NOT_FOUND":
            missing_fields.append("current_location")
        elif code == "VEHICLE_NOT_FOUND":
            missing_fields.append("vehicle_id")

    update["missing_fields"] = list(dict.fromkeys(missing_fields))
    return update
