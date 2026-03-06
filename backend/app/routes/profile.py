"""
ENCPServices - Profile Routes
User profile management (GET/PATCH/DELETE) — no agency_id
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import get_db, Database

router = APIRouter(prefix="/profile", tags=["Profile"])


# ============================================
# MODELS
# ============================================

class ProfileUpdate(BaseModel):
    nome: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    language: Optional[str] = None
    # Sensitive fields (auto-encrypted by database layer)
    address: Optional[str] = None


# ============================================
# ROUTES
# ============================================

@router.get("/")
async def get_profile(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get current user's profile (sensitive fields decrypted)"""
    profile = await db.get_user_profile(current_user["user_id"])
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Remove internal fields
    safe_profile = {k: v for k, v in profile.items() if not k.endswith("_encrypted")}
    safe_profile["id"] = str(safe_profile.get("id", ""))
    safe_profile["user_id"] = str(safe_profile.get("user_id", ""))

    return safe_profile


@router.patch("/")
async def update_profile(
    request: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Update current user's profile (sensitive fields auto-encrypted)"""
    update_data = request.model_dump(exclude_none=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate language
    if "language" in update_data and update_data["language"] not in ("en", "pt", "es"):
        raise HTTPException(status_code=400, detail="Language must be en, pt, or es")

    result = await db.update_user_profile(current_user["user_id"], **update_data)

    if not result:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.log_audit(
        user_id=current_user["user_id"],
        action="profile_updated",
        details={"fields": list(update_data.keys())}
    )

    return {"message": "Profile updated successfully"}


@router.delete("/data")
async def delete_user_data(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Delete all user data (GDPR/privacy compliance).
    Removes: profile, memories, conversations, messages.
    User account is deactivated but not deleted for audit trail.
    """
    user_id = current_user["user_id"]

    # Delete memories
    await db.delete_user_memories(user_id)

    # Delete messages and conversations
    await db.execute(
        """
        DELETE FROM messages WHERE conversation_id IN (
            SELECT id FROM conversations WHERE user_id = $1
        )
        """,
        user_id
    )
    await db.execute("DELETE FROM conversations WHERE user_id = $1", user_id)

    # Delete profile
    await db.execute("DELETE FROM user_profiles WHERE user_id = $1", user_id)

    # Deactivate user account (keep for audit trail)
    await db.execute(
        "UPDATE users SET is_active = false WHERE id = $1",
        user_id
    )

    await db.log_audit(
        user_id=user_id,
        action="user_data_deleted",
        details={"reason": "user_request", "scope": "full_deletion"}
    )

    return {"message": "All your data has been deleted. Your account has been deactivated."}
