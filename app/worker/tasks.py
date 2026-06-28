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
    db = SessionLocal()
    try:
        url = build_kleinanzeigen_url(**parameters)
        logger.info(f"Scraping: {url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Try multiple possible selectors (kleinanzeigen.de changes frequently)
        listings = (
            soup.find_all("article", class_="aditem") or
            soup.select("article.aditem") or
            soup.find_all("div", {"data-adid": True})
        )

        saved = 0

        for item in listings[:25]:
            try:
                # Title
                title_tag = item.find("h2") or item.find("a", class_="ellipsis")
                title = title_tag.get_text(strip=True) if title_tag else "No title found"

                # Price
                price_tag = item.find("p", class_="aditem-main--middle--price") or item.find(string=re.compile(r"€|EUR"))
                price = price_tag.get_text(strip=True) if price_tag else "N/A"

                # Location
                location_tag = item.find("div", class_="aditem-main--top--left") or item.find("span", class_="simpletag")
                location = location_tag.get_text(strip=True) if location_tag else "N/A"

                # Link
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
                saved += 1

            except Exception as e:
                logger.warning(f"Failed to parse listing: {e}")
                continue

        db.commit()
        logger.info(f"Saved {saved} results from {url}")

        return {"status": "success", "results_saved": saved, "url": url}

    except Exception as exc:
        logger.error(f"Scraping error: {str(exc)}")
        db.rollback()
        raise self.retry(exc=exc, countdown=120)
    finally:
        db.close()
