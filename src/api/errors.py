"""Central mapping from stable domain codes to HTTP responses."""

from fastapi import HTTPException, status

from src.core.errors import DomainError
from src.models.schemas import ErrorCode

_NOT_FOUND = {
    ErrorCode.SLOT_NOT_FOUND,
    ErrorCode.ROUTE_NODE_NOT_FOUND,
    ErrorCode.ACTIVE_SESSION_NOT_FOUND,
    ErrorCode.USER_NOT_FOUND,
    ErrorCode.VEHICLE_NOT_FOUND,
    ErrorCode.RESERVATION_NOT_FOUND,
    ErrorCode.ACTIVE_RESERVATION_NOT_FOUND,
    ErrorCode.SESSION_NOT_FOUND,
    ErrorCode.LOCATION_NODE_NOT_FOUND,
    ErrorCode.CURRENT_LOCATION_NOT_FOUND,
    ErrorCode.REPORT_NOT_FOUND,
    ErrorCode.OBSERVATION_NOT_FOUND,
    ErrorCode.REWARD_CATALOG_ITEM_NOT_FOUND,
}
_CONFLICT = {
    ErrorCode.INVALID_TRANSITION,
    ErrorCode.SLOT_NOT_AVAILABLE,
    ErrorCode.ACTIVE_RESERVATION_EXISTS,
    ErrorCode.RESERVATION_EXPIRED,
    ErrorCode.ACTIVE_SESSION_EXISTS,
    ErrorCode.INVALID_REPORT_TRANSITION,
    ErrorCode.REPORT_VERSION_CONFLICT,
    ErrorCode.OBSERVATION_ALREADY_EXISTS,
    ErrorCode.OBSERVATION_EXPIRED,
    ErrorCode.INVALID_OBSERVATION_TRANSITION,
    ErrorCode.OBSERVATION_VERSION_CONFLICT,
    ErrorCode.REWARD_ALREADY_SETTLED,
    ErrorCode.REPORT_REWARD_DUPLICATE,
    ErrorCode.IDEMPOTENCY_KEY_REUSED,
    ErrorCode.REWARD_CATALOG_ITEM_INACTIVE,
    ErrorCode.INSUFFICIENT_REWARD_POINTS,
}
_RATE_LIMITED = {
    ErrorCode.AGENT_DAILY_LIMIT_REACHED,
    ErrorCode.REPORT_DAILY_LIMIT_REACHED,
    ErrorCode.CONTRIBUTION_DAILY_LIMIT_REACHED,
}
_UNAVAILABLE = {
    ErrorCode.AGENT_DISABLED,
    ErrorCode.AGENT_TOOL_UNAVAILABLE,
    ErrorCode.SPEECH_DISABLED,
    ErrorCode.SPEECH_TRANSCRIPTION_UNAVAILABLE,
}


def status_for_error_code(code: ErrorCode) -> int:
    if code in _NOT_FOUND:
        return status.HTTP_404_NOT_FOUND
    if code in _CONFLICT:
        return status.HTTP_409_CONFLICT
    if code in _RATE_LIMITED:
        return status.HTTP_429_TOO_MANY_REQUESTS
    if code in _UNAVAILABLE:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_422_UNPROCESSABLE_CONTENT


def domain_http_error(
    error: DomainError,
    *,
    status_code: int | None = None,
    code: ErrorCode | None = None,
) -> HTTPException:
    effective_code = code or error.code
    return HTTPException(
        status_code=status_code or status_for_error_code(effective_code),
        detail={
            "code": effective_code.value,
            "message": error.message,
            "details": error.details or None,
        },
    )


__all__ = ["domain_http_error", "status_for_error_code"]
