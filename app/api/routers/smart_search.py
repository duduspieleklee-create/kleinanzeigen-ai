"""
API-Endpunkte für Smart Search Suggestions.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from fastapi_limiter.depends import RateLimiter
from pyrate_limiter import Duration, Limiter, Rate
from sqlalchemy.orm import Session

from app.api.config import settings
from app.ai.smart_search_suggestions import smart_search
from app.shared.database import get_db
from app.shared.models import SearchSuggestion

logger = logging.getLogger("kleinanzeigen-ai")

router = APIRouter(prefix="/api", tags=["smart_search"])
_suggestion_limiter = Limiter(Rate(10, Duration.SECOND * 60))


def _persist_suggestions(query: str, suggestions: dict, db: Session):
    """Speichere/erhöhe Vorschläge in der search_suggestions DB-Tabelle.

    Bestehende Einträge werden hochgezählt, neue angelegt. Fehler werden
    geloggt aber nicht propagiert — Persistenz darf nie blockierend wirken.
    """
    if not suggestions or not hasattr(db, "query"):
        return
    try:
        for suggestion_type, terms in suggestions.items():
            for term in terms:
                existing = (
                    db.query(SearchSuggestion)
                    .filter(
                        SearchSuggestion.keyword == query,
                        SearchSuggestion.suggestion == term,
                        SearchSuggestion.suggestion_type == suggestion_type,
                    )
                    .first()
                )
                if existing:
                    existing.usage_count = (existing.usage_count or 0) + 1
                else:
                    db.add(
                        SearchSuggestion(
                            keyword=query,
                            suggestion=term,
                            suggestion_type=suggestion_type,
                            usage_count=1,
                        )
                    )
        db.commit()
    except Exception:
        logger.warning("Persistenz der Suchvorschläge fehlgeschlagen", exc_info=True)
        db.rollback()


@router.get(
    "/search-suggestions",
    summary="Generiere Suchvorschläge",
    dependencies=[Depends(RateLimiter(limiter=_suggestion_limiter))],
)
def get_search_suggestions(query: str, db: Session = Depends(get_db)):
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
        _persist_suggestions(query, suggestions, db)
        return {
            "query": query,
            "suggestions": suggestions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/custom-model/provider-presets", summary="Liste Provider-Presets")
def get_custom_model_provider_presets():
    """
    Gibt die verfügbaren Provider-Presets für den Custom-Model-Endpoint zurück.

    Rückgabe:
        dict: {
            "providers": {
                "ollama": {"id": "ollama", "label": "Ollama", "endpoint": "...", "needs_api_key": false},
                ...
            }
        }
    """
    return {"providers": settings.custom_model_provider_presets()}