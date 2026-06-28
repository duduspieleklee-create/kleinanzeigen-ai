from celery.schedules import crontab
from app.worker.celery_app import celery_app

celery_app.conf.beat_schedule = {
    "scrape-cars-every-hour": {
        "task": "tasks.run_scrape",
        "schedule": crontab(minute=0),
        "kwargs": {"category": "fahrzeuge", "location": "", "max_pages": 10},
    },
    "scrape-electronics-every-2h": {
        "task": "tasks.run_scrape",
        "schedule": crontab(minute=0, hour="*/2"),
        "kwargs": {"category": "elektronik", "location": "", "max_pages": 5},
    },
}
