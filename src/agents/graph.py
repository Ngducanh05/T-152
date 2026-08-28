from __future__ import annotations

import json
from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.agents.context import AgentRuntimeContext
from src.agents.nodes.assistant import build_assistant_node
from src.agents.nodes.observe_tool import observe_tool_result
from src.agents.nodes.prepare_context import prepare_context
from src.agents.state import AgentState
from src.agents.tools import AGENT_TOOLS
from src.services.llm import get_llm

MAX_AGENT_STEPS = 8


def _safe_tool_node_error(error: Exception) -> str:
    return json.dumps(
        {
            "ok": False,
            "error": {
                "code": "AGENT_TOOL_UNAVAILABLE",
                "message": "The requested tool is temporarily unavailable.",
                "retryable": True,
            },
        }
    )


def _route_after_assistant(state: AgentState) -> str:
    return tools_condition(state)


def _lazy_bound_model_provider(
    model: BaseChatModel | None,
    tools: Sequence[BaseTool],
):
    bound_model = None

    def provide_model():
        nonlocal bound_model
        if bound_model is None:
            resolved_model = get_llm(model)
            try:
                bound_model = resolved_model.bind_tools(list(tools))
            except NotImplementedError:
                # Some deterministic test models emit scripted tool calls but do
                # not implement provider-specific binding.
                bound_model = resolved_model
        return bound_model

    return provide_model


def build_graph(
    model: BaseChatModel | None = None,
    *,
    tools: Sequence[BaseTool] | None = None,
    max_steps: int = MAX_AGENT_STEPS,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Build the parking assistant with injectable model, tools, and step budget.

    Model construction and tool binding remain inside a lazy provider, so importing
    this module never creates a provider client or performs network I/O.
    """
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    graph_tools = tuple(AGENT_TOOLS if tools is None else tools)
    model_provider = _lazy_bound_model_provider(model, graph_tools)
    graph = StateGraph(AgentState, context_schema=AgentRuntimeContext)
    graph.add_node("prepare_context", prepare_context)
    graph.add_node(
        "assistant",
        build_assistant_node(model_provider, max_steps=max_steps),
    )
    graph.add_node(
        "tools",
        ToolNode(graph_tools, handle_tool_errors=_safe_tool_node_error),
    )
    graph.add_node("observe_tool_result", observe_tool_result)

    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "assistant")
    graph.add_conditional_edges(
        "assistant",
        _route_after_assistant,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "observe_tool_result")
    graph.add_edge("observe_tool_result", "assistant")
    return graph.compile(checkpointer=checkpointer, name="parksmart-agent")
