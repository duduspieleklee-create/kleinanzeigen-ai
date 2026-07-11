"""Server-side geocoding for the results map, backed by a DB cache.

Why this is server-side: the dashboard map used to call
nominatim.openstreetmap.org directly from every visitor's browser on every
map open. That hammered a free community service, violated its ~1 req/s usage
policy (risking a 403/429 block of the app's egress IP), and re-geocoded the
same handful of cities over and over. Here the API geocodes each distinct
location string once, stores the result in ``GeocodeCache``, and serves every
later request (and every other user) from the DB — Nominatim is only ever hit
for a genuinely new location.

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
requires an identifying User-Agent and at most ~1 request/second; both are
enforced here. Heavy growth should move to a self-hosted or paid geocoder, but
with the cache in front the live call volume stays tiny.
"""
import re
import threading
import time
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.shared.models import GeocodeCache

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim asks for a genuine, identifying User-Agent (contact included) so
# they can reach the operator if a client misbehaves — a browser-style UA is
# explicitly discouraged for API use.
_HEADERS = {
    "User-Agent": "kleinanzeigen-ai/1.0 (results map geocoding; +https://kleeblatt.space)"
}

# Nominatim allows at most ~1 request/second. Serialise outbound calls and
# space them so a burst of new locations can never exceed the limit. This
# guards a single process; the DB cache keeps cross-process volume negligible.
_MIN_INTERVAL_S = 1.1
_rate_lock = threading.Lock()
_last_call_at = 0.0


def normalize_location(location: str) -> str:
    """Normalise a raw location string into a stable cache key.

    Lower-cases and collapses whitespace so "10115 Berlin" and "10115  berlin"
    share a single cache row (and a single Nominatim lookup).
    """
    return re.sub(r"\s+", " ", (location or "").strip().lower())


def _query_nominatim(location: str, timeout: float) -> Optional[tuple[float, float]]:
    """Call Nominatim for a single location, rate-limited. None if not found."""
    global _last_call_at
    with _rate_lock:
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = requests.get(
                _NOMINATIM_URL,
                params={"q": f"{location}, Germany", "format": "json", "limit": 1},
                headers=_HEADERS,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        finally:
            _last_call_at = time.monotonic()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"])


def geocode(location: str, db: Session, timeout: float = 6.0) -> Optional[dict]:
    """Resolve one location string to ``{"lat": .., "lon": ..}`` or ``None``.

    Cache-first: a hit (positive or negative) never touches the network. A miss
    queries Nominatim once and stores the outcome — including a NULL/NULL row
    for "not found", so an unresolvable string isn't re-queried on every call.
    Never raises on a network/HTTP error: it returns None (and does not cache),
    so a transient Nominatim outage just yields no marker, not a 500.
    """
    key = normalize_location(location)
    if not key:
        return None

    row = db.query(GeocodeCache).filter(GeocodeCache.location == key).first()
    if row is not None:
        if row.lat is None or row.lon is None:
            return None  # negative cache hit
        return {"lat": row.lat, "lon": row.lon}

    try:
        coords = _query_nominatim(key, timeout)
    except requests.RequestException:
        return None  # transient failure — don't poison the cache

    lat, lon = (coords if coords else (None, None))
    # Another concurrent request may have inserted the same key meanwhile;
    # tolerate the unique-constraint race and fall back to the stored value.
    row = GeocodeCache(location=key, lat=lat, lon=lon)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        existing = db.query(GeocodeCache).filter(GeocodeCache.location == key).first()
        if existing and existing.lat is not None and existing.lon is not None:
            return {"lat": existing.lat, "lon": existing.lon}
        return {"lat": lat, "lon": lon} if coords else None

    return {"lat": lat, "lon": lon} if coords else None
