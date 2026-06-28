from app.worker.celery_app import celery_app
from app.shared.url_builder import build_kleinanzeigen_url
from app.shared.database import SessionLocal
from app.shared.models import ScrapeResult
import requests
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger("kleinanzeigen-ai")


@celery_app.task(name="scrape.kleinanzeigen", bind=True, max_retries=2)
def scrape_kleinanzeigen(self, parameters: dict):
    """
    Celery task that scrapes kleinanzeigen.de and saves results to the database.
    """
    db = SessionLocal()
    try:
        # Build the search URL
        url = build_kleinanzeigen_url(**parameters)
        logger.info(f"Starting scrape for: {url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Try common selectors for kleinanzeigen.de listings
        listings = (
            soup.find_all("article", class_="aditem") or
            soup.select("article.aditem") or
            soup.find_all("div", {"data-adid": True})
        )

        saved_count = 0

        for item in listings[:25]:  # Limit results for Milestone 1
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
                    item_url = f"https://www.kleinanzeigen.de{href}" if href.startswith("/") else href

                # Save to database
                result = ScrapeResult(
                    title=title[:255],
                    price=price[:50],
                    location=location[:100],
                    url=item_url,
                )
                db.add(result)
                saved_count += 1

            except Exception as e:
                logger.warning(f"Failed to parse one listing: {e}")
                continue

        db.commit()
        logger.info(f"Saved {saved_count} results from {url}")

        return {"status": "success", "results_saved": saved_count, "url": url}

    except Exception as exc:
        logger.error(f"Scraping failed: {str(exc)}")
        db.rollback()
        raise self.retry(exc=exc, countdown=120)

    finally:
        db.close()
