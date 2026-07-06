"""Sentry custom Metrics helpers for Celery jobs (worker tasks + Beat schedule).

Calls are safe no-ops when Sentry isn't initialized (missing SENTRY_DSN, or
dev without SENTRY_ENABLE_IN_DEV) -- same behavior as init_sentry().
"""
import time
from contextlib import contextmanager

import sentry_sdk.metrics as sentry_metrics


@contextmanager
def track_job(job_name: str):
    """Emit started/completed/failed counters and a duration distribution for one job run.

    job.started / job.completed / job.failed (counters, tag: job)
    job.duration_ms (distribution, tag: job)
    """
    sentry_metrics.count("job.started", 1, attributes={"job": job_name})
    start = time.monotonic()
    failed = False
    try:
        yield
    except Exception:
        failed = True
        raise
    finally:
        sentry_metrics.count(
            "job.failed" if failed else "job.completed", 1, attributes={"job": job_name}
        )
        sentry_metrics.distribution(
            "job.duration_ms",
            (time.monotonic() - start) * 1000,
            unit="millisecond",
            attributes={"job": job_name},
        )
