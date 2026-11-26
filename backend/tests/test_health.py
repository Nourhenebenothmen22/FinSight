"""Tests for health check endpoints."""

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.routes import health as health_module


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test GET /health returns 200 and healthy when all checks pass."""
        monkeypatch.setattr(health_module, "_check_redis", AsyncMock(return_value="healthy"))
        monkeypatch.setattr(health_module, "_check_qdrant", AsyncMock(return_value="healthy"))
        monkeypatch.setattr(health_module, "_check_storage", AsyncMock(return_value="healthy"))

        response = await async_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "FinSight"
        assert data["version"] == "0.1.0"
        assert data["status"] == "healthy"
        assert data["checks"] == {
            "database": "healthy",
            "redis": "healthy",
            "qdrant": "healthy",
            "storage": "healthy",
        }

    @pytest.mark.asyncio
    async def test_health_check_returns_503_when_dependency_unhealthy(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test GET /health returns 503 when any dependency is unhealthy."""
        monkeypatch.setattr(health_module, "_check_redis", AsyncMock(return_value="healthy"))
        monkeypatch.setattr(health_module, "_check_qdrant", AsyncMock(return_value="unhealthy"))
        monkeypatch.setattr(health_module, "_check_storage", AsyncMock(return_value="healthy"))

        response = await async_client.get("/health")
        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["qdrant"] == "unhealthy"
        assert "Traceback" not in response.text

    @pytest.mark.asyncio
    async def test_readiness_check_returns_503_when_unhealthy(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test GET /health/ready mirrors dependency readiness status."""
        monkeypatch.setattr(health_module, "_check_redis", AsyncMock(return_value="unhealthy"))
        monkeypatch.setattr(health_module, "_check_qdrant", AsyncMock(return_value="healthy"))
        monkeypatch.setattr(health_module, "_check_storage", AsyncMock(return_value="healthy"))

        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_liveness_check(self, async_client: AsyncClient) -> None:
        """Test GET /health/live returns alive status."""
        response = await async_client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    @pytest.mark.asyncio
    async def test_root_endpoint(self, async_client: AsyncClient) -> None:
        """Test GET / returns service info."""
        response = await async_client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert data["service"] == "FinSight"
        assert data["version"] == "0.1.0"
        assert data["health"] == "/health"


class TestHealthResponseSchema:
    """Test health response schema validation."""

    @pytest.mark.asyncio
    async def test_health_response_structure(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test health response has expected structure."""
        monkeypatch.setattr(health_module, "_check_redis", AsyncMock(return_value="healthy"))
        monkeypatch.setattr(health_module, "_check_qdrant", AsyncMock(return_value="healthy"))
        monkeypatch.setattr(health_module, "_check_storage", AsyncMock(return_value="healthy"))

        response = await async_client.get("/health")
        data = response.json()

        required_fields = ["status", "service", "version", "environment", "checks"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

        assert data["environment"] in ("development", "staging", "production", "test")
        assert isinstance(data["checks"], dict)

        for check in ("database", "redis", "qdrant", "storage"):
            assert check in data["checks"], f"Missing check: {check}"
            assert isinstance(data["checks"][check], str)
