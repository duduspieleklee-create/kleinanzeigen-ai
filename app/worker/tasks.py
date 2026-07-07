import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
import sentry_sdk
import sentry_sdk.metrics as sentry_metrics
from bs4 import BeautifulSoup
from sqlalchemy import or_, func

from app.api.config import settings
from app.shared.database import SessionLocal
from app.shared.email_notifications import (
    create_new_results_email,
    email_configured,
    send_email_notification,
)
from app.shared.metrics import track_job
from app.shared.models import AdminSearch, PushSubscription, ScrapeTask, ScrapeResult, User
from app.shared.smart_alerts import build_smart_summary
from app.shared.plans import ensure_weekly_credits, plan_config
from app.shared.pricing import deal_badge, median_price, parse_price, calculate_trust_score
from app.shared.proxy import proxies_for_requests
from app.shared.token_tracking import log_token_usage
from app.shared.url_builder import build_kleinanzeigen_url
from app.worker.celery_app import celery_app
from app.worker.seller_scraper import extract_seller_info

logger = logging.getLogger("kleinanzeigen-ai")


def extract_seller_info_from_listing(url: str) -> Optional[dict]:
    """Fetch listing detail page and extract seller information.
    
    This is a wrapper around seller_scraper that handles the HTTP request
    and returns seller data or None if extraction fails.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=6)
        response.raise_for_status()
        return extract_seller_info(response.text)
    except Exception as e:
        logger.debug(f"Failed to extract seller info from {url}: {e}")
        return None


def _describe_scrape_error(exc: Exception) -> str:
    """Translate a scrape exception into a short, user-facing explanation.

    Full tracebacks and exception details go to Sentry (see the except block
    in scrape_kleinanzeigen); this is only what a non-technical user sees
    next to their search on the dashboard.
    """
    if isinstance(exc, requests.exceptions.Timeout):
        return "kleinanzeigen.de did not respond in time. This usually clears up on the next scheduled run."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Could not connect to kleinanzeigen.de (network or proxy issue)."
    if isinstance(exc, requests.exceptions.HTTPError):
        code = exc.response.status_code if exc.response is not None else None
        if code in (403, 429):
            return f"kleinanzeigen.de temporarily blocked this request (HTTP {code}), likely rate-limiting."
        if code and code >= 500:
            return f"kleinanzeigen.de's server had an error (HTTP {code})."
        return f"kleinanzeigen.de returned an unexpected response (HTTP {code})." if code else \
            "kleinanzeigen.de returned an unexpected response."
    if isinstance(exc, requests.exceptions.RequestException):
        return "A network error occurred while reaching kleinanzeigen.de."
    return "An unexpected error occurred while running this search. Our team has been notified."


def _in_quiet_hours(quiet_start: str | None, quiet_end: str | None) -> bool:
    """True if the current UTC time falls in the user's quiet-hours window.

    Both bounds are "HH:MM" strings. The window may wrap midnight
    (e.g. 22:00-08:00), so we can't just compare start < end.
    """
    if not quiet_start or not quiet_end:
        return False
    now = datetime.now(timezone.utc).strftime("%H:%M")
    if quiet_start <= quiet_end:
        return quiet_start <= now < quiet_end
    return now >= quiet_start or now < quiet_end


def _send_push_notifications(
    db, user_id: int, result_count: int, keywords: str, highlight: str = None,
    location: str = None, price_range: str = None, best_price: str = None,
    image_url: str = None, task_id: int = None, bypass_preferences: bool = False
) -> dict:
    """Send a web push to every subscription of a user.

    Returns a summary so callers (e.g. the admin test button) can report what
    actually happened instead of failing silently:
    {configured, total, sent, failed, removed, errors}.

    Honors the user's notification preferences (push toggle, deals-only mode,
    quiet hours) set on /settings, unless bypass_preferences is set — used by
    the explicit "send test notification" button, which should fire
    regardless of the current toggle state.
    """
    summary = {
        "configured": True,
        "total": 0,
        "sent": 0,
        "failed": 0,
        "removed": 0,
        "errors": [],
    }

    if not settings.vapid_private_key or not settings.vapid_public_key:
        summary["configured"] = False
        summary["errors"].append("VAPID keys are not configured on the server.")
        return summary
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        summary["configured"] = False
        summary["errors"].append("pywebpush is not installed.")
        return summary

    if not bypass_preferences:
        user = db.query(User).filter(User.id == user_id).first()
        if user and not user.push_notifications_enabled:
            summary["errors"].append("User has disabled push notifications.")
            return summary
        if user and user.deals_only_enabled and not highlight:
            summary["errors"].append("User only wants deal-highlight notifications.")
            return summary
        if user and _in_quiet_hours(user.quiet_start, user.quiet_end):
            summary["errors"].append("Current time is within the user's quiet hours.")
            return summary

    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    summary["total"] = len(subs)
    if not subs:
        return summary

    # Build compelling notification title and body
    if highlight:
        # Highlight the best deal
        title = "🎯 Great Deal Found!"
        body = highlight
    else:
        # Multiple new listings
        title = f"✨ {result_count} new listing{'s' if result_count != 1 else ''}"
        body = f"{keywords}"

    # Build rich notification payload with actions and metadata
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": "/static/icon-192x192.png",
        "badge": "/static/badge-72x72.png",
        "tag": f"search-{task_id}",  # Group by search to avoid notification spam
        "requireInteraction": True,  # Keep notification visible
        "data": {
            "searchKeywords": keywords,
            "resultCount": result_count,
            "location": location or "All locations",
            "priceRange": price_range or "Any price",
            "bestPrice": best_price,
            "taskId": task_id,
            "url": "/dashboard#tab-my-results",
        },
        "actions": [
            {
                "action": "view-results",
                "title": "View Results",
                "icon": "/static/icon-view.png"
            },
            {
                "action": "open-search",
                "title": "Open Search",
                "icon": "/static/icon-search.png"
            },
            {
                "action": "dismiss",
                "title": "Dismiss"
            }
        ]
    })
    # VAPID_PRIVATE_KEY must be the raw base64url-encoded 32-byte EC scalar
    # (paired with the raw public key the browser uses), not PEM. pywebpush's
    # webpush() loads string keys via Vapid.from_string(), which only strips
    # newlines before base64url-decoding — it does not strip PEM's
    # "-----BEGIN/END-----" armor, so a PEM string corrupts into garbage DER
    # and fails with "Could not deserialize key data ... ASN.1 ...".
    private_key = "".join((settings.vapid_private_key or "").split())

    # py_vapid requires the "sub" claim to be a mailto:/https: URI. Accept a
    # bare email in VAPID_EMAIL and normalise it, so this common misconfig
    # doesn't silently break every push.
    sub_claim = (settings.vapid_email or "").strip()
    if sub_claim and not sub_claim.startswith(("mailto:", "http://", "https://")):
        sub_claim = f"mailto:{sub_claim}"
    if not sub_claim:
        sub_claim = "mailto:admin@example.com"

    stale = []
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                # pywebpush mutates the claims dict (adds aud/exp), so pass a
                # fresh copy per subscription.
                vapid_claims={"sub": sub_claim},
            )
            summary["sent"] += 1
        except WebPushException as e:
            # 404/410 means the subscription has expired — clean it up
            if e.response is not None and e.response.status_code in (404, 410):
                stale.append(sub.id)
                summary["removed"] += 1
            else:
                summary["failed"] += 1
                summary["errors"].append(str(e))
                logger.warning(f"Push failed for sub {sub.id}: {e}")
        except Exception as e:
            summary["failed"] += 1
            summary["errors"].append(str(e))
            logger.warning(f"Push failed for sub {sub.id}: {e}")

    if stale:
        db.query(PushSubscription).filter(PushSubscription.id.in_(stale)).delete(synchronize_session=False)
        db.commit()

    if summary["sent"]:
        sentry_metrics.count("notifications.push_sent", summary["sent"])
    if summary["failed"]:
        sentry_metrics.count("notifications.push_failed", summary["failed"])

    return summary


def _send_email_notifications(
    db, user_id: int, result_count: int, keywords: str,
    new_results: list, highlight: str = None, bypass_preferences: bool = False
) -> dict:
    """Email a user about genuinely-new listings.

    Fires at the same point as _send_push_notifications and honors the same
    preferences (email toggle, deals-only mode, quiet hours), unless
    bypass_preferences is set.
    """
    summary = {"configured": True, "sent": False, "errors": []}

    if not email_configured():
        summary["configured"] = False
        summary["errors"].append("RESEND_API_KEY is not configured on the server.")
        return summary

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.email:
        summary["errors"].append("No user/email on file.")
        return summary

    if not bypass_preferences:
        if not user.email_notifications_enabled:
            summary["errors"].append("User has disabled email notifications.")
            return summary
        if user.deals_only_enabled and not highlight:
            summary["errors"].append("User only wants deal-highlight notifications.")
            return summary
        if _in_quiet_hours(user.quiet_start, user.quiet_end):
            summary["errors"].append("Current time is within the user's quiet hours.")
            return summary

    # Trust scores are a Core/Pro feature — leave them off the email for
    # Basic owners, same gating as the dashboard and the push payload.
    show_trust = bool(user.is_admin or plan_config(user.plan).get("trust_scores"))
    results_payload = [
        {
            "title": r.title,
            "price": r.price,
            "location": r.location,
            "url": r.url,
            "trust_score": r.trust_score if show_trust else None,
            "show_trust": show_trust,
        }
        for r in new_results
    ]

    notification = create_new_results_email(
        user_email=user.email,
        keywords=keywords,
        result_count=result_count,
        results=results_payload,
        highlight=highlight,
    )
    summary["sent"] = send_email_notification(notification)
    if summary["sent"]:
        sentry_metrics.count("notifications.email_sent", 1)
    else:
        summary["errors"].append("Email send failed; see server logs.")
        sentry_metrics.count("notifications.email_failed", 1)
    return summary


def run_test_push(db, user_id: int) -> dict:
    """Send a one-off test push synchronously and return a result summary.

    Called directly from the admin endpoint (not via Celery) so the admin sees
    the real outcome immediately: whether it was sent, or the actual error if
    delivery failed. Reuses the exact same send path as real notifications.
    """
    return _send_push_notifications(
        db,
        user_id,
        result_count=0,
        keywords="",
        highlight="Test notification - push is working!",
        bypass_preferences=True,
    )


def _ensure_task(db, task_id: int | None, parameters: dict) -> tuple[int, object | None]:
    """
    Return (task_id, task_orm_object).

    - If task_id is supplied (API-triggered run): load and return the existing ScrapeTask.
    - If task_id is None (Beat-scheduled run): create a new ScrapeTask owned by the
      configured SYSTEM_USER_ID so that ScrapeResult FK constraints are always satisfied.
    """
    if task_id is not None:
        task = db.query(ScrapeTask).filter(ScrapeTask.id == task_id).first()
        return task_id, task

    # Beat-scheduled run — create an internal task record
    task = ScrapeTask(
        user_id=settings.system_user_id,
        url="pending",
        parameters=parameters,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info(f"Beat-scheduled run: created ScrapeTask id={task.id}")
    return task.id, task


@celery_app.task(name="scrape.kleinanzeigen", bind=True, max_retries=2)
def scrape_kleinanzeigen(self, parameters: dict, task_id: int | None = None):
    """
    Celery task that scrapes kleinanzeigen.de, saves results, then self-re-schedules
    when the caller supplied an interval_seconds in parameters.

    task_id is supplied by the API for user-initiated scrapes.
    When called by Celery Beat (no task_id), a ScrapeTask is created automatically
    under settings.system_user_id so that ScrapeResult FK constraints are satisfied.
    """
    db = SessionLocal()
    resolved_task_id = None
    task = None
    job_start = time.monotonic()
    sentry_metrics.count("job.started", 1, attributes={"job": "scrape.kleinanzeigen"})
    try:
        resolved_task_id, task = _ensure_task(db, task_id, parameters)

        # Guard: if the user cancelled before this queued run started, bail out
        # without touching the status so the "cancelled" state is preserved.
        if task and task.status == "cancelled":
            logger.info(
                f"Task {resolved_task_id} was cancelled before this queued run started — aborting"
            )
            return

        # Mark task as running
        if task:
            task.status = "running"
            db.commit()

        # Build scrape URL (strip scheduling key before passing to url_builder)
        scrape_params = {k: v for k, v in parameters.items() if k != "interval_seconds"}
        url = build_kleinanzeigen_url(**scrape_params)
        logger.info(f"Starting scrape for: {url}")

        if task:
            task.url = url
            db.commit()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # Route through a rotating proxy when the admin has enabled the feature
        # and at least one active proxy exists; otherwise a direct request.
        proxies = proxies_for_requests(db)
        if proxies:
            logger.info(f"Using rotating proxy for scrape (task_id={resolved_task_id})")

        response = None
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=20, proxies=proxies)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                if attempt == 2:
                    raise
                logger.warning(f"Scrape request failed (attempt {attempt + 1}): {exc}")
                time.sleep(1)

        soup = BeautifulSoup(response.text, "lxml")

        listings = (
            soup.find_all("article", class_="aditem") or
            soup.select("article.aditem") or
            soup.find_all("div", {"data-adid": True})
        )

        # ── Credit metering: 1 credit per NEW listing saved ──────────────────
        # Admin accounts and the internal system user are exempt. When the
        # owner runs out of credits, saving stops for this run but the search
        # stays scheduled — it resumes finding listings after the weekly
        # refill or an upgrade.
        owner = None
        metered = False
        if task and task.user_id:
            owner = db.query(User).filter(User.id == task.user_id).first()
        if owner and not owner.is_admin and owner.id != settings.system_user_id:
            ensure_weekly_credits(db, owner)
            metered = True

        # The first successful run of a search is a free baseline: everything
        # it finds is "new" by definition, so it seeds the dedup set without
        # charging credits and without sending a push. Charged runs start with
        # the second check (baseline_done flips on success, below).
        is_baseline = bool(task is not None and not task.baseline_done)

        # Dedupe against listings already saved for this (recurring) task so we
        # only store — and only notify about — genuinely new listings. Keyed by
        # listing URL, falling back to title|price|location when a URL is absent.
        existing = (
            db.query(
                ScrapeResult.url,
                ScrapeResult.title,
                ScrapeResult.price,
                ScrapeResult.location,
            )
            .filter(ScrapeResult.task_id == resolved_task_id)
            .all()
        )
        seen_keys = {(r.url or f"{r.title}|{r.price}|{r.location}") for r in existing}

        new_count = 0
        new_results = []

        for item in listings[:25]:
            try:
                title_tag = item.find("h2") or item.find("a", class_="ellipsis")
                title = title_tag.get_text(strip=True) if title_tag else "No title"

                # kleinanzeigen renamed the price element; keep old class as fallback
                # for any cached/legacy HTML that may still use the old name.
                price_tag = (
                    item.find("p", class_="aditem-main--middle--price-shipping--price")
                    or item.find("p", class_="aditem-main--middle--price")
                )
                price = price_tag.get_text(strip=True) if price_tag else "N/A"

                location_tag = item.find("div", class_="aditem-main--top--left")
                location = location_tag.get_text(strip=True) if location_tag else "N/A"

                link_tag = item.find("a", href=True)
                item_url = None
                if link_tag:
                    href = link_tag["href"]
                    item_url = (
                        f"https://www.kleinanzeigen.de{href}"
                        if href.startswith("/")
                        else href
                    )

                # Listing thumbnail — kleinanzeigen lazy-loads images, so the
                # real URL may live in data-imgsrc/data-src/srcset while src holds
                # a data: placeholder. Take the first real (non-data:) URL.
                image_url = None
                img_tag = item.find("img")
                if img_tag:
                    candidates = [
                        img_tag.get("src"),
                        img_tag.get("data-imgsrc"),
                        img_tag.get("data-src"),
                    ]
                    image_url = next(
                        (u for u in candidates if u and not u.startswith("data:")), None
                    )
                    if not image_url and img_tag.get("srcset"):
                        image_url = img_tag["srcset"].split()[0]

                desc_tag = item.find("p", class_="aditem-main--middle--description")
                description = desc_tag.get_text(strip=True) if desc_tag else None

                key = item_url or f"{title}|{price}|{location}"
                if key in seen_keys:
                    continue  # already seen on a previous run — not new
                if metered and not is_baseline:
                    # Spend 1 credit atomically BEFORE saving. The conditional
                    # UPDATE (credits > 0) runs inside the same transaction as
                    # the result inserts: the first decrement takes a row lock
                    # on the user, so concurrent tasks for the same user are
                    # serialized and can never spend more credits than exist.
                    # Rollback on failure undoes both results and decrements.
                    spent = (
                        db.query(User)
                        .filter(User.id == owner.id, User.credits > 0)
                        .update(
                            {User.credits: User.credits - 1},
                            synchronize_session=False,
                        )
                    )
                    if not spent:
                        logger.info(
                            f"Credits exhausted for user {owner.id} "
                            f"(task_id={resolved_task_id}) — skipping remaining new listings"
                        )
                        break
                seen_keys.add(key)

                # Extract seller information from the listing detail page
                seller_info = None
                if item_url:
                    try:
                        seller_info = extract_seller_info_from_listing(item_url)
                    except Exception as e:
                        logger.debug(f"Could not extract seller info from {item_url}: {e}")

                # Calculate trust score if seller info is available
                trust_score = None
                if seller_info:
                    trust_score = calculate_trust_score(
                        seller_info.get("seller_rating"),
                        seller_info.get("seller_badges"),
                        seller_info.get("seller_active_since"),
                        seller_info.get("seller_listings_count")
                    )

                result = ScrapeResult(
                    task_id=resolved_task_id,
                    title=title[:255],
                    price=price[:50],
                    price_value=parse_price(price),
                    location=location[:100],
                    url=item_url,
                    image_url=image_url,
                    description=description,
                    seller_id=seller_info.get("seller_id") if seller_info else None,
                    seller_name=seller_info.get("seller_name") if seller_info else None,
                    seller_rating=seller_info.get("seller_rating") if seller_info else None,
                    seller_badges=seller_info.get("seller_badges") if seller_info else None,
                    seller_active_since=seller_info.get("seller_active_since") if seller_info else None,
                    seller_listings_count=seller_info.get("seller_listings_count") if seller_info else None,
                    trust_score=trust_score,
                )
                db.add(result)
                new_results.append(result)
                new_count += 1

            except Exception as e:
                logger.warning(f"Failed to parse listing: {e}")
                continue

        db.commit()

        # If the duplicate unique-index was missed by in-memory dedupe, drop
        # any now-duplicate rows surfaced by the DB constraint without failing
        # the whole task.
        dupes = (
            db.query(ScrapeResult.url, func.min(ScrapeResult.id).label("keep_id"))
            .filter(ScrapeResult.task_id == resolved_task_id, ScrapeResult.url.isnot(None))
            .group_by(ScrapeResult.url)
            .having(func.count(ScrapeResult.id) > 1)
            .all()
        )
        for dup_url, keep_id in dupes:
            db.query(ScrapeResult).filter(
                ScrapeResult.task_id == resolved_task_id,
                ScrapeResult.url == dup_url,
                ScrapeResult.id != keep_id,
            ).delete(synchronize_session=False)
        if dupes:
            db.commit()

        # Track token usage for this run
        # Estimate: ~1 token per result (for seller data extraction + processing)
        if task and new_count > 0:
            log_token_usage(db, user_id=task.user_id, task_id=resolved_task_id, tokens=new_count)
            logger.info(f"Tracked {new_count} tokens for task {resolved_task_id}")

        if task:
            # Re-fetch to respect a cancellation that arrived while the task was running.
            task = db.query(ScrapeTask).filter(ScrapeTask.id == resolved_task_id).first()
            if task:
                if task.status != "cancelled":
                    task.status = "completed"
                    task.error_message = None
                # A successful run consumed the free baseline (a failed run
                # keeps it — nothing was charged, so the retry is still free).
                task.baseline_done = True
                db.commit()

        logger.info(f"Saved {new_count} new result(s) from {url}")

        # ── Push notifications — only for genuinely new listings ────────────
        # The baseline run is silent: a "25 new listings" push right after
        # setting up a search is noise, and none of it is genuinely new.
        if task and new_count > 0 and not is_baseline:
            # Highlight the best below-market deal among the new listings.
            # Deal badges are a Core/Pro feature — Basic owners get the plain
            # "N new listing(s)" body.
            highlight = None
            best_price_str = None
            best_image_url = None
            best_title = None
            if owner and (owner.is_admin or plan_config(owner.plan).get("deal_badges")):
                all_values = [
                    v for (v,) in db.query(ScrapeResult.price_value)
                    .filter(ScrapeResult.task_id == resolved_task_id).all()
                ]
                med = median_price(all_values)
                best = None
                for r in new_results:
                    badge = deal_badge(r.price_value, med)
                    if badge and badge["cls"] == "deal-great":
                        if best is None or r.price_value < best[0]:
                            best = (r.price_value, r.title, badge["label"], r.image_url)
                if best:
                    highlight = f"🔥 {best[2]}: {best[1]}"
                    best_price_str = f"€{best[0]}"
                    best_image_url = best[3]
                    best_title = best[1]

            # Smart Alerts: one deterministic sentence for the dashboard, reusing
            # the deal data computed above (so it's plan-gated for free — Basic
            # owners never had a best_title/best_price_str set).
            task.last_summary = build_smart_summary(
                new_count,
                parameters.get("keywords", ""),
                deal_title=best_title,
                best_price_str=best_price_str,
            )
            db.commit()

            location = parameters.get("location", "All locations")
            price_min = parameters.get("price_min")
            price_max = parameters.get("price_max")
            price_range = None
            if price_min or price_max:
                price_range = f"€{price_min or '0'}–€{price_max or '∞'}"

            _send_push_notifications(
                db,
                user_id=task.user_id,
                result_count=new_count,
                keywords=parameters.get("keywords", "your search"),
                highlight=highlight,
                location=location,
                price_range=price_range,
                best_price=best_price_str,
                image_url=best_image_url,
                task_id=resolved_task_id,
            )
            _send_email_notifications(
                db,
                user_id=task.user_id,
                result_count=new_count,
                keywords=parameters.get("keywords", "your search"),
                new_results=new_results,
                highlight=highlight,
            )
        # ───────────────────────────────────────────────────────────────────

        # ── Self-re-scheduling ──────────────────────────────────────────────
        # Only re-queue if the task wasn't cancelled between start and now.
        # Read the schedule from the task's CURRENT parameters in the DB, not
        # the in-flight copy: a plan-downgrade sweep (plans.enforce_plan_limits)
        # may have raised interval_seconds since this run was queued. As a
        # second line of defense, clamp the interval to the owner's current
        # plan floor for metered users so a missed webhook can't leave a
        # cancelled subscriber running at paid-tier speed.
        if task and task.status == "completed":
            next_params = dict(task.parameters or parameters)
            try:
                interval = int(next_params.get("interval_seconds") or 0)
            except (TypeError, ValueError):
                interval = 0
            if interval:
                if metered and owner:
                    db.refresh(owner)  # plan may have changed mid-run
                    floor = plan_config(owner.plan)["min_interval_seconds"]
                    if interval < floor:
                        logger.info(
                            f"Raising interval {interval}s -> plan floor {floor}s "
                            f"for user {owner.id} (task_id={resolved_task_id})"
                        )
                        interval = floor
                        next_params["interval_seconds"] = floor
                        task.parameters = next_params
                        db.commit()
                logger.info(f"Re-scheduling scrape in {interval}s (task_id={resolved_task_id})")
                scrape_kleinanzeigen.apply_async(
                    args=[next_params, resolved_task_id],
                    countdown=interval,
                )
        # ───────────────────────────────────────────────────────────────────

        sentry_metrics.count("job.completed", 1, attributes={"job": "scrape.kleinanzeigen"})
        sentry_metrics.distribution(
            "job.duration_ms",
            (time.monotonic() - job_start) * 1000,
            unit="millisecond",
            attributes={"job": "scrape.kleinanzeigen"},
        )
        sentry_metrics.count("scrape.listings_found", new_count, attributes={"baseline": is_baseline})

        return {
            "status": "success",
            "results_saved": new_count,
            "url": url,
        }

    except Exception as exc:
        # resolved_task_id covers both API-triggered and Beat-triggered paths;
        # fall back to task_id only if _ensure_task itself raised before setting it.
        update_id = resolved_task_id if resolved_task_id is not None else task_id
        attempt = self.request.retries + 1
        error_detail = _describe_scrape_error(exc)

        logger.error(
            f"Scraping failed (task_id={update_id}, attempt={attempt}): {exc}",
            exc_info=True,
        )
        db.rollback()

        # Full context for debugging, independent of the short message shown to users.
        sentry_sdk.capture_exception(
            exc,
            tags={"task_id": str(update_id), "attempt": str(attempt)},
            contexts={
                "scrape": {
                    "task_id": update_id,
                    "attempt": attempt,
                    "keywords": parameters.get("keywords"),
                    "location": parameters.get("location"),
                    "url": locals().get("url"),
                }
            },
        )
        sentry_metrics.count("job.failed", 1, attributes={"job": "scrape.kleinanzeigen"})
        sentry_metrics.distribution(
            "job.duration_ms",
            (time.monotonic() - job_start) * 1000,
            unit="millisecond",
            attributes={"job": "scrape.kleinanzeigen"},
        )

        if update_id is not None:
            failed_task = db.query(ScrapeTask).filter(ScrapeTask.id == update_id).first()
            if failed_task:
                try:
                    failed_task.status = "failed"
                    failed_task.error_message = error_detail
                    db.commit()
                except Exception:
                    logger.exception(
                        "Could not mark scrape task %s as failed after error", update_id
                    )
                    db.rollback()
        retries = self.request.retries
        countdown = min(2 ** retries * 60, 600)
        logger.info(f"Retrying in {countdown}s (attempt {retries + 1})")
        raise self.retry(exc=exc, countdown=countdown)

    finally:
        db.close()


@celery_app.task(name="scrape.dispatch_admin_searches", bind=False)
def dispatch_admin_searches():
    """Dispatches scrape tasks for all due admin-configured searches."""
    db = SessionLocal()
    try:
        with track_job("scrape.dispatch_admin_searches"):
            now = datetime.now(timezone.utc)
            searches = (
                db.query(AdminSearch)
                .filter(
                    AdminSearch.is_active.is_(True),
                    or_(AdminSearch.next_run_at.is_(None), AdminSearch.next_run_at <= now),
                )
                .all()
            )
            for search in searches:
                parameters = {k: v for k, v in {
                    "keywords": search.keywords,
                    "category": search.category,
                    "location": search.location,
                    "location_id": search.location_id,
                    "price_min": search.price_min,
                    "price_max": search.price_max,
                    "radius": search.radius,
                    "ad_type": search.ad_type,
                    "poster_type": search.poster_type,
                    "condition": search.condition,
                    "shipping": search.shipping,
                }.items() if v is not None}
                scrape_kleinanzeigen.apply_async(args=[parameters])
                search.last_run_at = now
                search.next_run_at = now + timedelta(minutes=search.interval_minutes)
                logger.info(f"Dispatched admin search id={search.id} keywords={search.keywords}")
            if searches:
                db.commit()
            sentry_metrics.count("admin_search.dispatched", len(searches))
    except Exception as e:
        logger.error(f"dispatch_admin_searches failed: {e}")
        db.rollback()
    finally:
        db.close()
