from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.models import ScrapeResult, ScrapeTask
from app.shared.url_builder import build_kleinanzeigen_url
from app.worker.tasks import scrape_kleinanzeigen

router = APIRouter()
templates = Jinja2Templates(directory="app/api/templates")


@router.post("/submit")
async def submit_scrape(
    request: Request,
    keywords: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    price_max: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Accept the dashboard form, create a ScrapeTask, dispatch to Celery."""
    parameters = {
        "keywords": keywords or None,
        "category": category or None,
        "location": location or None,
        "price_max": price_max or None,
    }

    url = build_kleinanzeigen_url(**{k: v for k, v in parameters.items() if v is not None})

    task = ScrapeTask(
        user_id=current_user["id"],
        url=url,
        status="pending",
        parameters=parameters,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Dispatch the Celery task with the DB task ID so the worker can update status
    scrape_kleinanzeigen.delay(parameters, task.id)

    return RedirectResponse(url="/scrapes/results", status_code=303)


@router.get("/results", response_class=HTMLResponse)
async def get_results(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all scrape results belonging to the current user."""
    results = (
        db.query(ScrapeResult)
        .join(ScrapeTask, ScrapeResult.task_id == ScrapeTask.id)
        .filter(ScrapeTask.user_id == current_user["id"])
        .order_by(ScrapeResult.created_at.desc())
        .all()
    )

    return templates.TemplateResponse("results.html", {
        "request": request,
        "results": results,
    })
