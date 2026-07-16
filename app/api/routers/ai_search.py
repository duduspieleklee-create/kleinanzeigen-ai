"""
API-Endpunkte für den KI-gestützten Such-Assistenten + Chat.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.ai_search import parse_query, extract_keywords_for_search, generate_search_text, rank_results
from app.ai.ai_search_chat import build_chat_response, format_results_as_chat, GREETING
from app.shared.database import get_db
from app.api.config import Settings
import httpx
from app.shared.models import ScrapeResult

router = APIRouter(prefix="/api", tags=["ai_search"])


class AISearchRequest(BaseModel):
    query: str


class AISearchFeedback(BaseModel):
    query: str
    liked: list[int] = []
    disliked: list[int] = []


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str
    search_text: str = ""
    results: list[dict] = []
    total: int = 0
    llm_connected: bool = False
    model_name: str = ""
    llm_error: str = ""




@router.post("/ai-search", summary="KI-Suche mit natürlichsprachlicher Beschreibung")
def ai_search(payload: AISearchRequest, db: Session = Depends(get_db)):
    if not payload.query or len(payload.query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Bitte gib eine Beschreibung ein (min. 3 Zeichen)")
    parsed = parse_query(payload.query)
    keyword = extract_keywords_for_search(parsed)
    results = _fetch_matching_results(keyword, db)
    ranked = rank_results(results, payload.query)
    return {
        "query": payload.query,
        "parsed": {"keywords": parsed.get("keywords", []), "category": parsed.get("category", ""),
                    "price_min": parsed.get("price_min"), "price_max": parsed.get("price_max"),
                    "location": parsed.get("location", "")},
        "search_text": generate_search_text(parsed),
        "results": ranked[:15],
        "total": len(ranked),
    }


@router.post("/ai-search/feedback", summary="Feedback geben und Suche verfeinern")
def ai_search_feedback(payload: AISearchFeedback, db: Session = Depends(get_db)):
    parsed = parse_query(payload.query)
    keyword = extract_keywords_for_search(parsed)
    results = _fetch_matching_results(keyword, db)
    ranked = rank_results(results, payload.query, liked_ids=set(payload.liked))
    filtered = [r for r in ranked if r["id"] not in payload.disliked]
    return {"query": payload.query, "results": filtered[:15], "total": len(filtered), "removed": len(ranked) - len(filtered)}


@router.post("/ai-search/chat", summary="Chat-basierte KI-Suche")
def ai_search_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """Chat: User unterhält sich, KI fragt nach, sucht, zeigt Ergebnisse."""
    msgs = [{"role": m.role, "content": m.content} for m in payload.messages]

    # Determine if the LLM is reachable/enabled
    settings = Settings()
    llm_connected = False
    model_name = ""
    llm_error = ""
    if settings.custom_model_enabled:
        model_name = settings.custom_model_name or ""
        try:
            if settings.custom_model_provider == "ollama":
                # Ollama's /api/tags lives at the base URL, not under /v1.
                # CUSTOM_MODEL_ENDPOINT typically points at the OpenAI-compatible
                # /v1 root, so strip it before appending the native Ollama path.
                base_url = settings.custom_model_endpoint_resolved.rstrip("/")
                if base_url.endswith("/v1"):
                    base_url = base_url[:-3]
                health_url = f"{base_url}/api/tags"
                resp = httpx.get(health_url, timeout=2.0)
            else:
                health_url = f"{settings.custom_model_endpoint_resolved}/v1/models"
                resp = httpx.post(health_url, timeout=2.0)
            resp.raise_for_status()
            llm_connected = True
        except Exception as e:
            llm_connected = False
            llm_error = f"LLM connection failed: {str(e)}"


    if len(msgs) <= 1:
        return ChatResponse(
            reply=GREETING,
            llm_connected=llm_connected,
            model_name=model_name,
            llm_error=llm_error,
        )


    chat_result = build_chat_response(msgs)

    if chat_result["search_text"]:
        parsed = parse_query(" ".join(m["content"] for m in msgs if m["role"] == "user"))
        keyword = extract_keywords_for_search(parsed)
        results = _fetch_matching_results(keyword, db)
        ranked = rank_results(results, chat_result["search_text"])

        reply = format_results_as_chat(ranked[:15], len(ranked))
        return ChatResponse(reply=reply, search_text=chat_result["search_text"], results=ranked[:15], total=len(ranked), llm_connected=llm_connected, model_name=model_name, llm_error=llm_error)
    return ChatResponse(reply=chat_result["reply"], llm_connected=llm_connected, model_name=model_name, llm_error=llm_error)

def _fetch_matching_results(keyword: str, db: Session) -> list[dict]:
    if not keyword:
        return []
    terms = keyword.lower().split()
    if not terms:
        return []
    rows = db.query(ScrapeResult).filter(ScrapeResult.title.ilike(f"%{terms[0]}%")).limit(30).all()
    results = []
    for r in rows:
        title = (r.title or "").lower()
        desc = (r.description or "").lower()
        text = title + " " + desc
        if all(t in text for t in terms[:3]):
            results.append({
                "id": r.id, "title": r.title, "price": r.price,
                "price_value": r.price_value, "location": r.location,
                "url": r.url, "image_url": r.image_url, "trust_score": r.trust_score,
            })
    return results
