import json
import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from sqlalchemy import or_

from app.api.config import settings
from app.shared.database import SessionLocal
from app.shared.models import AdminSearch, PushSubscription, ScrapeTask, ScrapeResult, User
from app.shared.plans import ensure_weekly_credits, plan_config
from app.shared.pricing import deal_badge, median_price, parse_price
from app.shared.proxy import proxies_for_requests
from app.shared.url_builder import build_kleinanzeigen_url
from app.worker.celery_app import celery_app

logger = logging.getLogger("kleinanzeigen-ai")


def _send_push_notifications(
    db, user_id: int, result_count: int, keywords: str, highlight: str = None
) -> dict:
    """Send a web push to every subscription of a user.

    Returns a summary so callers (e.g. the admin test button) can report what
    actually happened instead of failing silently:
    {configured, total, sent, failed, removed, errors}.
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

    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    summary["total"] = len(subs)
    if not subs:
        return summary

    # Lead with a deal highlight when there is one, otherwise the plain count.
    body = highlight or f"{result_count} new listing(s) found for \"{keywords}\""
    payload = json.dumps({
        "title": "kleinanzeigen-ai",
        "body": body,
    })
    # VAPID private keys come in two shapes and py_vapid picks its parser by
    # looking for "BEGIN"/newlines in the string:
    #  - PEM: env vars usually store the newlines escaped as literal "\n".
    #  - Raw base64url (the web-push standard, paired with the public key the
    #    browser uses): must have NO newlines, or py_vapid misroutes it into PEM
    #    parsing and dies with "Could not deserialize key data ... ASN.1 ...".
    raw_key = (settings.vapid_private_key or "").strip()
    if "BEGIN" in raw_key:
        private_key = raw_key.replace("\\n", "\n")
    else:
        private_key = "".join(raw_key.split()).replace("\\n", "")

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
    try:
        resolved_task_id, task = _ensure_task(db, task_id, parameters)

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

        response = requests.get(url, headers=headers, timeout=20, proxies=proxies)
        response.raise_for_status()

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

                price_tag = item.find("p", class_="aditem-main--middle--price")
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

                result = ScrapeResult(
                    task_id=resolved_task_id,
                    title=title[:255],
                    price=price[:50],
                    price_value=parse_price(price),
                    location=location[:100],
                    url=item_url,
                    image_url=image_url,
                    description=description,
                )
                db.add(result)
                new_results.append(result)
                new_count += 1

            except Exception as e:
                logger.warning(f"Failed to parse listing: {e}")
                continue

        db.commit()

        if task:
            # Re-fetch to respect a cancellation that arrived while the task was running.
            task = db.query(ScrapeTask).filter(ScrapeTask.id == resolved_task_id).first()
            if task:
                if task.status != "cancelled":
                    task.status = "completed"
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
                            best = (r.price_value, r.title, badge["label"])
                if best:
                    highlight = f"🔥 {best[2]}: {best[1]}"

            _send_push_notifications(
                db,
                user_id=task.user_id,
                result_count=new_count,
                keywords=parameters.get("keywords", "your search"),
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

        return {
            "status": "success",
            "results_saved": new_count,
            "url": url,
        }

    except Exception as exc:
        logger.error(f"Scraping failed: {str(exc)}")
        db.rollback()

        try:
            # resolved_task_id covers both API-triggered and Beat-triggered paths;
            # fall back to task_id only if _ensure_task itself raised before setting it.
            update_id = resolved_task_id if resolved_task_id is not None else task_id
            if update_id is not None:
                failed_task = db.query(ScrapeTask).filter(ScrapeTask.id == update_id).first()
                if failed_task:
                    failed_task.status = "failed"
                    db.commit()
        except Exception:
            pass

        raise self.retry(exc=exc, countdown=120)

    finally:
        db.close()


@celery_app.task(name="scrape.dispatch_admin_searches", bind=False)
def dispatch_admin_searches():
    """Dispatches scrape tasks for all due admin-configured searches."""
    db = SessionLocal()
    try:
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
            }.items() if v is not None}
            scrape_kleinanzeigen.apply_async(args=[parameters])
            search.last_run_at = now
            search.next_run_at = now + timedelta(minutes=search.interval_minutes)
            logger.info(f"Dispatched admin search id={search.id} keywords={search.keywords}")
        if searches:
            db.commit()
    except Exception as e:
        logger.error(f"dispatch_admin_searches failed: {e}")
        db.rollback()
    finally:
        db.close()
