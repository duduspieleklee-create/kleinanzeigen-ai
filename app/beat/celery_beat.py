from celery.schedules import crontab
from app.worker.celery_app import celery_app

# Celery Beat Schedule
celery_app.conf.beat_schedule = {
    # Example: Run a scrape task every 30 minutes
    "scheduled-scrape-every-30-minutes": {
        "task": "scrape.kleinanzeigen",
        "schedule": crontab(minute="*/30"),   # Every 30 minutes
        "args": [{
            "keywords": "handwerker",
            "location": "berlin",
            "price_max": 200
        }]
    },
}

celery_app.conf.timezone = "Europe/Berlin"
