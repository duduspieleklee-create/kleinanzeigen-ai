from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, scrapes
from app.shared.database import Base, engine

# Create database tables (for development only)
# In production, use Alembic migrations instead
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="kleinanzeigen-ai",
    description="Intelligent scraping platform for kleinanzeigen.de",
    version="0.1.0"
)

# CORS middleware (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(scrapes.router, prefix="/scrapes", tags=["Scrapes"])


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "kleinanzeigen-ai"}
