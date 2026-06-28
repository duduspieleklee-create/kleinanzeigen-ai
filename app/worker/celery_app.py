from celery import Celery

celery_app = Celery(
    "kleinanzeigen-ai-worker",
    broker="redis://localhost:6379/0",      # Will be replaced with Azure Redis
    backend="redis://localhost:6379/0"
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
)
