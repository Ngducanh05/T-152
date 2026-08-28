from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import nullcontext
from time import perf_counter

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.runtime import Runtime
from opentelemetry.trace import SpanKind

from src.agents.context import AgentRuntimeContext
from src.agents.prompts import SYSTEM_PROMPT
from src.agents.state import AgentState
from src.core.observability import get_active_observability
from src.services.llm import LLMConfigurationError

ModelProvider = Callable[[], Runnable]
_LOGGER = logging.getLogger(__name__)


def _safe_error_message(message: str) -> AIMessage:
    return AIMessage(content=message)


def _context_prompt(state: AgentState) -> str:
    location = state.get("current_location")
    location_context = (
        f" Vị trí hiện tại đã được hệ thống xác nhận là {location}; dùng vị trí này và không hỏi lại."
        if location
        else " Vị trí hiện tại chưa được xác nhận."
    )
    if "vehicle_id" in state.get("missing_fields", []):
        return "Ngữ cảnh tin cậy: người dùng chưa chọn xe cho request này." + location_context
    return "Ngữ cảnh tin cậy: request này đã có vehicle identity từ runtime context." + location_context


def _safe_model_name(model: object) -> str | None:
    for attribute in ("model_name", "model"):
        value = getattr(model, attribute, None)
        if isinstance(value, str) and value and len(value) <= 200:
            return value
    return None


def _usage_tokens(response: AIMessage) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        return {}
    allowed = {
        "input_tokens": "gen_ai.usage.input_tokens",
        "output_tokens": "gen_ai.usage.output_tokens",
        "total_tokens": "gen_ai.usage.total_tokens",
    }
    return {target: usage[source] for source, target in allowed.items() if type(usage.get(source)) is int}


def _safe_finish_reason(response: AIMessage) -> str | None:
    metadata = getattr(response, "response_metadata", None)
    if not isinstance(metadata, dict):
        return None
    finish_reason = metadata.get("finish_reason")
    if isinstance(finish_reason, str) and len(finish_reason) <= 100:
        return finish_reason
    return None


def build_assistant_node(model_provider: ModelProvider, *, max_steps: int):
    """Create an assistant node without resolving its model during graph build."""

    async def assistant_node(
        state: AgentState,
        runtime: Runtime[AgentRuntimeContext],
    ) -> dict[str, object]:
        current_steps = state.get("agent_step_count", 0)
        if current_steps >= max_steps:
            return {
                "messages": [
                    _safe_error_message(
                        "Xin lỗi, yêu cầu đã vượt quá giới hạn xử lý an toàn. "
                        "Vui lòng thử lại với một yêu cầu ngắn hơn."
                    )
                ],
                "error": "AGENT_TOOL_UNAVAILABLE: Agent step limit exceeded.",
            }

        try:
            model = model_provider()
        except LLMConfigurationError as exc:
            return {
                "messages": [_safe_error_message("Trợ lý đỗ xe hiện chưa được cấu hình. Vui lòng thử lại sau.")],
                "error": f"AGENT_TOOL_UNAVAILABLE: {exc}",
            }

        prompt: list[BaseMessage] = [SystemMessage(content=f"{SYSTEM_PROMPT}\n\n{_context_prompt(state)}")]
        prompt.extend(state.get("messages", []))
        model_name = _safe_model_name(model)
        started_at = perf_counter()
        runtime_observability = get_active_observability()
        attributes: dict[str, object] = {"gen_ai.operation.name": "chat"}
        if model_name is not None:
            attributes["gen_ai.request.model"] = model_name
        context_manager = (
            runtime_observability.start_span("agent.llm.invoke", kind=SpanKind.CLIENT, attributes=attributes)
            if runtime_observability is not None
            else nullcontext(None)
        )
        try:
            with context_manager as span:
                response = await model.ainvoke(prompt)
                tool_call_count = len(response.tool_calls)
                if span is not None:
                    span.set_attribute("agent.tool_call_count", tool_call_count)
                    for key, value in _usage_tokens(response).items():
                        span.set_attribute(key, value)
                    if finish_reason := _safe_finish_reason(response):
                        span.set_attribute("gen_ai.response.finish_reason", finish_reason)
        except Exception as error:  # noqa: BLE001 - model boundary must be safe
            request_id = runtime.context.request_id if runtime.context is not None else "missing"
            _LOGGER.error(
                "agent_model_failed request_id=%s duration_ms=%.2f exception_type=%s",
                request_id,
                (perf_counter() - started_at) * 1000,
                type(error).__name__,
            )
            return {
                "messages": [_safe_error_message("Trợ lý đỗ xe tạm thời không khả dụng. Vui lòng thử lại sau.")],
                "error": "AGENT_TOOL_UNAVAILABLE: Model invocation failed.",
            }

        usage_tokens = _usage_tokens(response)
        log_parts: list[object] = [
            runtime.context.request_id if runtime.context is not None else "missing",
            (perf_counter() - started_at) * 1000,
            tool_call_count,
        ]
        log_message = "agent_model_completed request_id=%s duration_ms=%.2f tool_call_count=%s"
        if model_name is not None:
            log_message += " model=%s"
            log_parts.append(model_name)
        for key, label in (
            ("gen_ai.usage.input_tokens", "input_tokens"),
            ("gen_ai.usage.output_tokens", "output_tokens"),
            ("gen_ai.usage.total_tokens", "total_tokens"),
        ):
            if key in usage_tokens:
                log_message += f" {label}=%s"
                log_parts.append(usage_tokens[key])
        _LOGGER.info(log_message, *log_parts)

        next_steps = current_steps + 1
        projected_steps = next_steps + len(response.tool_calls)
        if projected_steps > max_steps:
            return {
                "messages": [
                    _safe_error_message(
                        "Xin lỗi, yêu cầu đã vượt quá giới hạn xử lý an toàn. "
                        "Vui lòng thử lại với một yêu cầu ngắn hơn."
                    )
                ],
                "agent_step_count": next_steps,
                "error": "AGENT_TOOL_UNAVAILABLE: Agent step limit exceeded.",
            }

        # Persist only user-facing content. Provider metadata may contain internal
        # reasoning details and is intentionally excluded from conversation state.
        public_response = AIMessage(
            content=response.content,
            tool_calls=response.tool_calls,
            invalid_tool_calls=response.invalid_tool_calls,
            name=response.name,
            id=response.id,
        )
        return {
            "messages": [public_response],
            "agent_step_count": next_steps,
        }

    return assistant_node
