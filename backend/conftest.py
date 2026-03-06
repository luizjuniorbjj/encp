"""
Shared test fixtures for ENCP Services backend tests
"""

import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment before importing app modules
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing-only"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db():
    """Mock database for unit tests"""
    db = AsyncMock()
    db.pool = MagicMock()
    db.get_user_by_email = AsyncMock(return_value=None)
    db.get_user_by_id = AsyncMock(return_value=None)
    db.create_user = AsyncMock(return_value={
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "test@test.com",
        "role": "client",
        "created_at": "2025-01-01T00:00:00"
    })
    db.log_audit = AsyncMock()
    db.create_user_profile = AsyncMock()
    db.update_last_login = AsyncMock()
    return db


@pytest.fixture
def admin_token():
    """Generate a valid admin JWT token for testing"""
    from app.security import create_access_token
    return create_access_token(
        user_id="550e8400-e29b-41d4-a716-446655440000",
        email="admin@encpservices.com",
        role="admin"
    )


@pytest.fixture
def client_token():
    """Generate a valid client JWT token for testing"""
    from app.security import create_access_token
    return create_access_token(
        user_id="660e8400-e29b-41d4-a716-446655440001",
        email="client@test.com",
        role="client"
    )
