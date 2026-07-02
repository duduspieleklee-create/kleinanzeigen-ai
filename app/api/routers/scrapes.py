import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from app.shared.database import get_db, SessionLocal
from app.shared.models import ScrapeTask, ScrapeResult, User, Favorite
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

MIN_INTERVAL_PROD = 60  # 1 minute — enforced in non-dev environments (Pro's floor)


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
    # credit system: 1 credit per NEW listing found, a cap on concurrently
    # active recurring searches, and a per-plan minimum check interval.
    user = db.query(User).filter(User.id == current_user["id"]).first()
    is_exempt = bool(user and user.is_admin)

    if user and not is_exempt:
        # 0. Email verification — throwaway accounts must confirm their inbox
        # before they can consume scraping capacity / farm weekly credits.
        if not user.email_verified:
            return _flash_error(
                "Please verify your email address before starting searches - "
                "check your inbox or use 'Resend verification email' above."
            )

        ensure_weekly_credits(db, user)
        cfg = plan_config(user.plan)

        # 1. Credits — 1 credit is consumed per NEW listing found (charged by
        # the worker when results are saved). Starting a search itself is
        # free, but pointless at 0 credits, so block it with a clear message.
        if user.credits <= 0:
            reset_str = (
                user.credits_reset_at.strftime("%d.%m. %H:%M UTC")
                if user.credits_reset_at
                else "next week"
            )
            return _flash_error(
                f"No credits left on the {cfg['label']} plan - each new listing "
                f"found uses 1 credit. Credits reset on {reset_str}. "
                "Upgrade at /billing for more."
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
    # No credit is charged here — credits are consumed by the worker, 1 per
    # NEW listing saved (see app/worker/tasks.py).
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
    page: int = Query(default=1, ge=1),
    tab: str = Query(default="all"),
):
    from datetime import datetime, timezone
    from collections import Counter

    PAGE_SIZE = 10
    COOKIE_NAME = f"rv_{task_id}"  # "results visited" — stores last-visit Unix timestamp

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

    all_results = (
        db.query(ScrapeResult)
        .filter(ScrapeResult.task_id == task_id)
        .order_by(ScrapeResult.created_at.desc())
        .all()
    )

    # ── "New since last visit" cutoff ────────────────────────────────────────
    # Cookie rv_{task_id} stores the Unix timestamp of the user's previous page
    # load. Results whose created_at is strictly after that timestamp are "new".
    # First visit: no cookie → no NEW badges (nothing to compare against yet).
    # The cookie is always updated to now() at the end of the response so the
    # NEXT visit will correctly compare against the current visit time.
    now_utc = datetime.now(timezone.utc)
    last_visit: datetime | None = None
    raw_cookie = request.cookies.get(COOKIE_NAME)
    if raw_cookie:
        try:
            last_visit = datetime.fromtimestamp(float(raw_cookie), tz=timezone.utc)
        except (ValueError, OSError):
            last_visit = None

    def _is_new(r) -> bool:
        if last_visit is None or not r.created_at:
            return False
        ts = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
        return ts > last_visit

    new_count = sum(1 for r in all_results if _is_new(r))

    # ── Subcategory tabs: unique locations (up to 4 most common) ────────────
    loc_counts = Counter(
        r.location.split("\n")[0].strip()
        for r in all_results
        if r.location and r.location.strip() and r.location.strip() != "N/A"
    )
    location_tabs = [loc for loc, _ in loc_counts.most_common(4)] if len(loc_counts) > 1 else []

    # ── Apply tab filter ──────────────────────────────────────────────────────
    if tab == "new":
        filtered = [r for r in all_results if _is_new(r)]
    elif tab in location_tabs:
        filtered = [r for r in all_results if r.location and tab in r.location]
    else:
        tab = "all"
        filtered = list(all_results)

    # ── Pagination ────────────────────────────────────────────────────────────
    total_in_tab = len(filtered)
    total_pages = max(1, (total_in_tab + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    page_results = filtered[offset:offset + PAGE_SIZE]

    # ── Market context + deal badges + NEW flag ───────────────────────────────
    user = db.query(User).filter(User.id == current_user["id"]).first()
    show_deals = bool(user and (user.is_admin or plan_config(user.plan).get("deal_badges")))
    median = median_price([r.price_value for r in all_results]) if show_deals else None
    for r in page_results:
        r.deal = deal_badge(r.price_value, median) if show_deals else None
        r.is_new = _is_new(r)

    response = templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "task": task,
            "results": page_results,
            "total_count": len(all_results),
            "new_count": new_count,
            "median": median,
            "show_deals": show_deals,
            "tab": tab,
            "location_tabs": location_tabs,
            "page": page,
            "total_pages": total_pages,
            "total_in_tab": total_in_tab,
        },
    )
    # Stamp this visit so the next load can compare against it.
    # 30-day expiry; httponly prevents JS tampering; samesite=lax is safe for nav.
    response.set_cookie(
        COOKIE_NAME,
        value=str(now_utc.timestamp()),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return response


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


@router.post("/{task_id}/delete")
async def delete_scrape(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a search and all its results (unless favorited)."""
    task = db.query(ScrapeTask).filter(
        ScrapeTask.id == task_id,
        ScrapeTask.user_id == current_user["id"],
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Search not found")

    db.delete(task)
    db.commit()

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("flash_success", f"Search #{task_id} and all results deleted.", max_age=5)
    return response


@router.post("/results/{result_id}/favorite")
async def toggle_favorite(
    result_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Toggle a result as favorite for the current user."""
    result = db.query(ScrapeResult).join(ScrapeTask).filter(
        ScrapeResult.id == result_id,
        ScrapeTask.user_id == current_user["id"]
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    existing = db.query(Favorite).filter(
        Favorite.user_id == current_user["id"],
        Favorite.result_id == result_id
    ).first()

    if existing:
        db.delete(existing)
        status = "removed"
    else:
        new_fav = Favorite(user_id=current_user["id"], result_id=result_id)
        db.add(new_fav)
        status = "added"
    
    db.commit()
    return {"status": "success", "favorite": status}


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
