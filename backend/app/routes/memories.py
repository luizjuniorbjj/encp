"""
ENCPServices - Memories Routes
Client memory management (list, delete) — no agency_id
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from app.auth import get_current_user
from app.database import get_db, Database

router = APIRouter(prefix="/memories", tags=["Memories"])


@router.get("/")
async def list_memories(
    categoria: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, le=100),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """List user's active memories"""
    memories = await db.get_user_memories(
        current_user["user_id"],
        categoria=categoria
    )

    # Apply limit
    memories = memories[:limit]

    return [
        {
            "id": str(m["id"]),
            "categoria": m["categoria"],
            "fato": m["fato"],
            "detalhes": m.get("detalhes"),
            "importancia": m["importancia"],
            "mencoes": m["mencoes"],
            "confianca": float(m["confianca"]) if m.get("confianca") else 0.8,
            "pinned": m.get("pinned", False),
            "created_at": m["created_at"].isoformat() if m.get("created_at") else None,
            "ultima_mencao": m["ultima_mencao"].isoformat() if m.get("ultima_mencao") else None
        }
        for m in memories
    ]


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Delete a specific memory"""
    # Verify the memory belongs to the user
    memories = await db.get_user_memories(current_user["user_id"])
    memory_ids = [str(m["id"]) for m in memories]

    if memory_id not in memory_ids:
        raise HTTPException(status_code=404, detail="Memory not found")

    await db.execute(
        "DELETE FROM user_memories WHERE id = $1 AND user_id = $2",
        memory_id, current_user["user_id"]
    )

    await db.log_audit(
        user_id=current_user["user_id"],
        action="memory_deleted",
        details={"memory_id": memory_id}
    )

    return {"message": "Memory deleted"}


@router.delete("/")
async def delete_all_memories(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Delete ALL memories for current user (privacy compliance)"""
    await db.delete_user_memories(current_user["user_id"])

    await db.log_audit(
        user_id=current_user["user_id"],
        action="all_memories_deleted",
        details={}
    )

    return {"message": "All memories deleted"}
