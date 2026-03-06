"""
ENCP Services Group - Main Application
FastAPI backend for AI tile/remodel contractor assistant
Single company — NO multi-tenant
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.config import (
    APP_NAME, APP_VERSION, DEBUG, MAINTENANCE_MODE,
    CORS_ORIGINS, CORS_ALLOW_CREDENTIALS, CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS,
    PRODUCTION_ORIGINS, ADMIN_PANEL_PATH
)

# ============================================
# SENTRY (error monitoring)
# ============================================
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        environment="production" if not DEBUG else "development",
        release=f"{APP_NAME}@{APP_VERSION}",
    )
from app.database import init_db, close_db, _pool
from app.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.profile import router as profile_router
from app.routes.memories import router as memories_router
from app.routes.leads import router as leads_router
from app.routes.estimates import router as estimates_router
from app.routes.projects import router as projects_router
from app.routes.admin import router as admin_router
from app.routes.webhook import router as webhook_router
from app.routes.voice import router as voice_router
from app.routes.export import router as export_router
from app.routes.marketing import router as marketing_router
from app.routes.blog import router as blog_router

logger = logging.getLogger("encp")


# ============================================
# LOGGING SETUP
# ============================================

def setup_logging():
    """Configure structured logging for the application"""
    log_level = logging.DEBUG if DEBUG else logging.INFO
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(level=log_level, format=log_format, force=True)
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)


setup_logging()


# ============================================
# LIFECYCLE
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown"""
    # Startup
    logger.info("%s v%s starting", APP_NAME, APP_VERSION)
    logger.info("Encryption key configured via environment")

    try:
        await init_db()
        logger.info("Database connected")
    except Exception as e:
        logger.warning("Database not available: %s", e)
        logger.warning("Running without database - some features disabled")

    if MAINTENANCE_MODE:
        logger.warning("MAINTENANCE MODE ACTIVE")

    # Start blog scheduler
    import asyncio
    from app.blog.scheduler import blog_scheduler_loop
    asyncio.create_task(blog_scheduler_loop())
    logger.info("Blog scheduler started")

    logger.info("API ready")

    yield

    # Shutdown
    try:
        await close_db()
    except Exception:
        pass
    logger.info("%s stopped", APP_NAME)


# ============================================
# APP
# ============================================

app = FastAPI(
    title=APP_NAME,
    description="AI assistant for ENCP Services Group",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None
)


# ============================================
# CORS
# ============================================

def get_cors_origins():
    """Return CORS origins based on environment"""
    if DEBUG:
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8080",
            "*"
        ]
    elif CORS_ORIGINS != ["*"]:
        return [o for o in CORS_ORIGINS if not o.startswith("https://*.")]
    else:
        return PRODUCTION_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
    expose_headers=["X-Request-ID"],
)


# ============================================
# HTTPS REDIRECT (production)
# ============================================

@app.middleware("http")
async def redirect_to_https(request: Request, call_next):
    """Redirect HTTP to HTTPS in production"""
    if not DEBUG:
        proto = request.headers.get("x-forwarded-proto", "https")
        if proto == "http":
            url = str(request.url).replace("http://", "https://", 1)
            return RedirectResponse(url=url, status_code=301)
    return await call_next(request)


# ============================================
# ROUTES
# ============================================

@app.get("/api", tags=["Status"])
async def api_status():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "message": "AI assistant for ENCP Services Group"
    }


@app.get("/health", tags=["Status"])
async def health():
    """Detailed health check with DB status"""
    db_ok = False
    try:
        if _pool:
            async with _pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
    except Exception:
        pass

    status = "healthy" if db_ok else "degraded"
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": status,
            "version": APP_VERSION,
            "database": "connected" if db_ok else "unavailable",
        }
    )


# Register routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(profile_router)
app.include_router(memories_router)
app.include_router(leads_router)
app.include_router(estimates_router)
app.include_router(projects_router)
app.include_router(admin_router)
app.include_router(webhook_router)
app.include_router(voice_router)
app.include_router(export_router)
app.include_router(marketing_router)
app.include_router(blog_router)


# ============================================
# FRONTEND (Static files)
# ============================================

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/", tags=["Frontend"])
async def serve_landing():
    """Serve ENCP Services landing page (public site)"""
    if MAINTENANCE_MODE:
        return {"status": "maintenance", "message": "System under maintenance"}
    landing = FRONTEND_DIR / "index.html"
    if landing.exists():
        return FileResponse(landing)
    return {"message": f"{APP_NAME} API is running. Frontend not yet deployed."}


@app.get("/styles.css", tags=["Frontend"])
async def serve_styles():
    """Serve landing page stylesheet"""
    css = FRONTEND_DIR / "styles.css"
    if css.exists():
        return FileResponse(css, media_type="text/css")
    raise HTTPException(status_code=404)


@app.get("/chat", tags=["Frontend"])
@app.get("/chat/", tags=["Frontend"])
async def serve_chat():
    """Serve ENCP chat app"""
    chat = FRONTEND_DIR / "chat.html"
    if chat.exists():
        return FileResponse(chat)
    return {"message": "Chat not available"}


@app.get("/blog", tags=["Frontend"])
@app.get("/blog/", tags=["Frontend"])
async def serve_blog_listing():
    """Serve blog listing page"""
    blog_page = FRONTEND_DIR / "blog.html"
    if blog_page.exists():
        return FileResponse(blog_page)
    return {"message": "Blog page not available"}


@app.get("/blog/{slug}", tags=["Frontend"])
@app.get("/blog/{slug}/", tags=["Frontend"])
async def serve_blog_post(slug: str):
    """Serve individual blog post as HTML with JSON-LD structured data"""
    from app.blog.service import get_post
    from fastapi.responses import HTMLResponse

    post = await get_post(slug)
    if not post or post['status'] != 'published':
        return HTMLResponse(status_code=404, content="<h1>Post not found</h1>")

    html = _render_blog_post(post)
    return HTMLResponse(content=html)


@app.get("/sitemap.xml", tags=["SEO"])
async def sitemap_xml():
    """Dynamic sitemap.xml for blog posts"""
    from app.blog.service import get_published_posts_for_sitemap
    from fastapi.responses import Response

    posts = await get_published_posts_for_sitemap()
    base = "https://encpservices.com"

    urls = [f"""  <url>
    <loc>{base}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>""",
    f"""  <url>
    <loc>{base}/blog/</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>"""]

    for p in posts:
        lastmod = (p.get('updated_at') or p.get('published_at'))
        lastmod_str = lastmod.strftime('%Y-%m-%d') if lastmod else ''
        urls.append(f"""  <url>
    <loc>{base}/blog/{p['slug']}/</loc>
    <lastmod>{lastmod_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""
    return Response(content=xml, media_type="application/xml")


def _render_blog_post(post: dict) -> str:
    """Render blog post as full HTML page with JSON-LD structured data"""
    import json as _json
    import html as _html

    title = _html.escape(post['title'])
    meta_desc = _html.escape(post.get('meta_description', ''))
    content = post['content']
    category = post.get('category', '')
    city = post.get('city', '')
    tags = post.get('tags', []) or []
    slug = post['slug']
    views = post.get('views', 0)
    published_at = post.get('published_at')
    published_str = published_at.strftime('%B %d, %Y') if published_at else ''
    published_iso = published_at.isoformat() if published_at else ''
    base_url = "https://encpservices.com"
    canonical = f"{base_url}/blog/{slug}/"

    # JSON-LD structured data
    json_ld = _json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post['title'],
        "description": post.get('meta_description', ''),
        "url": canonical,
        "datePublished": published_iso,
        "author": {
            "@type": "Organization",
            "name": "ENCP Services Group",
            "url": base_url,
            "telephone": "+1-561-506-7035"
        },
        "publisher": {
            "@type": "Organization",
            "name": "ENCP Services Group",
            "logo": {
                "@type": "ImageObject",
                "url": f"{base_url}/assets/logo/encp-logo-horizontal.png"
            }
        },
        "mainEntityOfPage": canonical,
        "articleSection": category,
        "keywords": ", ".join(tags) if tags else ""
    }, indent=2)

    tags_html = "".join(f'<span class="tag">{_html.escape(t)}</span>' for t in tags)
    city_span = f'<span>{_html.escape(city)}</span>' if city else ''

    template_path = FRONTEND_DIR / "blog-post.html"
    template = template_path.read_text(encoding="utf-8")

    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{META_DESCRIPTION}}", meta_desc)
    html = html.replace("{{CANONICAL_URL}}", canonical)
    html = html.replace("{{PUBLISHED_AT}}", published_iso)
    html = html.replace("{{CATEGORY}}", _html.escape(category.title()) if category else "General")
    html = html.replace("{{DATE}}", published_str)
    html = html.replace("{{CITY_SPAN}}", city_span)
    html = html.replace("{{VIEWS}}", str(views))
    html = html.replace("{{CONTENT}}", content)
    html = html.replace("{{TAGS_HTML}}", tags_html)
    html = html.replace("{{JSON_LD}}", json_ld)

    return html


@app.get(ADMIN_PANEL_PATH, include_in_schema=False)
@app.get(ADMIN_PANEL_PATH + "/", include_in_schema=False)
async def serve_admin():
    """Serve admin dashboard (hidden path)"""
    admin = FRONTEND_DIR / "admin.html"
    if admin.exists():
        return FileResponse(admin)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(status_code=404, content="<h1>404</h1><p>Not found</p>")


# ============================================
# PWA FILES
# ============================================

@app.get("/manifest.json", tags=["PWA"])
async def serve_manifest():
    manifest = FRONTEND_DIR / "manifest.json"
    if manifest.exists():
        return FileResponse(manifest, media_type="application/manifest+json")
    return {"error": "manifest.json not found"}


@app.get("/sw.js", tags=["PWA"])
async def serve_service_worker():
    sw = FRONTEND_DIR / "sw.js"
    if sw.exists():
        return FileResponse(sw, media_type="application/javascript")
    return {"error": "sw.js not found"}


# ============================================
# STATIC FILES
# ============================================

if FRONTEND_DIR.exists():
    static_dir = FRONTEND_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static_assets")
    # Serve landing page assets (logos, photos, css)
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="landing_assets")
    styles_file = FRONTEND_DIR / "styles.css"
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8004,
        reload=DEBUG
    )
