from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import ToolMessage
from pydantic import TypeAdapter, ValidationError

from src.agents.state import AgentState
from src.models.schemas import FloorScopedId, RouteResult

_FLOOR_SCOPED_ID_ADAPTER = TypeAdapter(FloorScopedId)
_PARKING_SLOT_ID = re.compile(r"^F1-[A-D]\d{2}$")


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


def _intent_for_tool(
    tool_name: str | None,
    state: AgentState,
    update: dict[str, object],
) -> str | None:
    if tool_name == "get_route":
        active_session_id = update.get("active_session_id") or state.get(
            "active_session_id"
        )
        return "GET_ROUTE_TO_CAR" if active_session_id else "GET_ROUTE_TO_SLOT"
    return {
        "get_parking_status": "GET_PARKING_STATUS",
        "get_parking_slot_status": "GET_PARKING_STATUS",
        "recommend_parking_slot": "RECOMMEND_SLOT",
        "reserve_parking_slot": "RESERVE_SLOT",
        "set_user_location": "CONFIRM_USER_LOCATION",
        "confirm_parking": "CONFIRM_PARKING",
        "find_parked_vehicle": "FIND_MY_CAR",
        "cancel_reservation": "CANCEL_RESERVATION",
        "complete_parking_session": "COMPLETE_PARKING_SESSION",
        "get_reward_configuration": "GET_REWARD_INFO",
        "get_my_reward_summary": "GET_REWARD_SUMMARY",
    }.get(tool_name)


def _apply_success(
    update: dict[str, object],
    tool_name: str | None,
    data: object,
    missing_fields: list[str],
    resolved_fields: set[str],
) -> list[str]:
    if not isinstance(data, dict):
        return missing_fields

    if tool_name == "recommend_parking_slot":
        recommendations = data.get("recommendations", [])
        if isinstance(recommendations, list):
            slot_ids: list[str] = []
            for candidate in recommendations:
                if not isinstance(candidate, dict):
                    continue
                try:
                    slot_id = _FLOOR_SCOPED_ID_ADAPTER.validate_python(
                        candidate.get("slot_id")
                    )
                except ValidationError:
                    continue
                slot_ids.append(slot_id)
            update["recommended_slot_ids"] = slot_ids
    elif tool_name == "get_route":
        try:
            update["route"] = RouteResult.model_validate(
                {
                    "path": data.get("path"),
                    "distance_m": data.get("distance_m"),
                    "polyline": data.get("polyline"),
                }
            )
        except ValidationError:
            # An invalid success payload is not safe structured output.
            pass
        else:
            destination_node_id = data.get("destination_node_id")
            if isinstance(destination_node_id, str) and _PARKING_SLOT_ID.fullmatch(
                destination_node_id
            ):
                update["selected_slot"] = destination_node_id
    elif tool_name == "reserve_parking_slot":
        if isinstance(data.get("slot_id"), str):
            update["selected_slot"] = data["slot_id"]
        if isinstance(data.get("id"), str):
            update["active_reservation_id"] = data["id"]
    elif tool_name == "set_user_location":
        if isinstance(data.get("node_id"), str):
            update["current_location"] = data["node_id"]
            resolved_fields.add("current_location")
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
    resolved_fields: set[str] = set()
    reported_errors: list[tuple[str, str]] = []
    for message in messages:
        result = _parse_tool_content(message.content)
        update["tool_result"] = result
        intent = _intent_for_tool(message.name, state, update)
        if intent is not None:
            update["intent"] = intent
        if result.get("ok") is True:
            missing_fields = _apply_success(
                update,
                message.name,
                result.get("data"),
                missing_fields,
                resolved_fields,
            )
            continue

        error = result.get("error", {})
        if isinstance(error, dict):
            code = str(error.get("code", "AGENT_TOOL_UNAVAILABLE"))
            message_text = str(error.get("message", "Tool request failed."))
        else:
            code = "AGENT_TOOL_UNAVAILABLE"
            message_text = "Tool request failed."
        reported_errors.append((code, message_text))
        if code == "CURRENT_LOCATION_NOT_FOUND":
            missing_fields.append("current_location")
        elif code == "VEHICLE_NOT_FOUND":
            missing_fields.append("vehicle_id")

    error_fields = {
        "CURRENT_LOCATION_NOT_FOUND": "current_location",
        "VEHICLE_NOT_FOUND": "vehicle_id",
    }
    effective_errors = {
        f"{code}: {message_text}"
        for code, message_text in reported_errors
        if error_fields.get(code) not in resolved_fields
    }
    update["error"] = " | ".join(sorted(effective_errors))
    update["missing_fields"] = [
        field
        for field in dict.fromkeys(missing_fields)
        if field not in resolved_fields
    ]
    return update
