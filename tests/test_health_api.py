"""Integration tests for US-002 Health Check Endpoint."""

import pytest
from examples.health_api.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_health_returns_200_with_status_ok(client: TestClient) -> None:
    """T-1: GET /health → 200, application/json, body identical to {"status": "ok"}."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok"}


def test_post_health_returns_405_method_not_allowed(client: TestClient) -> None:
    """T-2: POST /health → 405, application/json, exact Method Not Allowed body."""
    response = client.post("/health")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Method Not Allowed"}


def test_put_health_returns_405_method_not_allowed(client: TestClient) -> None:
    """T-3: PUT /health → 405 with same body and media type as T-2."""
    response = client.put("/health")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Method Not Allowed"}


def test_delete_health_returns_405_method_not_allowed(client: TestClient) -> None:
    """T-4: DELETE /health → 405 with same body and media type as T-2."""
    response = client.delete("/health")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Method Not Allowed"}


def test_patch_health_returns_405_method_not_allowed(client: TestClient) -> None:
    """T-5: PATCH /health → 405 with same body and media type as T-2."""
    response = client.patch("/health")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Method Not Allowed"}