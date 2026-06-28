from pydantic import BaseModel
from typing import Optional, Dict, Any


class ScrapeRequest(BaseModel):
    keywords: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    price_max: Optional[int] = None


class ScrapeResponse(BaseModel):
    task_id: int
    status: str
    message: str
