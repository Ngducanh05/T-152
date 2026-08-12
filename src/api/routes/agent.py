"""Thread-aware ParkSmart Agent chat endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable
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


@dataclass(slots=True)
class _ThreadDeletion:
    namespaced_thread_id: str
    completed: asyncio.Event = field(default_factory=asyncio.Event)


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


async def _delete_expired_thread(
    request: Request,
    thread_id: str,
    user_id: str,
    deletion: _ThreadDeletion,
) -> None:
    deleted = False
    try:
        await request.app.state.agent_checkpointer.adelete_thread(
            deletion.namespaced_thread_id
        )
        deleted = True
    except Exception as error:  # noqa: BLE001 - cleanup must not crash requests
        logger.warning(
            "agent_thread_cleanup_failed exception_type=%s",
            type(error).__name__,
        )
    finally:
        async with request.app.state.agent_thread_registry_lock:
            current = request.app.state.agent_thread_deletions.get(thread_id)
            if current is deletion:
                if deleted:
                    if request.app.state.agent_thread_owners.get(thread_id) == user_id:
                        request.app.state.agent_thread_owners.pop(thread_id, None)
                    request.app.state.agent_thread_last_access.pop(thread_id, None)
                else:
                    request.app.state.agent_thread_last_access[thread_id] = monotonic()
                request.app.state.agent_thread_deletions.pop(thread_id, None)
                deletion.completed.set()


def _track_cleanup_task(request: Request, coroutine: Awaitable[None]) -> None:
    task = asyncio.create_task(coroutine)
    request.app.state.agent_thread_cleanup_tasks.add(task)
    task.add_done_callback(request.app.state.agent_thread_cleanup_tasks.discard)


def _schedule_expired_threads(request: Request, now: float) -> None:
    for thread_id, last_access in list(
        request.app.state.agent_thread_last_access.items()
    ):
        user_id = request.app.state.agent_thread_owners.get(thread_id)
        if user_id is None or now - last_access < request.app.state.agent_thread_ttl_seconds:
            continue
        namespaced_thread_id = f"{user_id}:{thread_id}"
        if (
            namespaced_thread_id in request.app.state.agent_thread_locks
            or thread_id in request.app.state.agent_thread_deletions
        ):
            continue
        deletion = _ThreadDeletion(namespaced_thread_id)
        request.app.state.agent_thread_deletions[thread_id] = deletion
        _track_cleanup_task(
            request,
            _delete_expired_thread(request, thread_id, user_id, deletion),
        )


@asynccontextmanager
async def _thread_invocation(
    request: Request,
    thread_id: str,
    user_id: str,
) -> AsyncIterator[str]:
    """Atomically claim a thread and register its active invocation reference."""
    entry: _ThreadLockEntry
    namespaced_thread_id: str
    while True:
        deletion: _ThreadDeletion | None
        async with request.app.state.agent_thread_registry_lock:
            now = monotonic()
            _schedule_expired_threads(request, now)
            deletion = request.app.state.agent_thread_deletions.get(thread_id)
            if deletion is None:
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
                entry = request.app.state.agent_thread_locks.setdefault(
                    namespaced_thread_id, _ThreadLockEntry()
                )
                entry.users += 1
                break
        await deletion.completed.wait()

    try:
        async with entry.lock:
            yield namespaced_thread_id
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


def _successful_tool_names(messages: list[Any]) -> set[str]:
    names: set[str] = set()
    for message in messages:
        if not isinstance(message, ToolMessage) or not message.name:
            continue
        content = message.content
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                continue
        if (
            message.name in _REGISTERED_TOOL_NAMES
            and _SAFE_TOOL_NAME.fullmatch(message.name)
            and isinstance(content, dict)
            and content.get("ok") is True
        ):
            names.add(message.name)
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
    message_id = f"request:{request_id}"
    runtime_context = AgentRuntimeContext(
        user_id=payload.user_id,
        vehicle_id=payload.vehicle_id,
        request_id=request_id,
        session_factory=get_session_factory(),
    )
    logger.info(
        "agent_chat_started request_id=%s user_id=%s thread_id=%s",
        request_id,
        payload.user_id,
        payload.thread_id,
    )
    try:
        async with _thread_invocation(
            request, payload.thread_id, payload.user_id
        ) as namespaced_thread_id:
            config = {"configurable": {"thread_id": namespaced_thread_id}}
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
    successful_tools = _successful_tool_names(current_messages)
    response = ChatResponse(
        thread_id=payload.thread_id,
        message=_public_message(current_messages),
        intent=result.get("intent") or None,
        selected_slot=result.get("selected_slot") or None,
        tool_names=_safe_tool_names(current_messages),
        current_location=result.get("current_location") or None,
        recommended_slot_ids=(
            result.get("recommended_slot_ids") or []
            if "recommend_parking_slot" in successful_tools
            else []
        ),
        route=(
            result.get("route") or None if "get_route" in successful_tools else None
        ),
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
