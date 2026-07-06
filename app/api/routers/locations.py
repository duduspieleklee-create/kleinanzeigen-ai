import requests as _requests
from fastapi import APIRouter, Depends, Query, Request, HTTPException

from app.api.dependencies import get_current_user
from app.api.security import limiter

router = APIRouter()

_KA_SUGGEST_URL = "https://www.kleinanzeigen.de/s-ort-empfehlungen.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


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
        resp = _requests.get(
            _KA_SUGGEST_URL,
            params={"query": q},
            headers=_HEADERS,
            timeout=5,
        )
        resp.raise_for_status()
    except _requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Location service unavailable") from exc

    return [
        {"id": key.lstrip("_"), "label": label}
        for key, label in resp.json().items()
        if key != "_0"  # skip the "Deutschland" catch-all entry
    ]
