from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from starlette.templating import Jinja2Templates

from app.shared.database import get_db
from app.shared.models import ScrapeResult
from app.api.dependencies import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/api/templates")


@router.get("/results", response_class=HTMLResponse)
async def get_results(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    results = (
        db.query(ScrapeResult)
        .join(ScrapeResult.task)
        .filter(ScrapeResult.task.has(user_id=current_user["id"]))
        .order_by(ScrapeResult.created_at.desc())
        .all()
    )

    return templates.TemplateResponse("results.html", {
        "request": request,
        "results": results
    })
