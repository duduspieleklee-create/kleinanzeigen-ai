import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Query
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional

from app.shared.database import get_db, SessionLocal
from app.shared.models import ScrapeTask, ScrapeResult
from app.api.models.schemas import ScrapeResponse
from app.api.dependencies import get_current_user
from app.worker.tasks import scrape_kleinanzeigen
from app.api.config import settings

router = APIRouter()

MIN_INTERVAL_PROD = 300  # 5 minutes — enforced in non-dev environments


@router.post("/", response_model=None)
async def create_scrape(
    request: Request,
    keywords: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    price_max: Optional[int] = Form(None),
    interval_seconds: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Enforce minimum interval outside dev
    if interval_seconds is not None and settings.environment != "dev":
        if interval_seconds < MIN_INTERVAL_PROD:
            interval_seconds = MIN_INTERVAL_PROD

    parameters = {
        "keywords": keywords,
        "category": category,
        "location": location,
        "price_max": price_max,
    }
    if interval_seconds:
        parameters["interval_seconds"] = interval_seconds

    # Remove None values so url_builder receives clean kwargs
    parameters = {k: v for k, v in parameters.items() if v is not None}

    task = ScrapeTask(
        user_id=current_user["id"],
        url="pending",
        parameters=parameters,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    scrape_kleinanzeigen.delay(parameters, task.id)

    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("flash_success", f"Scrape job #{task.id} started!", max_age=5)
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
