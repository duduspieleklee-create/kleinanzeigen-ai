from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class ScrapeRequest(BaseModel):
    keywords: str | None = None
    category: str | None = None
    location: str | None = None
    price_max: int | None = None

@router.post("/")
async def create_scrape(request: ScrapeRequest):
    # TODO: Build URL using shared/url_builder.py
    # TODO: Send task to Celery
    return {
        "message": "Scrape job created",
        "parameters": request.dict()
    }
