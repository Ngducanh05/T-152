"""Isolated, opt-in OpenTelemetry and LangSmith runtime configuration."""

import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from urllib.parse import unquote

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from src.core.config import Settings

logger = logging.getLogger(__name__)
_SUPPORTED_SAMPLER = "parentbased_traceidratio"


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
        if self.provider is not None:
            self.provider.force_flush()
            self.provider.shutdown()


def configure_langsmith(settings: Settings) -> None:
    """Bridge Settings values to LangSmith's environment-driven integrations."""
    api_key = (settings.langsmith_api_key or "").strip()
    if not settings.langsmith_tracing or not api_key:
        os.environ["LANGSMITH_TRACING"] = "false"
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_METADATA"] = "true"
