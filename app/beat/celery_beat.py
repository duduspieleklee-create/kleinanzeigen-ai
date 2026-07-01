from app.worker.celery_app import celery_app

# Beat dispatches all active AdminSearch entries every 60 seconds.
# The task itself skips entries whose next_run_at is still in the future,
# so the effective poll interval per search is controlled by interval_minutes.
celery_app.conf.beat_schedule = {
    "dispatch-admin-searches": {
        "task": "scrape.dispatch_admin_searches",
        "schedule": 60.0,
    },
}

celery_app.conf.timezone = "Europe/Berlin"
