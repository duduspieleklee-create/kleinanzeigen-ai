"""Shared kleinanzeigen.de location-suggestion client.

Factored out of ``app/api/routers/locations.py`` so both the public
``/locations/suggest`` HTTP endpoint AND server-side search creation can
resolve a free-text location to a numeric ``locationId`` without duplicating
the network call.

The rate limiter (``30/minute``) lives ONLY on the HTTP endpoint
(``locations.py``), never here — internal reuse must not inherit the public
endpoint's throttle.
"""
import requests

_KA_SUGGEST_URL = "https://www.kleinanzeigen.de/s-ort-empfehlungen.json"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def suggest_locations(q: str, timeout: float = 5.0) -> list[dict]:
    """Return ``[{"id": ..., "label": ...}, ...]`` for the given query.

    Raises ``requests.RequestException`` on network/HTTP failure so each
    caller decides how to fail: the HTTP endpoint turns it into a 502, while
    server-side search creation fails soft (see ``create_scrape``).
    """
    resp = requests.get(
        _KA_SUGGEST_URL,
        params={"query": q},
        headers=_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    return [
        {"id": key.lstrip("_"), "label": label}
        for key, label in resp.json().items()
        if key != "_0"  # skip the "Deutschland" catch-all entry
    ]
