"""Archival task for removing old search results.

Results older than 14 days are automatically removed from the dashboard,
unless they have been marked as favorites or belong to the system user
(admin-owned reference-data searches — see app/shared/models.py::AdminSearch
and CLAUDE.md's SYSTEM_USER_ID note). Those accumulate indefinitely by design:
they're market-reference data, not per-user search results.

This task is meant to be scheduled via Celery Beat (e.g., daily at midnight).
"""
import logging
from datetime import datetime, timedelta, timezone

import sentry_sdk.metrics as sentry_metrics
from sqlalchemy import and_

from app.api.config import settings
from app.shared.database import SessionLocal
from app.shared.metrics import track_job
from app.shared.models import ScrapeResult, ScrapeTask
from app.worker.celery_app import celery_app

logger = logging.getLogger("kleinanzeigen-ai")

# Results older than this many days are archived (unless favorited)
ARCHIVAL_THRESHOLD_DAYS = 14


@celery_app.task(name="archival.cleanup_old_results")
def cleanup_old_results():
    """Remove search results older than ARCHIVAL_THRESHOLD_DAYS.

    Favorited results and system-user (admin reference-data) results are
    preserved indefinitely.

    This task:
    1. Calculates the cutoff date (today - 14 days)
    2. Finds all non-favorited, non-system-user results older than the cutoff
    3. Deletes them
    4. Logs the count
    """
    db = SessionLocal()
    try:
        with track_job("archival.cleanup_old_results"):
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=ARCHIVAL_THRESHOLD_DAYS)

            # Find all results older than the cutoff that are NOT in favorites
            # and NOT owned by the system user (admin reference-data searches
            # are kept indefinitely — see module docstring).
            old_results = (
                db.query(ScrapeResult)
                .join(ScrapeTask, ScrapeResult.task_id == ScrapeTask.id)
                .filter(
                    and_(
                        ScrapeResult.created_at < cutoff_date,
                        ~ScrapeResult.favorited_by.any(),  # NOT favorited
                        ScrapeTask.user_id != settings.system_user_id,
                    )
                )
                .all()
            )

            result_ids = [r.id for r in old_results]
            count = len(result_ids)

            if count > 0:
                # Delete the results
                db.query(ScrapeResult).filter(ScrapeResult.id.in_(result_ids)).delete(
                    synchronize_session=False
                )
                db.commit()
                logger.info(f"Archived {count} old search results (older than {ARCHIVAL_THRESHOLD_DAYS} days)")
            else:
                logger.info("No old results to archive")

            sentry_metrics.count("archival.results_purged", count)

            return {
                "archived_count": count,
                "cutoff_date": cutoff_date.isoformat(),
            }

    except Exception as e:
        logger.error(f"Error during result archival: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@celery_app.task(name="archival.cleanup_old_token_usage")
def cleanup_old_token_usage():
    """Remove token usage records older than 90 days.
    
    Token usage is kept for analytics, but old records can be archived
    to keep the database lean.
    """
    from app.shared.models import TokenUsage
    
    db = SessionLocal()
    try:
        with track_job("archival.cleanup_old_token_usage"):
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)

            old_records = db.query(TokenUsage).filter(
                TokenUsage.date < cutoff_date.date()
            ).all()

            count = len(old_records)

            if count > 0:
                db.query(TokenUsage).filter(TokenUsage.date < cutoff_date.date()).delete(
                    synchronize_session=False
                )
                db.commit()
                logger.info(f"Archived {count} old token usage records (older than 90 days)")
            else:
                logger.info("No old token usage records to archive")

            sentry_metrics.count("archival.token_usage_purged", count)

            return {
                "archived_count": count,
                "cutoff_date": cutoff_date.isoformat(),
            }

    except Exception as e:
        logger.error(f"Error during token usage archival: {e}")
        db.rollback()
        raise
    finally:
        db.close()
