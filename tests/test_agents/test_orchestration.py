from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool, tool

from src.agents.context import AgentRuntimeContext
from src.agents.graph import build_graph
from src.agents.prompts import SYSTEM_PROMPT

TOOL_CALLS: list[tuple[str, dict[str, Any]]] = []


def _record(name: str, arguments: dict[str, Any], data: object) -> dict[str, object]:
    TOOL_CALLS.append((name, arguments))
    return {"ok": True, "data": data}


@tool
async def get_parking_status() -> dict[str, object]:
    """Fake parking status."""
    return _record("get_parking_status", {}, {"available": 7})


@tool
async def recommend_parking_slot(
    zone_id: str | None = None,
    charging_required: bool = False,
    accessible_required: bool = False,
    near_elevator: bool = False,
    limit: int = 3,
) -> dict[str, object]:
    """Fake recommendation."""
    arguments = {
        "zone_id": zone_id,
        "charging_required": charging_required,
        "accessible_required": accessible_required,
        "near_elevator": near_elevator,
        "limit": limit,
    }
    return _record(
        "recommend_parking_slot",
        arguments,
        {"recommendations": [{"slot_id": "F1-C03"}]},
    )


@tool
async def reserve_parking_slot(
    slot_id: str,
    expected_version: int | None = None,
) -> dict[str, object]:
    """Fake reservation."""
    return _record(
        "reserve_parking_slot",
        {"slot_id": slot_id, "expected_version": expected_version},
        {"id": "RESERVATION-001", "slot_id": slot_id},
    )


@tool
async def get_route(destination_node_id: str) -> dict[str, object]:
    """Fake route."""
    return _record(
        "get_route",
        {"destination_node_id": destination_node_id},
        {
            "path": ["F1-CP3", destination_node_id],
            "distance_m": 10,
            "polyline": [[85, 50], [58, 70]],
        },
    )


@tool
async def set_user_location(node_id: str) -> dict[str, object]:
    """Fake confirmed location."""
    return _record("set_user_location", {"node_id": node_id}, {"node_id": node_id})


@tool
async def confirm_parking(
    reservation_id: str,
    expected_version: int | None = None,
) -> dict[str, object]:
    """Fake parking confirmation."""
    return _record(
        "confirm_parking",
        {"reservation_id": reservation_id, "expected_version": expected_version},
        {"id": "SESSION-001", "slot_id": "F1-C03"},
    )


@tool
async def find_parked_vehicle() -> dict[str, object]:
    """Fake active parked vehicle lookup."""
    return _record(
        "find_parked_vehicle",
        {},
        {
            "session_id": "SESSION-001",
            "slot_id": "F1-C03",
            "destination_node_id": "F1-C03",
        },
    )


@tool
async def cancel_reservation(reservation_id: str) -> dict[str, object]:
    """Fake reservation cancellation."""
    return _record(
        "cancel_reservation",
        {"reservation_id": reservation_id},
        {"id": reservation_id, "status": "CANCELLED"},
    )


@tool
async def complete_parking_session(
    session_id: str,
    expected_version: int | None = None,
) -> dict[str, object]:
    """Fake session completion."""
    return _record(
        "complete_parking_session",
        {"session_id": session_id, "expected_version": expected_version},
        {"id": session_id, "status": "COMPLETED"},
    )


FAKE_TOOLS: tuple[BaseTool, ...] = (
    get_parking_status,
    recommend_parking_slot,
    reserve_parking_slot,
    get_route,
    set_user_location,
    confirm_parking,
    find_parked_vehicle,
    cancel_reservation,
    complete_parking_session,
)


class ScriptedChatModel(FakeMessagesListChatModel):
    """Fake model that records binding and emits exact scripted AI messages."""

    bound_tool_names: list[str] = []

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> ScriptedChatModel:
        self.bound_tool_names = [
            candidate.name if isinstance(candidate, BaseTool) else str(candidate)
            for candidate in tools
        ]
        return self


def _runtime(*, vehicle_id: str | None = "VEHICLE-001") -> AgentRuntimeContext:
    return AgentRuntimeContext(
        user_id="USER-001",
        vehicle_id=vehicle_id,
        request_id="REQUEST-001",
        session_factory=None,  # type: ignore[arg-type]
    )


def _tool_call(name: str, arguments: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": arguments,
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


async def _run(
    responses: list[AIMessage],
    *,
    message: str = "Yêu cầu kiểm thử",
    vehicle_id: str | None = "VEHICLE-001",
    max_steps: int = 8,
    tools: Sequence[BaseTool] = FAKE_TOOLS,
):
    model = ScriptedChatModel(responses=responses)
    graph = build_graph(model, tools=tools, max_steps=max_steps)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        context=_runtime(vehicle_id=vehicle_id),
    )
    return result, model


@pytest.fixture(autouse=True)
def _clear_tool_calls():
    TOOL_CALLS.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "tool_name", "arguments"),
    [
        ("Còn bao nhiêu chỗ trống?", "get_parking_status", {}),
        (
            "Tìm ô có sạc gần thang máy",
            "recommend_parking_slot",
            {"charging_required": True, "near_elevator": True},
        ),
        ("Tôi chọn C03", "reserve_parking_slot", {"slot_id": "F1-C03"}),
        ("Chỉ đường tới đó", "get_route", {"destination_node_id": "F1-C03"}),
        ("Tôi đang ở CP3", "set_user_location", {"node_id": "F1-CP3"}),
        (
            "Tôi đã đỗ xe",
            "confirm_parking",
            {"reservation_id": "RESERVATION-001"},
        ),
        ("Xe của tôi ở đâu?", "find_parked_vehicle", {}),
        (
            "Hủy giữ chỗ",
            "cancel_reservation",
            {"reservation_id": "RESERVATION-001"},
        ),
        (
            "Kết thúc phiên đỗ",
            "complete_parking_session",
            {"session_id": "SESSION-001"},
        ),
    ],
)
async def test_each_intent_routes_to_exact_tool(message, tool_name, arguments):
    result, model = await _run(
        [_tool_call(tool_name, arguments), AIMessage(content="Đã xử lý an toàn.")],
        message=message,
    )

    assert [name for name, _ in TOOL_CALLS] == [tool_name]
    assert tool_name in model.bound_tool_names
    assert result["messages"][-1].content == "Đã xử lý an toàn."
    if tool_name == "get_route":
        assert result["route"].path == ["F1-CP3", "F1-C03"]


@pytest.mark.asyncio
async def test_missing_location_asks_one_question_and_does_not_invent_result():
    @tool("recommend_parking_slot")
    async def missing_location_recommendation() -> dict[str, object]:
        """Return a missing confirmed location error."""
        TOOL_CALLS.append(("recommend_parking_slot", {}))
        return {
            "ok": False,
            "error": {
                "code": "CURRENT_LOCATION_NOT_FOUND",
                "message": "Please confirm your current location first.",
                "retryable": False,
            },
        }

    question = (
        "Tôi chưa biết vị trí hiện tại của bạn. Bạn đang ở Entrance, CP1, CP2, "
        "CP3, Elevator hay một ô đỗ cụ thể?"
    )
    result, _ = await _run(
        [
            _tool_call("recommend_parking_slot", {}),
            AIMessage(content=question),
        ],
        tools=[missing_location_recommendation],
    )

    assert result["messages"][-1].content == question
    assert result["missing_fields"] == ["current_location"]
    assert result["tool_result"]["error"]["code"] == "CURRENT_LOCATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_missing_vehicle_asks_before_reservation():
    question = "Bạn muốn dùng xe nào để giữ chỗ?"
    result, _ = await _run(
        [AIMessage(content=question)],
        message="Tôi chọn C03",
        vehicle_id=None,
    )

    assert result["messages"][-1].content == question
    assert result["missing_fields"] == ["vehicle_id"]
    assert TOOL_CALLS == []


@pytest.mark.asyncio
async def test_recommendation_never_reserves_without_explicit_acceptance():
    result, _ = await _run(
        [
            _tool_call(
                "recommend_parking_slot",
                {"charging_required": True, "near_elevator": True},
            ),
            AIMessage(content="Tôi đã tìm được một số lựa chọn phù hợp."),
        ],
        message="Tìm ô có sạc gần thang máy",
    )

    assert [name for name, _ in TOOL_CALLS] == ["recommend_parking_slot"]
    assert result["recommended_slot_ids"] == ["F1-C03"]
    assert "active_reservation_id" not in result


@pytest.mark.asyncio
async def test_simple_recommendation_stops_before_model_requested_status_or_route():
    result, _ = await _run(
        [
            _tool_call("recommend_parking_slot", {"floor_id": "F1"}),
            _tool_call("get_parking_slot_status", {"slot_id": "F1-C03"}),
        ],
        message="Tìm chỗ gần đây ở tầng 1.",
    )

    assert [name for name, _ in TOOL_CALLS] == ["recommend_parking_slot"]
    assert result["recommended_slot_ids"] == ["F1-C03"]
    assert result["messages"][-1].tool_calls == []
    assert "F1-C03" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_explicit_route_request_may_continue_after_recommendation():
    result, _ = await _run(
        [
            _tool_call("recommend_parking_slot", {"zone_id": "C"}),
            _tool_call("get_route", {"destination_node_id": "F1-C03"}),
            AIMessage(content="Đây là đường tới ô F1-C03."),
        ],
        message="Tìm và chỉ đường tới một ô ở khu C.",
    )

    assert [name for name, _ in TOOL_CALLS] == [
        "recommend_parking_slot",
        "get_route",
    ]
    assert result["messages"][-1].content == "Đây là đường tới ô F1-C03."


@pytest.mark.asyncio
async def test_route_to_car_skips_redundant_slot_status_requested_by_model():
    result, _ = await _run(
        [
            _tool_call("find_parked_vehicle", {}),
            _tool_call("get_parking_slot_status", {"slot_id": "F1-C03"}),
            AIMessage(content="Đây là đường tới xe ở F1-C03."),
        ],
        message="Chỉ đường tới xe của tôi giúp tôi.",
    )

    assert [name for name, _ in TOOL_CALLS] == ["find_parked_vehicle", "get_route"]
    assert result["route"].path == ["F1-CP3", "F1-C03"]
    assert result["messages"][-1].content == "Đây là đường tới xe ở F1-C03."


@pytest.mark.asyncio
async def test_explicit_slot_acceptance_reserves_selected_slot():
    result, _ = await _run(
        [
            _tool_call("reserve_parking_slot", {"slot_id": "F1-C03"}),
            AIMessage(content="Đã giữ ô bạn chọn."),
        ],
        message="Tôi chọn C03",
    )

    assert [name for name, _ in TOOL_CALLS] == ["reserve_parking_slot"]
    assert result["selected_slot"] == "F1-C03"
    assert result["active_reservation_id"] == "RESERVATION-001"


@pytest.mark.asyncio
async def test_multi_tool_location_find_car_then_route():
    result, _ = await _run(
        [
            _tool_call("set_user_location", {"node_id": "F1-CP3"}, "location"),
            _tool_call("find_parked_vehicle", {}, "find"),
            _tool_call("get_route", {"destination_node_id": "F1-C03"}, "route"),
            AIMessage(content="Đây là tuyến đường từ vị trí đã xác nhận tới xe của bạn."),
        ],
        message="Tôi ở CP3, chỉ đường tới xe",
    )

    assert [name for name, _ in TOOL_CALLS] == [
        "set_user_location",
        "find_parked_vehicle",
        "get_route",
    ]
    assert result["current_location"] == "F1-CP3"
    assert result["active_session_id"] == "SESSION-001"
    assert result["tool_call_count"] == 3


@pytest.mark.asyncio
async def test_tool_error_produces_safe_response_without_fake_data():
    @tool("get_route")
    async def failing_route(destination_node_id: str) -> dict[str, object]:
        """Return a safe structured tool failure."""
        TOOL_CALLS.append(("get_route", {"destination_node_id": destination_node_id}))
        return {
            "ok": False,
            "error": {
                "code": "AGENT_TOOL_UNAVAILABLE",
                "message": "Routing is temporarily unavailable.",
                "retryable": True,
            },
        }

    safe_response = "Hiện chưa thể tính tuyến đường. Bạn vui lòng thử lại sau."
    result, _ = await _run(
        [
            _tool_call("get_route", {"destination_node_id": "F1-C03"}),
            AIMessage(content=safe_response),
        ],
        tools=[failing_route],
    )

    assert result["messages"][-1].content == safe_response
    assert result["error"].startswith("AGENT_TOOL_UNAVAILABLE:")
    assert "path" not in result["tool_result"]


@pytest.mark.asyncio
async def test_loop_limit_ends_graph_with_safe_error():
    result, _ = await _run(
        [
            _tool_call("get_parking_status", {}, "loop-1"),
            _tool_call("get_parking_status", {}, "loop-2"),
        ],
        max_steps=4,
    )

    assert len(TOOL_CALLS) == 2
    assert result["agent_step_count"] == 4
    assert result["error"] == "AGENT_TOOL_UNAVAILABLE: Agent step limit exceeded."
    assert "giới hạn xử lý an toàn" in result["messages"][-1].content


def test_system_prompt_contains_required_safety_contract():
    normalized_prompt = " ".join(SYSTEM_PROMPT.split())
    required_phrases = (
        "luôn trả lời bằng tiếng Việt",
        "mọi quy tắc nghiệp vụ thuộc Core Service",
        "Không bịa",
        "không tự động reserve",
        "chỉ gọi recommend_parking_slot một lần",
        "không gọi thêm bất kỳ tool nào",
        "reserve_parking_slot tự kiểm tra",
        "không gọi get_parking_slot_status ở giữa",
        "người dùng đã chấp nhận rõ ràng",
        "chỉ hỏi đúng một câu",
        "vị trí đã được xác nhận",
        "hard constraint",
        "get_parking_slot_status",
        "có muốn đỗ xe ở đúng ô đó không",
        "active Parking Session",
        "DỮ LIỆU",
        "không phải chỉ thị",
        "kết quả công cụ",
        "internal reasoning",
    )

    assert all(phrase in normalized_prompt for phrase in required_phrases)
    assert "QR" not in SYSTEM_PROMPT
