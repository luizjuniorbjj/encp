"""
ENCPServices - Seguranca e Criptografia
Sistema de autenticacao e protecao de dados sensiveis
Forked from SegurIA — adapted salt for ENCPServices data isolation
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional
from base64 import b64encode

logger = logging.getLogger("encp.security")

import cryptography.fernet
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import bcrypt
import jwt

from app.config import SECRET_KEY, ENCRYPTION_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_HOURS, JWT_REFRESH_TOKEN_DAYS, REDIS_URL


# ============================================
# PASSWORD HASHING
# ============================================

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


# ============================================
# JWT TOKENS (NO agency_id — single company)
# ============================================

def create_access_token(user_id: str, email: str, role: str = "client") -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_ACCESS_TOKEN_HOURS),
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": str(user_id),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_DAYS),
        "type": "refresh"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ============================================
# DATA ENCRYPTION (Fernet - AES 128)
# ============================================

def _get_fernet_key(user_salt: str = "") -> bytes:
    combined = f"{ENCRYPTION_KEY}{user_salt}".encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        # Salt unico para ENCPServices — dados NUNCA sao compativeis com SegurIA ou ClaWin
        salt=b"encp_salt_v1",
        iterations=100000,
    )
    key = b64encode(kdf.derive(combined))
    return key


def encrypt_data(data: str, user_id: str = "") -> bytes:
    if not data:
        return b""
    key = _get_fernet_key(user_id)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(data.encode('utf-8'))
    return encrypted


def decrypt_data(encrypted_data: bytes, user_id: str = "") -> str:
    if not encrypted_data:
        return ""
    try:
        key = _get_fernet_key(user_id)
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_data)
        return decrypted.decode('utf-8')
    except (InvalidToken, ValueError, TypeError) as e:
        logger.error("Failed to decrypt for user %s...: %s", user_id[:8] if user_id else "N/A", type(e).__name__)
        return "[Data could not be recovered]"


# ============================================
# UTILITY FUNCTIONS
# ============================================

def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def hash_for_audit(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


# ============================================
# RATE LIMITING (Redis distributed + in-memory fallback)
# ============================================

_redis_client = None
_redis_available = False


def _init_redis():
    """Initialize Redis connection (lazy, called on first use)"""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return
    try:
        if REDIS_URL:
            import redis
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            _redis_client.ping()
            _redis_available = True
            logger.info("Redis connected for rate limiting")
        else:
            _redis_available = False
            logger.info("REDIS_URL not set — using in-memory rate limiting")
    except Exception as e:
        _redis_available = False
        logger.warning("Redis unavailable, falling back to in-memory: %s", e)


class RateLimiter:
    def __init__(self):
        self._requests = {}  # fallback in-memory

    def is_allowed(self, user_id: str, max_requests: int = 60, window_seconds: int = 60) -> bool:
        _init_redis()
        if _redis_available:
            return self._redis_is_allowed(user_id, max_requests, window_seconds)
        return self._memory_is_allowed(user_id, max_requests, window_seconds)

    def get_remaining(self, user_id: str, max_requests: int = 60, window_seconds: int = 60) -> int:
        _init_redis()
        if _redis_available:
            return self._redis_get_remaining(user_id, max_requests, window_seconds)
        return self._memory_get_remaining(user_id, max_requests, window_seconds)

    # --- Redis implementation (sliding window counter) ---

    def _redis_is_allowed(self, user_id: str, max_requests: int, window_seconds: int) -> bool:
        try:
            key = f"rl:{user_id}:{window_seconds}"
            current = _redis_client.get(key)
            if current and int(current) >= max_requests:
                return False
            pipe = _redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            pipe.execute()
            return True
        except Exception as e:
            logger.warning("Redis rate limit error, falling back: %s", e)
            return self._memory_is_allowed(user_id, max_requests, window_seconds)

    def _redis_get_remaining(self, user_id: str, max_requests: int, window_seconds: int) -> int:
        try:
            key = f"rl:{user_id}:{window_seconds}"
            current = _redis_client.get(key)
            used = int(current) if current else 0
            return max(0, max_requests - used)
        except Exception as e:
            logger.warning("Redis remaining error, falling back: %s", e)
            return self._memory_get_remaining(user_id, max_requests, window_seconds)

    # --- In-memory fallback ---

    def _memory_is_allowed(self, user_id: str, max_requests: int, window_seconds: int) -> bool:
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)

        if user_id not in self._requests:
            self._requests[user_id] = []

        self._requests[user_id] = [
            req_time for req_time in self._requests[user_id]
            if req_time > window_start
        ]

        if len(self._requests[user_id]) >= max_requests:
            return False

        self._requests[user_id].append(now)
        return True

    def _memory_get_remaining(self, user_id: str, max_requests: int, window_seconds: int) -> int:
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)

        if user_id not in self._requests:
            return max_requests

        recent = [
            req_time for req_time in self._requests[user_id]
            if req_time > window_start
        ]

        return max(0, max_requests - len(recent))


rate_limiter = RateLimiter()
