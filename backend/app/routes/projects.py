"""
ENCPServices - Projects Routes
CRUD for tile/remodel project management + stage tracking
"""

from typing import Optional
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.auth import get_admin_user
from app.database import get_db, Database

router = APIRouter(prefix="/projects", tags=["Projects"])


# ============================================
# MODELS
# ============================================

class ProjectCreate(BaseModel):
    lead_id: Optional[str] = None
    estimate_id: Optional[str] = None
    user_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: str = "FL"
    description: Optional[str] = None
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    crew_assigned: Optional[str] = None
    total_cost: Optional[float] = None


class ProjectUpdate(BaseModel):
    description: Optional[str] = None
    start_date: Optional[date] = None
    estimated_end_date: Optional[date] = None
    crew_assigned: Optional[str] = None
    total_cost: Optional[float] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    notes: Optional[str] = None


class StageUpdate(BaseModel):
    stage: str  # scheduled, prep, in_progress, installation, grouting, inspection, completed


# ============================================
# ACTIVE PROJECTS (must be BEFORE /{id})
# ============================================

@router.get("/active")
async def get_active_projects(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get all active (non-completed) projects for dashboard"""
    projects = await db.get_active_projects()
    return {
        "projects": [_serialize_project(p) for p in projects],
        "count": len(projects)
    }


# ============================================
# LIST PROJECTS
# ============================================

@router.get("/")
async def list_projects(
    stage: Optional[str] = Query(None, description="Filter by stage"),
    limit: int = Query(50, le=100),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """List projects with optional stage filter"""
    projects = await db.get_projects(stage=stage, limit=limit)

    return {
        "projects": [_serialize_project(p) for p in projects],
        "count": len(projects)
    }


# ============================================
# GET PROJECT DETAIL
# ============================================

@router.get("/{project_id}")
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get project detail"""
    project = await db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return _serialize_project(project)


# ============================================
# CREATE PROJECT (admin only)
# ============================================

@router.post("/")
async def create_project(
    request: ProjectCreate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Create a project from an accepted estimate — admin only"""
    # If estimate_id provided, verify it exists and is accepted
    if request.estimate_id:
        estimate = await db.get_estimate_by_id(request.estimate_id)
        if not estimate:
            raise HTTPException(status_code=404, detail="Estimate not found")

    # If lead_id provided, verify it exists
    if request.lead_id:
        lead = await db.get_lead_by_id(request.lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        # Update lead status to in_progress
        await db.update_lead(request.lead_id, status="in_progress")

    project = await db.create_project(
        lead_id=request.lead_id,
        estimate_id=request.estimate_id,
        user_id=request.user_id,
        address=request.address,
        city=request.city,
        state=request.state,
        description=request.description,
        start_date=request.start_date,
        estimated_end_date=request.estimated_end_date,
        crew_assigned=request.crew_assigned,
        total_cost=request.total_cost
    )

    await db.log_audit(
        user_id=current_user["user_id"],
        action="project_created",
        details={
            "project_id": str(project["id"]),
            "lead_id": request.lead_id,
            "estimate_id": request.estimate_id
        }
    )

    return _serialize_project(project)


# ============================================
# UPDATE PROJECT (admin only)
# ============================================

@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    request: ProjectUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Update project details — admin only"""
    existing = await db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = request.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await db.update_project(project_id, **update_data)

    await db.log_audit(
        user_id=current_user["user_id"],
        action="project_updated",
        details={"project_id": project_id, "fields": list(update_data.keys())}
    )

    return _serialize_project(result)


# ============================================
# MOVE PROJECT BETWEEN STAGES (admin only)
# ============================================

VALID_STAGES = ("scheduled", "prep", "in_progress", "installation", "grouting", "inspection", "completed")

@router.patch("/{project_id}/stage")
async def update_project_stage(
    project_id: str,
    request: StageUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Move project between stages — admin only
    Stages: scheduled -> prep -> in_progress -> installation -> grouting -> inspection -> completed
    """
    existing = await db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    if request.stage not in VALID_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage. Must be one of: {', '.join(VALID_STAGES)}"
        )

    old_stage = existing.get("stage", "unknown")

    update_data = {"stage": request.stage}

    # Set completed_at when moving to completed stage
    if request.stage == "completed":
        update_data["completed_at"] = datetime.utcnow()
        # Also update the associated lead if any
        lead_id = existing.get("lead_id")
        if lead_id:
            await db.update_lead(str(lead_id), status="completed")

    result = await db.update_project(project_id, **update_data)

    await db.log_audit(
        user_id=current_user["user_id"],
        action="project_stage_changed",
        details={
            "project_id": project_id,
            "old_stage": old_stage,
            "new_stage": request.stage
        }
    )

    return {
        "message": f"Project moved from {old_stage} to {request.stage}",
        "project": _serialize_project(result)
    }


# ============================================
# HELPERS
# ============================================

def _serialize_project(p: dict) -> dict:
    """Serialize project for API response"""
    result = {}
    for k, v in p.items():
        if k.endswith("_encrypted"):
            continue
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        elif k in ("id", "lead_id", "estimate_id", "user_id") and v is not None:
            result[k] = str(v)
        else:
            result[k] = v
    return result
