"""
API-Endpunkte für den KI-gestützten Such-Assistenten.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.ai_search import parse_query, extract_keywords_for_search, generate_search_text, rank_results
from app.shared.database import get_db
from app.shared.models import ScrapeResult

router = APIRouter(prefix="/api", tags=["ai_search"])


class AISearchRequest(BaseModel):
    query: str


class AISearchFeedback(BaseModel):
    query: str
    liked: list[int] = []
    disliked: list[int] = []


@router.post("/ai-search", summary="KI-Suche mit natürlichsprachlicher Beschreibung")
def ai_search(payload: AISearchRequest, db: Session = Depends(get_db)):
    """Nimmt eine natürlichsprachliche Beschreibung entgegen und findet passende Ergebnisse."""
    if not payload.query or len(payload.query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Bitte gib eine Beschreibung ein (min. 3 Zeichen)")

    parsed = parse_query(payload.query)
    keyword = extract_keywords_for_search(parsed)
    results = _fetch_matching_results(keyword, db)

    ranked = rank_results(results, payload.query)

    return {
        "query": payload.query,
        "parsed": {
            "keywords": parsed.get("keywords", []),
            "category": parsed.get("category", ""),
            "price_min": parsed.get("price_min"),
            "price_max": parsed.get("price_max"),
            "location": parsed.get("location", ""),
        },
        "search_text": generate_search_text(parsed),
        "results": ranked[:15],
        "total": len(ranked),
    }


@router.post("/ai-search/feedback", summary="Feedback geben und Suche verfeinern")
def ai_search_feedback(payload: AISearchFeedback, db: Session = Depends(get_db)):
    """Verfeinert die Suche basierend auf User-Feedback (like/dislike)."""
    parsed = parse_query(payload.query)
    keyword = extract_keywords_for_search(parsed)
    results = _fetch_matching_results(keyword, db)

    ranked = rank_results(results, payload.query, liked_ids=set(payload.liked))
    filtered = [r for r in ranked if r["id"] not in payload.disliked]

    return {
        "query": payload.query,
        "results": filtered[:15],
        "total": len(filtered),
        "removed": len(ranked) - len(filtered),
    }


def _fetch_matching_results(keyword: str, db: Session) -> list[dict]:
    """Holt Ergebnisse die zu den Keywords passen."""
    if not keyword:
        return []
    terms = keyword.lower().split()
    if not terms:
        return []
    rows = (
        db.query(ScrapeResult)
        .filter(ScrapeResult.title.ilike(f"%{terms[0]}%"))
        .limit(30)
        .all()
    )
    results = []
    for r in rows:
        title = (r.title or "").lower()
        desc = (r.description or "").lower()
        text = title + " " + desc
        if all(t in text for t in terms[:3]):
            results.append({
                "id": r.id,
                "title": r.title,
                "price": r.price,
                "price_value": r.price_value,
                "location": r.location,
                "url": r.url,
                "image_url": r.image_url,
                "trust_score": r.trust_score,
            })
    return results
