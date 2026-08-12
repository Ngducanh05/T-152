from __future__ import annotations

from langchain_core.messages import ToolMessage

from src.agents.state import AgentState


def observe_tool_result(state: AgentState) -> dict[str, object]:
    """Record the latest tool observation without interpreting business data."""
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], ToolMessage):
        return {}

    return {
        "tool_result": {"content": messages[-1].content},
        "tool_call_count": state.get("tool_call_count", 0) + 1,
    }
