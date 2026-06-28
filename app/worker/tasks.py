import logging
from app.worker.celery_app import celery_app
from app.shared.url_builder import build_search_url

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.run_scrape", max_retries=3)
def run_scrape(self, category: str, location: str = "", max_pages: int = 5) -> dict:
    """Scrape listings for a given category and location."""
    try:
        logger.info("Starting scrape: category=%s location=%s pages=%d", category, location, max_pages)
        results = []
        for page in range(1, max_pages + 1):
            url = build_search_url(category=category, location=location, page=page)
            logger.debug("Scraping page %d: %s", page, url)
            # TODO: implement actual HTTP scraping logic here
            results.append({"page": page, "url": url, "listings": []})
        logger.info("Scrape complete: %d pages processed", len(results))
        return {"status": "done", "pages": len(results)}
    except Exception as exc:
        logger.error("Scrape failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
