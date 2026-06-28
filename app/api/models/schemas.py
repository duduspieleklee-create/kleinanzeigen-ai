from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    category: str = Field(..., description="Kleinanzeigen category slug")
    location: str = Field(default="", description="City or region filter")
    max_pages: int = Field(default=5, ge=1, le=50, description="Maximum pages to scrape")


class ScrapeResponse(BaseModel):
    task_id: str
    status: str


class ListingSchema(BaseModel):
    external_id: str
    title: str
    price: float | None
    location: str | None
    url: str
    description: str | None = None
