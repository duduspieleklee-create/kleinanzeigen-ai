from celery.schedules import crontab
from app.worker.celery_app import celery_app
from app.api.config import settings

# Celery Beat Schedule — configure search params via env vars:
# BEAT_KEYWORDS, BEAT_LOCATION, BEAT_PRICE_MAX
celery_app.conf.beat_schedule = {
    "scheduled-scrape-every-30-minutes": {
        "task": "scrape.kleinanzeigen",
        "schedule": crontab(minute="*/30"),
        "args": [{
            "keywords": settings.beat_keywords,
            "location": settings.beat_location,
            "price_max": settings.beat_price_max,
        }]
    },
}

celery_app.conf.timezone = "Europe/Berlin"
