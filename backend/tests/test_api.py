"""Tests for API status endpoints and health check"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db


@pytest.fixture
def client():
    """Create test client with mocked database"""
    db = AsyncMock()

    async def override_get_db():
        return db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, raise_server_exceptions=False), db
    app.dependency_overrides.clear()


class TestStatusEndpoints:
    def test_api_status(self, client):
        test_client, _ = client
        response = test_client.get("/api")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "ENCPServices"
        assert data["status"] == "online"

    def test_health_check_db_down(self, client):
        test_client, _ = client
        with patch("app.main._pool", None):
            response = test_client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["database"] == "unavailable"

    def test_health_check_db_up(self, client):
        test_client, _ = client
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_pool.acquire = MagicMock(return_value=mock_ctx)

        with patch("app.main._pool", mock_pool):
            response = test_client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["database"] == "connected"


class TestRateLimiting:
    def test_blog_generate_rate_limit(self, client):
        test_client, db = client
        from app.security import create_access_token, rate_limiter

        token = create_access_token(
            "test-user-rate-limit",
            "admin@encpservices.com",
            role="admin"
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Reset rate limiter for clean test
        rate_limiter._requests.pop("test-user-rate-limit", None)

        with patch("app.blog.service.generate_blog_post", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"id": "1", "title": "Test", "slug": "test"}

            response = test_client.post("/blog/admin/generate", json={
                "topic": "Test Topic"
            }, headers=headers)
            assert response.status_code == 200
