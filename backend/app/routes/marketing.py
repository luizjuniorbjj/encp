"""
ENCPServices - Marketing Routes
SEO monitoring, review responses, content generation
All endpoints require admin role
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from app.auth import get_admin_user
from app.database import get_db, Database
from app.marketing.service import MarketingService

router = APIRouter(prefix="/marketing", tags=["Marketing"])


# ============================================
# REQUEST MODELS
# ============================================

class SearchTermCreate(BaseModel):
    term: str = Field(..., min_length=2, max_length=300)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(default="FL", max_length=2)


class ReviewRequest(BaseModel):
    platform: str = Field(..., min_length=1, max_length=50)
    review_text: str = Field(..., min_length=5)
    rating: int = Field(..., ge=1, le=5)
    reviewer_name: str = Field(default="Customer", max_length=200)


class ContentRequest(BaseModel):
    content_type: str = Field(default="social_post", max_length=50)
    city: str = Field(..., min_length=2, max_length=100)
    service: str = Field(..., min_length=2, max_length=100)
    platform: str = Field(default="instagram", max_length=50)


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(draft|approved|posted)$")


# ============================================
# SEO ENDPOINTS
# ============================================

@router.get("/seo/terms")
async def list_search_terms(
    active_only: bool = Query(True),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """List all tracked SEO search terms."""
    svc = MarketingService(db)
    terms = await svc.get_search_terms(active_only=active_only)
    return {"terms": terms, "count": len(terms)}


@router.post("/seo/terms")
async def add_search_term(
    body: SearchTermCreate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Add a new search term to track."""
    svc = MarketingService(db)
    term = await svc.add_search_term(body.term, body.city, body.state)
    return {"term": term}


@router.delete("/seo/terms/{term_id}")
async def remove_search_term(
    term_id: str,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Remove a search term from tracking."""
    svc = MarketingService(db)
    deleted = await svc.delete_search_term(term_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Term not found")
    return {"deleted": True}


@router.post("/seo/check")
async def run_seo_check(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Run SEO ranking check for all active terms."""
    svc = MarketingService(db)
    results = await svc.check_all_rankings()
    return results


@router.post("/seo/sync-gsc")
async def sync_gsc(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Sync SEO data from Google Search Console API."""
    svc = MarketingService(db)
    try:
        results = await svc.sync_from_gsc()
        return results
    except Exception as e:
        return {"error": f"GSC sync failed: {str(e)}", "checked": 0}


@router.get("/seo/dashboard")
async def seo_dashboard(
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Get SEO dashboard with rankings overview."""
    svc = MarketingService(db)
    dashboard = await svc.get_seo_dashboard()
    return dashboard


# ============================================
# REVIEW ENDPOINTS
# ============================================

@router.post("/reviews/generate")
async def generate_review_response(
    body: ReviewRequest,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Generate AI response to a customer review."""
    svc = MarketingService(db)
    result = await svc.generate_review_response(
        platform=body.platform,
        review_text=body.review_text,
        rating=body.rating,
        reviewer_name=body.reviewer_name,
        created_by=current_user.get("user_id")
    )
    return {"review_response": result}


@router.get("/reviews")
async def list_review_responses(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """List generated review responses."""
    svc = MarketingService(db)
    responses = await svc.get_review_responses(status=status, limit=limit)
    return {"responses": responses, "count": len(responses)}


@router.patch("/reviews/{review_id}")
async def update_review_status(
    review_id: str,
    body: StatusUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Update review response status (draft -> approved -> posted)."""
    svc = MarketingService(db)
    result = await svc.update_review_status(review_id, body.status)
    if not result:
        raise HTTPException(status_code=404, detail="Review response not found")
    return {"review_response": result}


# ============================================
# CONTENT ENDPOINTS
# ============================================

@router.post("/content/generate")
async def generate_content(
    body: ContentRequest,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Generate social media content with AI."""
    svc = MarketingService(db)
    result = await svc.generate_content(
        content_type=body.content_type,
        city=body.city,
        service=body.service,
        platform=body.platform,
        created_by=current_user.get("user_id")
    )
    return {"content": result}


@router.get("/content")
async def list_content(
    status: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """List generated marketing content."""
    svc = MarketingService(db)
    items = await svc.get_content(status=status, content_type=content_type, limit=limit)
    return {"content": items, "count": len(items)}


@router.patch("/content/{content_id}")
async def update_content_status(
    content_id: str,
    body: StatusUpdate,
    current_user: dict = Depends(get_admin_user),
    db: Database = Depends(get_db)
):
    """Update content status (draft -> approved -> posted)."""
    svc = MarketingService(db)
    result = await svc.update_content_status(content_id, body.status)
    if not result:
        raise HTTPException(status_code=404, detail="Content not found")
    return {"content": result}
