from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

from langgraph.prebuilt import ToolRuntime
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.context import AgentRuntimeContext
from src.agents.state import AgentState
from src.core.location import LocationError
from src.core.parking_session import ParkingSessionError
from src.core.parking_state import ParkingStateError
from src.core.recommendation import RecommendationError
from src.core.reward import RewardError
from src.core.routing import RoutingError
from src.models.schemas import ErrorCode

AgentToolRuntime = ToolRuntime[AgentRuntimeContext, AgentState]
"""Runtime type injected by LangGraph and hidden from model tool schemas."""

ToolResult = dict[str, Any]
ToolOperation = Callable[[AsyncSession], Awaitable[ToolResult]]

_DOMAIN_ERRORS = (
    LocationError,
    ParkingSessionError,
    ParkingStateError,
    RecommendationError,
    RewardError,
    RoutingError,
)
_LOGGER = logging.getLogger(__name__)


class AgentToolError(Exception):
    """Expected adapter-level error with a stable public error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def tool_success(data: object) -> ToolResult:
    return {"ok": True, "data": data}


def tool_error(
    code: ErrorCode,
    message: str,
    *,
    retryable: bool = False,
) -> ToolResult:
    return {
        "ok": False,
        "error": {
            "code": code.value,
            "message": message,
            "retryable": retryable,
        },
    }


def require_vehicle_id(runtime: AgentToolRuntime) -> str:
    vehicle_id = runtime.context.vehicle_id
    if vehicle_id is None:
        raise AgentToolError(
            ErrorCode.VEHICLE_NOT_FOUND,
            "No vehicle is associated with this request.",
        )
    return vehicle_id


def _masked_identifier(value: object) -> str:
    """Return a stable non-reversible identifier suitable for structured logs."""
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:10]
    return f"masked-{digest}"


def _runtime_thread_id(runtime: AgentToolRuntime) -> str:
    configurable = runtime.config.get("configurable", {})
    if not isinstance(configurable, dict):
        return "unknown"
    return str(configurable.get("thread_id", "unknown"))


def _result_error_code(result: ToolResult) -> str:
    error = result.get("error")
    if not isinstance(error, dict):
        return "NONE"
    return str(error.get("code", ErrorCode.AGENT_TOOL_UNAVAILABLE.value))


def _log_tool_result(
    runtime: AgentToolRuntime,
    tool_name: str,
    result: ToolResult,
    *,
    started_at: float,
    exception_type: str = "NONE",
) -> None:
    outcome = "success" if result.get("ok") is True else "error"
    _LOGGER.info(
        "agent_tool_completed request_id=%s thread_id=%s user_id=%s "
        "tool_name=%s duration_ms=%.2f outcome=%s error_code=%s exception_type=%s",
        runtime.context.request_id,
        _masked_identifier(_runtime_thread_id(runtime)),
        _masked_identifier(runtime.context.user_id),
        tool_name,
        (perf_counter() - started_at) * 1000,
        outcome,
        _result_error_code(result),
        exception_type,
    )


async def execute_tool(
    runtime: AgentToolRuntime,
    tool_name: str,
    operation: ToolOperation,
    *,
    write: bool = False,
) -> ToolResult:
    """Run one adapter operation with session ownership and safe error mapping."""
    started_at = perf_counter()
    exception_type = "NONE"
    try:
        async with runtime.context.session_factory() as session:
            if write:
                async with session.begin():
                    result = await operation(session)
            else:
                result = await operation(session)
    except AgentToolError as error:
        result = tool_error(error.code, error.message)
    except _DOMAIN_ERRORS as error:
        result = tool_error(error.code, error.message)
    except Exception as error:  # noqa: BLE001 - boundary must shield the model
        exception_type = type(error).__name__
        result = tool_error(
            ErrorCode.AGENT_TOOL_UNAVAILABLE,
            "The parking service is temporarily unavailable. Please try again.",
            retryable=True,
        )
    _log_tool_result(
        runtime,
        tool_name,
        result,
        started_at=started_at,
        exception_type=exception_type,
    )
    return result


__all__ = [
    "AgentToolError",
    "AgentToolRuntime",
    "ToolResult",
    "execute_tool",
    "require_vehicle_id",
    "tool_error",
    "tool_success",
]
