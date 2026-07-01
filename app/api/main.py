import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.config import settings
from app.api.routers import admin, auth, scrapes, push, locations
from app.api.dependencies import get_current_user
from app.api.security import limiter
from app.api.version import BUILD_INFO, register_globals
from app.shared.database import get_db
from app.shared.models import AdminSearch, Proxy, ScrapeTask, ScrapeResult, User
from app.shared.proxy import is_rotating_enabled
from app.shared.logging_config import logger

logger.info("Starting kleinanzeigen-ai application...")

app = FastAPI(title="kleinanzeigen-ai")

# Rate limiting — brute-force / credential-stuffing protection on auth routes.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "dev" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Signed session cookie — required by Authlib to carry the Google OAuth
# state/nonce between the redirect and the callback.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=settings.environment != "dev",
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # ── CSRF defense: same-origin check for state-changing methods ───────────
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        source = request.headers.get("origin") or request.headers.get("referer")
        if source:
            source_host = urlparse(source).netloc
            if source_host and source_host != request.url.netloc:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected"},
                )

    response = await call_next(request)

    # ── Security response headers ────────────────────────────────────────────
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )
    if settings.environment != "dev":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

templates = Jinja2Templates(directory="app/api/templates")
register_globals(templates)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(scrapes.router, prefix="/scrapes", tags=["Scrapes"])
app.include_router(push.router, prefix="/push", tags=["Push"])
app.include_router(locations.router, prefix="/locations", tags=["Locations"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.get("/healthz", tags=["Ops"], include_in_schema=False)
async def healthz():
    return JSONResponse({"status": "ok"})


@app.get("/version", tags=["Ops"], include_in_schema=False)
async def version():
    return JSONResponse(BUILD_INFO)


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    sw_path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    return FileResponse(sw_path, media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})


@app.get("/offline", tags=["Web"], include_in_schema=False)
async def offline(request: Request):
    return templates.TemplateResponse("offline.html", {"request": request})


@app.get("/", tags=["Web"])
async def home(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "google_enabled": bool(settings.google_client_id)},
    )


@app.get("/dashboard", tags=["Web"])
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        current_user = get_current_user(
            request, token=request.cookies.get("access_token") or "", db=db
        )
    except HTTPException:
        return RedirectResponse(url="/")

    flash_success = request.cookies.get("flash_success")
    flash_error = request.cookies.get("flash_error")

    rows = (
        db.query(ScrapeTask, func.count(ScrapeResult.id).label("result_count"))
        .outerjoin(ScrapeResult, ScrapeResult.task_id == ScrapeTask.id)
        .filter(ScrapeTask.user_id == current_user["id"])
        .group_by(ScrapeTask.id)
        .order_by(ScrapeTask.created_at.desc())
        .limit(50)
        .all()
    )

    tasks_with_counts = []
    for task, count in rows:
        task.result_count = count
        tasks_with_counts.append(task)

    is_admin = current_user["is_admin"]

    admin_searches = []
    proxies = []
    rotating_proxy_enabled = False
    if is_admin:
        try:
            admin_searches = db.query(AdminSearch).order_by(AdminSearch.created_at.desc()).all()
        except Exception:
            pass
        try:
            proxies = db.query(Proxy).order_by(Proxy.created_at.desc()).all()
            rotating_proxy_enabled = is_rotating_enabled(db)
        except Exception:
            pass

    # Daily search quota (0 == unlimited, e.g. admin)
    db_user = db.query(User).filter(User.id == current_user["id"]).first()
    daily_limit = db_user.daily_limit if db_user else 0
    used_today = 0
    if daily_limit and daily_limit > 0:
        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        used_today = (
            db.query(ScrapeTask)
            .filter(
                ScrapeTask.user_id == current_user["id"],
                ScrapeTask.created_at >= start_of_day,
            )
            .count()
        )

    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tasks": tasks_with_counts,
            "flash_success": flash_success,
            "flash_error": flash_error,
            "is_admin": is_admin,
            "admin_searches": admin_searches,
            "daily_limit": daily_limit,
            "used_today": used_today,
            "proxies": proxies,
            "rotating_proxy_enabled": rotating_proxy_enabled,
        },
    )

    if flash_success:
        response.delete_cookie("flash_success")
    if flash_error:
        response.delete_cookie("flash_error")

    return response
