from pydantic import BaseModel
from typing import Optional


class ScrapeRequest(BaseModel):
    keywords: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    price_max: Optional[int] = None
    radius: Optional[int] = None
    sort: Optional[str] = "neueste"   # Default sorting option


class ScrapeResponse(BaseModel):
    task_id: int
    status: str
    message: str
