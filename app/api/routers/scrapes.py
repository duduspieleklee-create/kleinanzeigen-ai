from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from app.shared.database import get_db
from app.shared.models import ScrapeTask
from app.worker.tasks import scrape_kleinanzeigen
from app.api.dependencies import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/api/templates")


@router.post("/submit", response_class=HTMLResponse)
async def submit_scrape_form(
    request: Request,
    keywords: str = Form(None),
    category: str = Form(None),
    location: str = Form(None),
    price_max: int = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Build parameters from form
    parameters = {
        "keywords": keywords,
        "category": category,
        "location": location,
        "price_max": price_max
    }

    # Create database record
    task = ScrapeTask(
        user_id=current_user["id"],
        url="pending",  # Will be updated by worker or URL builder
        parameters=parameters,
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Send task to Celery
    scrape_kleinanzeigen.delay(parameters)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "message": f"Scrape job #{task.id} submitted successfully!"
    })
