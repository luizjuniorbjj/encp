"""
ENCPServices - Leads Routes (Core Business)
CRUD for lead management + pipeline tracking
No agency_id — single company
"""

from typing import Optional
from datetime import datetime

import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.auth import get_current_user, get_admin_user
from app.database import get_db, Database

logger = logging.getLogger("encp.leads")

router = APIRouter(prefix="/leads", tags=["Leads"])


# ============================================
# MODELS
# ============================================

class LeadCreate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: str = "FL"
    zip_code: Optional[str] = None
    property_type: str = "residential"
    service_type: Optional[str] = None
    rooms_areas: Optional[str] = None
    timeline: str = "flexible"
    budget_range: Optional[str] = None
    source: str = "manual"


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    property_type: Optional[str] = None
    service_type: Optional[str] = None
    rooms_areas: Optional[str] = None
    timeline: Optional[str] = None
    budget_range: Optional[str] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str
    loss_reason: Optional[str] = None


# ============================================
# PIPELINE SUMMARY (must be BEFORE /{id})
# ============================================

@router.get("/pipeline")
async def get_pipeline(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get lead counts by status for pipeline view"""
    pipeline = await db.get_lead_pipeline()
    return {"pipeline": pipeline}


# ============================================
# LEAD STATS (must be BEFORE /{id})
# ============================================

@router.get("/stats")
async def get_lead_stats(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get lead statistics — admin only"""
    stats = await db.get_lead_stats()
    return stats


# ============================================
# LIST LEADS
# ============================================

@router.get("/")
async def list_leads(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source (whatsapp, web, manual, referral)"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """List leads with optional filters — admin only"""
    leads = await db.get_leads(
        status=status,
        source=source,
        limit=limit,
        offset=offset
    )

    return {
        "leads": [_serialize_lead(lead) for lead in leads],
        "count": len(leads),
        "limit": limit,
        "offset": offset
    }


# ============================================
# GET LEAD DETAIL
# ============================================

@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get lead detail — admin only"""
    lead = await db.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return _serialize_lead(lead)


# ============================================
# CREATE LEAD (admin only)
# ============================================

@router.post("/")
async def create_lead(
    request: LeadCreate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Create a lead manually — admin only"""
    lead = await db.create_lead(
        name=request.name,
        phone=request.phone,
        email=request.email,
        address=request.address,
        city=request.city,
        state=request.state,
        zip_code=request.zip_code,
        property_type=request.property_type,
        service_type=request.service_type,
        rooms_areas=request.rooms_areas,
        timeline=request.timeline,
        budget_range=request.budget_range,
        source=request.source
    )

    await db.log_audit(
        user_id=current_user["user_id"],
        action="lead_created",
        details={"lead_id": str(lead["id"]), "source": request.source}
    )

    return _serialize_lead(lead)


# ============================================
# UPDATE LEAD (admin only)
# ============================================

@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str,
    request: LeadUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Update lead details — admin only"""
    existing = await db.get_lead_by_id(lead_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await db.update_lead(lead_id, **update_data)

    await db.log_audit(
        user_id=current_user["user_id"],
        action="lead_updated",
        details={"lead_id": lead_id, "fields": list(update_data.keys())}
    )

    return _serialize_lead(result)


# ============================================
# MOVE LEAD IN PIPELINE (admin only)
# ============================================

VALID_STATUSES = (
    "new", "contacted", "estimate_scheduled", "estimate_given",
    "accepted", "in_progress", "completed", "closed_lost"
)

@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    request: StatusUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Move lead to a new pipeline stage — admin only"""
    existing = await db.get_lead_by_id(lead_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Lead not found")

    if request.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"
        )

    old_status = existing.get("status", "unknown")

    update_kwargs = {"status": request.status}
    if request.loss_reason and request.status == "closed_lost":
        update_kwargs["loss_reason"] = request.loss_reason

    result = await db.update_lead(lead_id, **update_kwargs)

    await db.log_audit(
        user_id=current_user["user_id"],
        action="lead_status_changed",
        details={
            "lead_id": lead_id,
            "old_status": old_status,
            "new_status": request.status,
            "loss_reason": request.loss_reason
        }
    )

    return {
        "message": f"Lead moved from {old_status} to {request.status}",
        "lead": _serialize_lead(result)
    }


# ============================================
# HELPERS
# ============================================

def _serialize_lead(lead: dict) -> dict:
    """Serialize lead for API response"""
    result = {}
    for k, v in lead.items():
        if k.endswith("_encrypted"):
            continue  # Skip encrypted fields
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        elif k in ("id", "user_id", "conversation_id") and v is not None:
            result[k] = str(v)
        else:
            result[k] = v
    return result
