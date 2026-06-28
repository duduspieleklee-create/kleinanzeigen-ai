from app.worker.celery_app import celery_app
from app.shared.url_builder import build_kleinanzeigen_url
from app.shared.database import SessionLocal
from app.shared.models import ScrapeTask, ScrapeResult
import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger("kleinanzeigen-ai")


@celery_app.task(name="scrape.kleinanzeigen", bind=True, max_retries=2)
def scrape_kleinanzeigen(self, parameters: dict):
    """
    Real scraping task for Milestone 1.
    """
    db = SessionLocal()
    try:
        # 1. Build the search URL
        url = build_kleinanzeigen_url(**parameters)
        logger.info(f"Starting scrape for: {url}")

        # 2. Make HTTP request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        # 3. Parse HTML
        soup = BeautifulSoup(response.text, "lxml")

        # Find listing items (this selector may need adjustment based on current site structure)
        listings = soup.find_all("article", class_="aditem") or soup.select("article.aditem")

        saved_count = 0

        for item in listings[:20]:  # Limit to first 20 results for Milestone 1
            try:
                title = item.find("h2").get_text(strip=True) if item.find("h2") else "No title"
                price_tag = item.find("p", class_="aditem-main--middle--price")
                price = price_tag.get_text(strip=True) if price_tag else "N/A"
                location_tag = item.find("div", class_="aditem-main--top--left")
                location = location_tag.get_text(strip=True) if location_tag else "N/A"
                link_tag = item.find("a", href=True)
                item_url = "https://www.kleinanzeigen.de" + link_tag["href"] if link_tag else None

                # Save to database
                result = ScrapeResult(
                    title=title,
                    price=price,
                    location=location,
                    url=item_url,
                )
                db.add(result)
                saved_count += 1

            except Exception as e:
                logger.warning(f"Failed to parse one listing: {e}")
                continue

        db.commit()
        logger.info(f"Successfully saved {saved_count} results from {url}")

        return {
            "status": "success",
            "url": url,
            "results_saved": saved_count
        }

    except Exception as exc:
        logger.error(f"Scraping failed: {str(exc)}")
        db.rollback()
        raise self.retry(exc=exc, countdown=120)

    finally:
        db.close()
