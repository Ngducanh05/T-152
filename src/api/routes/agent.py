"""Thread-aware ParkSmart Agent chat endpoint."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.context import AgentRuntimeContext
from src.agents.tools import PARKING_TOOLS
from src.core.database import get_session_factory
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import ChatRequest, ChatResponse, ErrorCode

router = APIRouter(prefix="/agent", tags=["Agent"])
logger = logging.getLogger(__name__)

_SAFE_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REGISTERED_TOOL_NAMES = frozenset(agent_tool.name for agent_tool in PARKING_TOOLS)


@dataclass(slots=True)
class _ThreadLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _service_unavailable(message: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": ErrorCode.AGENT_TOOL_UNAVAILABLE.value,
            "message": message,
        },
    )


async def _claim_thread(request: Request, thread_id: str, user_id: str) -> str:
    """Claim a public thread ID and return its user-namespaced checkpoint ID."""
    async with request.app.state.agent_thread_registry_lock:
        now = monotonic()
        expired_threads = [
            (public_thread_id, owner_id, f"{owner_id}:{public_thread_id}")
            for public_thread_id, last_access in list(
                request.app.state.agent_thread_last_access.items()
            )
            if now - last_access >= request.app.state.agent_thread_ttl_seconds
            if (owner_id := request.app.state.agent_thread_owners.get(public_thread_id))
            is not None
            if f"{owner_id}:{public_thread_id}"
            not in request.app.state.agent_thread_locks
        ]
        for public_thread_id, _, namespaced_id in expired_threads:
            await request.app.state.agent_checkpointer.adelete_thread(namespaced_id)
            request.app.state.agent_thread_owners.pop(public_thread_id, None)
            request.app.state.agent_thread_last_access.pop(public_thread_id, None)

        owner = request.app.state.agent_thread_owners.get(thread_id)
        if owner is not None and owner != user_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": ErrorCode.INVALID_TRANSITION.value,
                    "message": "This thread belongs to another user.",
                },
            )
        request.app.state.agent_thread_owners[thread_id] = user_id
        request.app.state.agent_thread_last_access[thread_id] = now
        namespaced_thread_id = f"{user_id}:{thread_id}"
        return namespaced_thread_id


@asynccontextmanager
async def _thread_lock(
    request: Request,
    thread_id: str,
    namespaced_thread_id: str,
) -> AsyncIterator[None]:
    async with request.app.state.agent_thread_registry_lock:
        entry = request.app.state.agent_thread_locks.setdefault(
            namespaced_thread_id, _ThreadLockEntry()
        )
        entry.users += 1
    try:
        async with entry.lock:
            yield
    finally:
        async with request.app.state.agent_thread_registry_lock:
            entry.users -= 1
            request.app.state.agent_thread_last_access[thread_id] = monotonic()
            if entry.users == 0:
                request.app.state.agent_thread_locks.pop(namespaced_thread_id, None)


def _messages_after_current_input(result: dict[str, Any], message_id: str) -> list[Any]:
    messages = result.get("messages", [])
    for index in range(len(messages) - 1, -1, -1):
        if getattr(messages[index], "id", None) == message_id:
            return messages[index + 1 :]
    return list(messages)


def _public_message(messages: list[Any]) -> str:
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        if isinstance(message.content, str) and message.content.strip():
            return message.content.strip()
    raise _service_unavailable("The agent did not produce a safe response.")


def _safe_tool_names(messages: list[Any]) -> list[str]:
    names: list[str] = []
    for message in messages:
        candidates: list[str] = []
        if isinstance(message, ToolMessage) and message.name:
            candidates.append(message.name)
        elif isinstance(message, AIMessage):
            candidates.extend(
                str(call.get("name", "")) for call in message.tool_calls
            )
        for name in candidates:
            if (
                name in _REGISTERED_TOOL_NAMES
                and _SAFE_TOOL_NAME.fullmatch(name)
                and name not in names
            ):
                names.append(name)
    return names


@router.post(
    "/chat",
    response_model=SuccessResponse[ChatResponse],
    responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def chat(
    payload: ChatRequest,
    request: Request,
) -> SuccessResponse[ChatResponse]:
    request_id = _request_id(request)
    namespaced_thread_id = await _claim_thread(
        request,
        payload.thread_id,
        payload.user_id,
    )
    message_id = f"request:{request_id}"
    runtime_context = AgentRuntimeContext(
        user_id=payload.user_id,
        vehicle_id=payload.vehicle_id,
        request_id=request_id,
        session_factory=get_session_factory(),
    )
    config = {"configurable": {"thread_id": namespaced_thread_id}}

    logger.info(
        "agent_chat_started request_id=%s user_id=%s thread_id=%s",
        request_id,
        payload.user_id,
        payload.thread_id,
    )
    try:
        async with _thread_lock(request, payload.thread_id, namespaced_thread_id):
            async with asyncio.timeout(request.app.state.agent_chat_timeout_seconds):
                result = await request.app.state.agent.ainvoke(
                    {
                        "messages": [
                            HumanMessage(content=payload.message, id=message_id)
                        ]
                    },
                    config=config,
                    context=runtime_context,
                )
    except TimeoutError as error:
        logger.warning(
            "agent_chat_timeout request_id=%s user_id=%s thread_id=%s",
            request_id,
            payload.user_id,
            payload.thread_id,
        )
        raise _service_unavailable("Agent request timed out. Please try again.") from error
    except HTTPException:
        raise
    except Exception as error:
        logger.exception(
            "agent_chat_failed request_id=%s user_id=%s thread_id=%s exception_type=%s",
            request_id,
            payload.user_id,
            payload.thread_id,
            type(error).__name__,
        )
        raise _service_unavailable(
            "The parking assistant is temporarily unavailable. Please try again."
        ) from error

    if not isinstance(result, dict):
        raise _service_unavailable("The agent returned an invalid response.")
    error_text = str(result.get("error", ""))
    if error_text.startswith(ErrorCode.AGENT_TOOL_UNAVAILABLE.value):
        logger.warning(
            "agent_chat_unavailable request_id=%s user_id=%s thread_id=%s",
            request_id,
            payload.user_id,
            payload.thread_id,
        )
        raise _service_unavailable(
            "The parking assistant is temporarily unavailable. Please try again."
        )

    current_messages = _messages_after_current_input(result, message_id)
    response = ChatResponse(
        thread_id=payload.thread_id,
        message=_public_message(current_messages),
        intent=result.get("intent") or None,
        selected_slot=result.get("selected_slot") or None,
        tool_names=_safe_tool_names(current_messages),
    )
    logger.info(
        "agent_chat_completed request_id=%s user_id=%s thread_id=%s tool_count=%s",
        request_id,
        payload.user_id,
        payload.thread_id,
        len(response.tool_names),
    )
    return SuccessResponse(data=response)


__all__ = ["router"]
