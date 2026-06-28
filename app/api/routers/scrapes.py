from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.models import ScrapeTask
from app.api.dependencies import get_current_user
from app.api.models.schemas import ScrapeRequest, ScrapeResponse

router = APIRouter()


@router.post("/", response_model=ScrapeResponse)
async def create_scrape(
    request: ScrapeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # TODO: Use shared/url_builder.py to generate the real URL
    generated_url = "https://www.kleinanzeigen.de/s-example/berlin/"  # Placeholder

    task = ScrapeTask(
        user_id=current_user["id"],
        url=generated_url,
        parameters=request.model_dump(),
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return ScrapeResponse(
        task_id=task.id,
        status=task.status,
        message="Scrape job created successfully"
    )
