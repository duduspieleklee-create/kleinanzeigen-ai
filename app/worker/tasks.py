import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
import sentry_sdk
import sentry_sdk.metrics as sentry_metrics
from bs4 import BeautifulSoup
from sqlalchemy import or_, func, and_

from app.api.config import settings
from app.shared.database import SessionLocal
from app.shared.email_notifications import (
    create_new_results_email,
    email_configured,
    send_email_notification,
)
from app.shared.metrics import track_job
from app.shared.observability import track_job_decorator, metric
from app.shared.metrics_prom import job_duration
from app.shared.models import AdminSearch, NotificationDelivery, PushSubscription, ScrapeTask, ScrapeResult, User
from app.shared.smart_alerts import build_smart_summary, build_push_notification
from app.shared.category_profiles import NO_PRICE_PROFILES, resolve_profile
from app.shared.plans import ensure_weekly_credits, plan_config, consume_credit, auto_topup_credits
from app.shared.pricing import deal_badge, median_price, parse_price, calculate_trust_score
from app.shared.proxy import proxies_for_requests
from app.shared.token_tracking import log_token_usage
from app.shared.url_builder import build_kleinanzeigen_url
from app.shared.result_filters import passes_filters
from app.worker.celery_app import celery_app
from app.worker.seller_scraper import extract_seller_info

logger = logging.getLogger("kleinanzeigen-ai")

# Keys stored in a task's parameters JSON that are NOT kleinanzeigen URL params
# and must be stripped before build_kleinanzeigen_url(**scrape_params): the
# scheduling interval and the advanced result-filter lists (applied post-scrape,
# see app/shared/result_filters.py).
_NON_URL_PARAM_KEYS = frozenset(
    {"interval_seconds", "require_keywords", "exclude_keywords", "exclude_locations"}
)

_SELLER_PAGE_CACHE: dict[str, str] = {}


def _clear_seller_page_cache() -> None:
    _SELLER_PAGE_CACHE.clear()


def _get_cached_seller_page(url: str) -> Optional[str]:
    return _SELLER_PAGE_CACHE.get(url)


def _set_cached_seller_page(url: str, html: str) -> None:
    _SELLER_PAGE_CACHE[url] = html


def extract_seller_info_from_listing(url: str) -> Optional[dict]:
    """Fetch listing detail page and extract seller information.

    Reuses fetched HTML within one task runtime so repeated identical URLs do
    not hit kleinanzeigen.de multiple times. Failure mode is unchanged: log
    the error and return ``None``.
    """
    try:
        cached = _get_cached_seller_page(url)
        if cached is None:
            start = time.monotonic()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=6)
            response.raise_for_status()
            try:
                sentry_metrics.distribution(
                    "seller_extraction.request_duration_ms",
                    (time.monotonic() - start) * 1000,
                    unit="millisecond",
                )
                metric("seller_extraction.request", 1, cached="false")
            except Exception:
                pass
            html = response.text
            _set_cached_seller_page(url, html)
        else:
            html = cached
            try:
                metric("seller_extraction.request", 1, cached="true")
            except Exception:
                pass

        seller_info = extract_seller_info(html)
        if seller_info is None:
            try:
                sentry_metrics.count(
                    "seller_extraction.no_match",
                    1,
                    attributes={"url": str(url)[:120]},
                )
            except Exception:
                pass
        return seller_info
    except Exception as e:
        logger.debug(f"Failed to extract seller info from {url}: {e}")
        try:
            sentry_metrics.count(
                "seller_extraction.fetch_failed",
                1,
                attributes={"url": str(url)[:120]},
            )
        except Exception:
            pass
        return None


def extract_seller_info_from_listing_with_retry(
    url: str,
    max_attempts: int = 2,
    backoff_cap_s: int = 10,
) -> Optional[dict]:
    """Retry seller fetch within one task to improve hit rate under flaky DOM/timeouts."""
    for attempt in range(1, max_attempts + 1):
        info = extract_seller_info_from_listing(url)
        if info is not None:
            return info
        logger.debug(
            "Seller fetch returned no data (%s attempt %s/%s)",
            url,
            attempt,
            max_attempts,
        )
        if attempt < max_attempts:
            time.sleep(min(2 ** attempt, backoff_cap_s))
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


def _retry_with_backoff(policy: dict, op_name: str, send_fn):
    """Call `send_fn()` up to `policy['max_attempts']` times with backoff.

    Returns
    -------
    tuple(bool, Exception | None)
        Whether the send succeeded, and the last exception if not.
    """
    last = None
    for attempt in range(1, policy.get("max_attempts", 1) + 1):
        try:
            send_fn()
            return True, None
        except Exception as exc:  # pragma: no cover - behavior verified by source
            last = exc
            logger.warning("%s failed (attempt %s): %s", op_name, attempt, exc)
            if attempt < policy.get("max_attempts", 1):
                time.sleep(min(2 ** attempt, policy.get("backoff_cap", 60)))
    return False, last


def _save_notification_delivery(db, user_id: int, task_id: int | None, channel: str, summary: dict | None) -> None:
    summary = summary or {}
    raw_payload = dict(summary)
    if isinstance(raw_payload.get("errors"), list):
        raw_payload["errors"] = [str(e) for e in raw_payload["errors"] if e is not None]
    delivered = bool(summary.get("sent"))
    status = "sent" if delivered else "failed"
    last_error = "; ".join([str(e) for e in summary.get("errors", []) if e]) or None
    db.add(
        NotificationDelivery(
            user_id=user_id,
            task_id=task_id,
            channel=channel,
            status=status,
            attempt_count=int(summary.get("sent", 0)) + int(summary.get("failed", 0)) + int(summary.get("removed", 0)),
            last_error=last_error,
            sent_at=datetime.now(timezone.utc) if delivered else None,
            raw_payload=raw_payload,
        )
    )


@track_job_decorator("notifications.send_push")
def _send_push_notifications(
    db, user_id: int, result_count: int, keywords: str = "", highlight: str = None,
    location: str = None, price_range: str = None, best_price: str = None,
    image_url: str = None, task_id: int | None = None, bypass_preferences: bool = False,
    tag: str = None, title: str = None, deal: dict = None, cheapest_price: str = None,
    profile: str = "item", trust_score: int | None = None, sample_title: str | None = None,
) -> dict:
    """Send a web push to every subscription of a user.

    Returns a summary so callers (e.g. the admin test button) can report what
    actually happened instead of failing silently:
    {configured, total, sent, failed, removed, errors}.

    Honors the user's notification preferences (push toggle) set on /settings,
    unless bypass_preferences is set — used by the explicit "send test
    notification" button, which should fire regardless of the current toggle state.

    `tag` and `title` are optional overrides. Real notifications use tag =
    "search-{task_id}" to group repeats of the same search into one toast;
    tests pass a fresh per-click tag (e.g. a timestamp) so every click pops a
    distinct, visible notification instead of silently replacing the previous
    one. `title` lets tests label themselves clearly (e.g. "TEST").

    `profile`, `trust_score` and `sample_title` are forwarded to
    build_push_notification (see app/shared/smart_alerts.py) to shape the
    body for non-item searches (Jobs, Immobilien, Dienstleistungen, Tiere,
    Verschenken, Gesuche) — see app/shared/category_profiles.py for how a
    search's category maps to a profile. Both `trust_score` and
    `sample_title` are expected to already be plan-gated / count-gated by
    the caller; this function just displays what it's given.
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
    logger.info(f"Push: vapid_email={settings.vapid_email} private_key_len={len(settings.vapid_private_key)} public_key_len={len(settings.vapid_public_key)}")
    try:
        from pywebpush import webpush
    except ImportError:
        summary["configured"] = False
        summary["errors"].append("pywebpush is not installed.")
        return summary

    if not bypass_preferences:
        user = db.query(User).filter(User.id == user_id).first()
        if user and not user.push_notifications_enabled:
            summary["errors"].append("User has disabled push notifications.")
            return summary

    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    summary["total"] = len(subs)
    if not subs:
        return summary

    # Build compelling notification title and body.
    # Test paths pass explicit title/highlight; keep honoring those verbatim so
    # the "send test notification" button stays a clear, self-labeled toast.
    if title or highlight:
        title_text = title or (
            "🎯 Top-Deal gefunden!" if highlight else
            f"🆕 {result_count} neue Treffer"
        )
        body = highlight if highlight else keywords
    else:
        # Real runs: deterministic, German, value-first (price/saving/location).
        # `deal` is only present when the user searched a concrete item AND a
        # below-market offer was found — see the caller in scrape_kleinanzeigen.
        built = build_push_notification(
            new_count=result_count,
            keywords=keywords,
            cheapest_price=cheapest_price,
            location=location,
            deal=deal,
            profile=profile,
            trust_score=trust_score,
            sample_title=sample_title,
        )
        title_text = built["title"]
        body = built["body"]

    # Tag: tests pass an explicit, per-click unique tag so each click is a
    # distinct, visible toast (browsers collapse same-tag notifications). Real
    # runs group by search via "search-{task_id}".
    effective_tag = tag if tag is not None else f"search-{task_id}"

    payload_data = {
        "title": title_text,
        "body": body,
        "icon": "/static/icons/icon-192.png",
        "badge": "/static/icons/icon-72.png",
        "tag": effective_tag,  # Group by search, or unique per test click
        "requireInteraction": True,  # Keep notification visible
        "data": {
            "searchKeywords": keywords,
            "resultCount": result_count,
            "location": location or "Alle Orte",
            "priceRange": price_range or "Beliebig",
            "bestPrice": best_price,
            "taskId": task_id,
            "url": "/dashboard#tab-my-results",
        },
        "actions": [
            {
                "action": "view-results",
                "title": "Ansehen",
            },
            {
                "action": "open-search",
                "title": "Suche öffnen",
            },
            {
                "action": "dismiss",
                "title": "Ausblenden",
            }
        ]
    }
    # Big preview image (listing thumbnail) when we have one — supported by
    # Chrome/Edge/Android. Data is already computed by the caller; we just
    # surface it (previously it was passed in but never rendered).
    if image_url:
        payload_data["image"] = image_url
    payload = json.dumps(payload_data)
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
    push_policy = {"max_attempts": 3, "backoff_cap": 60}
    for sub in subs:
        def _do_push() -> None:
            resp = webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": sub_claim},
                ttl=86400,  # 24h — FCM will retry delivery if device is offline
            )
            logger.info(f"Push sub={sub.id} resp={resp.status_code} body={resp.text[:200]}")

        ok, last = _retry_with_backoff(push_policy, f"webpush(subs={sub.id})", _do_push)
        if ok:
            summary["sent"] += 1
            continue

        # The retry wrapper swallows the exception and returns it as `last`,
        # so we can't rely on the outer try/except to catch WebPushException.
        # Detect a 404/410 (expired/unsubscribed endpoint) here and prune it;
        # any other failure is a genuine send error.
        status = getattr(getattr(last, "response", None), "status_code", None)
        if status in (404, 410):
            stale.append(sub.id)
            summary["removed"] += 1
        else:
            summary["failed"] += 1
            summary["errors"].append(str(last))
            logger.warning(f"Push failed for sub {sub.id}: {last}")

    if stale:
        db.query(PushSubscription).filter(PushSubscription.id.in_(stale)).delete(synchronize_session=False)
        db.commit()

    if summary["sent"]:
        metric("notifications.push_sent", summary["sent"])
    if summary["failed"]:
        metric("notifications.push_failed", summary["failed"])

    _save_notification_delivery(db, user_id, task_id, "push", summary)
    return summary


@track_job_decorator("notifications.send_email")
def _send_email_notifications(
    db, user_id: int, result_count: int, keywords: str,
    new_results: list, highlight: str = None, bypass_preferences: bool = False,
    task_id: int = None,
) -> dict:
    """Email a user about genuinely-new listings.

    Fires at the same point as _send_push_notifications and honors the same
    preferences (email toggle), unless bypass_preferences is set.
    """
    summary = {"configured": True, "sent": False, "errors": []}

    if not email_configured():
        summary["configured"] = False
        summary["errors"].append("SENDGRID_API_KEY is not configured on the server.")
        return summary

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.email:
        summary["errors"].append("No user/email on file.")
        return summary

    if not bypass_preferences:
        if not user.email_notifications_enabled:
            summary["errors"].append("User has disabled email notifications.")
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

    email_policy = {"max_attempts": 3, "backoff_cap": 60}
    def _do_send():
        if not send_email_notification(notification):
            raise RuntimeError("Email send failed; see server logs.")
        return True

    ok, last = _retry_with_backoff(email_policy, f"sendgrid(user={user.id},task={task_id})", _do_send)
    summary["sent"] = bool(ok)
    if summary["sent"]:
        metric("notifications.email_sent", 1)
        from app.shared.email_status import clear_email_failed
        clear_email_failed()
    else:
        summary["errors"].append(f"Email send failed: {last}")
        metric("notifications.email_failed", 1)
        from app.shared.email_status import mark_email_failed
        mark_email_failed()

    _save_notification_delivery(db, user_id, task_id, "email", summary)
    return summary


@track_job_decorator("notifications.run_test_push")
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
        task_id=None,
        bypass_preferences=True,
        tag=f"test-{int(time.time() * 1000)}",
        title="TEST - kleeblatt.space",
    )


def _ensure_task(db, task_id: int | None, parameters: dict) -> tuple[int | None, object | None]:
    """
    Return (task_id, task_orm_object).

    - If task_id is supplied (API-triggered run): load and return the existing ScrapeTask.
      If the row no longer exists (e.g. the user deleted the search between a reaper
      claim and this run) return (None, None) — the caller bails, so we never insert
      ScrapeResults against a missing parent (would blow the scrape_results_task_id_fkey
      FK; see Sentry PYTHON-FASTAPI-X).
    - If task_id is None (Beat-scheduled run): create a new ScrapeTask owned by the
      configured SYSTEM_USER_ID so that ScrapeResult FK constraints are always satisfied.
    """
    if task_id is not None:
        task = db.query(ScrapeTask).filter(ScrapeTask.id == task_id).first()
        if task is None:
            logger.warning(
                f"ScrapeTask id={task_id} no longer exists — skipping run to avoid "
                f"orphaned ScrapeResult inserts (FK scrape_results_task_id_fkey)"
            )
            return None, None
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
    _clear_seller_page_cache()
    resolved_task_id = None
    task = None
    job_start = time.monotonic()
    metric("job.started", 1, task="scrape.kleinanzeigen")
    try:
        resolved_task_id, task = _ensure_task(db, task_id, parameters)

        # Guard: the ScrapeTask row vanished (user deleted the search, or a
        # reaper pass revived a task whose row was dropped). _ensure_task returns
        # (None, None) in that case — bail before the doomed ScrapeResult insert
        # that would otherwise violate scrape_results_task_id_fkey (Sentry #X).
        if task is None:
            logger.info(
                f"ScrapeTask for task_id={task_id} missing — aborting run cleanly."
            )
            return
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
        scrape_params = {
            k: v for k, v in parameters.items() if k not in _NON_URL_PARAM_KEYS
        }
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
        parse_error_count = 0

        # Advanced result filters (Core/Pro) — the API only stores these for
        # plan-eligible users. Applied per listing below, BEFORE dedup/credit/
        # save, so a filtered-out listing costs no credit and sends no alert.
        require_kw = parameters.get("require_keywords") or []
        exclude_kw = parameters.get("exclude_keywords") or []
        exclude_loc = parameters.get("exclude_locations") or []

        for item in listings[:25]:
            item_url = None
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

                # Advanced filters (Core/Pro): drop listings the user excluded
                # (or that miss a required term) before they can become results.
                if (require_kw or exclude_kw or exclude_loc) and not passes_filters(
                    title, description, location,
                    require=require_kw, exclude=exclude_kw, exclude_locations=exclude_loc,
                ):
                    continue

                key = item_url or f"{title}|{price}|{location}"
                if key in seen_keys:
                    continue  # already seen on a previous run — not new
                if metered and not is_baseline:
                    if not consume_credit(db, owner):
                        if auto_topup_credits(owner):
                            db.refresh(owner)
                            if not consume_credit(db, owner):
                                logger.info(
                                    f"Credits exhausted for user {owner.id} "
                                    f"(task_id={resolved_task_id}) — skipping remaining new listings"
                                )
                                break
                        else:
                            logger.info(
                                f"Credits exhausted for user {owner.id} "
                                f"(task_id={resolved_task_id}) — skipping remaining new listings"
                            )
                            break
                seen_keys.add(key)

                seller_info = None
                if item_url:
                    seller_info = extract_seller_info_from_listing_with_retry(item_url)

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
                err_msg = f"{type(e).__name__}: {e}"
                logger.warning(f"Failed to parse listing: {err_msg}")
                parse_error_count += 1
                db.add(
                    ScrapeResult(
                        task_id=resolved_task_id,
                        title="Parse failed",
                        price="N/A",
                        price_value=None,
                        location="N/A",
                        url=item_url,
                        image_url=None,
                        description=None,
                        seller_id=None,
                        seller_name=None,
                        seller_rating=None,
                        seller_badges=None,
                        seller_active_since=None,
                        seller_listings_count=None,
                        trust_score=None,
                        parse_error=err_msg,
                    )
                )
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
                    if parse_error_count > 0:
                        task.status = "partial_failed"
                        task.error_message = f"{parse_error_count} listing(s) failed to parse; see ScrapeResult.parse_error for details."
                    else:
                        task.status = "completed"
                        task.error_message = None
                # Stamp every run (success or partial) so the dashboard can show
                # "zuletzt geprüft vor X" even when no new listing was found.
                task.last_run_at = datetime.now(timezone.utc)
                # A successful run consumed the free baseline (a failed run
                # keeps it — nothing was charged, so the retry is still free).
                task.baseline_done = True
                db.commit()

        logger.info(f"Saved {new_count} new result(s) from {url}")

        # ── Push notifications — only for genuinely new listings ────────────
        # The baseline run is silent: a "25 new listings" push right after
        # setting up a search is noise, and none of it is genuinely new.
        if task and new_count > 0 and not is_baseline:
            keywords = parameters.get("keywords", "") or ""
            category = parameters.get("category")
            ad_type = parameters.get("ad_type")
            # What kind of search this is (Job/Immobilie/Dienstleistung/Tier/
            # Verschenken/Gesuch/…) — decides whether price/"deal" framing
            # applies at all. See app/shared/category_profiles.py.
            profile = resolve_profile(category, ad_type)

            # Trust score is its OWN Core/Pro plan flag (app/shared/plans.py:
            # "trust_scores"), separate from "deal_badges" below. Gate it on
            # its own flag rather than piggybacking on deal_gated — the two
            # flags happen to be identical per plan today, but nothing
            # enforces that, and piggybacking would silently leak Trust
            # Scores to Basic users the moment that changes.
            show_trust = bool(owner and (owner.is_admin or plan_config(owner.plan).get("trust_scores")))

            # Deal-Highlight nur bei preisvergleichbaren Profilen (item /
            # ticket / vehicle-mit-Keyword) — bei Jobs, Immobilien,
            # Dienstleistungen, Verschenken, Tieren und Gesuchen ist ein
            # "unter Marktpreis" sinnlos oder unpassend, unabhängig vom Plan.
            # Zusätzlich für die verbleibenden Profile Core/Pro-gated.
            highlight = None
            best_price_str = None
            best_image_url = None
            best_title = None
            deal = None
            deal_gated = owner and (owner.is_admin or plan_config(owner.plan).get("deal_badges"))
            if profile not in NO_PRICE_PROFILES and keywords and deal_gated:
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
                            best = (r.price_value, r.title, badge["label"], r.image_url, r.trust_score)
                if best:
                    highlight = f"🔥 {best[2]}: {best[1]}"
                    best_price_str = f"€{best[0]}"
                    best_image_url = best[3]
                    best_title = best[1]
                    deal = {
                        "title": best[1],
                        "price": "geschenkt" if best[0] == 0 else f"{best[0]} €",
                        "saving_eur": int(round(med - best[0])) if med else None,
                        "trust_score": best[4] if show_trust else None,
                    }

            # Smart Alerts: one deterministic sentence for the dashboard, reusing
            # the deal data computed above (so it's plan-gated for free — Basic
            # owners never had a best_title/best_price_str set).
            task.last_summary = build_smart_summary(
                new_count,
                keywords,
                deal_title=best_title,
                best_price_str=best_price_str,
            )
            db.commit()

            location = parameters.get("location") or None
            price_min = parameters.get("price_min")
            price_max = parameters.get("price_max")
            price_range = None
            if price_min or price_max:
                price_range = f"€{price_min or '0'}–€{price_max or '∞'}"

            # Günstigster neuer Treffer (für den Fallback-Body ohne Deal) —
            # nutzt die bereits geparsten Preise, kein Netzwerk/kein Plan-Gate.
            priced = [r for r in new_results if r.price_value is not None]
            cheapest_price = None
            if priced:
                cheapest = min(priced, key=lambda r: r.price_value)
                cheapest_price = "geschenkt" if cheapest.price_value == 0 \
                    else f"{cheapest.price_value} €"

            # No-price profiles (Jobs, Immobilien, Dienstleistungen, …) show
            # the single new listing's title instead of a bare count when
            # there's exactly one match — and its seller's trust score, but
            # only for profiles where that's useful (service/animal) and only
            # when show_trust allows it (see build_push_notification).
            sample_title = new_results[0].title if new_count == 1 and new_results else None
            profile_trust_score = None
            if profile in NO_PRICE_PROFILES and new_count == 1 and new_results and show_trust:
                profile_trust_score = new_results[0].trust_score

            _send_push_notifications(
                db,
                user_id=task.user_id,
                result_count=new_count,
                keywords=keywords,
                location=location,
                price_range=price_range,
                best_price=best_price_str,
                image_url=best_image_url,
                task_id=resolved_task_id,
                deal=deal,
                cheapest_price=cheapest_price,
                profile=profile,
                trust_score=profile_trust_score,
                sample_title=sample_title,
            )
            _send_email_notifications(
                db,
                user_id=task.user_id,
                result_count=new_count,
                keywords=keywords or "deine Suche",
                new_results=new_results,
                highlight=highlight,
                task_id=resolved_task_id,
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

        metric("job.completed", 1, task="scrape.kleinanzeigen")
        duration_s = time.monotonic() - job_start
        sentry_metrics.distribution(
            "job.duration_ms",
            duration_s * 1000,
            unit="millisecond",
            attributes={"job": "scrape.kleinanzeigen"},
        )
        job_duration.labels(task="scrape.kleinanzeigen").observe(duration_s)
        metric("scrape.listings_found", new_count, baseline=str(bool(is_baseline)).lower())

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
        # The SentryLogHandler bridge already captures this exception (exc_info=True);
        # attach the structured scrape context here so it's queryable in Sentry.
        sentry_sdk.set_context(
            "scrape",
            {
                "task_id": update_id,
                "attempt": attempt,
                "keywords": parameters.get("keywords"),
                "location": parameters.get("location"),
                "url": locals().get("url"),
            },
        )
        metric("job.failed", 1, task="scrape.kleinanzeigen")
        duration_s = time.monotonic() - job_start
        sentry_metrics.distribution(
            "job.duration_ms",
            duration_s * 1000,
            unit="millisecond",
            attributes={"job": "scrape.kleinanzeigen"},
        )
        job_duration.labels(task="scrape.kleinanzeigen").observe(duration_s)

        # Only mark as permanently failed if this is the last retry attempt.
        # Earlier attempts should leave the task in "running" state so a
        # successful retry can complete normally without having to overwrite
        # a stale "failed" status.
        will_retry = self.request.retries < self.max_retries
        
        if update_id is not None:
            try:
                # Use a conditional update to avoid race conditions: only update
                # if the task hasn't been cancelled or completed by another process.
                # This prevents a retry from overwriting a successful completion
                # or a user cancellation that arrived while the task was running.
                if will_retry:
                    # Store error for debugging but keep status as "running" for retry
                    updated = (
                        db.query(ScrapeTask)
                        .filter(
                            ScrapeTask.id == update_id,
                            ScrapeTask.status.in_(["running", "pending"])
                        )
                        .update(
                            {
                                "error_message": f"Attempt {attempt} failed: {error_detail}. Retrying..."
                            },
                            synchronize_session=False,
                        )
                    )
                else:
                    # Final attempt failed - mark as permanently failed
                    updated = (
                        db.query(ScrapeTask)
                        .filter(
                            ScrapeTask.id == update_id,
                            ScrapeTask.status != "cancelled"
                        )
                        .update(
                            {
                                "status": "failed",
                                "error_message": error_detail
                            },
                            synchronize_session=False,
                        )
                    )
                db.commit()
                if updated:
                    logger.info(
                        f"Task {update_id} marked as {'retrying' if will_retry else 'failed'} "
                        f"(attempt {attempt}/{self.max_retries + 1})"
                    )
            except Exception:
                logger.exception(
                    "Could not update scrape task %s after error", update_id
                )
                db.rollback()
        
        if will_retry:
            retries = self.request.retries
            countdown = min(2 ** retries * 60, 600)
            logger.info(f"Retrying in {countdown}s (attempt {retries + 1}/{self.max_retries + 1})")
            raise self.retry(exc=exc, countdown=countdown)
        else:
            logger.error(f"Task {update_id} exhausted all retries, permanently failed")
            # Don't retry - let the exception propagate so Celery marks it as failed
            raise

    finally:
        db.close()


@celery_app.task(name="scrape.dispatch_admin_searches", bind=False)
@track_job_decorator("scrape.dispatch_admin_searches")
def dispatch_admin_searches():
    """Dispatches scrape tasks for all due admin-configured searches.
    
    Uses an idempotency check to prevent dispatching duplicate tasks for the
    same AdminSearch when multiple Beat instances run concurrently or when
    the dispatcher is triggered manually while scheduled runs are pending.
    """
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
            dispatched = 0
            for search in searches:
                # Idempotency check: only dispatch if we can atomically claim
                # this run by updating next_run_at. If another dispatcher beat
                # us to it, the update returns 0 rows and we skip this search.
                next_run = now + timedelta(minutes=search.interval_minutes)
                claimed = (
                    db.query(AdminSearch)
                    .filter(
                        AdminSearch.id == search.id,
                        AdminSearch.is_active.is_(True),
                        or_(
                            AdminSearch.next_run_at.is_(None),
                            AdminSearch.next_run_at <= now
                        ),
                    )
                    .update(
                        {
                            "last_run_at": now,
                            "next_run_at": next_run,
                        },
                        synchronize_session=False,
                    )
                )
                
                if not claimed:
                    logger.debug(
                        f"Skipping admin search id={search.id} - already dispatched by another process"
                    )
                    continue
                
                db.commit()
                
                # Build parameters for the scrape task
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
                dispatched += 1
                logger.info(
                    f"Dispatched admin search id={search.id} keywords={search.keywords} "
                    f"next_run={next_run.isoformat()}"
                )
            
            metric("admin_search.dispatched", dispatched)
            if dispatched:
                logger.info(f"Dispatched {dispatched} admin search(es)")
    except Exception as e:
        logger.error(f"dispatch_admin_searches failed: {e}")
        db.rollback()
    finally:
        db.close()


@celery_app.task(name="scrape.reap_stale_recurring_searches", bind=False)
@track_job_decorator("scrape.reap_stale_recurring_searches")
def reap_stale_recurring_searches():
    """Restart user recurring searches whose self-rescheduling chain died.

    User searches re-queue themselves via ``apply_async(countdown=interval)``
    at the end of every run. That pending ETA task lives only in the broker,
    so a worker restart/crash (or any run that errors before the reschedule
    line) breaks the chain permanently — unlike admin searches, which Beat
    re-dispatches from ``next_run_at`` every minute. This reaper is that same
    safety net for user searches: it finds recurring tasks that are overdue
    and re-primes them, so no deploy or crash can silently strand a search.

    A task is "overdue" when its last run finished more than
    ``interval + grace`` ago (grace absorbs a run that's merely in flight, so
    we never race a healthy chain). Only settled statuses are eligible; a
    ``running``/``pending`` task is left alone, and ``cancelled`` is honoured.
    Re-priming atomically bumps ``last_run_at`` (same claim trick as the admin
    dispatcher) so overlapping reaper passes can't double-dispatch.
    """
    db = SessionLocal()
    try:
        with track_job("scrape.reap_stale_recurring_searches"):
            now = datetime.now(timezone.utc)
            
            # Candidates: settled statuses with last_run_at OR orphaned running tasks with last_run_at=NULL
            candidates = (
                db.query(ScrapeTask)
                .filter(
                    or_(
                        # Settled statuses with last_run_at
                        and_(
                            ScrapeTask.status.in_(("completed", "partial_failed", "failed")),
                            ScrapeTask.last_run_at.isnot(None),
                        ),
                        # Orphaned running tasks with last_run_at=NULL
                        and_(
                            ScrapeTask.status == "running",
                            ScrapeTask.last_run_at.is_(None),
                        ),
                        # Orphaned pending tasks with old created_at and last_run_at=NULL
                        and_(
                            ScrapeTask.status == "pending",
                            ScrapeTask.last_run_at.is_(None),
                            ScrapeTask.created_at < now - timedelta(seconds=60),  # 60s grace period
                        ),
                    )
                )
                .all()
            )
            
            logger.info(f"Reaper candidates: {[c.id for c in candidates]}")
            
            revived = 0
            for task in candidates:
                try:
                    interval = int((task.parameters or {}).get("interval_seconds") or 0)
                except (TypeError, ValueError):
                    interval = 0
                if interval <= 0 and task.status != "pending":
                    continue  # one-shot search, nothing to reschedule
                grace = max(interval // 2, 120)
                due_before = now - timedelta(seconds=interval + grace)
                last_run = task.last_run_at
                if last_run is not None and last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                if last_run is not None and last_run > due_before:
                    continue  # chain still healthy (or run in flight)

                # Atomically claim: only proceed if last_run_at is still the
                # stale value we saw, so a concurrent reaper/real run wins the
                # race and we don't double-dispatch.
                claimed = (
                    db.query(ScrapeTask)
                    .filter(
                        ScrapeTask.id == task.id,
                        or_(
                            and_(
                                ScrapeTask.last_run_at == task.last_run_at,
                                task.status != "pending",
                            ),
                            and_(
                                ScrapeTask.last_run_at.is_(None),
                                task.status == "pending",
                            ),
                        ),
                        or_(
                            ScrapeTask.status.in_(("completed", "partial_failed", "failed")),
                            ScrapeTask.status == "running",
                            ScrapeTask.status == "pending",
                        ),
                    )
                    .update({"last_run_at": now}, synchronize_session=False)
                )
                if not claimed:
                    continue
                db.commit()

                # Guard: the task row may have been deleted (user removed the
                # search) since we selected it as a candidate. Don't re-enqueue a
                # run against a missing parent — that only produces FK violations
                # downstream (scrape_results_task_id_fkey) and re-primes forever.
                still_exists = (
                    db.query(ScrapeTask.id)
                    .filter(ScrapeTask.id == task.id)
                    .first()
                )
                if not still_exists:
                    logger.info(
                        f"Skipping reaped task_id={task.id}: ScrapeTask row gone "
                        f"(search likely deleted) — not re-enqueuing."
                    )
                    continue

                scrape_kleinanzeigen.apply_async(args=[dict(task.parameters), task.id])
                revived += 1
                logger.info(
                    f"Reaped stale recurring search task_id={task.id} "
                    f"(interval={interval}s, last_run={task.last_run_at})"
                )

            metric("scrape.recurring_reaped", revived)
            if revived:
                logger.info(f"Reaped {revived} stale recurring search(es)")
    except Exception as e:
        logger.error(f"reap_stale_recurring_searches failed: {e}")
        db.rollback()
    finally:
        db.close()
