from fastapi import APIRouter, Depends
from app.api.dependencies import require_auth
from app.api.models.schemas import ScrapeRequest, ScrapeResponse
from app.worker.tasks import run_scrape

router = APIRouter()


@router.post("/", response_model=ScrapeResponse)
async def create_scrape(request: ScrapeRequest, _: str = Depends(require_auth)):
    """Enqueue a new scrape job."""
    task = run_scrape.delay(
        category=request.category,
        location=request.location,
        max_pages=request.max_pages,
    )
    return ScrapeResponse(task_id=task.id, status="queued")


@router.get("/{task_id}", response_model=ScrapeResponse)
async def get_scrape_status(task_id: str, _: str = Depends(require_auth)):
    """Get the status of a scrape job."""
    task = run_scrape.AsyncResult(task_id)
    return ScrapeResponse(task_id=task_id, status=task.state.lower())
