import os
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
from app.shared.models import AdminSearch, ScrapeTask, ScrapeResult
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

    response = templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tasks": tasks_with_counts,
            "flash_success": flash_success,
            "flash_error": flash_error,
            "is_admin": True,
            "admin_searches": admin_searches,
        },
    )

    if flash_success:
        response.delete_cookie("flash_success")
    if flash_error:
        response.delete_cookie("flash_error")

    return response
