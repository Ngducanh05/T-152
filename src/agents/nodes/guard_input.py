from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from src.agents.context import AgentRuntimeContext
from src.agents.state import AgentState

_OTHER_USER_ID = re.compile(r"\bUSER-[A-Za-z0-9-]+\b", re.IGNORECASE)
_PROMPT_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:system|developer)(?:\s+(?:mới|message|prompt))?\s*:",
        r"\b(?:bỏ qua|phớt lờ)[\s\S]{0,100}\b(?:hướng dẫn|chỉ dẫn|quy tắc|system prompt)\b",
        r"\bignore[\s\S]{0,80}\b(?:previous|prior)[\s\S]{0,40}\binstructions?\b",
        r"\b(?:chế độ|mode)\s+(?:debug|developer|nhà phát triển)\b",
        r"\b(?:in|hiển thị|tiết lộ)[\s\S]{0,60}\b(?:system prompt|hướng dẫn nội bộ)\b",
        r"\b(?:tắt|bỏ|vô hiệu hóa)[\s\S]{0,60}\b(?:quy tắc an toàn|guard)\b",
    )
)

CROSS_IDENTITY_ERROR_CODE = "UNSAFE_REQUEST"
CROSS_IDENTITY_REFUSAL_MESSAGE = (
    "Tôi chỉ có thể cho bạn biết hoặc thao tác trên thông tin của chính tài khoản "
    "bạn đang đăng nhập, không thể tra cứu hay tiết lộ thông tin của người dùng khác."
)
PROMPT_INJECTION_REFUSAL_MESSAGE = (
    "Tôi không thể làm theo chỉ thị giả mạo hệ thống, yêu cầu bỏ qua quy tắc hoặc "
    "thao tác vượt quyền. Tôi chỉ hỗ trợ các yêu cầu đỗ xe hợp lệ theo quy trình an toàn."
)


def _latest_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return message.content if isinstance(message.content, str) else ""
    return ""


def guard_cross_identity_request(
    state: AgentState,
    runtime: Runtime[AgentRuntimeContext],
) -> dict[str, object]:
    """Deterministically block identity abuse and direct prompt injection.

    The system prompt already tells the model not to reveal another user's
    data, but every tool (e.g. get_my_reward_summary) always returns the
    trusted caller's own data with no parameter to target anyone else — so
    a model trying to comply could still call it and then narrate the
    result as if it belonged to whichever id the user named. That
    mislabeling risk exists the moment the model is allowed to answer at
    all, so this check runs before the assistant node and skips the model
    entirely for this pattern instead of relying on it to decline.
    """
    text = _latest_human_text(state)
    if any(pattern.search(text) for pattern in _PROMPT_INJECTION_PATTERNS):
        return {
            "messages": [AIMessage(content=PROMPT_INJECTION_REFUSAL_MESSAGE)],
            "intent": "REFUSE_UNSAFE_REQUEST",
            "error": (
                f"{CROSS_IDENTITY_ERROR_CODE}: "
                "Prompt-injection request blocked before tool invocation."
            ),
        }

    context = runtime.context
    if context is None:
        return {}

    mentioned_ids = {match.group(0).upper() for match in _OTHER_USER_ID.finditer(text)}
    own_id = context.user_id.upper()
    if not (mentioned_ids - {own_id}):
        return {}

    return {
        "messages": [AIMessage(content=CROSS_IDENTITY_REFUSAL_MESSAGE)],
        "intent": "REFUSE_UNSAFE_REQUEST",
        "error": (
            f"{CROSS_IDENTITY_ERROR_CODE}: "
            "Cross-identity request blocked before tool invocation."
        ),
    }


__all__ = [
    "CROSS_IDENTITY_ERROR_CODE",
    "CROSS_IDENTITY_REFUSAL_MESSAGE",
    "PROMPT_INJECTION_REFUSAL_MESSAGE",
    "guard_cross_identity_request",
]
