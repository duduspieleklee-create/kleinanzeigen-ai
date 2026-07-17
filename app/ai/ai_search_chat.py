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
SYSTEM_PROMPT = """
You are a helpful, concise AI assistant for the Kleinanzeigen‑AI web app.
- Keep answers under 3 sentences unless the user asks for details.
- For project/Docker/OAuth questions, answer directly and briefly.
- Never fabricate data; if you don't know, say so.
"""

_MAX_DOC_SNIPPET_CHARS = 2000
_MAX_MATCHED_DOCS = 2


def _fetch_relevant_docs(query: str) -> list[dict]:
    """Very simple RAG: read all *.md files in the repository and return
    those that contain any word from the query. Returns a list of dicts with
    'title' and 'content' fields that can be injected as a system message.
    This is lightweight and does not require an external vector store.
    """
    import os
    docs = []
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    for root, _, files in os.walk(repo_root):
        for f in files:
            if f.lower().endswith('.md'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8') as fp:
                        text = fp.read()
                    keywords = [w.lower() for w in query.split() if len(w) > 2]
                    if any(kw in text.lower() for kw in keywords):
                        title = os.path.relpath(path, repo_root)
                        docs.append({"title": title, "content": text[:_MAX_DOC_SNIPPET_CHARS]})
                        if len(docs) >= _MAX_MATCHED_DOCS:
                            break
                except Exception:
                    continue
        if len(docs) >= _MAX_MATCHED_DOCS:
            break
    return docs


def _prepare_messages(user_messages: list[dict]) -> list[dict]:
    """Combine system prompt, optional relevant docs and the user messages.
    If we can find relevant docs we add them as an additional system message.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    query_text = " ".join(m["content"] for m in user_messages if m["role"] == "user")
    docs = _fetch_relevant_docs(query_text)
    if docs:
        docs_content = "\n---\n".join(f"Title: {d['title']}\n\n{d['content']}" for d in docs)
        messages.append({"role": "system", "content": f"Relevant project documentation:\n{docs_content}"})
    messages.extend(user_messages)
    return messages


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
        "top_p": getattr(settings, 'custom_model_top_p', 0.9),
        "repeat_penalty": getattr(settings, 'custom_model_repeat_penalty', 1.2),
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


def _fallback_response(conversation: list[dict]) -> dict:
    """Deterministic fallback used when the LLM is unavailable or when we
    want a predictable answer for very short/ambiguous queries.
    """
    # Use only the latest user message for parsing.
    user_msg = conversation[-1]["content"] if conversation else ""
    from app.ai.ai_search import parse_query, generate_search_text
    parsed = parse_query(user_msg)

    # If the query is too vague (no article keyword at all), ask for it.
    if not parsed.get("keywords"):
        return {"reply": _MISSING_KEYWORDS, "search_text": "", "search_results": None}
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


def _use_llm_reply(llm_reply: str, fallback: dict) -> bool:
    """Return True if the LLM produced a useful answer we should prefer.

    We prefer the LLM unless it errored out, or the user has not even told us
    what kind of item they are looking for yet (the _MISSING_KEYWORDS
    clarifying question). Once the user mentions an article, let the LLM
    answer naturally — it can ask for price/location itself if needed.
    """
    if not llm_reply or llm_reply.startswith("["):
        return False
    # Keep only the "what item?" clarifying question deterministic.
    if fallback["reply"] == _MISSING_KEYWORDS:
        return False
    return True


def build_chat_response(conversation: list[dict]) -> dict:
    """Return the LLM's reply for the given conversation.
    The primary path forwards the full history to the configured LLM.
    If the LLM request fails (e.g., the local Ollama server is unavailable),
    we fall back to a deterministic response.
    """
    # Empty conversation: return the greeting string.
    if not conversation:
        return {"reply": GREETING, "search_text": "", "search_results": None}

    # Try the LLM first for any non-empty conversation, including the very
    # first user message, so the assistant feels responsive immediately.
    llm_messages = _prepare_messages(conversation)
    llm_reply = _call_llm(llm_messages)
    fallback = _fallback_response(conversation)
    if _use_llm_reply(llm_reply, fallback):
        return {"reply": llm_reply, "search_text": "", "search_results": None}
    # Otherwise return the deterministic fallback (greeting for vague first msg).
    return fallback



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
