import logging
from uuid import UUID, uuid4

from fastapi import APIRouter
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.api.main import REQUEST_ID_HEADER, app, create_app
from src.core.config import Settings, get_settings

client = TestClient(app)


def test_health_returns_contract():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    settings = get_settings()
    assert body == {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "request_id": body["request_id"],
    }
    UUID(body["request_id"])


def test_health_generates_request_id():
    for headers in ({}, {REQUEST_ID_HEADER: "not-a-uuid"}):
        response = client.get("/health", headers=headers)
        UUID(response.json()["request_id"])


def test_health_preserves_valid_request_id():
    request_id = str(uuid4())

    response = client.get("/health", headers={REQUEST_ID_HEADER: request_id})

    assert response.json()["request_id"] == request_id
    assert response.headers[REQUEST_ID_HEADER] == request_id


def test_response_contains_request_id_header():
    response = client.get("/health")

    response_request_id = response.headers[REQUEST_ID_HEADER]
    UUID(response_request_id)
    assert response_request_id == response.json()["request_id"]


def test_error_response_contains_request_id():
    request_id = str(uuid4())

    response = client.get(
        "/route-that-does-not-exist",
        headers={REQUEST_ID_HEADER: request_id},
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.json()["error"]["request_id"] == request_id


def test_src_main_entrypoint_still_works():
    from src.main import app as compatibility_app

    assert compatibility_app is app


def test_application_health_is_in_openapi_schema():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
    assert "/api/v1/health/database" in response.json()["paths"]


def test_unexpected_request_failure_is_traceable_without_logging_details(caplog):
    request_id = str(uuid4())
    application = create_app(Settings(llm_api_key="test-key"))
    router = APIRouter()

    @router.get("/failing-request")
    async def failing_request():
        raise RuntimeError("secret database detail")

    application.include_router(router)
    caplog.set_level(logging.INFO)

    with TestClient(application, raise_server_exceptions=False) as test_client:
        response = test_client.get(
            "/failing-request",
            headers={REQUEST_ID_HEADER: request_id},
        )

    assert response.status_code == 500
    assert response.json()["error"]["request_id"] == request_id
    assert f"request_failed request_id={request_id}" in caplog.text
    assert f"request_completed request_id={request_id}" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert "secret database detail" not in caplog.text


def test_observability_disabled_keeps_health_response_without_trace_header() -> None:
    application = create_app(
        Settings(_env_file=None, agent_enabled=False, speech_enabled=False, observability_enabled=False)
    )

    with TestClient(application) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
    assert "X-Trace-ID" not in response.headers


def test_observability_exports_server_span_and_respects_traceparent(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr("src.core.observability.OTLPSpanExporter", lambda **_kwargs: exporter)
    application = create_app(
        Settings(
            _env_file=None,
            agent_enabled=False,
            speech_enabled=False,
            observability_enabled=True,
            otel_exporter_otlp_endpoint="https://tenant.grafana.net/otlp",
            otel_exporter_otlp_headers="Authorization=Basic%20encoded-value",
        )
    )
    request_id = str(uuid4())
    trace_id = "0123456789abcdef0123456789abcdef"

    with TestClient(application) as test_client:
        response = test_client.get(
            "/health",
            headers={
                REQUEST_ID_HEADER: request_id,
                "traceparent": f"00-{trace_id}-0123456789abcdef-01",
            },
        )

    spans = exporter.get_finished_spans()
    health_span = next(span for span in spans if span.name == "GET /health")
    assert response.headers[REQUEST_ID_HEADER] == request_id
    assert response.headers["X-Trace-ID"] == trace_id
    assert health_span.context.trace_id == int(trace_id, 16)
    assert health_span.attributes["http.request.method"] == "GET"
    assert health_span.attributes["url.path"] == "/health"
    assert health_span.attributes["parksmart.request_id"] == request_id


def test_observability_exports_safe_exception_type_only(monkeypatch, caplog) -> None:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr("src.core.observability.OTLPSpanExporter", lambda **_kwargs: exporter)
    application = create_app(
        Settings(
            _env_file=None,
            agent_enabled=False,
            speech_enabled=False,
            observability_enabled=True,
            otel_exporter_otlp_endpoint="https://tenant.grafana.net/otlp",
            otel_exporter_otlp_headers="Authorization=Basic%20encoded-value",
        )
    )
    router = APIRouter()

    @router.get("/observed-failure")
    async def observed_failure():
        raise RuntimeError("secret database detail")

    application.include_router(router)
    caplog.set_level(logging.INFO)
    with TestClient(application, raise_server_exceptions=False) as test_client:
        response = test_client.get("/observed-failure")

    failure_span = next(
        span for span in exporter.get_finished_spans() if span.name == "GET /observed-failure"
    )
    assert response.status_code == 500
    assert failure_span.attributes["error.type"] == "RuntimeError"
    assert "secret database detail" not in caplog.text
    assert "secret database detail" not in str(failure_span.attributes)
