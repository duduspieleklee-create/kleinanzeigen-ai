"""
API-Endpunkte für Smart Search Suggestions.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.dependencies import require_admin, get_current_user
from app.ai.smart_search_suggestions import smart_search
from app.shared.database import get_db
from app.shared.models import SearchSuggestion, SystemSetting
from app.api.security import limiter

router = APIRouter(prefix="/api", tags=["smart_search"])


@router.get("/search-suggestions", summary="Generiere Suchvorschläge")
@limiter.limit("20/minute")
def get_search_suggestions(request: Request, query: str, current_user: dict = Depends(get_current_user)):
    """Generiert Suchvorschläge für eine Nutzeranfrage."""
    try:
        suggestions = smart_search.get_suggestions(query)
        # Normalize keyword to lowercase for consistent storage
        normalized_keyword = query.lower()
        _persist_suggestions(normalized_keyword, suggestions, db)
        return {"query": query, "suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _persist_suggestions(keyword: str, suggestions: dict, db: Session):
    """Speichert Vorschläge in der DB oder inkrementiert usage_count (Issue #266)."""
    from app.shared.models import SearchSuggestion

    for group_key, terms in suggestions.items():
        suggestion_type = group_key.split(" für ")[0].strip()
        for term in terms:
            existing = (
                db.query(SearchSuggestion)
                .filter(
                    SearchSuggestion.keyword == keyword,
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
                        keyword=keyword,
                        suggestion=term,
                        suggestion_type=suggestion_type,
                        usage_count=1,
                    )
                )
    db.commit()


# ── Click Tracking (Issue #269) ────────────────────────────────────────────

class ClickPayload(BaseModel):
    keyword: str
    suggestion: str
    suggestion_type: Optional[str] = "generic"


@router.post("/search-suggestions/click", summary="Trackt einen Klick auf einen Vorschlag")
def track_suggestion_click(payload: ClickPayload, db: Session = Depends(get_db)):
    """Inkrementiert click_count für einen angeklickten Vorschlag."""
    existing = db.query(SearchSuggestion).filter(
        SearchSuggestion.keyword == payload.keyword.lower(),
        SearchSuggestion.suggestion == payload.suggestion,
        SearchSuggestion.suggestion_type == payload.suggestion_type,
    ).first()
    if existing:
        existing.click_count = (existing.click_count or 0) + 1
    else:
        db.add(SearchSuggestion(
            keyword=payload.keyword.lower(),
            suggestion=payload.suggestion,
            suggestion_type=payload.suggestion_type,
            click_count=1,
        ))
    db.commit()
    return {"status": "ok"}


class ImpressionPayload(BaseModel):
    keyword: str
    suggestion: str
    suggestion_type: str = "generic"


@router.post("/search-suggestions/impression", summary="Trackt eine Impression")
def track_suggestion_impression(payload: ImpressionPayload, db: Session = Depends(get_db)):
    """Inkrementiert usage_count wenn ein Vorschlag angezeigt wurde."""
    existing = db.query(SearchSuggestion).filter(
        SearchSuggestion.keyword == payload.keyword.lower(),
        SearchSuggestion.suggestion == payload.suggestion,
        SearchSuggestion.suggestion_type == payload.suggestion_type,
    ).first()
    if existing:
        existing.usage_count = (existing.usage_count or 0) + 1
    else:
        db.add(SearchSuggestion(
            keyword=payload.keyword.lower(),
            suggestion=payload.suggestion,
            suggestion_type=payload.suggestion_type,
            usage_count=1,
        ))
    db.commit()
    return {"status": "ok"}


# ── Provider-Presets (read-only) ──────────────────────────────────────────

@router.get("/custom-model/provider-presets", summary="Liste Provider-Presets")
def get_custom_model_provider_presets():
    """Gibt die verfügbaren Provider-Presets zurück."""
    return {"providers": settings.custom_model_provider_presets()}


# ── Admin: Custom Model Settings (Issue #268) ─────────────────────────────

class CustomModelSettingsPayload(BaseModel):
    provider: str = ""
    endpoint: str = ""
    api_key: str = ""
    model_name: str = ""
    temperature: float = 0.3
    max_tokens: int = 256


@router.get("/custom-model/config", summary="Zeigt aktuelle Custom-Model-Konfiguration")
def get_custom_model_config(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: Liest die Custom-Model-Konfiguration aus .env + DB-Overrides."""
    def _get(key: str, default: str = "") -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        val = row.value if row else None
        return val or default

    return {
        "provider": _get("custom_model_provider", settings.custom_model_provider),
        "endpoint": _get("custom_model_endpoint", settings.custom_model_endpoint),
        "api_key_configured": bool(_get("custom_model_api_key", settings.custom_model_api_key)),
        "model_name": _get("custom_model_name", settings.custom_model_name),
        "temperature": float(_get("custom_model_temperature", str(settings.custom_model_temperature))),
        "max_tokens": int(_get("custom_model_max_tokens", str(settings.custom_model_max_tokens))),
        "providers": settings.custom_model_provider_presets(),
        "active_endpoint": settings.custom_model_endpoint_resolved,
        "active_model": settings.custom_model_name,
        "disabled": not bool(settings.custom_model_endpoint_resolved and settings.custom_model_name),
    }


@router.post("/custom-model/config", summary="Speichert Custom-Model-Konfiguration")
def save_custom_model_config(
    payload: CustomModelSettingsPayload,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: Persistiert Custom-Model-Konfiguration in der DB."""
    def _upsert(key: str, value: str):
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(SystemSetting(key=key, value=value))

    _upsert("custom_model_provider", payload.provider)
    _upsert("custom_model_endpoint", payload.endpoint)
    _upsert("custom_model_api_key", payload.api_key)
    _upsert("custom_model_name", payload.model_name)
    _upsert("custom_model_temperature", str(payload.temperature))
    _upsert("custom_model_max_tokens", str(payload.max_tokens))
    db.commit()

    return {"status": "saved", "note": "Settings stored. Restart containers to apply (docker compose up -d)."}


# ── Admin: Top-Clicked Suggestions ────────────────────────────────────────

@router.get("/custom-model/top-suggestions", summary="Admin: Top-geklickte Vorschläge")
def get_top_suggestions(
    limit: int = 20,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only: listet die meistgeklickten Suchvorschläge."""
    rows = (
        db.query(SearchSuggestion)
        .order_by(SearchSuggestion.click_count.desc())
        .limit(limit)
        .all()
    )
    return {
        "suggestions": [
            {
                "keyword": r.keyword,
                "suggestion": r.suggestion,
                "type": r.suggestion_type,
                "impressions": r.usage_count or 0,
                "clicks": r.click_count or 0,
            }
            for r in rows
        ]
    }
