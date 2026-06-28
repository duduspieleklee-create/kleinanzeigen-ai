from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.api.routers import auth, scrapes
from app.shared.database import Base, engine
from app.shared.logging_config import logger

logger.info("Starting kleinanzeigen-ai application...")

# TODO: Replace with Alembic migrations before production
Base.metadata.create_all(bind=engine)

app = FastAPI(title="kleinanzeigen-ai")

app.add_middleware(
    CORSMiddleware,
    # TODO: Restrict to specific origins in production
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/api/static"), name="static")
templates = Jinja2Templates(directory="app/api/templates")

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(scrapes.router, prefix="/scrapes", tags=["Scrapes"])


@app.get("/", tags=["Web"])
async def home(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", tags=["Web"])
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})
