"""Tests for security module: passwords, JWT tokens, encryption, rate limiting"""

import pytest
import time
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    encrypt_data,
    decrypt_data,
    generate_secure_token,
    hash_for_audit,
    RateLimiter,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "MySecurePass123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_different_hashes_per_call(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # Different salts


class TestJWT:
    def test_create_and_verify_access_token(self):
        token = create_access_token("user-123", "test@test.com", role="admin")
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@test.com"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_create_and_verify_refresh_token(self):
        token = create_refresh_token("user-123")
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"

    def test_invalid_token_returns_none(self):
        assert verify_token("invalid.token.here") is None

    def test_tampered_token_fails(self):
        token = create_access_token("user-123", "test@test.com")
        tampered = token[:-5] + "XXXXX"
        assert verify_token(tampered) is None


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "Sensitive client data: 123 Main St"
        user_id = "user-abc-123"
        encrypted = encrypt_data(original, user_id)
        decrypted = decrypt_data(encrypted, user_id)
        assert decrypted == original

    def test_empty_data(self):
        assert encrypt_data("", "user-1") == b""
        assert decrypt_data(b"", "user-1") == ""

    def test_different_users_different_ciphertext(self):
        data = "Same data"
        enc1 = encrypt_data(data, "user-1")
        enc2 = encrypt_data(data, "user-2")
        assert enc1 != enc2

    def test_wrong_user_cannot_decrypt(self):
        encrypted = encrypt_data("secret", "user-1")
        result = decrypt_data(encrypted, "user-2")
        assert result == "[Data could not be recovered]"


class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter()
        for _ in range(5):
            assert rl.is_allowed("user-1", max_requests=5, window_seconds=60)

    def test_blocks_over_limit(self):
        rl = RateLimiter()
        for _ in range(3):
            rl.is_allowed("user-1", max_requests=3, window_seconds=60)
        assert not rl.is_allowed("user-1", max_requests=3, window_seconds=60)

    def test_different_users_independent(self):
        rl = RateLimiter()
        for _ in range(3):
            rl.is_allowed("user-1", max_requests=3, window_seconds=60)
        assert rl.is_allowed("user-2", max_requests=3, window_seconds=60)

    def test_get_remaining(self):
        rl = RateLimiter()
        assert rl.get_remaining("user-1", max_requests=5) == 5
        rl.is_allowed("user-1", max_requests=5)
        rl.is_allowed("user-1", max_requests=5)
        assert rl.get_remaining("user-1", max_requests=5) == 3


class TestUtilities:
    def test_secure_token_length(self):
        token = generate_secure_token(32)
        assert len(token) > 20  # URL-safe base64 encoding

    def test_secure_token_unique(self):
        t1 = generate_secure_token()
        t2 = generate_secure_token()
        assert t1 != t2

    def test_audit_hash(self):
        h = hash_for_audit("some data")
        assert len(h) == 16
        assert hash_for_audit("some data") == h  # Deterministic
