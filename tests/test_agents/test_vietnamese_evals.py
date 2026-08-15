from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool, tool

from eval.vietnamese_agent_cases import VIETNAMESE_AGENT_EVAL_CASES
from src.agents.context import AgentRuntimeContext
from src.agents.graph import build_graph

EVAL_CALLS: list[tuple[str, dict[str, Any]]] = []


def _success(name: str, arguments: dict[str, Any], data: object) -> dict[str, object]:
    EVAL_CALLS.append((name, arguments))
    return {"ok": True, "data": data}


@tool
async def get_parking_status() -> dict[str, object]:
    """Return deterministic parking counts."""
    return _success(
        "get_parking_status",
        {},
        {"available": 7, "by_zone": {"D": {"AVAILABLE": 5}}},
    )


@tool
async def get_parking_slot_status(slot_id: str) -> dict[str, object]:
    """Return the authoritative state of one deterministic slot."""
    return _success(
        "get_parking_slot_status",
        {"slot_id": slot_id},
        {"id": slot_id, "zone_id": "D", "status": "AVAILABLE"},
    )


@tool
async def recommend_parking_slot(
    zone_id: str | None = None,
    charging_required: bool = False,
    accessible_required: bool = False,
    near_elevator: bool = False,
    limit: int = 3,
) -> dict[str, object]:
    """Return one deterministic recommendation without reserving it."""
    arguments = {
        "zone_id": zone_id,
        "charging_required": charging_required,
        "accessible_required": accessible_required,
        "near_elevator": near_elevator,
        "limit": limit,
    }
    return _success(
        "recommend_parking_slot",
        arguments,
        {"recommendations": [{"slot_id": "F1-D01"}]},
    )


@tool
async def reserve_parking_slot(
    slot_id: str,
    expected_version: int | None = None,
) -> dict[str, object]:
    """Return a reservation or a deterministic occupied-slot error."""
    arguments = {"slot_id": slot_id, "expected_version": expected_version}
    EVAL_CALLS.append(("reserve_parking_slot", arguments))
    if expected_version == 1:
        return {
            "ok": False,
            "error": {
                "code": "SLOT_NOT_AVAILABLE",
                "message": "Ô đỗ không còn trống.",
                "retryable": False,
            },
        }
    return {
        "ok": True,
        "data": {"id": "RESERVATION-001", "slot_id": slot_id},
    }


@tool
async def get_route(destination_node_id: str) -> dict[str, object]:
    """Return a deterministic route."""
    return _success(
        "get_route",
        {"destination_node_id": destination_node_id},
        {
            "start_node_id": "F1-CP3",
            "destination_node_id": destination_node_id,
            "path": ["F1-CP3", destination_node_id],
            "distance_m": 10,
            "polyline": [[85, 50], [58, 70]],
        },
    )


@tool
async def set_user_location(node_id: str) -> dict[str, object]:
    """Return a deterministic confirmed location."""
    return _success("set_user_location", {"node_id": node_id}, {"node_id": node_id})


@tool
async def confirm_parking(
    reservation_id: str,
    expected_version: int | None = None,
) -> dict[str, object]:
    """Return a deterministic active parking session."""
    return _success(
        "confirm_parking",
        {"reservation_id": reservation_id, "expected_version": expected_version},
        {"id": "SESSION-001", "slot_id": "F1-D01"},
    )


@tool
async def find_parked_vehicle() -> dict[str, object]:
    """Return a deterministic vehicle from an active session."""
    return _success(
        "find_parked_vehicle",
        {},
        {
            "session_id": "SESSION-001",
            "slot_id": "F1-D01",
            "destination_node_id": "F1-D01",
        },
    )


@tool
async def cancel_reservation(reservation_id: str) -> dict[str, object]:
    """Return deterministic cancellation data."""
    return _success(
        "cancel_reservation",
        {"reservation_id": reservation_id},
        {"id": reservation_id, "status": "CANCELLED"},
    )


EVAL_TOOLS: tuple[BaseTool, ...] = (
    get_parking_status,
    get_parking_slot_status,
    recommend_parking_slot,
    reserve_parking_slot,
    get_route,
    set_user_location,
    confirm_parking,
    find_parked_vehicle,
    cancel_reservation,
)


class EvalScriptedModel(FakeMessagesListChatModel):
    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> EvalScriptedModel:
        return self


def _tool_call(name: str, arguments: dict[str, Any], index: int) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": arguments,
                "id": f"eval-call-{index}",
                "type": "tool_call",
            }
        ],
    )


def _runtime(*, vehicle_id: str | None = "VEHICLE-001") -> AgentRuntimeContext:
    return AgentRuntimeContext(
        user_id="USER-001",
        vehicle_id=vehicle_id,
        request_id="EVAL-REQUEST-001",
        session_factory=None,  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def _clear_calls():
    EVAL_CALLS.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    VIETNAMESE_AGENT_EVAL_CASES,
    ids=lambda case: case.name,
)
async def test_vietnamese_intent_eval_is_deterministic(case):
    responses = [
        _tool_call(name, arguments, index)
        for index, (name, arguments) in enumerate(
            zip(case.tool_sequence, case.tool_arguments, strict=True),
            start=1,
        )
    ]
    if case.name == "reject_direct_database_bypass":
        final_text = "Tôi không thể bỏ qua quy tắc hoặc sửa cơ sở dữ liệu trực tiếp."
    elif case.name == "occupied_slot_is_rejected":
        final_text = "Ô đó không còn trống; tôi chưa giữ chỗ nào cho bạn."
    elif case.name == "route_to_exact_slot_with_status":
        final_text = (
            "Ô F1-D01 hiện đang AVAILABLE. Đây là tuyến đường tới ô. "
            "Bạn có muốn đỗ xe ở ô F1-D01 không?"
        )
    elif case.name == "route_to_zone_d_with_status":
        final_text = (
            "Khu D còn 5 ô AVAILABLE; tôi đã chỉ đường tới ô F1-D01 đang trống. "
            "Bạn có muốn đỗ xe ở ô F1-D01 không?"
        )
    else:
        final_text = "Đã xử lý yêu cầu bằng dữ liệu từ công cụ."
    responses.append(AIMessage(content=final_text))
    graph = build_graph(EvalScriptedModel(responses=responses), tools=EVAL_TOOLS)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=case.utterance)]},
        context=_runtime(),
    )

    assert tuple(name for name, _ in EVAL_CALLS) == case.tool_sequence
    assert tuple(arguments for _, arguments in EVAL_CALLS) == case.tool_arguments
    for _, arguments in EVAL_CALLS:
        assert {"user_id", "vehicle_id", "request_id", "runtime"}.isdisjoint(arguments)
    if case.expected_intent is not None and case.tool_sequence:
        assert result["intent"] == case.expected_intent
    if case.expected_selected_slot is not None:
        assert result["selected_slot"] == case.expected_selected_slot
    assert result["messages"][-1].content == final_text
    assert "analysis" not in result

    if case.name in {"recommend_ev_near_elevator", "recommend_in_zone_d"}:
        assert result["recommended_slot_ids"] == ["F1-D01"]
        assert "active_reservation_id" not in result
        assert "reserve_parking_slot" not in [name for name, _ in EVAL_CALLS]
    elif case.name in {"route_to_exact_slot_with_status", "route_to_zone_d_with_status"}:
        assert result["route"].path[-1] == "F1-D01"
        assert result["selected_slot"] == "F1-D01"
        assert "AVAILABLE" in final_text
        assert "Bạn có muốn đỗ xe ở ô F1-D01 không?" in final_text
    elif case.name == "occupied_slot_is_rejected":
        assert result["tool_result"]["error"]["code"] == "SLOT_NOT_AVAILABLE"
        assert "active_reservation_id" not in result
    elif case.name == "reject_direct_database_bypass":
        assert EVAL_CALLS == []
        assert "không thể" in final_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "vehicle_id", "question", "missing_field"),
    [
        (
            "CURRENT_LOCATION_NOT_FOUND",
            "VEHICLE-001",
            "Bạn đang ở Entrance, CP1, CP2, CP3, Elevator hay ô đỗ nào?",
            "current_location",
        ),
        (
            "VEHICLE_NOT_FOUND",
            None,
            "Bạn muốn dùng xe nào để giữ chỗ?",
            "vehicle_id",
        ),
        (
            "ACTIVE_SESSION_NOT_FOUND",
            "VEHICLE-001",
            "Hiện bạn chưa có phiên đỗ xe đang hoạt động.",
            None,
        ),
    ],
)
async def test_missing_context_and_session_errors_are_safe(
    error_code,
    vehicle_id,
    question,
    missing_field,
):
    tool_name = {
        "CURRENT_LOCATION_NOT_FOUND": "recommend_parking_slot",
        "VEHICLE_NOT_FOUND": "reserve_parking_slot",
        "ACTIVE_SESSION_NOT_FOUND": "find_parked_vehicle",
    }[error_code]

    @tool(tool_name)
    async def failing_tool() -> dict[str, object]:
        """Return one deterministic domain error."""
        EVAL_CALLS.append((tool_name, {}))
        return {
            "ok": False,
            "error": {
                "code": error_code,
                "message": "Safe domain failure.",
                "retryable": False,
            },
        }

    graph = build_graph(
        EvalScriptedModel(
            responses=[_tool_call(tool_name, {}, 1), AIMessage(content=question)]
        ),
        tools=[failing_tool],
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Yêu cầu thiếu dữ liệu")]},
        context=_runtime(vehicle_id=vehicle_id),
    )

    assert result["tool_result"]["error"]["code"] == error_code
    assert result["messages"][-1].content == question
    assert "selected_slot" not in result
    if missing_field is not None:
        assert missing_field in result["missing_fields"]


@pytest.mark.asyncio
async def test_tool_exception_does_not_create_fake_slot_or_route():
    @tool("get_route")
    async def exploding_route(destination_node_id: str) -> dict[str, object]:
        """Raise an unexpected deterministic tool exception."""
        raise RuntimeError("SECRET-INTERNAL-DETAIL")

    safe_text = "Hiện chưa thể tính tuyến đường. Bạn vui lòng thử lại sau."
    graph = build_graph(
        EvalScriptedModel(
            responses=[
                _tool_call("get_route", {"destination_node_id": "F1-D01"}, 1),
                AIMessage(content=safe_text),
            ]
        ),
        tools=[exploding_route],
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Chỉ đường tới đó.")]},
        context=_runtime(),
    )

    assert result["tool_result"]["error"]["code"] == "AGENT_TOOL_UNAVAILABLE"
    assert result["messages"][-1].content == safe_text
    assert "selected_slot" not in result
    assert result["recommended_slot_ids"] == []
    assert "path" not in result["tool_result"]


_LIVE_LLM_ENABLED = os.getenv("RUN_LIVE_LLM_EVAL") == "1" and bool(
    os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
)


@pytest.mark.live_llm
@pytest.mark.skipif(
    not _LIVE_LLM_ENABLED,
    reason="Live eval requires a key and explicit RUN_LIVE_LLM_EVAL=1 opt-in",
)
@pytest.mark.asyncio
async def test_live_llm_selects_parking_status_tool_without_exact_text_matching():
    graph = build_graph(tools=[get_parking_status])

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Còn bao nhiêu chỗ trống?")]},
        context=_runtime(),
    )

    assert [name for name, _ in EVAL_CALLS] == ["get_parking_status"]
    assert result["intent"] == "GET_PARKING_STATUS"
