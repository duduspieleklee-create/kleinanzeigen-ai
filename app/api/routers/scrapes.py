from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.models import ScrapeTask
from app.api.models.schemas import ScrapeRequest, ScrapeResponse
from app.api.dependencies import get_current_user
from app.worker.tasks import scrape_kleinanzeigen

router = APIRouter()


@router.post("/", response_model=ScrapeResponse)
async def create_scrape(
    request: ScrapeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    parameters = request.model_dump()

    task = ScrapeTask(
        user_id=current_user["id"],
        url="pending",
        parameters=parameters,
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Send to Celery
    scrape_kleinanzeigen.delay(parameters)

    return ScrapeResponse(
        task_id=task.id,
        status=task.status,
        message="Scrape job submitted successfully"
    )
