from app.worker.celery_app import celery_app
from app.shared.url_builder import build_kleinanzeigen_url
from app.shared.database import SessionLocal
from app.shared.models import ScrapeResult, ScrapeTask
import requests
from bs4 import BeautifulSoup
import logging
import re
from typing import Optional

logger = logging.getLogger("kleinanzeigen-ai")


def _extract_description(item) -> Optional[str]:
    """
    Extract raw listing description text from a parsed aditem element.

    Kleinanzeigen renders the short description in a <p> with class
    'aditem-main--middle--description'.  We fall back to a broader search
    for any <p> that isn't the price tag so this stays useful if the
    site's markup changes slightly.
    """
    # Primary: dedicated description paragraph
    desc_tag = item.find("p", class_="aditem-main--middle--description")
    if desc_tag:
        return desc_tag.get_text(strip=True) or None

    # Fallback: first <p> that is not the price line
    for p in item.find_all("p"):
        classes = p.get("class", [])
        if "aditem-main--middle--price" in classes:
            continue
        text = p.get_text(strip=True)
        if text:
            return text

    return None


@celery_app.task(name="scrape.kleinanzeigen", bind=True, max_retries=2)
def scrape_kleinanzeigen(self, parameters: dict, task_id: Optional[int] = None):
    """
    Scrape kleinanzeigen.de listings and persist results to PostgreSQL.

    Args:
        parameters: dict with optional keys: keywords, category, location, price_max, radius, sort
        task_id:    ID of a pre-created ScrapeTask row (from API). When None (beat-triggered),
                    a new ScrapeTask is created here without a user_id.
    """
    db = SessionLocal()
    try:
        clean_params = {k: v for k, v in parameters.items() if v is not None}
        url = build_kleinanzeigen_url(**clean_params)
        logger.info(f"Scraping: {url}")

        # Create or update the ScrapeTask status
        if task_id is None:
            task = ScrapeTask(url=url, status="running", parameters=parameters)
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id
        else:
            db.query(ScrapeTask).filter(ScrapeTask.id == task_id).update({"status": "running"})
            db.commit()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        listings = (
            soup.find_all("article", class_="aditem")
            or soup.select("article.aditem")
            or soup.find_all("div", {"data-adid": True})
        )

        saved = 0
        for item in listings[:25]:
            try:
                title_tag = item.find("h2") or item.find("a", class_="ellipsis")
                title = title_tag.get_text(strip=True) if title_tag else "No title found"

                price_tag = item.find("p", class_="aditem-main--middle--price") or item.find(
                    string=re.compile(r"€|EUR")
                )
                price = price_tag.get_text(strip=True) if price_tag else "N/A"

                location_tag = item.find("div", class_="aditem-main--top--left") or item.find(
                    "span", class_="simpletag"
                )
                location = location_tag.get_text(strip=True) if location_tag else "N/A"

                link_tag = item.find("a", href=True)
                item_url = None
                if link_tag:
                    href = link_tag["href"]
                    item_url = (
                        f"https://www.kleinanzeigen.de{href}" if href.startswith("/") else href
                    )

                description = _extract_description(item)

                result = ScrapeResult(
                    task_id=task_id,
                    title=title[:255],
                    price=price[:50],
                    location=location[:100],
                    url=item_url,
                    description=description,
                )
                db.add(result)
                saved += 1

            except Exception as e:
                logger.warning(f"Failed to parse listing: {e}")
                continue

        db.commit()
        db.query(ScrapeTask).filter(ScrapeTask.id == task_id).update({"status": "completed"})
        db.commit()
        logger.info(f"Saved {saved} results from {url}")

        return {"status": "completed", "results_saved": saved, "url": url}

    except Exception as exc:
        logger.error(f"Scraping error: {exc}")
        db.rollback()
        if task_id:
            try:
                db.query(ScrapeTask).filter(ScrapeTask.id == task_id).update({"status": "failed"})
                db.commit()
            except Exception:
                pass
        raise self.retry(exc=exc, countdown=120)
    finally:
        db.close()
