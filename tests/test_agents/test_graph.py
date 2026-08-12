from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.context import AgentRuntimeContext
from src.agents.graph import build_graph
from src.agents.tools.common import AgentToolRuntime
from src.core.config import Settings
from src.services.llm import LLMConfigurationError, get_llm


@pytest.mark.asyncio
async def test_agent_messages_accumulate_with_add_messages():
    graph = build_graph(FakeListChatModel(responses=["Xin chào", "Tạm biệt"]))

    first = await graph.ainvoke({"messages": [HumanMessage(content="Chào")]})
    second = await graph.ainvoke(
        {**first, "messages": [*first["messages"], HumanMessage(content="Tạm biệt")]}
    )

    assert [message.content for message in second["messages"]] == [
        "Chào",
        "Xin chào",
        "Tạm biệt",
        "Tạm biệt",
    ]


def test_runtime_context_is_hidden_from_tool_schema():
    @tool
    def context_aware_tool(slot_id: str, runtime: AgentToolRuntime) -> str:
        """Return a slot for the trusted runtime identity."""
        return f"{runtime.context.user_id}:{slot_id}"

    schema = context_aware_tool.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {"slot_id"}
    assert "runtime" not in schema["properties"]


def test_missing_api_key_raises_safe_configuration_error():
    settings = Settings(_env_file=None, llm_api_key=None)

    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY is not configured"):
        get_llm(settings=settings)


@pytest.mark.asyncio
async def test_fake_model_is_injected_without_provider_or_network_call():
    fake_model = FakeListChatModel(responses=["Không gọi network"])

    with patch("src.services.llm.get_settings") as settings_mock:
        graph = build_graph(fake_model)
        result = await graph.ainvoke({"messages": [HumanMessage(content="Test")]})

    settings_mock.assert_not_called()
    assert isinstance(result["messages"][-1], AIMessage)
    assert result["messages"][-1].content == "Không gọi network"


def test_runtime_context_contract_keeps_session_out_of_state():
    assert set(AgentRuntimeContext.__dataclass_fields__) == {
        "user_id",
        "vehicle_id",
        "request_id",
        "session_factory",
    }


@pytest.mark.asyncio
async def test_checkpoint_does_not_store_runtime_dependencies_or_request_id():
    checkpointer = InMemorySaver()
    graph = build_graph(
        FakeListChatModel(responses=["Phản hồi an toàn"]),
        checkpointer=checkpointer,
    )
    config = {"configurable": {"thread_id": "USER-001:THREAD-001"}}
    context = AgentRuntimeContext(
        user_id="USER-001",
        vehicle_id="VEHICLE-001",
        request_id="SECRET-REQUEST-ID",
        session_factory=object(),  # type: ignore[arg-type]
    )

    await graph.ainvoke(
        {"messages": [HumanMessage(content="Xin chào")]},
        config=config,
        context=context,
    )
    checkpoint = await checkpointer.aget_tuple(config)

    assert checkpoint is not None
    channel_values = checkpoint.checkpoint["channel_values"]
    serialized_state = repr(channel_values)
    assert "session_factory" not in serialized_state
    assert "SECRET-REQUEST-ID" not in serialized_state
    assert "api_key" not in serialized_state.lower()
