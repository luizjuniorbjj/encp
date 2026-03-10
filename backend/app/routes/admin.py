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
# DASHBOARD CHART DATA
# ============================================

@router.get("/dashboard/charts")
async def get_dashboard_charts(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """
    Historical data for dashboard charts:
    - leads_by_week: last 8 weeks
    - conversations_by_day: last 14 days
    - leads_by_status: current distribution
    - projects_by_stage: current distribution
    """
    from datetime import datetime, timezone, timedelta

    async with db._conn() as conn:
        # Leads per week (last 8 weeks)
        leads_weekly = await conn.fetch("""
            SELECT date_trunc('week', created_at)::date AS week,
                   COUNT(*) AS count
            FROM leads
            WHERE created_at >= NOW() - INTERVAL '8 weeks'
            GROUP BY week ORDER BY week
        """)

        # Conversations per day (last 14 days)
        convos_daily = await conn.fetch("""
            SELECT created_at::date AS day, COUNT(*) AS count
            FROM conversations
            WHERE created_at >= NOW() - INTERVAL '14 days'
            GROUP BY day ORDER BY day
        """)

        # Leads by status
        leads_status = await conn.fetch("""
            SELECT status, COUNT(*) AS count
            FROM leads GROUP BY status ORDER BY count DESC
        """)

        # Projects by stage
        projects_stage = await conn.fetch("""
            SELECT stage, COUNT(*) AS count
            FROM projects GROUP BY stage ORDER BY count DESC
        """)

    return {
        "leads_by_week": [
            {"week": str(r["week"]), "count": r["count"]}
            for r in leads_weekly
        ],
        "conversations_by_day": [
            {"day": str(r["day"]), "count": r["count"]}
            for r in convos_daily
        ],
        "leads_by_status": [
            {"status": r["status"], "count": r["count"]}
            for r in leads_status
        ],
        "projects_by_stage": [
            {"stage": r["stage"], "count": r["count"]}
            for r in projects_stage
        ],
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
