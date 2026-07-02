"""Subscription plans and weekly credit management.

Plan model:
  - basic (free): 10 credits/week, up to 3 recurring searches, 60-minute interval and up
  - core:         50 credits/week, up to 10 recurring searches, 30-minute interval and up
  - pro:         150 credits/week, up to 25 recurring searches, all intervals

One credit is consumed each time a user starts a new search. Recurring re-runs
of an existing search do NOT consume credits. Credits refill weekly (lazy: the
refill is applied on the next request after the reset time passes, so no
scheduled job is needed).
"""
from datetime import datetime, timedelta, timezone

PLANS = {
    "basic": {
        "label": "Basic",
        "credits_per_week": 10,
        "max_active_searches": 3,
        "min_interval_seconds": 3600,
    },
    "core": {
        "label": "Core",
        "credits_per_week": 50,
        "max_active_searches": 10,
        "min_interval_seconds": 1800,
    },
    "pro": {
        "label": "Pro",
        "credits_per_week": 150,
        "max_active_searches": 25,
        "min_interval_seconds": 300,
    },
}

DEFAULT_PLAN = "basic"
PAID_PLANS = ("core", "pro")


def plan_config(plan: str | None) -> dict:
    """Return the config dict for a plan name, falling back to basic."""
    return PLANS.get(plan or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])


def ensure_weekly_credits(db, user) -> None:
    """Lazily refill the user's weekly credits when the reset time has passed.

    Commits when a refill happens; otherwise leaves the session untouched.
    """
    now = datetime.now(timezone.utc)
    if user.credits_reset_at is None or now >= user.credits_reset_at:
        cfg = plan_config(user.plan)
        user.credits = cfg["credits_per_week"]
        user.credits_reset_at = now + timedelta(days=7)
        db.commit()
        db.refresh(user)


def grant_plan(db, user, plan: str) -> None:
    """Switch the user to a plan and grant its weekly credits immediately."""
    cfg = plan_config(plan)
    user.plan = plan
    user.credits = cfg["credits_per_week"]
    user.credits_reset_at = datetime.now(timezone.utc) + timedelta(days=7)
    db.commit()
