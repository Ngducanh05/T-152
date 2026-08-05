from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_application_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_application_health_is_in_openapi_schema():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
