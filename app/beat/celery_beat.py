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
    # Safety net for USER recurring searches: unlike admin searches (dispatched
    # from next_run_at above), user searches self-reschedule via an in-broker
    # ETA task that a worker restart/crash drops, silently killing the chain.
    # This reaper re-primes any recurring user search that's overdue so a deploy
    # can't strand it. The task's own grace window prevents racing healthy chains.
    "reap-stale-recurring-searches": {
        "task": "scrape.reap_stale_recurring_searches",
        "schedule": 120.0,
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
    # Admin-search category rotation (app/worker/category_rotation_task.py) —
    # checked every 6h; the task itself only acts once ROTATION_INTERVAL_DAYS
    # (3.5 days) has elapsed since the current batch started.
    "rotate-admin-search-categories": {
        "task": "admin_search.rotate_categories",
        "schedule": crontab(minute=5, hour="*/6"),
    },
}

celery_app.conf.timezone = "Europe/Berlin"
