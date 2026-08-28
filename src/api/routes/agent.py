"""Thread-aware ParkSmart Agent chat endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import ceil
from time import monotonic
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.context import AgentRuntimeContext
from src.agents.tools import AGENT_TOOLS
from src.api.dependencies import (
    ParkingUserDependency,
    SessionDependency,
    resolve_parking_user_id,
    resolve_vehicle_id,
)
from src.api.ui_actions import derive_chat_ui_actions
from src.core.agent_quota import (
    AgentQuotaError,
    AgentQuotaExceeded,
    AgentQuotaService,
)
from src.core.database import get_session_factory
from src.core.route_guidance import vietnamese_route_guidance
from src.models.common import ErrorResponse, SuccessResponse
from src.models.schemas import ChatRequest, ChatResponse, ErrorCode

router = APIRouter(prefix="/agent", tags=["Agent"])
logger = logging.getLogger(__name__)

_SAFE_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REGISTERED_TOOL_NAMES = frozenset(agent_tool.name for agent_tool in AGENT_TOOLS)


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


def _agent_disabled() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": ErrorCode.AGENT_DISABLED.value,
            "message": "The parking assistant is currently disabled.",
        },
    )


def _daily_limit_reached(error: AgentQuotaExceeded) -> HTTPException:
    retry_after = max(
        1,
        ceil((error.reset_at - datetime.now(UTC)).total_seconds()),
    )
    return HTTPException(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        detail={
            "code": ErrorCode.AGENT_DAILY_LIMIT_REACHED.value,
            "message": "The daily parking assistant request limit has been reached.",
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


def _successful_route_guidance(messages: list[Any]) -> str | None:
    for message in reversed(messages):
        if not isinstance(message, ToolMessage) or message.name != "get_route":
            continue
        content = message.content
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                continue
        if not isinstance(content, dict) or content.get("ok") is not True:
            continue
        data = content.get("data")
        if not isinstance(data, dict):
            continue
        path = data.get("path")
        distance_m = data.get("distance_m")
        if (
            isinstance(path, list)
            and all(isinstance(node_id, str) for node_id in path)
            and isinstance(distance_m, int | float)
        ):
            return vietnamese_route_guidance(path, float(distance_m))
    return None


def _recommendation_fallback(slot_ids: list[str]) -> str:
    """Build a safe answer when recommendation data outlives an LLM failure."""
    if not slot_ids:
        return (
            "Hiện không có ô trống phù hợp với yêu cầu của bạn. "
            "Bạn có muốn thay đổi khu vực hoặc tiêu chí tìm kiếm không?"
        )
    if len(slot_ids) == 1:
        return (
            f"Tôi đã tìm thấy ô {slot_ids[0]} đang trống và đánh dấu ô này "
            "trên bản đồ. Bạn có muốn đỗ xe ở ô này không?"
        )
    formatted_slots = ", ".join(slot_ids)
    return (
        f"Tôi đã tìm thấy các ô đang trống: {formatted_slots} và đánh dấu chúng "
        "trên bản đồ. Bạn muốn chọn ô nào?"
    )


@router.post(
    "/chat",
    response_model=SuccessResponse[ChatResponse],
    responses={
        429: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def chat(
    payload: ChatRequest,
    request: Request,
    session: SessionDependency,
    current_user: ParkingUserDependency,
) -> SuccessResponse[ChatResponse]:
    settings = request.app.state.settings
    if not settings.agent_enabled:
        raise _agent_disabled()

    user_id = resolve_parking_user_id(payload.user_id, current_user)
    request_id = _request_id(request)
    message_id = f"request:{request_id}"
    try:
        async with _thread_invocation(
            request, payload.thread_id, user_id
        ) as namespaced_thread_id:
            try:
                async with session.begin():
                    vehicle_id = await resolve_vehicle_id(
                        payload.vehicle_id,
                        current_user,
                        session,
                    )
                    await AgentQuotaService(session, settings=settings).consume(user_id)
            except AgentQuotaExceeded as error:
                logger.info(
                    "agent_quota_checked request_id=%s user_id=%s status=exceeded",
                    request_id,
                    user_id,
                )
                raise _daily_limit_reached(error) from error
            except AgentQuotaError as error:
                logger.warning(
                    "agent_quota_checked request_id=%s user_id=%s status=error code=%s",
                    request_id,
                    user_id,
                    error.code.value,
                )
                status_code = 404 if error.code is ErrorCode.USER_NOT_FOUND else 409
                raise HTTPException(
                    status_code=status_code,
                    detail={"code": error.code.value, "message": error.message},
                ) from error

            logger.info(
                "agent_quota_checked request_id=%s user_id=%s status=%s",
                request_id,
                user_id,
                "disabled" if settings.agent_daily_request_limit == 0 else "consumed",
            )
            runtime_context = AgentRuntimeContext(
                user_id=user_id,
                vehicle_id=vehicle_id,
                request_id=request_id,
                session_factory=get_session_factory(),
                current_location=payload.current_location,
            )
            logger.info(
                "agent_chat_started request_id=%s user_id=%s thread_id=%s",
                request_id,
                user_id,
                payload.thread_id,
            )
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
            user_id,
            payload.thread_id,
        )
        raise _service_unavailable("Agent request timed out. Please try again.") from error
    except HTTPException:
        raise
    except Exception as error:
        logger.exception(
            "agent_chat_failed request_id=%s user_id=%s thread_id=%s exception_type=%s",
            request_id,
            user_id,
            payload.thread_id,
            type(error).__name__,
        )
        raise _service_unavailable(
            "The parking assistant is temporarily unavailable. Please try again."
        ) from error

    if not isinstance(result, dict):
        raise _service_unavailable("The agent returned an invalid response.")
    current_messages = _messages_after_current_input(result, message_id)
    successful_tools = _successful_tool_names(current_messages)
    recommendation_ids = result.get("recommended_slot_ids") or []
    error_text = str(result.get("error", ""))
    recovered_recommendation = (
        error_text.startswith(ErrorCode.AGENT_TOOL_UNAVAILABLE.value)
        and "recommend_parking_slot" in successful_tools
    )
    if error_text.startswith(ErrorCode.AGENT_TOOL_UNAVAILABLE.value):
        if not recovered_recommendation:
            logger.warning(
                "agent_chat_unavailable request_id=%s user_id=%s thread_id=%s",
                request_id,
                user_id,
                payload.thread_id,
            )
            raise _service_unavailable(
                "The parking assistant is temporarily unavailable. Please try again."
            )
        logger.warning(
            "agent_chat_recovered_recommendation request_id=%s user_id=%s "
            "thread_id=%s recommendation_count=%s",
            request_id,
            user_id,
            payload.thread_id,
            len(recommendation_ids),
        )

    route_guidance = _successful_route_guidance(current_messages)
    response = ChatResponse(
        thread_id=payload.thread_id,
        message=(
            _recommendation_fallback(recommendation_ids)
            if recovered_recommendation
            else route_guidance or _public_message(current_messages)
        ),
        intent=result.get("intent") or None,
        selected_slot=result.get("selected_slot") or None,
        tool_names=_safe_tool_names(current_messages),
        current_location=result.get("current_location") or None,
        recommended_slot_ids=(
            recommendation_ids
            if "recommend_parking_slot" in successful_tools
            else []
        ),
        route=(
            result.get("route") or None if "get_route" in successful_tools else None
        ),
    )
    response.ui_actions.extend(
        derive_chat_ui_actions(
            current_location=response.current_location,
            recommended_slot_ids=response.recommended_slot_ids,
            selected_slot=response.selected_slot,
            intent=response.intent,
            successful_tool_names=successful_tools,
            active_reservation_id=result.get("active_reservation_id") or None,
            active_session_id=result.get("active_session_id") or None,
            route=response.route,
        )
    )
    logger.info(
        "agent_chat_completed request_id=%s user_id=%s thread_id=%s tool_count=%s",
        request_id,
        user_id,
        payload.thread_id,
        len(response.tool_names),
    )
    return SuccessResponse(data=response)


__all__ = ["router"]
