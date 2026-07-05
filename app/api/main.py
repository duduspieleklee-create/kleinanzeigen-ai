import os
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
from app.api.routers import (
    admin, auth, billing, scrapes, push, locations, settings as settings_router
)
from app.api.dependencies import get_current_user
from app.api.security import limiter
from app.api.version import BUILD_INFO
from app.shared.database import get_db
from app.shared.models import AdminSearch, Proxy, ScrapeTask, ScrapeResult, User, Favorite
from app.shared.plans import ensure_weekly_credits, plan_config
from app.shared.pricing import deal_badge, median_price
from app.shared.token_tracking import get_token_usage_stats
from app.shared.proxy import is_rotating_enabled
from app.shared.logging_config import logger
from app.shared.sentry import init_sentry

logger.info("Starting kleinanzeigen-ai application...")
init_sentry("api")

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
    # The Stripe webhook is exempt: server-to-server calls send no Origin or
    # Referer header (which already passes this check) and are authenticated
    # by their own signature verification instead.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and \
            request.url.path != "/billing/webhook":
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

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(scrapes.router, prefix="/scrapes", tags=["Scrapes"])
app.include_router(push.router, prefix="/push", tags=["Push"])
app.include_router(locations.router, prefix="/locations", tags=["Locations"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(billing.router, prefix="/billing", tags=["Billing"])
app.include_router(settings_router.router, tags=["Settings"])


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
async def home(request: Request, db: Session = Depends(get_db)):
    try:
        get_current_user(
            request, token=request.cookies.get("access_token") or "", db=db
        )
        return RedirectResponse(url="/dashboard")
    except HTTPException:
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

    # ── Plan / credit status for the plan bar ────────────────────────────────
    db_user = db.query(User).filter(User.id == current_user["id"]).first()
    # One-shot downgrade notice (set by plans.enforce_plan_limits when a plan
    # change cancelled/slowed searches): show it once, then clear it.
    plan_notice = db_user.plan_notice if db_user else None
    plan_name = (db_user.plan if db_user else None) or "basic"
    cfg = plan_config(plan_name)
    credits = 0
    credits_reset_at = None
    active_searches = 0
    if db_user and not is_admin:
        ensure_weekly_credits(db, db_user)
        credits = db_user.credits
        credits_reset_at = db_user.credits_reset_at
        active_searches = (
            db.query(ScrapeTask)
            .filter(
                ScrapeTask.user_id == db_user.id,
                ScrapeTask.status.in_(("pending", "running", "completed")),
                ScrapeTask.parameters.op("->>")("interval_seconds").isnot(None),
            )
            .count()
        )

    # ── "My Results" tab: latest listings across all of the user's searches ──
    recent_rows = (
        db.query(ScrapeResult, ScrapeTask)
        .join(ScrapeTask, ScrapeResult.task_id == ScrapeTask.id)
        .filter(ScrapeTask.user_id == current_user["id"])
        .order_by(ScrapeResult.created_at.desc())
        .limit(60)
        .all()
    )
    # Deal badges are a Core/Pro feature — Basic users get plain results.
    show_deals = bool(is_admin or (cfg and cfg.get("deal_badges")))
    # Trust Score badges are a Core/Pro feature — Basic users see them grayed out
    show_trust_scores = bool(is_admin or (cfg and cfg.get("trust_scores", False)))
    recent_results = []
    if recent_rows:
        medians = {}
        # Pre-calculate medians if needed for deal badges
        task_ids = {t.id for _, t in recent_rows}
        # Only query for medians if there are task IDs (avoid empty IN () SQL error)
        if task_ids:
            by_task: dict = {}
            for tid, val in (
                db.query(ScrapeResult.task_id, ScrapeResult.price_value)
                .filter(ScrapeResult.task_id.in_(task_ids))
                .all()
            ):
                by_task.setdefault(tid, []).append(val)
            medians = {tid: median_price(vals) for tid, vals in by_task.items()}

        for r, t in recent_rows:
            # Attach extra context to each result for the template
            r.deal = deal_badge(r.price_value, medians.get(t.id)) if show_deals else None
            r.search_keywords = (t.parameters or {}).get("keywords") or f"Search #{t.id}"
            recent_results.append(r)

    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tasks": tasks_with_counts,
            "recent_results": recent_results,
            "show_deals": show_deals,
            "show_trust_scores": show_trust_scores,
            "flash_success": flash_success,
            "flash_error": flash_error,
            "plan_notice": plan_notice,
            "is_admin": is_admin,
            "admin_searches": admin_searches,
            "proxies": proxies,
            "rotating_proxy_enabled": rotating_proxy_enabled,
            # Plan bar
            "plan_name": plan_name,
            "plan_label": cfg["label"],
            "credits": credits,
            "credits_reset_at": credits_reset_at,
            "active_searches": active_searches,
            "max_active_searches": cfg["max_active_searches"],
            "min_interval_seconds": 5 if is_admin else cfg["min_interval_seconds"],
            # Email verification banner (admins are exempt from verification).
            "email_verified": bool(db_user.email_verified) if db_user else True,
            "user_email": db_user.email if db_user else "",
            # First-login guided tutorial: shown once until completed/skipped.
            "show_tutorial": bool(db_user and not db_user.has_completed_tutorial),
            # Token stats for "Meine Suchen" tab
            "token_stats": get_token_usage_stats(db, current_user["id"]),
            # Favorites for "Favoriten" sub-tab
            "favorites": (
                db.query(ScrapeResult)
                .join(Favorite)
                .filter(Favorite.user_id == current_user["id"])
                .all()
            ),
        },
    )

    if flash_success:
        response.delete_cookie("flash_success")
    if flash_error:
        response.delete_cookie("flash_error")

    if plan_notice and db_user is not None:
        db_user.plan_notice = None
        db.commit()

    return response
