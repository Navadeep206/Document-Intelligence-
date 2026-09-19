"""Test suite for health and readiness probe endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.core.config import get_settings
from app.main import app
from app.workers.celery_app import health_check_task

client = TestClient(app, raise_server_exceptions=False)
settings = get_settings()


def test_liveness_endpoint() -> None:
    """Test GET /api/v1/health returns 200 with service metadata."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == settings.APP_NAME


def test_readiness_endpoint_healthy() -> None:
    """Test GET /api/v1/health/ready returns 200 when all dependencies are healthy."""
    with (
        patch("app.api.v1.health.check_db_health", return_value=(True, "healthy")),
        patch("app.api.v1.health.check_redis_health", return_value=(True, "healthy")),
    ):
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "healthy"
        assert data["redis"] == "healthy"


def test_readiness_endpoint_database_down() -> None:
    """Test GET /api/v1/health/ready returns 503 when database is unreachable."""
    with (
        patch("app.api.v1.health.check_db_health", return_value=(False, "unhealthy")),
        patch("app.api.v1.health.check_redis_health", return_value=(True, "healthy")),
    ):
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "unhealthy"
        assert data["redis"] == "healthy"


def test_readiness_endpoint_redis_down() -> None:
    """Test GET /api/v1/health/ready returns 503 when Redis is unreachable."""
    with (
        patch("app.api.v1.health.check_db_health", return_value=(True, "healthy")),
        patch("app.api.v1.health.check_redis_health", return_value=(False, "unhealthy")),
    ):
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "healthy"
        assert data["redis"] == "unhealthy"


def test_celery_health_check_task() -> None:
    """Test that baseline Celery task executes and returns expected status."""
    result = health_check_task.apply()
    assert result.result == {"status": "ok"}


def test_structured_error_response_format() -> None:
    """Test that non-existent routes return our structured error model."""
    response = client.get("/api/v1/undefined-endpoint")
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "message" in data["error"]
