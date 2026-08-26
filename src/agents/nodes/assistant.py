from __future__ import annotations

import logging
from collections.abc import Callable

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.runtime import Runtime

from src.agents.context import AgentRuntimeContext
from src.agents.prompts import SYSTEM_PROMPT
from src.agents.state import AgentState
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
        try:
            response = await model.ainvoke(prompt)
        except Exception as error:  # noqa: BLE001 - model boundary must be safe
            request_id = runtime.context.request_id if runtime.context is not None else "missing"
            _LOGGER.exception(
                "Agent model failed request_id=%s exception_type=%s",
                request_id,
                type(error).__name__,
            )
            return {
                "messages": [_safe_error_message("Trợ lý đỗ xe tạm thời không khả dụng. Vui lòng thử lại sau.")],
                "error": "AGENT_TOOL_UNAVAILABLE: Model invocation failed.",
            }

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
