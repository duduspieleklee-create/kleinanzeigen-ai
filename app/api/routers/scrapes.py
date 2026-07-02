import asyncio
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from app.shared.database import get_db, SessionLocal
from app.shared.models import ScrapeTask, ScrapeResult, User
from app.api.models.schemas import ScrapeResponse
from app.api.dependencies import get_current_user
from app.api.version import register_globals
from app.shared.pricing import deal_badge, median_price
from app.shared.plans import plan_config, ensure_weekly_credits
from app.worker.tasks import scrape_kleinanzeigen
from app.api.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/api/templates")
register_globals(templates)

MIN_INTERVAL_PROD = 300  # 5 minutes — enforced in non-dev environments


def _clean_str(value: Optional[str]) -> Optional[str]:
    """Trim whitespace and treat an empty string as absent."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _clean_int(value: Optional[str], label: str, errors: list) -> Optional[int]:
    """Empty -> None; valid digits -> int; otherwise record a friendly error.

    HTML forms submit blank optional fields as "" rather than omitting them,
    so numeric fields must accept strings and coerce here — declaring them as
    Optional[int] makes FastAPI reject the whole request with a raw 422.
    """
    value = _clean_str(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(f"{label} must be a whole number")
        return None


def count_active_recurring(db: Session, user_id: int) -> int:
    """Number of the user's recurring searches that still occupy a plan slot.

    A search occupies a slot while it can keep re-running: it is recurring
    (has interval_seconds) and was not cancelled or failed.
    """
    return (
        db.query(ScrapeTask)
        .filter(
            ScrapeTask.user_id == user_id,
            ScrapeTask.status.in_(("pending", "running", "completed")),
            ScrapeTask.parameters.op("->>")("interval_seconds").isnot(None),
        )
        .count()
    )


@router.post("/", response_model=None)
async def create_scrape(
    request: Request,
    keywords: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    location_id: Optional[str] = Form(None),
    price_min: Optional[str] = Form(None),
    price_max: Optional[str] = Form(None),
    radius: Optional[str] = Form(None),
    ad_type: Optional[str] = Form(None),
    poster_type: Optional[str] = Form(None),
    condition: Optional[str] = Form(None),
    shipping: Optional[str] = Form(None),
    interval_seconds: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    errors: list = []

    keywords = _clean_str(keywords)
    if not keywords:
        errors.append("Please enter search keywords")

    location_id_v = _clean_int(location_id, "Location", errors)
    price_min_v = _clean_int(price_min, "Minimum price", errors)
    price_max_v = _clean_int(price_max, "Maximum price", errors)
    radius_v = _clean_int(radius, "Radius", errors)
    interval_v = _clean_int(interval_seconds, "Interval", errors)

    if price_min_v is not None and price_max_v is not None and price_min_v > price_max_v:
        errors.append("Minimum price cannot be greater than maximum price")

    # On any bad input, go back to the dashboard with a readable message
    # instead of returning a raw 422 JSON body.
    if errors:
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie("flash_error", " · ".join(errors), max_age=10)
        return response

    # ── Plan enforcement (credits / search slots / interval floor) ───────────
    # Admin accounts (is_admin) are exempt. Everyone else runs on the weekly
    # credit system: 1 credit per newly started search, a cap on concurrently
    # active recurring searches, and a per-plan minimum check interval.
    user = db.query(User).filter(User.id == current_user["id"]).first()
    is_exempt = bool(user and user.is_admin)

    if user and not is_exempt:
        ensure_weekly_credits(db, user)
        cfg = plan_config(user.plan)

        # 1. Credits — one per newly started search.
        if user.credits <= 0:
            reset_str = (
                user.credits_reset_at.strftime("%d.%m. %H:%M UTC")
                if user.credits_reset_at
                else "next week"
            )
            return _flash_error(
                f"No search credits left on the {cfg['label']} plan. "
                f"Credits reset on {reset_str}. Upgrade at /billing for more."
            )

        # 2. Recurring-search slots.
        if interval_v is not None:
            active = count_active_recurring(db, user.id)
            if active >= cfg["max_active_searches"]:
                return _flash_error(
                    f"Your {cfg['label']} plan allows {cfg['max_active_searches']} "
                    "active recurring searches. Cancel one or upgrade at /billing."
                )

            # 3. Interval floor per plan.
            if interval_v < cfg["min_interval_seconds"]:
                minutes = cfg["min_interval_seconds"] // 60
                return _flash_error(
                    f"The {cfg['label']} plan allows check intervals of "
                    f"{minutes} minutes or more. Upgrade at /billing for faster checks."
                )

    # Enforce global minimum interval outside dev
    if interval_v is not None and settings.environment != "dev":
        if interval_v < MIN_INTERVAL_PROD:
            interval_v = MIN_INTERVAL_PROD

    parameters = {
        "keywords": keywords,
        "category": _clean_str(category),
        "location": _clean_str(location),
        "location_id": location_id_v,
        "price_min": price_min_v,
        "price_max": price_max_v,
        "radius": radius_v,
        "ad_type": _clean_str(ad_type),
        "poster_type": _clean_str(poster_type),
        "condition": _clean_str(condition),
        "shipping": _clean_str(shipping),
    }
    if interval_v:
        parameters["interval_seconds"] = interval_v

    # Remove None values so url_builder receives clean kwargs
    parameters = {k: v for k, v in parameters.items() if v is not None}

    task = ScrapeTask(
        user_id=current_user["id"],
        url="pending",
        parameters=parameters,
        status="pending",
    )
    db.add(task)
    # Deduct the credit atomically in the same transaction that creates the
    # task. The conditional UPDATE (credits > 0) prevents two concurrent
    # requests from both spending the last credit — the earlier credits check
    # above only produces the friendly error message.
    if user and not is_exempt:
        spent = (
            db.query(User)
            .filter(User.id == user.id, User.credits > 0)
            .update({User.credits: User.credits - 1}, synchronize_session=False)
        )
        if not spent:
            db.rollback()
            return _flash_error(
                "No search credits left. Credits reset weekly - upgrade at /billing for more."
            )
    db.commit()
    db.refresh(task)

    scrape_kleinanzeigen.delay(parameters, task.id)

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("flash_success", f"Scrape job #{task.id} started!", max_age=5)
    return response


def _flash_error(message: str) -> RedirectResponse:
    # Flash cookie values must stay ASCII — Starlette encodes Set-Cookie
    # headers as latin-1 and non-ASCII raises at response time.
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("flash_error", message, max_age=10)
    return response


@router.get("/stream")
async def stream_task_updates(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]

    def fetch_tasks():
        db = SessionLocal()
        try:
            rows = (
                db.query(ScrapeTask, func.count(ScrapeResult.id).label("result_count"))
                .outerjoin(ScrapeResult, ScrapeResult.task_id == ScrapeTask.id)
                .filter(ScrapeTask.user_id == user_id)
                .group_by(ScrapeTask.id)
                .order_by(ScrapeTask.created_at.desc())
                .limit(50)
                .all()
            )
            return [
                {
                    "id": t.id,
                    "status": t.status,
                    "result_count": count,
                    "parameters": t.parameters or {},
                    "url": t.url,
                }
                for t, count in rows
            ]
        finally:
            db.close()

    async def event_generator():
        loop = asyncio.get_running_loop()
        while True:
            if await request.is_disconnected():
                break
            tasks = await loop.run_in_executor(None, fetch_tasks)
            yield f"data: {json.dumps(tasks)}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{task_id}/results", response_model=None)
async def view_results(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    # Mirror the dashboard's auth handling: redirect to login instead of 401
    # so a missed-session user lands on a friendly page.
    try:
        current_user = get_current_user(request, token=request.cookies.get("access_token") or "", db=db)
    except HTTPException:
        return RedirectResponse(url="/")

    task = db.query(ScrapeTask).filter(
        ScrapeTask.id == task_id,
        ScrapeTask.user_id == current_user["id"],
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Search not found")

    results = (
        db.query(ScrapeResult)
        .filter(ScrapeResult.task_id == task_id)
        .order_by(ScrapeResult.created_at.desc())
        .all()
    )

    # Market context: median price across the search, and a deal badge per
    # listing (below / at / above market) — something kleinanzeigen never shows.
    median = median_price([r.price_value for r in results])
    for r in results:
        r.deal = deal_badge(r.price_value, median)

    return templates.TemplateResponse(
        "results.html",
        {"request": request, "task": task, "results": results, "median": median},
    )


@router.get("/{task_id}", response_model=ScrapeResponse)
async def get_scrape_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    task = db.query(ScrapeTask).filter(
        ScrapeTask.id == task_id,
        ScrapeTask.user_id == current_user["id"],
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result_count = db.query(ScrapeResult).filter(ScrapeResult.task_id == task_id).count()

    return ScrapeResponse(
        task_id=task.id,
        status=task.status,
        message=f"{result_count} result(s) saved",
    )


@router.get("/", response_model=list[ScrapeResponse])
async def list_scrapes(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    tasks = (
        db.query(ScrapeTask)
        .filter(ScrapeTask.user_id == current_user["id"])
        .order_by(ScrapeTask.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        ScrapeResponse(task_id=t.id, status=t.status, message=t.url)
        for t in tasks
    ]


@router.post("/{task_id}/cancel")
async def cancel_scrape(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    task = db.query(ScrapeTask).filter(
        ScrapeTask.id == task_id,
        ScrapeTask.user_id == current_user["id"],
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "cancelled"
    db.commit()

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("flash_success", f"Scrape job #{task_id} cancelled.", max_age=5)
    return response
