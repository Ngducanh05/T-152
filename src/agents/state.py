from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """Conversation state persisted and reduced by LangGraph.

    Runtime-only dependencies belong in ``AgentRuntimeContext``, never in this
    serializable state. Internal reasoning is deliberately not part of the contract.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    vehicle_id: str
    current_location: str
    intent: str
    selected_slot: str
    recommended_slot_ids: list[str]
    active_reservation_id: str
    active_session_id: str
    missing_fields: list[str]
    tool_result: dict[str, Any]
    error: str
    tool_call_count: int
    agent_step_count: int
