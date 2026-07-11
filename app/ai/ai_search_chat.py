"""
Chat-basierter KI-Such-Assistent für kleinanzeigen-ai.

Der User unterhält sich mit der KI, die nach und nach die Suchparameter
erfragt und dann passende Ergebnisse liefert — iterativ verfeinerbar.
"""

import logging
from app.ai.ai_search import parse_query

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


def build_chat_response(conversation: list[dict]) -> dict:
    """
    Verarbeitet den gesamten Chat-Verlauf und gibt eine Antwort.

    conversation: Liste von {"role": "user"|"assistant", "content": "..."}
    Rückgabe: {"reply": "...", "search_results": [...], "search_text": "..."}
    """
    # Extrahiere den gesamten User-Text
    user_texts = [m["content"] for m in conversation if m["role"] == "user"]
    full_query = " ".join(user_texts)

    parsed = parse_query(full_query)
    kw = parsed.get("keywords", [])
    price_min = parsed.get("price_min")
    price_max = parsed.get("price_max")
    location = parsed.get("location", "")
    category = parsed.get("category", "")

    result: dict = {"reply": "", "search_results": None, "search_text": ""}

    # Noch nicht genug Info → nachfragen
    if not kw and not category:
        result["reply"] = _MISSING_KEYWORDS
        return result

    if price_max is None and price_min is None:
        # Nur beim ersten Mal fragen
        has_asked_price = any(
            "Preis" in m.get("content", "")
            for m in conversation
            if m["role"] == "assistant"
        )
        if not has_asked_price:
            result["reply"] = _MISSING_PRICE
            return result

    if not location:
        has_asked_location = any(
            "Stadt" in m.get("content", "") or "Region" in m.get("content", "")
            for m in conversation
            if m["role"] == "assistant"
        )
        if not has_asked_location:
            result["reply"] = _MISSING_LOCATION
            return result

    # Genug Info → Suche ausführen
    search_text_parts = []
    if kw:
        search_text_parts.append(" ".join(kw[:3]))
    if category:
        search_text_parts.append(f"({category})")
    price_str = ""
    if price_min and price_max:
        price_str = f"{price_min}€–{price_max}€"
    elif price_max:
        price_str = f"bis {price_max}€"
    elif price_min:
        price_str = f"ab {price_min}€"
    if price_str:
        search_text_parts.append(price_str)
    if location:
        search_text_parts.append(f"in {location}")

    summary = " ".join(search_text_parts) if search_text_parts else full_query
    result["search_text"] = summary
    result["reply"] = _CONFIRM_SEARCH.format(summary=summary)

    return result


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
