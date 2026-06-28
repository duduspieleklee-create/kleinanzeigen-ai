from fastapi import FastAPI
from app.api.routers import auth, scrapes
from app.api.config import settings

app = FastAPI(
    title="kleinanzeigen-ai API",
    version="0.1.0",
    description="Intelligent scraping and analytics platform for kleinanzeigen.de",
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(scrapes.router, prefix="/scrapes", tags=["scrapes"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.environment}
