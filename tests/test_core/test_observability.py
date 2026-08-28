import os

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import Decision
from opentelemetry.trace import SpanKind
from sqlalchemy import create_engine, text

from src.core.config import Settings
from src.core.observability import (
    ObservabilityRuntime,
    _parse_otlp_headers,
    _trace_endpoint,
    bind_observability_runtime,
    configure_langsmith,
    get_active_observability,
    reset_observability_runtime,
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


def test_start_span_is_noop_when_disabled() -> None:
    runtime = ObservabilityRuntime(Settings(_env_file=None, observability_enabled=False))

    with runtime.start_span("private.operation") as span:
        assert span is None


def test_start_span_uses_app_provider_and_redacts_exception_message(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr("src.core.observability.OTLPSpanExporter", lambda **_kwargs: exporter)
    runtime = ObservabilityRuntime(_enabled_settings())

    with runtime.start_span("safe.operation") as span:
        assert span is not None
        span.set_attribute("safe.attribute", "value")
    with pytest.raises(RuntimeError, match="secret"):
        with runtime.start_span("safe.failure"):
            raise RuntimeError("secret database password")
    runtime.shutdown()

    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert spans["safe.operation"].attributes["safe.attribute"] == "value"
    assert spans["safe.failure"].attributes["error.type"] == "RuntimeError"
    assert "secret database password" not in str(spans["safe.failure"].attributes)
    assert not spans["safe.failure"].events


def test_active_runtime_binding_is_reset() -> None:
    runtime = ObservabilityRuntime(Settings(_env_file=None, observability_enabled=False))
    token = bind_observability_runtime(runtime)
    try:
        assert get_active_observability() is runtime
    finally:
        reset_observability_runtime(token)

    assert get_active_observability() is None


def test_sqlalchemy_engine_instrumentation_is_safe_and_idempotent(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr("src.core.observability.OTLPSpanExporter", lambda **_kwargs: exporter)
    runtime = ObservabilityRuntime(_enabled_settings())
    engine = create_engine("sqlite://")

    runtime.instrument_sqlalchemy_engine(engine)
    runtime.instrument_sqlalchemy_engine(engine)
    with engine.connect() as connection:
        connection.execute(text("SELECT :secret_value"), {"secret_value": "PRIVATE-PARAMETER"})
    runtime.shutdown()
    spans = [span for span in exporter.get_finished_spans() if span.name == "db.query"]

    assert len(spans) == 1
    assert spans[0].attributes == {"db.system.name": "sqlite", "db.operation.name": "SELECT"}
    assert "SELECT :secret_value" not in str(spans[0].attributes)
    assert "PRIVATE-PARAMETER" not in str(spans[0].attributes)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    assert len(exporter.get_finished_spans()) == 1
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
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    assert os.environ["LANGSMITH_HIDE_INPUTS"] == "true"
    assert os.environ["LANGSMITH_HIDE_OUTPUTS"] == "true"
    assert os.environ["LANGSMITH_HIDE_METADATA"] == "true"
