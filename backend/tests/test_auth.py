"""Tests for authentication routes"""

import pytest
from unittest.mock import AsyncMock
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


class TestLogin:
    def test_login_success(self, client):
        test_client, db = client
        from app.security import hash_password
        db.get_user_by_email = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "admin@encpservices.com",
            "password_hash": hash_password("admin123"),
            "role": "admin",
            "is_active": True,
        })
        db.update_last_login = AsyncMock()
        db.log_audit = AsyncMock()

        response = test_client.post("/auth/login", json={
            "email": "admin@encpservices.com",
            "password": "admin123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        test_client, db = client
        from app.security import hash_password
        db.get_user_by_email = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "admin@encpservices.com",
            "password_hash": hash_password("correct_password"),
            "role": "admin",
            "is_active": True,
        })

        response = test_client.post("/auth/login", json={
            "email": "admin@encpservices.com",
            "password": "wrong_password"
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client):
        test_client, db = client
        db.get_user_by_email = AsyncMock(return_value=None)

        response = test_client.post("/auth/login", json={
            "email": "nobody@test.com",
            "password": "whatever"
        })
        assert response.status_code == 401

    def test_login_deactivated_account(self, client):
        test_client, db = client
        from app.security import hash_password
        db.get_user_by_email = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "blocked@test.com",
            "password_hash": hash_password("password123"),
            "role": "client",
            "is_active": False,
        })

        response = test_client.post("/auth/login", json={
            "email": "blocked@test.com",
            "password": "password123"
        })
        assert response.status_code == 403


class TestRegister:
    def test_register_success(self, client):
        test_client, db = client
        db.get_user_by_email = AsyncMock(return_value=None)
        db.create_user = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "new@test.com",
            "role": "client",
        })
        db.create_user_profile = AsyncMock()
        db.log_audit = AsyncMock()

        response = test_client.post("/auth/register", json={
            "email": "new@test.com",
            "password": "strongpass123",
            "accepted_terms": True,
        })
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_register_without_terms(self, client):
        test_client, _ = client
        response = test_client.post("/auth/register", json={
            "email": "new@test.com",
            "password": "strongpass123",
            "accepted_terms": False,
        })
        assert response.status_code == 400

    def test_register_short_password(self, client):
        test_client, db = client
        db.get_user_by_email = AsyncMock(return_value=None)

        response = test_client.post("/auth/register", json={
            "email": "new@test.com",
            "password": "short",
            "accepted_terms": True,
        })
        assert response.status_code == 400

    def test_register_duplicate_email(self, client):
        test_client, db = client
        db.get_user_by_email = AsyncMock(return_value={"id": "exists"})

        response = test_client.post("/auth/register", json={
            "email": "existing@test.com",
            "password": "strongpass123",
            "accepted_terms": True,
        })
        assert response.status_code == 400


class TestTokenRefresh:
    def test_refresh_success(self, client):
        test_client, db = client
        from app.security import create_refresh_token
        refresh = create_refresh_token("550e8400-e29b-41d4-a716-446655440000")

        db.get_user_by_id = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "admin@encpservices.com",
            "role": "admin",
            "is_active": True,
        })

        response = test_client.post("/auth/refresh", json={
            "refresh_token": refresh
        })
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_refresh_invalid_token(self, client):
        test_client, _ = client
        response = test_client.post("/auth/refresh", json={
            "refresh_token": "invalid.token.here"
        })
        assert response.status_code == 401


class TestProtectedRoutes:
    def test_me_without_token(self, client):
        test_client, _ = client
        response = test_client.get("/auth/me")
        assert response.status_code == 422  # Missing header

    def test_me_with_valid_token(self, client, admin_token):
        test_client, db = client
        db.get_user_by_id = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "admin@encpservices.com",
            "role": "admin",
            "created_at": "2025-01-01T00:00:00",
        })
        db.get_user_profile = AsyncMock(return_value={
            "nome": "Admin",
            "phone": "5615067035",
        })

        response = test_client.get("/auth/me", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert response.status_code == 200
        assert response.json()["email"] == "admin@encpservices.com"
