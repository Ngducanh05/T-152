"""Isolated, opt-in OpenTelemetry and LangSmith runtime configuration."""

import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar, Token
from typing import Any
from urllib.parse import unquote

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import event
from sqlalchemy.engine import Engine

from src.core.config import Settings

logger = logging.getLogger(__name__)
_SUPPORTED_SAMPLER = "parentbased_traceidratio"
_ACTIVE_OBSERVABILITY: ContextVar["ObservabilityRuntime | None"] = ContextVar(
    "active_observability", default=None
)


def bind_observability_runtime(runtime: "ObservabilityRuntime") -> Token["ObservabilityRuntime | None"]:
    """Bind the application-owned runtime to the current request context."""
    return _ACTIVE_OBSERVABILITY.set(runtime)


def reset_observability_runtime(token: Token["ObservabilityRuntime | None"]) -> None:
    """Reset a runtime binding returned by :func:`bind_observability_runtime`."""
    _ACTIVE_OBSERVABILITY.reset(token)


def get_active_observability() -> "ObservabilityRuntime | None":
    """Return the request-local application-owned observability runtime."""
    return _ACTIVE_OBSERVABILITY.get()


def _trace_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/v1/traces"):
        return normalized
    return f"{normalized}/v1/traces"


def _parse_otlp_headers(raw_headers: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for entry in raw_headers.split(","):
        key, separator, value = entry.partition("=")
        if not separator or not key.strip():
            raise ValueError("OTEL_EXPORTER_OTLP_HEADERS must contain key=value entries")
        headers[unquote(key.strip())] = unquote(value.strip())
    return headers


def _resource_for(settings: Settings) -> Resource:
    attributes = {
        "service.name": settings.otel_service_name,
        "service.version": settings.service_version or settings.otel_service_version,
        "deployment.environment.name": settings.environment,
    }
    if settings.git_commit_sha:
        attributes["git.commit.sha"] = settings.git_commit_sha
    return Resource.create(attributes)


class ObservabilityRuntime:
    """Application-owned tracing provider that avoids global provider replacement."""

    def __init__(self, settings: Settings) -> None:
        self.enabled = False
        self.provider: TracerProvider | None = None
        self.tracer = trace.NoOpTracer()
        self.exporter: OTLPSpanExporter | None = None
        self.processor: BatchSpanProcessor | None = None
        self._shutdown = False
        self._engine_listeners: dict[int, tuple[Engine, tuple[Any, Any, Any]]] = {}

        if not settings.observability_enabled:
            return

        try:
            self._configure(settings)
        except Exception:  # noqa: BLE001 - telemetry must never prevent startup
            logger.warning("observability_disabled configuration_invalid")

    def _configure(self, settings: Settings) -> None:
        if settings.otel_exporter_otlp_protocol.lower() != "http/protobuf":
            raise ValueError("unsupported OTLP protocol")
        if settings.otel_traces_exporter.lower() != "otlp":
            raise ValueError("unsupported traces exporter")
        if settings.otel_traces_sampler.lower() != _SUPPORTED_SAMPLER:
            raise ValueError("unsupported sampler")
        if not (settings.otel_exporter_otlp_endpoint or "").strip():
            raise ValueError("missing OTLP endpoint")
        if not (settings.otel_exporter_otlp_headers or "").strip():
            raise ValueError("missing OTLP headers")

        sampler = ParentBased(TraceIdRatioBased(settings.otel_traces_sampler_arg))
        provider = TracerProvider(resource=_resource_for(settings), sampler=sampler)
        exporter = OTLPSpanExporter(
            endpoint=_trace_endpoint(settings.otel_exporter_otlp_endpoint.strip()),
            headers=_parse_otlp_headers(settings.otel_exporter_otlp_headers),
        )
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        self.provider = provider
        self.exporter = exporter
        self.processor = processor
        self.tracer = provider.get_tracer(settings.otel_service_name)
        self.enabled = True

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Mapping[str, object] | None = None,
    ) -> Iterator[Span | None]:
        """Create a privacy-safe current span from this runtime's tracer only."""
        if not self.enabled:
            with nullcontext(None) as span:
                yield span
            return
        with self.tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=dict(attributes or {}),
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception as error:  # noqa: BLE001 - safe telemetry boundary
                span.set_attribute("outcome", "error")
                self.mark_span_failed(span, exception=error)
                raise

    @staticmethod
    def mark_span_failed(
        span: Span | None,
        *,
        exception: BaseException | None = None,
        exception_type: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Mark a span failed without recording exception payloads or stack traces."""
        if span is None:
            return
        span.set_status(trace.Status(trace.StatusCode.ERROR))
        if exception is not None:
            span.set_attribute("error.type", type(exception).__name__)
        elif exception_type:
            span.set_attribute("error.type", exception_type)
        if error_code:
            span.set_attribute("error.code", error_code)

    @contextmanager
    def start_http_server_span(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
    ) -> Iterator[Span | None]:
        if not self.enabled:
            with nullcontext(None) as span:
                yield span
            return

        parent_context = TraceContextTextMapPropagator().extract(headers)
        with self.tracer.start_as_current_span(
            f"{method} {path}",
            context=parent_context,
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": method,
                "url.path": path,
            },
        ) as span:
            yield span

    def instrument_sqlalchemy_engine(self, sync_engine: Engine) -> None:
        """Attach safe query timing spans to an engine once for this runtime."""
        if not self.enabled or id(sync_engine) in self._engine_listeners:
            return

        def before_cursor_execute(
            conn: object,
            cursor: object,
            statement: str,
            parameters: object,
            execution_context: object,
            executemany: object,
        ) -> None:
            del conn, cursor, parameters, executemany
            keyword = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "OTHER"
            operation = keyword if keyword in {"SELECT", "INSERT", "UPDATE", "DELETE", "BEGIN", "COMMIT", "ROLLBACK"} else "OTHER"
            dialect = getattr(sync_engine, "dialect", None)
            span = self.tracer.start_span(
                "db.query",
                kind=SpanKind.CLIENT,
                attributes={
                    "db.system.name": str(getattr(dialect, "name", "unknown")),
                    "db.operation.name": operation,
                },
            )
            setattr(execution_context, "_parksmart_observability_span", span)

        def after_cursor_execute(
            conn: object,
            cursor: object,
            statement: str,
            parameters: object,
            execution_context: object,
            executemany: object,
        ) -> None:
            del conn, cursor, statement, parameters, executemany
            span = getattr(execution_context, "_parksmart_observability_span", None)
            if span is not None:
                span.end()
                delattr(execution_context, "_parksmart_observability_span")

        def handle_error(exception_context: object) -> None:
            execution_context = getattr(exception_context, "execution_context", None)
            span = getattr(execution_context, "_parksmart_observability_span", None)
            if span is not None:
                self.mark_span_failed(span, exception=getattr(exception_context, "original_exception", None))
                span.end()
                delattr(execution_context, "_parksmart_observability_span")

        event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
        event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)
        event.listen(sync_engine, "handle_error", handle_error)
        self._engine_listeners[id(sync_engine)] = (sync_engine, (before_cursor_execute, after_cursor_execute, handle_error))

    @staticmethod
    def trace_id_for_span(span: Span | None) -> str | None:
        if span is None:
            return None
        context = span.get_span_context()
        if not context.is_valid:
            return None
        return f"{context.trace_id:032x}"

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        for engine, listeners in self._engine_listeners.values():
            event.remove(engine, "before_cursor_execute", listeners[0])
            event.remove(engine, "after_cursor_execute", listeners[1])
            event.remove(engine, "handle_error", listeners[2])
        self._engine_listeners.clear()
        if self.provider is not None:
            self.provider.force_flush()
            self.provider.shutdown()


def configure_langsmith(settings: Settings) -> None:
    """Bridge Settings values to LangSmith's environment-driven integrations."""
    api_key = (settings.langsmith_api_key or "").strip()
    if not settings.langsmith_tracing or not api_key:
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
        os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
        os.environ["LANGSMITH_HIDE_METADATA"] = "true"
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_METADATA"] = "true"
