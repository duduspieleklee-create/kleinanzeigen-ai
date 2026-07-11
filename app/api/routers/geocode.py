"""Results-map geocoding endpoint.

The dashboard map POSTs the distinct location strings of the currently shown
results and gets back coordinates, so the browser never talks to Nominatim
directly (see app/shared/geocoding.py for the why). Cache hits are returned
immediately; a bounded number of cache misses are geocoded inline per request
(Nominatim is rate-limited to ~1 req/s), and anything past that budget comes
back null and is filled on a later open once the cache has warmed.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.security import limiter
from app.shared.database import get_db
from app.shared.geocoding import geocode, normalize_location
from app.shared.models import GeocodeCache, User
from app.shared.plans import plan_config

router = APIRouter()

# Bound the work a single request can trigger. Results are capped at 25/search
# so distinct locations are few; the cap plus the per-request network budget
# keep latency and outbound Nominatim volume in check.
_MAX_LOCATIONS = 60
_MAX_NETWORK_LOOKUPS = 12


class GeocodeRequest(BaseModel):
    locations: list[str] = Field(default_factory=list)


@router.post("/api/geocode")
@limiter.limit("60/minute")
def geocode_locations(
    request: Request,
    payload: GeocodeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Map each requested location string to ``{"lat","lon"}`` or ``null``.

    Keyed by the ORIGINAL strings the client sent, so it can match markers back
    to its cards. Distinct places are resolved once (normalised key); cache hits
    are free, misses are geocoded up to a per-request budget.
    """
    # The map is a Pro-only feature — gate the endpoint too (defense in depth:
    # the UI already hides it for non-Pro, see dashboard.html show_map).
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not (user and (user.is_admin or plan_config(user.plan).get("map_view"))):
        raise HTTPException(status_code=403, detail="Die Kartenansicht ist ein Pro-Feature.")

    # Distinct normalised keys → the original strings that map to them.
    originals_by_key: dict[str, list[str]] = {}
    for raw in payload.locations[:_MAX_LOCATIONS]:
        key = normalize_location(raw)
        if key:
            originals_by_key.setdefault(key, []).append(raw)

    result: dict[str, dict | None] = {raw: None for raw in payload.locations}

    # Serve everything already cached (positive or negative) in one query, for
    # free — no network, no budget spent.
    keys = list(originals_by_key)
    cached = {
        row.location: row
        for row in db.query(GeocodeCache).filter(GeocodeCache.location.in_(keys)).all()
    }
    misses = []
    for key in keys:
        row = cached.get(key)
        if row is None:
            misses.append(key)
            continue
        coords = None if row.lat is None or row.lon is None else {"lat": row.lat, "lon": row.lon}
        for raw in originals_by_key[key]:
            result[raw] = coords

    # Geocode misses inline, up to the budget; the rest stay null this call.
    for key in misses[:_MAX_NETWORK_LOOKUPS]:
        coords = geocode(key, db)
        for raw in originals_by_key[key]:
            result[raw] = coords

    return result
