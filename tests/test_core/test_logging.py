import json
import logging
import sys

from opentelemetry import context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from src.core.logging import (
    JsonFormatter,
    bind_request_id,
    configure_logging,
    get_request_id,
    mask_identifier,
    reset_request_id,
)


def test_text_mode_remains_caplog_compatible(caplog) -> None:
    configure_logging("INFO", "text")
    logger = logging.getLogger("tests.logging.text")

    logger.info("text-compatible message")

    assert "text-compatible message" in caplog.text


def test_json_formatter_emits_one_safe_object_with_bound_request_id() -> None:
    formatter = JsonFormatter(service="parksmart", environment="test", service_version="1.2.3")
    token = bind_request_id("request-123")
    try:
        record = logging.LogRecord("tests.logging.json", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        payload = json.loads(formatter.format(record))
    finally:
        reset_request_id(token)

    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "INFO",
        "logger": "tests.logging.json",
        "message": "hello world",
        "service": "parksmart",
        "environment": "test",
        "service_version": "1.2.3",
        "request_id": "request-123",
    }


def test_request_id_is_reset() -> None:
    token = bind_request_id("request-123")
    reset_request_id(token)

    assert get_request_id() is None


def test_mask_identifier_is_stable_and_does_not_return_raw_identifier() -> None:
    first = mask_identifier("USER-SECRET-001")

    assert first == mask_identifier("USER-SECRET-001")
    assert first.startswith("masked-")
    assert "USER-SECRET-001" not in first


def test_json_formatter_omits_invalid_zero_span_ids() -> None:
    formatter = JsonFormatter(service="parksmart", environment="test", service_version="1.2.3")
    invalid_context = SpanContext(0, 0, False, TraceFlags(0))
    token = context.attach(trace.set_span_in_context(NonRecordingSpan(invalid_context)))
    try:
        payload = json.loads(formatter.format(logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)))
    finally:
        context.detach(token)

    assert "trace_id" not in payload
    assert "span_id" not in payload


def test_json_formatter_emits_valid_active_span_ids() -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    formatter = JsonFormatter(service="parksmart", environment="test", service_version="1.2.3")
    with tracer.start_as_current_span("active"):
        payload = json.loads(formatter.format(logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)))

    assert len(payload["trace_id"]) == 32
    assert len(payload["span_id"]) == 16
    assert payload["trace_id"].islower()
    assert payload["span_id"].islower()


def test_json_formatter_does_not_serialize_exception_message() -> None:
    formatter = JsonFormatter(service="parksmart", environment="test", service_version="1.2.3")
    try:
        raise RuntimeError("secret database detail")
    except RuntimeError:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "request failed",
            (),
            sys.exc_info(),
        )

    rendered = formatter.format(record)
    payload = json.loads(rendered)

    assert payload["exception_type"] == "RuntimeError"
    assert "secret database detail" not in rendered
