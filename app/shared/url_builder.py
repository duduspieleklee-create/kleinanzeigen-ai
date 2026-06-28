"""Dynamic URL builder for kleinanzeigen.de search URLs."""

BASE_URL = "https://www.kleinanzeigen.de"


def build_search_url(category: str, location: str = "", page: int = 1) -> str:
    """Build a kleinanzeigen.de search URL.

    Args:
        category: The category slug (e.g. "fahrzeuge", "elektronik").
        location: Optional city or region filter.
        page: Page number (1-indexed).

    Returns:
        Full URL string ready for scraping.
    """
    parts = [BASE_URL, "s"]
    if location:
        parts.append(location.lower().replace(" ", "-"))
    parts.append(category)
    if page > 1:
        parts.append(f"seite:{page}")
    return "/".join(parts)


def build_listing_url(listing_id: str, slug: str) -> str:
    """Build a direct listing URL from its ID and slug."""
    return f"{BASE_URL}/s-anzeige/{slug}/{listing_id}"
