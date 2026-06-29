from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.models import ScrapeTask, ScrapeResult
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

    # Pass task_id so the worker can link ScrapeResults and update task status
    scrape_kleinanzeigen.delay(parameters, task.id)

    return ScrapeResponse(
        task_id=task.id,
        status=task.status,
        message="Scrape job submitted successfully"
    )


@router.get("/{task_id}", response_model=ScrapeResponse)
async def get_scrape_status(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    task = db.query(ScrapeTask).filter(
        ScrapeTask.id == task_id,
        ScrapeTask.user_id == current_user["id"]
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result_count = db.query(ScrapeResult).filter(ScrapeResult.task_id == task_id).count()

    return ScrapeResponse(
        task_id=task.id,
        status=task.status,
        message=f"{result_count} result(s) saved"
    )


@router.get("/", response_model=list[ScrapeResponse])
async def list_scrapes(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    skip: int = 0,
    limit: int = 20
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
