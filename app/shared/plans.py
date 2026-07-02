"""Subscription plans and weekly credit management.

Plan model:
  - basic (free): 10 credits/week, up to 3 recurring searches, 60-minute interval and up
  - core:         50 credits/week, up to 10 recurring searches, 30-minute interval and up
  - pro:         150 credits/week, up to 25 recurring searches, instant
                 notifications (60-second checks)

One credit is consumed for each NEW listing a search finds (charged by the
worker when the result is saved). Starting a search is free, and its first
(baseline) check is free too — everything it finds is "new" by definition.
Re-checks that find nothing new cost nothing. Credits refill weekly (lazy:
the refill is applied on the next request after the reset time passes, so
no scheduled job is needed).

Deal badges (below/above-market classification) are a Core/Pro feature —
Basic users get plain results.
"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("kleinanzeigen-ai")

PLANS = {
    "basic": {
        "label": "Basic",
        "credits_per_week": 10,
        "max_active_searches": 3,
        "min_interval_seconds": 3600,
        "deal_badges": False,
    },
    "core": {
        "label": "Core",
        "credits_per_week": 50,
        "max_active_searches": 10,
        "min_interval_seconds": 1800,
        "deal_badges": True,
    },
    "pro": {
        "label": "Pro",
        "credits_per_week": 150,
        "max_active_searches": 25,
        # Marketed as "Instant Notifications" — checks run every 60 seconds.
        "min_interval_seconds": 60,
        "deal_badges": True,
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


def enforce_plan_limits(db, user) -> dict:
    """Downgrade sweep: bring the user's recurring searches back within plan.

    Plan limits are otherwise only checked when a search is CREATED, so a
    user who downgrades would keep paid-tier searches re-running forever.
    Called from the billing webhook after every plan change (harmless no-op
    on upgrades). Two effects:

      - recurring searches beyond the plan's slot cap are cancelled, newest
        first (the oldest searches keep their slots)
      - surviving recurring searches with an interval below the plan's floor
        get their interval raised to the floor; the worker re-reads
        parameters from the DB before each re-schedule, so this takes effect
        on the search's next run

    Admin accounts are exempt (mirrors creation-time enforcement). When
    anything changed, a human-readable summary is stored in user.plan_notice
    so the dashboard can tell the user what happened and why.
    Commits. Returns {"cancelled": n, "slowed": n}.
    """
    from app.shared.models import ScrapeTask

    if user is None or getattr(user, "is_admin", False):
        return {"cancelled": 0, "slowed": 0}

    cfg = plan_config(user.plan)
    cap = cfg["max_active_searches"]
    floor = cfg["min_interval_seconds"]

    # Newest first — matches the cancellation order below.
    tasks = (
        db.query(ScrapeTask)
        .filter(
            ScrapeTask.user_id == user.id,
            ScrapeTask.status.in_(("pending", "running", "completed")),
            ScrapeTask.parameters.op("->>")("interval_seconds").isnot(None),
        )
        .order_by(ScrapeTask.created_at.desc(), ScrapeTask.id.desc())
        .all()
    )

    excess_count = max(len(tasks) - cap, 0)
    excess, kept = tasks[:excess_count], tasks[excess_count:]

    cancelled = 0
    for t in excess:
        t.status = "cancelled"
        cancelled += 1

    slowed = 0
    for t in kept:
        params = dict(t.parameters or {})
        try:
            interval = int(params.get("interval_seconds") or 0)
        except (TypeError, ValueError):
            interval = 0
        if interval and interval < floor:
            params["interval_seconds"] = floor
            # Reassign (not mutate) so SQLAlchemy detects the JSON change.
            t.parameters = params
            slowed += 1

    if cancelled or slowed:
        minutes = floor // 60
        bits = []
        if cancelled:
            bits.append(
                f"{cancelled} recurring search(es) were stopped because the "
                f"{cfg['label']} plan allows {cap} active recurring searches"
            )
        if slowed:
            bits.append(
                f"{slowed} search(es) were slowed down to the {cfg['label']} "
                f"plan minimum of {minutes} minutes between checks"
            )
        user.plan_notice = (
            "Your plan changed: " + "; ".join(bits) + ". Upgrade at /billing to restore them."
        )
        logger.info(
            f"Plan sweep for user {user.id} ({user.plan}): "
            f"cancelled={cancelled} slowed={slowed}"
        )
        db.commit()

    return {"cancelled": cancelled, "slowed": slowed}
