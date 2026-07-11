"""
API-Endpunkte für Smart Search Suggestions.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi_limiter.depends import RateLimiter
from pyrate_limiter import Duration, Limiter, Rate

from app.ai.smart_search_suggestions import smart_search

router = APIRouter(prefix="/api", tags=["smart_search"])
_suggestion_limiter = Limiter(Rate(10, Duration.SECOND * 60))


@router.get(
    "/search-suggestions",
    summary="Generiere Suchvorschläge",
    dependencies=[Depends(RateLimiter(limiter=_suggestion_limiter))],
)
def get_search_suggestions(query: str):
    """
    Generiert Suchvorschläge für eine Nutzeranfrage.

    Parameter:
        query (str): Die Suchanfrage des Nutzers (z. B. "Auto kaufen")

    Rückgabe:
        dict: {
            "query": "Auto kaufen",
            "suggestions": {
                "Synonyme für 'Auto'": ["PKW", "Wagen", "Fahrzeug"],
                "Verwandte Begriffe für 'Auto'": ["Reifen", "Motor", "Fahrer"]
            }
        }
    """
    try:
        suggestions = smart_search.get_suggestions(query)
        return {
            "query": query,
            "suggestions": suggestions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))