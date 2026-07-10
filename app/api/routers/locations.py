import requests as _requests
from fastapi import APIRouter, Depends, Query, Request, HTTPException

from app.api.dependencies import get_current_user
from app.api.security import limiter
from app.shared.locations_client import suggest_locations

router = APIRouter()


@router.get("/suggest")
@limiter.limit("30/minute")
def location_suggest(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100),
    current_user: dict = Depends(get_current_user),
):
    """
    Proxy for the kleinanzeigen.de location autocomplete API.
    Returns a list of {id, label} objects — id is the numeric locationId
    used to build canonical search URLs (k0l{id}r{radius}).

    Auth-gated (only used from the logged-in search wizard) and rate-limited
    — this was previously an open, unauthenticated proxy to an external API.
    """
    try:
        return suggest_locations(q)
    except _requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Location service unavailable") from exc
