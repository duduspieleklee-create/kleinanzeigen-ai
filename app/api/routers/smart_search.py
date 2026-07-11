"""
API-Endpunkte für Smart Search Suggestions.
"""

from fastapi import APIRouter, HTTPException
from app.ai.smart_search_suggestions import smart_search

router = APIRouter(prefix="/api", tags=["smart_search"])


@router.get("/search-suggestions", summary="Generiere Suchvorschläge")
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