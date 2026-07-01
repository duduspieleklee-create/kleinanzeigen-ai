"""Free/premium entitlements + welcome-task tracking.

Premium is earned once by completing every welcome task; it lasts
`settings.premium_days` days and unlocks a higher daily search limit and
faster (sub-hourly) intervals. This module is the single source of truth,
used by the API routes and the dashboard context.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.shared.models import User, WelcomeTask

# The tasks a user must complete to earn premium. Key/value storage means
# adding another (e.g. "connect_telegram") needs no migration.
REQUIRED_TASK_KEYS = [
    "first_search",
    "enable_notifications",
    "install_pwa",
    "leave_review",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime):
    """Treat a naive datetime (e.g. loaded from SQLite) as UTC so comparisons
    against an aware now() don't raise."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def is_admin(user: User) -> bool:
    return bool(user) and user.daily_limit == 0


def is_premium(user: User) -> bool:
    if not user or user.premium_until is None:
        return False
    return _aware(user.premium_until) > _now()


def is_privileged(user: User) -> bool:
    """Admin or currently-premium — bypasses the free-tier interval floor."""
    return is_admin(user) or is_premium(user)


def premium_days_left(user: User) -> int:
    if not is_premium(user):
        return 0
    return max(0, (_aware(user.premium_until) - _now()).days + 1)


def effective_daily_limit(user: User, settings) -> int:
    """0 == unlimited (admin). Premium users get the higher cap."""
    if is_admin(user):
        return 0
    if is_premium(user):
        return settings.premium_daily_limit
    return user.daily_limit


def min_interval_seconds(user: User, settings) -> int:
    """Lowest interval a user may pick. Dev has no floor."""
    if settings.environment == "dev":
        return 0
    if is_privileged(user):
        return settings.premium_min_interval_seconds
    return settings.free_min_interval_seconds


def completed_task_keys(db: Session, user_id: int) -> set:
    rows = db.query(WelcomeTask.task_key).filter(WelcomeTask.user_id == user_id).all()
    return {k for (k,) in rows}


def grant_premium_if_complete(db: Session, user: User) -> bool:
    """Grant the one-time 3-day premium once every required task is done.

    Returns True if premium was granted on this call.
    """
    from app.api.config import settings

    if user.welcome_completed_at is not None:
        return False  # already rewarded — not repeatable
    done = completed_task_keys(db, user.id)
    if not all(k in done for k in REQUIRED_TASK_KEYS):
        return False
    now = _now()
    user.welcome_completed_at = now
    user.premium_until = now + timedelta(days=settings.premium_days)
    db.commit()
    return True


def mark_task(db: Session, user_id: int, task_key: str) -> None:
    """Idempotently record a completed task, then grant premium if all done."""
    existing = (
        db.query(WelcomeTask)
        .filter(WelcomeTask.user_id == user_id, WelcomeTask.task_key == task_key)
        .first()
    )
    if existing is None:
        db.add(WelcomeTask(user_id=user_id, task_key=task_key))
        db.commit()
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None:
        grant_premium_if_complete(db, user)
