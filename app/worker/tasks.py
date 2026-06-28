from app.worker.celery_app import celery_app

@celery_app.task(name="scrape.kleinanzeigen")
def scrape_kleinanzeigen(url: str):
    # TODO: Replace with real scraping logic (requests + BeautifulSoup)
    print(f"Scraping URL: {url}")
    return {"status": "success", "url": url}
