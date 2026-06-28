from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.shared.database import get_db
from app.shared.models import ScrapeTask
from app.api.dependencies import get_current_user

router = APIRouter()

@router.post("/")
async def create_scrape(
    request: ScrapeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    task = ScrapeTask(
        user_id=current_user["id"],
        url="https://www.kleinanzeigen.de/...",   # Will come from URL builder
        parameters=request.dict(),
        status="pending"
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"task_id": task.id, "status": task.status}
