import os

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import Decision
from opentelemetry.trace import SpanKind

from src.core.config import Settings
from src.core.observability import (
    ObservabilityRuntime,
    _parse_otlp_headers,
    _trace_endpoint,
    configure_langsmith,
)


def _enabled_settings() -> Settings:
    return Settings(
        _env_file=None,
        observability_enabled=True,
        otel_exporter_otlp_endpoint="https://tenant.grafana.net/otlp",
        otel_exporter_otlp_headers="Authorization=Basic%20encoded-value",
    )


def test_disabled_runtime_does_not_create_exporter(monkeypatch) -> None:
    def unexpected_exporter(**_kwargs):
        raise AssertionError("exporter must not be created when disabled")

    monkeypatch.setattr("src.core.observability.OTLPSpanExporter", unexpected_exporter)
    runtime = ObservabilityRuntime(Settings(_env_file=None, observability_enabled=False))

    assert runtime.enabled is False
    runtime.shutdown()


def test_grafana_trace_endpoint_is_derived_exactly_once() -> None:
    assert _trace_endpoint("https://tenant.grafana.net/otlp") == "https://tenant.grafana.net/otlp/v1/traces"
    assert _trace_endpoint("https://tenant.grafana.net/otlp/v1/traces") == "https://tenant.grafana.net/otlp/v1/traces"


def test_otlp_headers_decode_percent_escaping_without_logging(caplog) -> None:
    headers = _parse_otlp_headers("Authorization=Basic%20encoded-value")

    assert headers == {"Authorization": "Basic encoded-value"}
    assert "encoded-value" not in caplog.text


def test_sampler_is_applied_and_shutdown_is_idempotent(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr("src.core.observability.OTLPSpanExporter", lambda **_kwargs: exporter)
    runtime = ObservabilityRuntime(_enabled_settings())

    assert runtime.enabled is True
    assert runtime.provider is not None
    sample_result = runtime.provider.sampler.should_sample(
        None,
        1,
        "GET /health",
        SpanKind.SERVER,
        {},
        [],
    )
    assert sample_result.decision is Decision.RECORD_AND_SAMPLE
    runtime.shutdown()
    runtime.shutdown()


def test_configure_langsmith_maps_legacy_settings_and_forces_privacy(monkeypatch) -> None:
    for name in ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_API_KEY", "legacy-key")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "legacy-project")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    settings = Settings(_env_file=None)

    configure_langsmith(settings)

    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "legacy-key"
    assert os.environ["LANGSMITH_PROJECT"] == "legacy-project"
    assert os.environ["LANGSMITH_HIDE_INPUTS"] == "true"
    assert os.environ["LANGSMITH_HIDE_OUTPUTS"] == "true"
    assert os.environ["LANGSMITH_HIDE_METADATA"] == "true"


def test_configure_langsmith_disables_runtime_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    settings = Settings(_env_file=None, langsmith_tracing=False)

    configure_langsmith(settings)

    assert os.environ["LANGSMITH_TRACING"] == "false"
