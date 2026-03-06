"""
Blog API Routes
- Public: list published posts, read post
- Admin: generate, edit, delete, manage posts
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from app.auth import get_admin_user
from app.blog import service as blog_service

router = APIRouter(prefix="/blog", tags=["blog"])


# ============================================
# Pydantic Models
# ============================================

class GenerateRequest(BaseModel):
    topic: Optional[str] = None
    city: Optional[str] = None
    service: Optional[str] = None
    keywords: Optional[str] = None
    content_type: str = "article"
    auto_publish: bool = False

class BatchRequest(BaseModel):
    count: int = 5
    auto_publish: bool = False

class UpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    meta_description: Optional[str] = None
    excerpt: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list] = None
    status: Optional[str] = None
    slug: Optional[str] = None


# ============================================
# Public Routes (no auth required)
# ============================================

@router.get("/posts")
async def list_published_posts(limit: int = 20, offset: int = 0):
    """List published blog posts (public)"""
    posts = await blog_service.list_posts(status="published", limit=limit, offset=offset)
    return {"posts": posts, "count": len(posts)}


@router.get("/posts/{slug}")
async def read_post(slug: str):
    """Read a single blog post by slug (public, increments views)"""
    post = await blog_service.get_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


# ============================================
# Admin Routes (auth required)
# ============================================

@router.get("/admin/posts")
async def admin_list_posts(status: str = None, limit: int = 50, offset: int = 0, user=Depends(get_admin_user)):
    """List all posts (admin) with optional status filter"""
    posts = await blog_service.list_posts(status=status, limit=limit, offset=offset)
    stats = await blog_service.get_stats()
    return {"posts": posts, "stats": stats}


@router.post("/admin/generate")
async def admin_generate_post(req: GenerateRequest, user=Depends(get_admin_user)):
    """Generate a single blog post using AI"""
    result = await blog_service.generate_blog_post(
        topic=req.topic,
        city=req.city,
        service=req.service,
        keywords=req.keywords,
        content_type=req.content_type,
        auto_publish=req.auto_publish,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/admin/generate-batch")
async def admin_generate_batch(req: BatchRequest, user=Depends(get_admin_user)):
    """Generate multiple blog posts at once"""
    results = await blog_service.generate_batch(count=req.count, auto_publish=req.auto_publish)
    return {
        "generated": len([r for r in results if "error" not in r]),
        "errors": len([r for r in results if "error" in r]),
        "results": results,
    }


@router.patch("/admin/posts/{post_id}")
async def admin_update_post(post_id: str, req: UpdateRequest, user=Depends(get_admin_user)):
    """Update a blog post"""
    updates = {k: v for k, v in req.dict().items() if v is not None}
    result = await blog_service.update_post(post_id, updates)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/admin/posts/{post_id}")
async def admin_delete_post(post_id: str, user=Depends(get_admin_user)):
    """Delete a blog post"""
    deleted = await blog_service.delete_post(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"deleted": True}


@router.get("/admin/topics")
async def admin_topic_suggestions(user=Depends(get_admin_user)):
    """Get available topic suggestions (not yet generated)"""
    topics = await blog_service.get_topic_suggestions()
    return {"available": len(topics), "topics": topics}


@router.get("/admin/stats")
async def admin_blog_stats(user=Depends(get_admin_user)):
    """Blog statistics"""
    return await blog_service.get_stats()
