import json
import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from sqlalchemy import or_

from app.api.config import settings
from app.shared.database import SessionLocal
from app.shared.models import AdminSearch, PushSubscription, ScrapeTask, ScrapeResult
from app.shared.url_builder import build_kleinanzeigen_url
from app.worker.celery_app import celery_app

logger = logging.getLogger("kleinanzeigen-ai")


def _send_push_notifications(db, user_id: int, result_count: int, keywords: str) -> None:
    if not settings.vapid_private_key or not settings.vapid_public_key:
        return
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return

    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    if not subs:
        return

    payload = json.dumps({
        "title": "kleinanzeigen-ai",
        "body": f"{result_count} new listing(s) found for \"{keywords}\"",
    })
    private_key = settings.vapid_private_key.replace("\\n", "\n")

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
                vapid_claims={"sub": settings.vapid_email},
            )
        except WebPushException as e:
            # 404/410 means the subscription has expired — clean it up
            if e.response is not None and e.response.status_code in (404, 410):
                stale.append(sub.id)
            else:
                logger.warning(f"Push failed for sub {sub.id}: {e}")
        except Exception as e:
            logger.warning(f"Push failed for sub {sub.id}: {e}")

    if stale:
        db.query(PushSubscription).filter(PushSubscription.id.in_(stale)).delete(synchronize_session=False)
        db.commit()


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

        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        listings = (
            soup.find_all("article", class_="aditem") or
            soup.select("article.aditem") or
            soup.find_all("div", {"data-adid": True})
        )

        saved_count = 0

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

                result = ScrapeResult(
                    task_id=resolved_task_id,
                    title=title[:255],
                    price=price[:50],
                    location=location[:100],
                    url=item_url,
                )
                db.add(result)
                saved_count += 1

            except Exception as e:
                logger.warning(f"Failed to parse listing: {e}")
                continue

        db.commit()

        if task:
            # Re-fetch to respect a cancellation that arrived while the task was running.
            task = db.query(ScrapeTask).filter(ScrapeTask.id == resolved_task_id).first()
            if task and task.status != "cancelled":
                task.status = "completed"
                db.commit()

        logger.info(f"Saved {saved_count} results from {url}")

        # ── Push notifications ──────────────────────────────────────────────
        if task and saved_count > 0:
            _send_push_notifications(
                db,
                user_id=task.user_id,
                result_count=saved_count,
                keywords=parameters.get("keywords", "your search"),
            )
        # ───────────────────────────────────────────────────────────────────

        # ── Self-re-scheduling ──────────────────────────────────────────────
        # Only re-queue if the task wasn't cancelled between start and now.
        interval = parameters.get("interval_seconds")
        if interval and task and task.status == "completed":
            logger.info(f"Re-scheduling scrape in {interval}s (task_id={resolved_task_id})")
            scrape_kleinanzeigen.apply_async(
                args=[parameters, resolved_task_id],
                countdown=int(interval),
            )
        # ───────────────────────────────────────────────────────────────────

        return {
            "status": "success",
            "results_saved": saved_count,
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
