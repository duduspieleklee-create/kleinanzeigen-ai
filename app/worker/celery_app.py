from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

# Redis connection from environment variable
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "kleinanzeigen-ai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker.tasks"]   # Import tasks module
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,        # 30 minutes max per task
)
