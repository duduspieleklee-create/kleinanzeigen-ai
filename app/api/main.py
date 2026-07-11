import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.config import settings
from app.api.routers import (
    admin, auth, billing, scrapes, push, locations, geocode, settings as settings_router
)
from app.api.dependencies import get_current_user
from app.api.security import limiter
from app.api.version import BUILD_INFO, register_globals
from app.shared.database import get_db
from app.shared.models import AdminSearch, Proxy, ScrapeTask, ScrapeResult, User, Favorite
from app.shared.plans import PLANS, ensure_weekly_credits, plan_config
from app.shared.pricing import deal_badge, median_price
from app.shared.token_tracking import get_token_usage_stats
from app.shared.proxy import is_rotating_enabled
from app.shared.logging_config import logger
from app.shared.sentry import init_sentry
from app.shared.observability import install_log_bridge
from app.shared.metrics_prom import start_db_collector

logger.info("Starting kleinanzeigen-ai application...")
init_sentry("api")
install_log_bridge()
start_db_collector()

def _relative_time_de(dt) -> str:
    """German relative-time label for the results feed ("vor 5 Min.", "gestern", ...)."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - dt).total_seconds()
    if seconds < 60:
        return "gerade eben"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"vor {minutes} Min."
    hours = int(minutes // 60)
    if hours < 24:
        return f"vor {hours} Std."
    days = int(hours // 24)
    if days == 1:
        return "gestern"
    if days < 7:
        return f"vor {days} Tagen"
    return dt.strftime("%d.%m.%Y")


def _is_recent(dt, hours: int = 6) -> bool:
    """True if dt is within the last `hours` — drives the "NEU" badge."""
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt < timedelta(hours=hours)


app = FastAPI(title="kleinanzeigen-ai")

# Sentry request context: tag route + (best-effort) user id per request so
# API errors become filterable in Sentry without touching every endpoint.
from jose import jwt as _jwt  # noqa: E402

from app.api.config import settings as _settings  # noqa: E402
from app.shared.observability import set_request_context  # noqa: E402


@app.middleware("http")
async def _sentry_request_context(request: Request, call_next):
    user_id = None
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = _jwt.decode(token, _settings.secret_key, algorithms=["HS256"])
            sub = payload.get("sub")
            if sub is not None:
                user_id = int(sub)
        except Exception:
            pass
    set_request_context(user_id, request.url.path, request.method)
    return await call_next(request)


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
            # Compare registrable hosts, ignoring a leading "www." so the same
            # site served from both www. and apex is not treated as cross-origin
            # (Caddy canonicalises www -> apex, but this keeps the check robust
            # if a proxy ever forwards a different Host).
            def _host_core(h: str) -> str:
                h = (h or "").lower()
                if h.startswith("www."):
                    h = h[4:]
                return h
            if source_host and _host_core(source_host) != _host_core(request.url.netloc):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected"},
                )

    response = await call_next(request)

    # ── Security response headers ────────────────────────────────────────────
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Cloudflare Turnstile loads its widget script and renders an iframe from
    # challenges.cloudflare.com, so it must be allowed in script-src/frame-src.
    # The results map view (dashboard "Kartenansicht") loads the Leaflet lib
    # (JS+CSS) from cdnjs.cloudflare.com and renders OpenStreetMap tiles (covered
    # by img-src 'https:'). Geocoding is done server-side (POST /api/geocode →
    # app/shared/geocoding.py), so the browser only ever calls our own origin —
    # connect-src does NOT need nominatim.openstreetmap.org.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com "
        "https://cdnjs.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; "
        "connect-src 'self' https://challenges.cloudflare.com; "
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
app.include_router(geocode.router, tags=["Geocode"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(billing.router, prefix="/billing", tags=["Billing"])
app.include_router(settings_router.router, tags=["Settings"])


@app.get("/healthz", tags=["Ops"], include_in_schema=False)
async def healthz():
    return JSONResponse({"status": "ok"})


@app.get("/version", tags=["Ops"], include_in_schema=False)
async def version():
    return JSONResponse(BUILD_INFO)


@app.get("/metrics", tags=["Ops"], include_in_schema=False)
async def metrics():
    """Prometheus scrape endpoint (text exposition format)."""
    from app.shared.metrics_prom import render_metrics
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


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
        # Public landing page — what a visitor without an account sees.
        # The login form itself now lives at GET /login.
        return templates.TemplateResponse(
            "landing.html",
            {"request": request, "plans": PLANS},
        )


@app.get("/login", tags=["Web"])
async def login_page(request: Request, db: Session = Depends(get_db)):
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
        return await _build_dashboard(request, db)
    except Exception:
        logger.exception("Unhandled exception on /dashboard")
        raise


async def _build_dashboard(
    request: Request,
    db: Session,
):
    try:
        current_user = get_current_user(
            request, token=request.cookies.get("access_token") or "", db=db
        )
    except HTTPException:
        return RedirectResponse(url="/")

    flash_success = request.cookies.get("flash_success")
    flash_error = request.cookies.get("flash_error")
    new_task_id = request.cookies.get("new_task_id")

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
        task.last_checked_de = _relative_time_de(task.last_run_at)
        tasks_with_counts.append(task)

    is_admin = current_user["is_admin"]

    admin_error = None
    proxy_error = None
    admin_searches = []
    proxies = []
    rotating_proxy_enabled = False
    if is_admin:
        try:
            admin_searches = db.query(AdminSearch).order_by(AdminSearch.created_at.desc()).all()
        except Exception:
            logger.exception("Failed to load admin searches for dashboard")
            admin_error = "Admin-Suchen konnten nicht geladen werden."
            db.rollback()  # reset session before the next query
        try:
            proxies = db.query(Proxy).order_by(Proxy.created_at.desc()).all()
            rotating_proxy_enabled = is_rotating_enabled(db)
        except Exception:
            logger.exception("Failed to load proxies for dashboard")
            proxy_error = "Proxy-Status konnte nicht geladen werden."
            db.rollback()

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
    # Advanced result filters (require/exclude keywords + exclude locations) are
    # a Core/Pro feature — the wizard shows the fields enabled only for eligible
    # plans (Basic sees them disabled with an upsell).
    show_advanced_filters = bool(is_admin or (cfg and cfg.get("advanced_filters", False)))
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
            r.relative_time = _relative_time_de(r.created_at)
            r.is_new = _is_recent(r.created_at)
            recent_results.append(r)

    favorites = (
        db.query(ScrapeResult)
        .join(Favorite)
        .filter(Favorite.user_id == current_user["id"])
        .all()
    )
    for fav in favorites:
        fav.relative_time = _relative_time_de(fav.created_at)

    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tasks": tasks_with_counts,
            "recent_results": recent_results,
            "show_deals": show_deals,
            "show_trust_scores": show_trust_scores,
            "show_advanced_filters": show_advanced_filters,
            "flash_success": flash_success,
            "flash_error": flash_error,
            "new_task_id": new_task_id,
            "plan_notice": plan_notice,
            "is_admin": is_admin,
            "admin_searches": admin_searches,
            "proxies": proxies,
            "rotating_proxy_enabled": rotating_proxy_enabled,
            "admin_error": admin_error,
            "proxy_error": proxy_error,
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
            "favorites": favorites,
        },
    )

    if flash_success:
        response.delete_cookie("flash_success")
    if flash_error:
        response.delete_cookie("flash_error")
    if new_task_id:
        response.delete_cookie("new_task_id")

    if plan_notice and db_user is not None:
        db_user.plan_notice = None
        db.commit()

    return response
