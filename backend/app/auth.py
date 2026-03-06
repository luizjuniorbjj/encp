"""
ENCPServices - Authentication System
Login/Register + OAuth (Google) — Single company (NO multi-tenant)
Forked from SegurIA, removed agency_id/agency_slug
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode
import secrets
import httpx

logger = logging.getLogger("encp.auth")

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    generate_secure_token
)
from app.database import get_db, Database
from app.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    RESEND_API_KEY,
    EMAIL_FROM,
    APP_URL,
    APP_NAME,
    REDIS_URL
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================
# OAUTH STATE STORE (Redis or in-memory fallback)
# ============================================

class OAuthStateStore:
    """Stores OAuth state tokens. Uses Redis when available, else in-memory dict."""

    def __init__(self):
        self._memory = {}
        self._redis = None
        self._initialized = False

    def _init(self):
        if self._initialized:
            return
        self._initialized = True
        if REDIS_URL:
            try:
                import redis
                self._redis = redis.from_url(REDIS_URL, decode_responses=True)
                self._redis.ping()
                logger.info("OAuth state store using Redis")
            except Exception as e:
                self._redis = None
                logger.warning("OAuth state store falling back to memory: %s", e)

    def set(self, state: str, data: dict, ttl_seconds: int = 600):
        self._init()
        if self._redis:
            try:
                import json
                self._redis.setex(f"oauth:{state}", ttl_seconds, json.dumps(data, default=str))
                return
            except Exception:
                pass
        self._memory[state] = data

    def pop(self, state: str) -> bool:
        """Remove state and return True if it existed."""
        self._init()
        if self._redis:
            try:
                result = self._redis.delete(f"oauth:{state}")
                return result > 0
            except Exception:
                pass
        return self._memory.pop(state, None) is not None

    def exists(self, state: str) -> bool:
        self._init()
        if self._redis:
            try:
                return self._redis.exists(f"oauth:{state}") > 0
            except Exception:
                pass
        return state in self._memory


oauth_states = OAuthStateStore()


# ============================================
# MODELS
# ============================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nome: Optional[str] = None
    phone: Optional[str] = None
    accepted_terms: bool = False
    language: Optional[str] = "en"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    nome: Optional[str] = None
    phone: Optional[str] = None
    profile_photo_url: Optional[str] = None
    created_at: datetime


# ============================================
# EMAIL HELPER
# ============================================

async def _send_reset_email(email: str, token: str):
    """Send password reset email via Resend API"""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured — reset token for %s: %s...", email, token[:8])
        return

    reset_url = f"{APP_URL}/reset-password?token={token}"

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        resend.Emails.send({
            "from": EMAIL_FROM,
            "to": [email],
            "subject": f"Password Reset — {APP_NAME}",
            "html": f"""
                <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
                    <h2 style="color: #1A3A5C;">{APP_NAME}</h2>
                    <p>You requested a password reset. Click the button below to set a new password:</p>
                    <a href="{reset_url}"
                       style="display: inline-block; background: #1A3A5C; color: #fff;
                              padding: 12px 24px; border-radius: 6px; text-decoration: none;
                              font-weight: bold; margin: 16px 0;">
                        Reset Password
                    </a>
                    <p style="color: #666; font-size: 13px;">
                        This link expires in 1 hour. If you didn't request this, ignore this email.
                    </p>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
                    <p style="color: #999; font-size: 11px;">Powered by {APP_NAME}</p>
                </div>
            """
        })
        logger.info("Password reset email sent to %s", email)
    except Exception as e:
        logger.error("Failed to send reset email to %s: %s", email, e)


# ============================================
# DEPENDENCY: AUTHENTICATED USER
# ============================================

async def get_current_user(
    authorization: str = Header(..., description="Bearer token")
) -> dict:
    """
    FastAPI dependency that extracts and validates user from JWT token.
    Returns: {user_id, email, role}
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")

    token = authorization.replace("Bearer ", "")
    payload = verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token expired or invalid")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    return {
        "user_id": payload["sub"],
        "email": payload["email"],
        "role": payload.get("role", "client")
    }


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency that ensures user is admin"""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ============================================
# ROUTES
# ============================================

@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest, db: Database = Depends(get_db)):
    """Register new user"""
    if not request.accepted_terms:
        raise HTTPException(
            status_code=400,
            detail="You must accept the Terms of Service and Privacy Policy"
        )

    # Check if email already exists
    existing = await db.get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Create user
    password_hash = hash_password(request.password)
    user = await db.create_user(
        email=request.email,
        password_hash=password_hash,
        nome=request.nome,
        phone=request.phone,
        accepted_terms=request.accepted_terms
    )

    # Create initial profile
    language = request.language if request.language in ["en", "pt", "es"] else "en"
    await db.create_user_profile(
        user_id=str(user["id"]),
        nome=request.nome,
        phone=request.phone,
        language=language
    )

    # Generate tokens
    access_token = create_access_token(
        user["id"], user["email"], role=user.get("role", "client")
    )
    refresh_token = create_refresh_token(user["id"])

    # Audit log
    await db.log_audit(
        user_id=str(user["id"]),
        action="register",
        details={"email": request.email, "accepted_terms": True}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Database = Depends(get_db)):
    """Login existing user"""
    user = await db.get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("password_hash") or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Update last login
    await db.update_last_login(str(user["id"]))

    # Generate tokens
    access_token = create_access_token(
        user["id"], user["email"], role=user.get("role", "client")
    )
    refresh_token = create_refresh_token(user["id"])

    # Audit log
    await db.log_audit(
        user_id=str(user["id"]),
        action="login",
        details={}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_route(request: RefreshRequest, db: Database = Depends(get_db)):
    """Renew tokens using refresh token"""
    payload = verify_token(request.refresh_token)

    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user = await db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")

    access_token = create_access_token(
        user["id"], user["email"], role=user.get("role", "client")
    )
    new_refresh_token = create_refresh_token(user["id"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """Return authenticated user data"""
    user = await db.get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await db.get_user_profile(current_user["user_id"])

    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        role=user.get("role", "client"),
        nome=profile.get("nome") if profile else None,
        phone=profile.get("phone") if profile else None,
        profile_photo_url=profile.get("profile_photo_url") if profile else None,
        created_at=user["created_at"]
    )


@router.post("/password-reset")
async def request_password_reset(request: PasswordResetRequest, db: Database = Depends(get_db)):
    """Request password reset"""
    user = await db.get_user_by_email(request.email)

    if user:
        token = generate_secure_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)
        await db.save_reset_token(str(user["id"]), token, expires_at)
        await _send_reset_email(request.email, token)

    # Always return success to avoid email enumeration
    return {"message": "If the email exists, you will receive password reset instructions"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(request: PasswordResetConfirm, db: Database = Depends(get_db)):
    """Confirm password reset with token"""
    token_data = await db.verify_reset_token(request.token)
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    password_hash = hash_password(request.new_password)
    await db.update_user_password(str(token_data["user_id"]), password_hash)
    await db.use_reset_token(request.token)

    await db.log_audit(
        user_id=str(token_data["user_id"]),
        action="password_reset",
        details={"method": "email_token"}
    )

    return {"message": "Password updated successfully"}


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """Logout (audit log only — JWT is stateless)"""
    await db.log_audit(
        user_id=current_user["user_id"],
        action="logout",
        details={}
    )

    return {"message": "Logged out successfully"}


# ============================================
# OAUTH - GOOGLE
# ============================================

@router.get("/google")
async def google_login():
    """Start Google OAuth flow"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google login not configured")

    state = secrets.token_urlsafe(32)
    oauth_states.set(state, {"provider": "google"})

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Database = Depends(get_db)
):
    """Google OAuth callback"""
    if error:
        return RedirectResponse(url=f"/?error={error}")

    if not code or not state:
        return RedirectResponse(url="/?error=missing_params")

    if not oauth_states.pop(state):
        return RedirectResponse(url="/?error=invalid_state")

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": GOOGLE_REDIRECT_URI
                }
            )

            if token_response.status_code != 200:
                return RedirectResponse(url="/?error=token_exchange_failed")

            tokens = token_response.json()
            access_token = tokens.get("access_token")

            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_response.status_code != 200:
                return RedirectResponse(url="/?error=user_info_failed")

            user_info = user_response.json()

        email = user_info.get("email")
        nome = user_info.get("name")
        google_id = user_info.get("id")
        picture = user_info.get("picture")

        if not email:
            return RedirectResponse(url="/?error=no_email")

        user = await db.get_user_by_email(email)

        if user:
            await db.update_last_login(str(user["id"]))
            if picture:
                profile = await db.get_user_profile(str(user["id"]))
                if profile and not profile.get("profile_photo_url"):
                    await db.update_user_profile(
                        user_id=str(user["id"]),
                        profile_photo_url=picture
                    )
        else:
            user = await db.create_user(
                email=email,
                password_hash=None,
                nome=nome,
                oauth_provider="google",
                oauth_id=google_id,
                accepted_terms=True
            )
            await db.create_user_profile(
                user_id=str(user["id"]),
                nome=nome
            )
            if picture:
                await db.update_user_profile(
                    user_id=str(user["id"]),
                    profile_photo_url=picture
                )

        jwt_access = create_access_token(
            user["id"], email, role=user.get("role", "client")
        )
        jwt_refresh = create_refresh_token(user["id"])

        await db.log_audit(
            user_id=str(user["id"]),
            action="oauth_login",
            details={"provider": "google"}
        )

        redirect_url = f"/?token={jwt_access}&refresh={jwt_refresh}"
        return RedirectResponse(url=redirect_url)

    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.error("Google OAuth error: %s", e)
        return RedirectResponse(url="/?error=oauth_failed")


@router.get("/oauth/providers")
async def get_oauth_providers():
    """Return which OAuth providers are configured"""
    return {
        "google": bool(GOOGLE_CLIENT_ID)
    }
