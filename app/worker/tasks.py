from app.worker.celery_app import celery_app
from app.shared.url_builder import build_kleinanzeigen_url
import time


@celery_app.task(name="scrape.kleinanzeigen", bind=True, max_retries=3)
def scrape_kleinanzeigen(self, parameters: dict):
    """
    Celery task to scrape kleinanzeigen.de.
    This is a simplified version for Milestone 1.
    """
    try:
        # Build the search URL from parameters
        url = build_kleinanzeigen_url(**parameters)
        print(f"Starting scrape for URL: {url}")

        # TODO: Replace this with actual scraping logic (requests + BeautifulSoup)
        # For now, we simulate the scraping work
        time.sleep(5)  # Simulate scraping time

        result = {
            "status": "success",
            "url": url,
            "message": "Scraping completed (simulated)"
        }

        print(f"Scrape completed: {result}")
        return result

    except Exception as exc:
        print(f"Error during scraping: {exc}")
        # Retry the task up to 3 times
        raise self.retry(exc=exc, countdown=60)
