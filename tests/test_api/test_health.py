from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.api.main import REQUEST_ID_HEADER, app
from src.core.config import get_settings

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
