"""Common URL building utilities shared across services."""
from urllib.parse import urljoin, urlencode


def build_url(base: str, path: str, params: dict | None = None) -> str:
    """Build a full URL from base, path, and optional query params."""
    url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    if params:
        url = f"{url}?{urlencode(params)}"
    return url
