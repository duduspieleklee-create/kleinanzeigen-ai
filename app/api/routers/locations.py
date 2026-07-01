import requests as _requests
from fastapi import APIRouter, Query, HTTPException

router = APIRouter()

_KA_SUGGEST_URL = "https://www.kleinanzeigen.de/s-ort-empfehlungen.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


@router.get("/suggest")
def location_suggest(q: str = Query(..., min_length=1, max_length=100)):
    """
    Proxy for the kleinanzeigen.de location autocomplete API.
    Returns a list of {id, label} objects — id is the numeric locationId
    used to build canonical search URLs (k0l{id}r{radius}).
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
