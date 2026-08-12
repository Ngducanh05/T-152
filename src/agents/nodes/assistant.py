from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from src.agents.prompts import SYSTEM_PROMPT
from src.agents.state import AgentState
from src.services.llm import LLMConfigurationError

ModelProvider = Callable[[], BaseChatModel]


def build_assistant_node(model_provider: ModelProvider):
    """Create an assistant node without resolving its model during graph build."""

    async def assistant_node(state: AgentState) -> dict[str, object]:
        try:
            model = model_provider()
        except LLMConfigurationError as exc:
            return {"error": str(exc)}

        prompt: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
        prompt.extend(state.get("messages", []))
        response = await model.ainvoke(prompt)

        # Persist only user-facing content. Provider metadata may contain internal
        # reasoning details and is intentionally excluded from conversation state.
        public_response = AIMessage(
            content=response.content,
            tool_calls=response.tool_calls,
            invalid_tool_calls=response.invalid_tool_calls,
            name=response.name,
            id=response.id,
        )
        return {"messages": [public_response], "error": ""}

    return assistant_node
