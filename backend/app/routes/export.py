"""
ENCPServices - Data Export Routes
Privacy-compliant data export for users.
Allows users to export their own data as JSON.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.database import get_db, Database, UUIDEncoder
import json

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/my-data")
async def export_user_data(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """
    Export all user data as JSON (privacy compliance).
    Returns profile, memories, and conversations.
    Sensitive fields are decrypted for portability.
    """
    user_id = current_user["user_id"]

    data = await db.export_user_data(user_id)

    # Audit log
    await db.log_audit(
        user_id=user_id,
        action="data_export",
        details={"tables": list(data.keys()), "record_counts": {
            k: len(v) if isinstance(v, list) else 1
            for k, v in data.items()
            if k not in ("exported_at",)
        }}
    )

    # Use UUIDEncoder to handle UUID and datetime serialization
    content = json.loads(json.dumps(data, cls=UUIDEncoder))

    return JSONResponse(content=content)
