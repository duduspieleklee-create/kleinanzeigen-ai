import os
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.routers import admin, auth, scrapes, push, locations
from app.api.dependencies import get_current_user
from app.api.version import BUILD_INFO, register_globals
from app.shared.database import get_db
from app.shared.models import AdminSearch, Proxy, ScrapeTask, ScrapeResult, User
from app.shared.pricing import deal_badge, median_price
from app.shared.proxy import is_rotating_enabled
from app.shared.logging_config import logger

logger.info("Starting kleinanzeigen-ai application...")

app = FastAPI(title="kleinanzeigen-ai")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "dev" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", tags=["Web"])
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        current_user = get_current_user(request, token=request.cookies.get("access_token") or "")
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

    admin_searches = []
    try:
        admin_searches = db.query(AdminSearch).order_by(AdminSearch.created_at.desc()).all()
    except Exception:
        pass

    proxies = []
    rotating_proxy_enabled = False
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

    # "New since your last visit" — listings that arrived after last_seen_at.
    # Skipped for brand-new accounts (NULL) so they aren't flooded on first login.
    new_results = []
    last_seen = db_user.last_seen_at if db_user else None
    if db_user and last_seen is not None:
        new_results = (
            db.query(ScrapeResult)
            .join(ScrapeTask, ScrapeResult.task_id == ScrapeTask.id)
            .filter(
                ScrapeTask.user_id == current_user["id"],
                ScrapeResult.created_at > last_seen,
            )
            .order_by(ScrapeResult.created_at.desc())
            .limit(60)
            .all()
        )
        # Deal badge per listing, relative to its own search's median price.
        medians = {}
        for tid in {r.task_id for r in new_results}:
            vals = [
                v for (v,) in db.query(ScrapeResult.price_value)
                .filter(ScrapeResult.task_id == tid).all()
            ]
            medians[tid] = median_price(vals)
        for r in new_results:
            r.deal = deal_badge(r.price_value, medians.get(r.task_id))

    # Advance the visit marker so the overlay only shows each new listing once.
    if db_user:
        db_user.last_seen_at = datetime.now(timezone.utc)
        db.commit()

    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tasks": tasks_with_counts,
            "flash_success": flash_success,
            "flash_error": flash_error,
            "is_admin": True,
            "admin_searches": admin_searches,
            "daily_limit": daily_limit,
            "used_today": used_today,
            "proxies": proxies,
            "rotating_proxy_enabled": rotating_proxy_enabled,
            "new_results": new_results,
        },
    )

    if flash_success:
        response.delete_cookie("flash_success")
    if flash_error:
        response.delete_cookie("flash_error")

    return response
