import sentry_sdk
from celery.schedules import crontab

from app.worker.celery_app import celery_app

# celery_app.py already calls init_sentry("worker") on import; retag as
# "beat" since this process dispatches schedules rather than running tasks.
sentry_sdk.set_tag("component", "beat")

# Beat dispatches all active AdminSearch entries every 60 seconds.
# The task itself skips entries whose next_run_at is still in the future,
# so the effective poll interval per search is controlled by interval_minutes.
celery_app.conf.beat_schedule = {
    "dispatch-admin-searches": {
        "task": "scrape.dispatch_admin_searches",
        "schedule": 60.0,
    },
    # Retention purge — app/worker/archival_task.py implements these but they
    # were never wired into a schedule, so results/token-usage rows piled up
    # forever despite the documented 14-day / 90-day policy. Run both once a
    # day at 03:00 Europe/Berlin, off-peak for scrape traffic.
    "cleanup-old-results": {
        "task": "archival.cleanup_old_results",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-old-token-usage": {
        "task": "archival.cleanup_old_token_usage",
        "schedule": crontab(hour=3, minute=15),
    },
}

celery_app.conf.timezone = "Europe/Berlin"
