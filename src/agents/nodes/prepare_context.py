from __future__ import annotations

from contextlib import nullcontext

from langgraph.runtime import Runtime
from opentelemetry.trace import Span

from src.agents.context import AgentRuntimeContext
from src.agents.state import AgentState
from src.core.observability import get_active_observability


def prepare_context(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """Copy trusted request identity into state and reset the per-run step budget."""
    runtime_observability = get_active_observability()
    context_manager = (
        runtime_observability.start_span("agent.prepare_context")
        if runtime_observability is not None
        else nullcontext(None)
    )
    with context_manager as span:
        return _prepare_context(state, runtime, span)


def _prepare_context(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
    span: Span | None,
) -> dict[str, object]:
    context = runtime.context
    if context is None:
        if span is not None:
            span.set_attribute("agent.missing_field_count", 1)
        return {
            "agent_step_count": 0,
            "error": "AGENT_TOOL_UNAVAILABLE: Agent runtime context is missing.",
            "missing_fields": ["runtime_context"],
        }

    resolved_fields = {"vehicle_id"}
    if context.current_location:
        resolved_fields.add("current_location")
    missing_fields = [field for field in state.get("missing_fields", []) if field not in resolved_fields]
    if context.vehicle_id is None:
        missing_fields.append("vehicle_id")
    if span is not None:
        span.set_attribute("agent.missing_field_count", len(set(missing_fields)))

    return {
        "user_id": context.user_id,
        "vehicle_id": context.vehicle_id or "",
        "current_location": context.current_location or state.get("current_location", ""),
        "missing_fields": list(dict.fromkeys(missing_fields)),
        # Structured tool output is scoped to this invocation. Conversation
        # context such as the confirmed location remains durable.
        "recommended_slot_ids": [],
        "route": None,
        "tool_result": {},
        "active_reservation_id": "",
        "active_session_id": "",
        "agent_step_count": 0,
        "error": "",
    }
