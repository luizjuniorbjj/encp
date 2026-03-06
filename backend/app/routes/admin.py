"""
ENCPServices - Admin Routes
Dashboard metrics, conversation management, customer search
All endpoints require admin role
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.auth import get_current_user, get_admin_user
from app.database import get_db, Database

router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================
# DASHBOARD METRICS
# ============================================

@router.get("/dashboard")
async def get_dashboard(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """
    Get dashboard metrics:
    - Leads this week
    - Active projects
    - Conversations (30 days)
    - Total leads
    - Converted leads
    - Conversion rate
    """
    stats = await db.get_dashboard_stats()

    return {
        "metrics": stats,
        "generated_at": _now_iso()
    }


# ============================================
# ALL CLIENT CONVERSATIONS
# ============================================

@router.get("/conversations")
async def get_all_conversations(
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get all client conversations — admin only"""
    conversations = await db.get_all_conversations(limit=limit, offset=offset)

    return {
        "conversations": [
            {
                "id": str(c["id"]),
                "user_id": str(c.get("user_id", "")),
                "email": c.get("email"),
                "phone": c.get("phone"),
                "nome": c.get("nome"),
                "channel": c.get("channel"),
                "message_count": c.get("message_count", 0),
                "resumo": c.get("resumo"),
                "is_archived": c.get("is_archived", False),
                "started_at": c["started_at"].isoformat() if c.get("started_at") else None,
                "last_message_at": c["last_message_at"].isoformat() if c.get("last_message_at") else None,
            }
            for c in conversations
        ],
        "count": len(conversations),
        "limit": limit,
        "offset": offset
    }


# ============================================
# CONVERSATION MESSAGES (admin view)
# ============================================

@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages_admin(
    conversation_id: str,
    limit: int = Query(100, le=500),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get messages for a specific conversation — admin only.
    Messages are decrypted using the conversation owner's user_id.
    """
    # Get conversation to find the user_id for decryption
    row = await db.fetchrow(
        "SELECT user_id FROM conversations WHERE id = $1",
        conversation_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = str(row["user_id"])

    messages = await db.get_messages(
        conversation_id,
        user_id,
        limit=limit
    )

    return {
        "conversation_id": conversation_id,
        "messages": [
            {
                "id": str(m["id"]),
                "role": m["role"],
                "content": m["content"],
                "created_at": m["created_at"].isoformat() if m.get("created_at") else None
            }
            for m in messages
        ]
    }


# ============================================
# SEARCH CUSTOMERS
# ============================================

@router.get("/search")
async def search_customers(
    q: str = Query(..., min_length=2, description="Search query (name, phone, or email)"),
    limit: int = Query(20, le=50),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Search customers by name, phone, or email — admin only"""
    results = await db.search_customers(q, limit=limit)

    return {
        "results": [
            {
                "id": str(r["id"]),
                "email": r.get("email"),
                "phone": r.get("phone"),
                "nome": r.get("nome"),
                "city": r.get("city"),
                "state": r.get("state"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None
            }
            for r in results
        ],
        "count": len(results),
        "query": q
    }


# ============================================
# AUDIT LOG (recent activity)
# ============================================

@router.get("/activity")
async def get_recent_activity(
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get recent audit log entries — admin only"""
    rows = await db.fetch(
        """
        SELECT al.*, u.email
        FROM audit_log al
        LEFT JOIN users u ON al.user_id = u.id
        ORDER BY al.created_at DESC
        LIMIT $1
        """,
        limit
    )

    return {
        "activity": [
            {
                "id": str(r["id"]),
                "user_id": str(r["user_id"]) if r.get("user_id") else None,
                "email": r.get("email"),
                "action": r["action"],
                "details": r.get("details"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None
            }
            for r in rows
        ],
        "count": len(rows)
    }


# ============================================
# HELPERS
# ============================================

def _now_iso() -> str:
    """Current UTC timestamp as ISO string"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
