from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.prebuilt import ToolRuntime
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.context import AgentRuntimeContext
from src.agents.state import AgentState
from src.core.location import LocationError
from src.core.parking_session import ParkingSessionError
from src.core.parking_state import ParkingStateError
from src.core.recommendation import RecommendationError
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


async def execute_tool(
    runtime: AgentToolRuntime,
    tool_name: str,
    operation: ToolOperation,
    *,
    write: bool = False,
) -> ToolResult:
    """Run one adapter operation with session ownership and safe error mapping."""
    try:
        async with runtime.context.session_factory() as session:
            if write:
                async with session.begin():
                    return await operation(session)
            return await operation(session)
    except AgentToolError as error:
        return tool_error(error.code, error.message)
    except _DOMAIN_ERRORS as error:
        return tool_error(error.code, error.message)
    except Exception as error:  # noqa: BLE001 - boundary must shield the model
        _LOGGER.exception(
            "Agent tool failed tool=%s request_id=%s exception_type=%s",
            tool_name,
            runtime.context.request_id,
            type(error).__name__,
        )
        return tool_error(
            ErrorCode.AGENT_TOOL_UNAVAILABLE,
            "The parking service is temporarily unavailable. Please try again.",
            retryable=True,
        )


__all__ = [
    "AgentToolError",
    "AgentToolRuntime",
    "ToolResult",
    "execute_tool",
    "require_vehicle_id",
    "tool_error",
    "tool_success",
]
