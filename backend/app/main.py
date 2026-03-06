"""
ENCP Services Group - Main Application
FastAPI backend for AI tile/remodel contractor assistant
Single company — NO multi-tenant
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from app.config import (
    APP_NAME, APP_VERSION, DEBUG, MAINTENANCE_MODE,
    CORS_ORIGINS, CORS_ALLOW_CREDENTIALS, CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS,
    PRODUCTION_ORIGINS, ADMIN_PANEL_PATH
)
from app.database import init_db, close_db
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


# ============================================
# LIFECYCLE
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown"""
    # Startup
    print(f"\n  {APP_NAME} v{APP_VERSION}")
    print("=" * 40)
    print("[CRYPTO] Encryption key configured via environment")

    try:
        await init_db()
        print("[DB] Database connected")
    except Exception as e:
        print(f"[WARN] Database not available: {e}")
        print("[WARN] Running without database - some features disabled")

    if MAINTENANCE_MODE:
        print("[WARN] MAINTENANCE MODE ACTIVE")
    print("[OK] API ready")
    print("=" * 40)

    yield

    # Shutdown
    try:
        await close_db()
    except Exception:
        pass
    print(f"\n[SHUTDOWN] {APP_NAME} stopped\n")


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
    return {"status": "healthy"}


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
