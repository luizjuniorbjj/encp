"""
ENCPServices - Estimates Routes
CRUD for tile/remodel project estimates
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.auth import get_admin_user
from app.database import get_db, Database

router = APIRouter(prefix="/estimates", tags=["Estimates"])


# ============================================
# MODELS
# ============================================

class EstimateCreate(BaseModel):
    lead_id: str
    user_id: Optional[str] = None
    scope_description: Optional[str] = None
    rooms_areas: Optional[list] = None
    material_type: Optional[str] = None
    prep_work_needed: Optional[str] = None
    estimated_hours: Optional[int] = None
    estimated_cost_low: Optional[float] = None
    estimated_cost_high: Optional[float] = None
    notes: Optional[str] = None


class EstimateUpdate(BaseModel):
    scope_description: Optional[str] = None
    rooms_areas: Optional[list] = None
    material_type: Optional[str] = None
    prep_work_needed: Optional[str] = None
    estimated_hours: Optional[int] = None
    estimated_cost_low: Optional[float] = None
    estimated_cost_high: Optional[float] = None
    notes: Optional[str] = None


class EstimateStatusUpdate(BaseModel):
    status: str  # draft, sent, accepted, rejected, expired


# ============================================
# LIST ESTIMATES
# ============================================

@router.get("/")
async def list_estimates(
    lead_id: Optional[str] = Query(None, description="Filter by lead"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, le=100),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """List estimates with optional filters — admin only"""
    estimates = await db.get_estimates(
        lead_id=lead_id,
        status=status,
        limit=limit
    )

    return {
        "estimates": [_serialize_estimate(e) for e in estimates],
        "count": len(estimates)
    }


# ============================================
# GET ESTIMATE DETAIL
# ============================================

@router.get("/{estimate_id}")
async def get_estimate(
    estimate_id: str,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get estimate detail — admin only"""
    estimate = await db.get_estimate_by_id(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    return _serialize_estimate(estimate)


# ============================================
# CREATE ESTIMATE (admin only)
# ============================================

@router.post("/")
async def create_estimate(
    request: EstimateCreate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Create an estimate for a lead — admin only"""
    # Verify lead exists
    lead = await db.get_lead_by_id(request.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    estimate = await db.create_estimate(
        lead_id=request.lead_id,
        user_id=request.user_id,
        scope_description=request.scope_description,
        rooms_areas=request.rooms_areas,
        material_type=request.material_type,
        prep_work_needed=request.prep_work_needed,
        estimated_hours=request.estimated_hours,
        estimated_cost_low=request.estimated_cost_low,
        estimated_cost_high=request.estimated_cost_high,
        notes=request.notes
    )

    # Update lead status to estimate_given
    await db.update_lead(request.lead_id, status="estimate_given")

    await db.log_audit(
        user_id=current_user["user_id"],
        action="estimate_created",
        details={
            "estimate_id": str(estimate["id"]),
            "lead_id": request.lead_id
        }
    )

    return _serialize_estimate(estimate)


# ============================================
# UPDATE ESTIMATE (admin only)
# ============================================

@router.patch("/{estimate_id}")
async def update_estimate(
    estimate_id: str,
    request: EstimateUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Update an estimate — admin only"""
    existing = await db.get_estimate_by_id(estimate_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Estimate not found")

    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await db.update_estimate(estimate_id, **update_data)

    await db.log_audit(
        user_id=current_user["user_id"],
        action="estimate_updated",
        details={"estimate_id": estimate_id, "fields": list(update_data.keys())}
    )

    return _serialize_estimate(result)


# ============================================
# UPDATE ESTIMATE STATUS (admin only)
# ============================================

VALID_ESTIMATE_STATUSES = ("draft", "sent", "accepted", "rejected", "expired")

@router.patch("/{estimate_id}/status")
async def update_estimate_status(
    estimate_id: str,
    request: EstimateStatusUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Accept, reject, or expire an estimate — admin only"""
    existing = await db.get_estimate_by_id(estimate_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Estimate not found")

    if request.status not in VALID_ESTIMATE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_ESTIMATE_STATUSES)}"
        )

    old_status = existing.get("status", "unknown")

    update_data = {"status": request.status}

    # Set timestamp based on status
    now = datetime.utcnow()
    if request.status == "sent":
        update_data["sent_at"] = now
    elif request.status == "accepted":
        update_data["accepted_at"] = now
        # Also update the lead status
        lead_id = existing.get("lead_id")
        if lead_id:
            await db.update_lead(str(lead_id), status="accepted")
    elif request.status == "rejected":
        update_data["rejected_at"] = now

    result = await db.update_estimate(estimate_id, **update_data)

    await db.log_audit(
        user_id=current_user["user_id"],
        action="estimate_status_changed",
        details={
            "estimate_id": estimate_id,
            "old_status": old_status,
            "new_status": request.status
        }
    )

    return {
        "message": f"Estimate moved from {old_status} to {request.status}",
        "estimate": _serialize_estimate(result)
    }


# ============================================
# HELPERS
# ============================================

def _serialize_estimate(e: dict) -> dict:
    """Serialize estimate for API response"""
    result = {}
    for k, v in e.items():
        if k.endswith("_encrypted"):
            continue
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        elif k in ("id", "lead_id", "user_id") and v is not None:
            result[k] = str(v)
        else:
            result[k] = v
    return result
