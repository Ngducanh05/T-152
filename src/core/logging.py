"""Privacy-safe application logging and request correlation helpers."""

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_MANAGED_HANDLER_ATTRIBUTE = "_parksmart_managed_handler"
_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind a request ID to the current async context."""
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Reset a request ID previously returned by :func:`bind_request_id`."""
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    return _REQUEST_ID.get()


def _active_span_ids() -> tuple[str | None, str | None]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None, None
    return f"{span_context.trace_id:032x}", f"{span_context.span_id:016x}"


class JsonFormatter(logging.Formatter):
    """Emit only an allowlisted, one-line JSON logging schema."""

    def __init__(self, *, service: str, environment: str, service_version: str) -> None:
        super().__init__()
        self.service = service
        self.environment = environment
        self.service_version = service_version

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _active_span_ids()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
            "environment": self.environment,
            "service_version": self.service_version,
        }
        if request_id := get_request_id():
            payload["request_id"] = request_id
        if trace_id and span_id:
            payload["trace_id"] = trace_id
            payload["span_id"] = span_id
        if record.exc_info:
            exception_type = record.exc_info[0]
            if exception_type is not None:
                payload["exception_type"] = exception_type.__name__
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "text",
    *,
    service: str = "parksmart-backend",
    environment: str = "development",
    service_version: str = "0.1.0",
) -> None:
    """Configure stdout logging without disturbing handlers installed by pytest."""
    normalized_level = log_level.upper()
    numeric_level = getattr(logging, normalized_level, logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    handler = next(
        (
            existing
            for existing in root_logger.handlers
            if getattr(existing, _MANAGED_HANDLER_ATTRIBUTE, False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        setattr(handler, _MANAGED_HANDLER_ATTRIBUTE, True)
        root_logger.addHandler(handler)

    handler.setLevel(numeric_level)
    if log_format == "json":
        handler.setFormatter(
            JsonFormatter(
                service=service,
                environment=environment,
                service_version=service_version,
            )
        )
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))
