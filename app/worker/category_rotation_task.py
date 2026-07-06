"""Rotates admin reference-data searches through every category over time.

Every ROTATION_INTERVAL_DAYS, replaces the currently active rotation-managed
AdminSearch rows (category, is_rotation_managed=True) with the next batch
from app/shared/category_rotation.py, wrapping back to the start once every
category has had a turn. Rotation state (current batch index + when it
started) lives in SystemSetting, the existing global key/value store (see
app/shared/proxy.py for the other user of that pattern).

Fixed filters for every rotation-managed search, per the 2026-07-06 product
decision: nationwide (no location), private sellers only, no keyword
restriction — these are broad market-reference samples, not user searches.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.shared.category_rotation import CATEGORY_BATCHES
from app.shared.database import SessionLocal
from app.shared.metrics import track_job
from app.shared.models import AdminSearch, SystemSetting
from app.worker.celery_app import celery_app

logger = logging.getLogger("kleinanzeigen-ai")

ROTATION_INTERVAL_DAYS = 3.5
_BATCH_INDEX_KEY = "admin_search_rotation_batch_index"
_STARTED_AT_KEY = "admin_search_rotation_started_at"

# Hourly rather than the AdminSearch default of 30 min: these searches have
# no keyword filter and no pagination (see TODO.txt #10), so a nationwide
# category scan already fills its 25-listing cap most runs — checking more
# often just burns proxy/request budget without seeing further back.
_FIXED_PARAMS = {"poster_type": "privat", "interval_minutes": 60}


def _get_setting(db, key: str) -> str | None:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else None


def _set_setting(db, key: str, value: str) -> None:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


def _activate_batch(db, batch_index: int) -> None:
    batch_index = batch_index % len(CATEGORY_BATCHES)
    categories = CATEGORY_BATCHES[batch_index]

    # Rotation-managed rows are fully owned by this task — delete-and-recreate
    # rather than toggle is_active, so rows don't accumulate over a multi-
    # month cycle. Manually-added admin searches (is_rotation_managed=False)
    # are never touched here.
    db.query(AdminSearch).filter(AdminSearch.is_rotation_managed.is_(True)).delete(
        synchronize_session=False
    )
    for category in categories:
        db.add(AdminSearch(
            keywords=None,
            category=category,
            is_rotation_managed=True,
            **_FIXED_PARAMS,
        ))

    now = datetime.now(timezone.utc)
    _set_setting(db, _BATCH_INDEX_KEY, str(batch_index))
    _set_setting(db, _STARTED_AT_KEY, now.isoformat())
    db.commit()
    logger.info(f"Admin-search rotation: activated batch {batch_index} {categories}")


@celery_app.task(name="admin_search.rotate_categories")
def rotate_categories():
    """Advance to the next category batch once ROTATION_INTERVAL_DAYS has elapsed."""
    db = SessionLocal()
    try:
        with track_job("admin_search.rotate_categories"):
            started_at_raw = _get_setting(db, _STARTED_AT_KEY)
            batch_index_raw = _get_setting(db, _BATCH_INDEX_KEY)

            if started_at_raw is None or batch_index_raw is None:
                _activate_batch(db, 0)
                return

            started_at = datetime.fromisoformat(started_at_raw)
            elapsed = datetime.now(timezone.utc) - started_at
            if elapsed >= timedelta(days=ROTATION_INTERVAL_DAYS):
                _activate_batch(db, int(batch_index_raw) + 1)
            else:
                logger.debug(
                    f"Admin-search rotation: batch {batch_index_raw} still active "
                    f"({elapsed.days}d elapsed, rotates at {ROTATION_INTERVAL_DAYS}d)"
                )
    except Exception as e:
        logger.error(f"admin_search.rotate_categories failed: {e}")
        db.rollback()
    finally:
        db.close()
