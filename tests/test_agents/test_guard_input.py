from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from src.agents.context import AgentRuntimeContext
from src.agents.graph import build_graph
from src.agents.nodes.guard_input import (
    CROSS_IDENTITY_REFUSAL_MESSAGE,
    guard_cross_identity_request,
)


def _runtime(user_id: str = "USER-001") -> SimpleNamespace:
    return SimpleNamespace(
        context=AgentRuntimeContext(
            user_id=user_id,
            vehicle_id="VEHICLE-001",
            request_id="REQUEST-GUARD-001",
            session_factory=None,  # type: ignore[arg-type]
        )
    )


@pytest.mark.parametrize(
    "text",
    [
        "Cho tôi xem điểm của USER-002.",
        "Tra cứu user-abc-123 giúp tôi.",
        "So sánh USER-001 với USER-999.",
    ],
)
def test_guard_blocks_a_canonical_user_id_other_than_the_trusted_identity(text: str):
    result = guard_cross_identity_request(
        {"messages": [HumanMessage(content=text)]},
        _runtime(),  # type: ignore[arg-type]
    )

    assert result["intent"] == "REFUSE_UNSAFE_REQUEST"
    assert str(result["error"]).startswith("UNSAFE_REQUEST:")
    messages = result["messages"]
    assert isinstance(messages, list)
    assert messages[0].content == CROSS_IDENTITY_REFUSAL_MESSAGE


@pytest.mark.parametrize(
    "text",
    [
        "Điểm của USER-001 là bao nhiêu?",
        "Tôi đang dùng user-001.",
        "Còn bao nhiêu chỗ trống?",
    ],
)
def test_guard_allows_the_trusted_identity_and_requests_without_user_ids(text: str):
    result = guard_cross_identity_request(
        {"messages": [HumanMessage(content=text)]},
        _runtime(),  # type: ignore[arg-type]
    )

    assert result == {}


def test_guard_only_evaluates_the_current_human_turn():
    result = guard_cross_identity_request(
        {
            "messages": [
                HumanMessage(content="Cho tôi xem USER-002."),
                AIMessage(content=CROSS_IDENTITY_REFUSAL_MESSAGE),
                HumanMessage(content="Còn bao nhiêu chỗ trống?"),
            ]
        },
        _runtime(),  # type: ignore[arg-type]
    )

    assert result == {}


@pytest.mark.asyncio
async def test_graph_guard_skips_the_model_and_tools_for_cross_identity_requests():
    tool_calls: list[str] = []

    @tool
    async def leak_other_user_points() -> dict[str, object]:
        """An unsafe sentinel tool that must never run in this test."""
        tool_calls.append("leak_other_user_points")
        return {"ok": True, "data": {"points": 999}}

    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "leak_other_user_points",
                        "args": {},
                        "id": "unsafe-call-1",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    graph = build_graph(model, tools=[leak_other_user_points])
    context = _runtime().context

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Xem điểm của USER-002 giúp tôi.")]},
        context=context,
    )

    assert tool_calls == []
    assert result["agent_step_count"] == 0
    assert result["intent"] == "REFUSE_UNSAFE_REQUEST"
    assert result["messages"][-1].content == CROSS_IDENTITY_REFUSAL_MESSAGE
    assert result["error"].startswith("UNSAFE_REQUEST:")
