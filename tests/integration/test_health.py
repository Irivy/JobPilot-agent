"""Integration tests for the health endpoint."""

from app.main import app
from fastapi.testclient import TestClient


def test_app_importable() -> None:
    assert app is not None


def test_health_returns_expected_response() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "application/json" in response.headers["content-type"]
