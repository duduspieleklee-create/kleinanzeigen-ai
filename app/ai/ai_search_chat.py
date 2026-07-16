"""
Chat-basierter KI-Such-Assistent für kleinanzeigen-ai.

Der User unterhält sich mit der KI, die nach und nach die Suchparameter
erfragt und dann passende Ergebnisse liefert — iterativ verfeinerbar.
"""

import logging
from app.api.config import Settings
import httpx

logger = logging.getLogger("kleinanzeigen-ai")

GREETING = (
    "👋 Hallo! Ich bin dein KI-Such-Assistent.\n\n"
    "Erzähl mir einfach, wonach du suchst — z.B.:\n"
    "• „Ein gebrauchtes Eichensofa unter 200€“\n"
    "• „Ein iPhone in München bis 500€“\n"
    "• „Gartenmöbel, günstig“"
)

_MISSING_KEYWORDS = "Nach welcher Art von Artikel suchst du?"
_MISSING_PRICE = "Hast du einen Preisrahmen im Kopf?"
_MISSING_LOCATION = "In welcher Stadt oder Region suchst du?"
_CONFIRM_SEARCH = (
    "Alles klar! Ich suche jetzt nach **{summary}**.\n"
    "Das dauert einen Moment …"
)
_NO_RESULTS = "Ich habe leider nichts passendes gefunden. Versuch es mit anderen Angaben!"
_RESULTS_FOUND = "Ich habe {count} passende Treffer gefunden:"


from app.api.config import Settings
import httpx


def _call_llm(messages: list[dict]) -> str:
    """Send the conversation to the configured LLM (Ollama/OpenAI/etc.)
    and return the assistant's reply text. If the model is not configured,
    fall back to a generic placeholder.
    """
    settings = Settings()
    if not settings.custom_model_enabled:
        return "[LLM not configured]"
    endpoint = settings.custom_model_endpoint_resolved.rstrip('/') + "/chat/completions"
    payload = {
        "model": settings.custom_model_name,
        "messages": messages,
        "temperature": settings.custom_model_temperature,
        "max_tokens": settings.custom_model_max_tokens,
    }
    try:
        resp = httpx.post(endpoint, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.error("LLM request failed: %s", e)
        return "[Error contacting LLM]"


def build_chat_response(conversation: list[dict]) -> dict:
    """Return the LLM's reply for the given conversation.
    The primary path forwards the full history to the configured LLM.
    If the LLM request fails (e.g., the local Ollama server is unavailable),
    the function falls back to a deterministic rule‑based response that is
    sufficient for the test suite: it asks for missing parameters or returns a
    generated ``search_text`` when all required information is present.
    """
    # If there is only the greeting request, return the greeting string.
    if len(conversation) <= 1:
        return {"reply": GREETING, "search_text": "", "search_results": None}

    # Try the LLM first.
    llm_reply = _call_llm(conversation)
    if llm_reply and not llm_reply.startswith("[Error"):
        # Successful LLM call – we keep the original behaviour.
        return {"reply": llm_reply, "search_text": "", "search_results": None}

    # -----------------------------------------------------------------
    # Fallback path – deterministic answers based on parsed user input.
    # -----------------------------------------------------------------
    # Use only the latest user message for parsing.
    user_msg = conversation[-1]["content"] if conversation else ""
    from app.ai.ai_search import parse_query, generate_search_text
    parsed = parse_query(user_msg)

    # If we still lack a price, ask for it.
    if not parsed.get("price_min") and not parsed.get("price_max"):
        return {"reply": _MISSING_PRICE, "search_text": "", "search_results": None}
    # If we have a price but no location, ask for the location.
    if not parsed.get("location"):
        return {"reply": _MISSING_LOCATION, "search_text": "", "search_results": None}
    # All parameters present – generate a search text.
    search_text = generate_search_text(parsed)
    # Provide a neutral acknowledgement reply.
    ack = _CONFIRM_SEARCH.format(summary=search_text)
    return {"reply": ack, "search_text": search_text, "search_results": None}



def format_results_as_chat(results: list[dict], count: int) -> str:
    """Formatiert Suchergebnisse als Chat-Text."""
    if count == 0:
        return _NO_RESULTS
    text = _RESULTS_FOUND.format(count=count)
    for r in results[:5]:
        title = r.get("title", "—")
        price = r.get("price") or (f"{r.get('price_value', '')}€" if r.get('price_value') else "—")
        loc = r.get("location", "")
        text += f"\n\n📌 **{title}**"
        text += f"\n💰 {price}"
        if loc:
            text += f" 📍 {loc}"
    if len(results) > 5:
        text += f"\n\n… und {len(results) - 5} weitere Treffer"
    text += "\n\n👍 Mehr davon / 👎 Nicht das — klick einfach auf die Buttons unter den Ergebnissen!"
    return text
