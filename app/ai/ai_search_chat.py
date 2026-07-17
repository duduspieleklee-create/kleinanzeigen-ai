"""
Chat-basierter KI-Such-Assistent fuer kleinanzeigen-ai.

Der User unterhaelt sich mit der KI. Die KI fuehrt den User durch einen
definierten Such-Funnel (Was suchst du? -> Kategorie -> Ort/PLZ+Umkreis
oder Preis) und loest am Ende eine Suche mit denselben Parametern aus,
die ein Nutzer auch manuell auf kleinanzeigen.de eingeben wuerde.

Wenn der User keine Idee hat, schlaegt die KI Suchbegriffe vor, die aus
frueheren Suchen und Ergebnissen in der PostgreSQL-Datenbank gelernt wurden.
"""

import logging
import re
from app.api.config import Settings
import httpx

logger = logging.getLogger("kleinanzeigen-ai")

GREETING = (
    "\U0001F44B Hallo! Ich bin dein KI-Such-Assistent.\n\n"
    "Erzaehl mir, wonach du suchst - ich fuehre dich Schritt fuer Schritt "
    "zu den passenden Anzeigen.\n\n"
    "Keine Idee? Sag einfach 'keine Ahnung' und ich mache Vorschlaege!"
)

# -- Deterministic fallback prompts (used when LLM is unavailable) ---------
_MISSING_KEYWORDS = "Wonach suchst du? Beschreib einfach, was du finden moechtest."
_MISSING_CATEGORY = (
    "Weisst du schon, in welche Kategorie das faellt? "
    "(z.B. Moebel, Elektronik, Fahrzeuge, Garten, Kleidung)"
)
_MISSING_PRICE = (
    "Hast du einen Preisrahmen im Kopf? "
    "(z.B. 'bis 200 Euro' oder '50-150 Euro')"
)
_MISSING_LOCATION = (
    "In welcher Stadt oder PLZ moechtest du suchen? Und welcher Umkreis? "
    "(z.B. '10115, 10 km' oder 'Muenchen, 50 km')"
)
_CONFIRM_SEARCH = (
    "Alles klar! Ich suche jetzt nach **{summary}**.\n"
    "Das dauert einen Moment ..."
)
_NO_RESULTS = "Ich habe leider nichts passendes gefunden. Versuch es mit anderen Angaben!"
_RESULTS_FOUND = "Ich habe {count} passende Treffer gefunden:"

# -- System prompt: the guided search funnel --------------------------------
SYSTEM_PROMPT = """\
Du bist der KI-Such-Assistent fuer die Plattform kleinanzeigen.de.

## Deine Hauptaufgabe
Du fuehrst den Nutzer Schritt fuer Schritt durch einen Such-Funnel, bis alle \
notwendigen Parameter erfasst sind. Am Ende wird eine echte kleinanzeigen.de-\
Suche ausgeloest - mit genau denselben Parametern, die ein Nutzer auch manuell \
eingeben wuerde.

## Der Such-Funnel (genau in dieser Reihenfolge)

1. **Was suchst du?** - Frage immer zuerst, wonach der Nutzer sucht. \
Beispiel-Antwort: 'Wonach suchst du? Ein Sofa, ein Handy, ein Fahrrad?'
2. **Kategorie** - Ordne die Antwort einer Kategorie zu. \
Verfuegbare Kategorien: Moebel, Elektronik, Fahrzeuge, Garten, Kleidung. \
Wenn die Kategorie aus der Antwort klar hervorgeht, nicht extra nachfragen.
3. **Ort / PLZ + Umkreis** UND/ODER **Preis** - je nach Kategorie:
   - **Fahrzeuge**: Frage nach Ort/PLZ + Umkreis (Preis meist nicht relevant).
   - **Moebel, Elektronik, Garten, Kleidung** (Items): Frage nach Preis \
     ('Hast du einen Preisrahmen?') UND nach Ort/PLZ+Umkreis.
   - Wenn der Nutzer bereits Preis oder Ort in seiner ersten Antwort \
     erwaehnt hat, nicht erneut danach fragen - nur die fehlenden Parameter \
     erfragen.
4. **Suche ausloesen** - Sobald die Pflicht-Parameter (Was + Kategorie) \
   erfasst sind, bestaetige kurz die Suchparameter und leite die Suche ein. \
   Antwort-Format hierbei: \
   'Ich suche jetzt nach: **[Stichwort] [Kategorie] [Preis] [Ort]**. \
   Einen Moment bitte ...'

## Wenn der Nutzer 'keine Ahnung' oder 'keine Idee' sagt
Schlage konkrete Suchbegriffe vor. Verwende dabei die weiter unten \
angegebenen 'Bisherige beliebte Suchen' als Inspiration. \
Antworte z.B.: \
'Vielleicht interessiert dich ja: Sofa, iPhone, Fahrrad, PlayStation? \
Oder eine ganz andere Kategorie?'

## Eckregeln
- Antworte immer auf Deutsch.
- Sei kurz: maximal 2 Saetze pro Nachricht, nie mehr als 60 Woerter.
- Stelle immer nur EINE Frage gleichzeitig (nicht Preis + Ort auf einmal).
- Erfinde NIEMALS Anzeigen, Preise, URLs oder Kontaktdaten. \
  Was du nicht weisst, fragst du nach.
- Gebe keine Code-Blocks, Shell-Befehle oder Dateipfade aus.
- Wenn der Nutzer die Kategorie Fahrzeuge nennt, frage nicht nach dem Preis.

## Beispiele

<Beispiel 1>
Nutzer: Ich suche ein Sofa.
Assistent: Schoen! Moebel also. Hast du einen Preisrahmen im Kopf?
Nutzer: Bis 200 Euro.
Assistent: Passt. Wo moechtest du suchen - welche Stadt oder PLZ, \
und in welchem Umkreis? (z.B. 'Muenchen, 20 km')
</Beispiel 1>

<Beispiel 2>
Nutzer: keine Ahnung
Assistent: Vielleicht interessiert dich: Sofa, iPhone, Fahrrad, \
PlayStation? Oder schau in ganz andere Kategorien - z.B. Garten oder Kleidung.
Nutzer: Fahrrad klingt gut.
Assistent: Cool! Weisst du, in welche Kategorie? Fahrzeuge ist \
sinnvoll. In welcher Stadt/PLZ suchst du, mit welchem Umkreis? \
(Preis ist bei Fahrzeugen weniger wichtig.)
</Beispiel 2>

<Beispiel 3>
Nutzer: iPhone in Muenchen bis 500
Assistent: Alles passt! Ich suche jetzt nach: \
**iPhone Elektronik bis 500 Euro in Muenchen**. Einen Moment bitte ...
</Beispiel 3>
"""

_MAX_DOC_SNIPPET_CHARS = 500
_MAX_MATCHED_DOCS = 1
_MAX_PAST_SEARCHES = 5


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


def _fetch_past_searches() -> list[str]:
    """Query the PostgreSQL database for popular past searches and results.

    Pulls the top-N most frequent keywords from:
    - ScrapeResult titles (what was actually found)
    - SearchSuggestion (what was suggested and clicked)

    Returns a list of plain-text search terms that can be injected as
    context for the LLM to use when a user says 'no idea'.
    """
    try:
        from app.shared.database import SessionLocal
        from app.shared.models import ScrapeResult, SearchSuggestion
        from sqlalchemy import select

        db = SessionLocal()
        suggestions: list[str] = []

        # 1) Top ScrapeResult titles (most common words in found listings)
        try:
            rows = db.execute(
                select(ScrapeResult.title).limit(200)
            ).scalars().all()
            word_freq: dict[str, int] = {}
            for title in rows:
                if not title:
                    continue
                tokens = re.findall(r'[A-Za-z\u00C0-\u017F]{3,}', title)
                for t in tokens:
                    t_lower = t.lower()
                    if t_lower in {
                        "der", "die", "das", "ein", "mit", "und", "fuer",
                        "von", "zu", "top", "neu", "gebraucht", "sehr",
                    }:
                        continue
                    word_freq[t_lower] = word_freq.get(t_lower, 0) + 1
            top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:_MAX_PAST_SEARCHES]
            suggestions.extend(w for w, _ in top_words)
        except Exception as e:
            logger.warning("Failed to fetch ScrapeResult titles for suggestions: %s", e)

        # 2) SearchSuggestion entries with highest usage_count
        try:
            rows = db.execute(
                select(SearchSuggestion.suggestion)
                .order_by(SearchSuggestion.usage_count.desc())
                .limit(_MAX_PAST_SEARCHES)
            ).scalars().all()
            suggestions.extend(rows)
        except Exception as e:
            logger.warning("Failed to fetch SearchSuggestion for suggestions: %s", e)

        db.close()

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for s in suggestions:
            s_lower = s.lower()
            if s_lower not in seen and len(s) >= 3:
                seen.add(s_lower)
                unique.append(s)
        return unique[:15]
    except Exception as e:
        logger.warning("Could not fetch past searches from DB: %s", e)
        return []


def _prepare_messages(user_messages: list[dict]) -> list[dict]:
    """Combine system prompt, past-search context, optional relevant docs
    and the user messages.

    If we can find relevant docs we add them as an additional system message.
    If we can fetch past searches from the DB, we inject them as context
    so the LLM can suggest real, previously-searched terms.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject past searches as context for 'no idea' suggestions
    past_searches = _fetch_past_searches()
    if past_searches:
        past_context = (
            "Bisherige beliebte Suchen auf dieser Plattform "
            "(nutze diese als Inspiration, wenn der Nutzer keine Idee hat):\n"
            + "\n".join(f"- {s}" for s in past_searches)
        )
        messages.append({"role": "system", "content": past_context})

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


# Categories where price is typically not the primary filter (e.g. vehicles)
_NO_PRICE_CATEGORIES = {"fahrzeuge"}


def _check_no_idea(text: str) -> bool:
    """Return True if the user says they have no idea / no preference."""
    t = text.strip().lower()
    patterns = [
        "keine ahnung", "keine idee", "keine ahnug", "wei\xdf nicht",
        "weiss nicht", "egal", "vorschlaege", "vorschlaege", "vorschlag",
        "schlag was vor", "was gibts", "was gibt es",
    ]
    return any(p in t for p in patterns)


def _fallback_response(conversation: list[dict]) -> dict:
    """Deterministic fallback used when the LLM is unavailable or when we
    want a predictable answer for very short/ambiguous queries.

    Implements the same guided funnel as the system prompt:
    item -> category -> (location or price) -> confirm & search.
    """
    from app.ai.ai_search import parse_query, generate_search_text

    # Use only the latest user message for parsing.
    user_msg = conversation[-1]["content"] if conversation else ""

    # -- 'No idea' -> suggest past searches -------------------------------
    if _check_no_idea(user_msg):
        past = _fetch_past_searches()
        if past:
            items = ", ".join(past[:8])
            return {
                "reply": (
                    f"Vielleicht interessiert dich: {items}?\n\n"
                    "Oder schau in eine ganz andere Kategorie - "
                    "z.B. Garten oder Kleidung."
                ),
                "search_text": "",
                "search_results": None,
            }
        return {
            "reply": "Sag mir einfach, was du suchst - z.B. Sofa, iPhone, Fahrrad ...",
            "search_text": "",
            "search_results": None,
        }

    parsed = parse_query(user_msg)

    # Step 1: If the query is too vague (no article keyword at all), ask.
    if not parsed.get("keywords"):
        return {"reply": _MISSING_KEYWORDS, "search_text": "", "search_results": None}

    # Step 2: If we still don't have a category, ask for it.
    if not parsed.get("category"):
        return {"reply": _MISSING_CATEGORY, "search_text": "", "search_results": None}

    # Step 3: Depending on category, ask for the next missing parameter.
    cat = parsed.get("category", "").lower()

    # For vehicles: ask for location, skip price.
    if cat in _NO_PRICE_CATEGORIES:
        if not parsed.get("location"):
            return {"reply": _MISSING_LOCATION, "search_text": "", "search_results": None}
    else:
        # For items: both price and location are needed.
        if not parsed.get("price_min") and not parsed.get("price_max"):
            return {"reply": _MISSING_PRICE, "search_text": "", "search_results": None}
        if not parsed.get("location"):
            return {"reply": _MISSING_LOCATION, "search_text": "", "search_results": None}

    # All parameters present - generate a search text.
    search_text = generate_search_text(parsed)
    ack = _CONFIRM_SEARCH.format(summary=search_text)
    return {"reply": ack, "search_text": search_text, "search_results": None}


def _use_llm_reply(llm_reply: str, fallback: dict) -> bool:
    """Return True if the LLM produced a useful answer we should prefer.

    We prefer the LLM unless it errored out, or the user has not even told us
    what kind of item they are looking for yet (the _MISSING_KEYWORDS
    clarifying question). Once the user mentions an article, let the LLM
    answer naturally - it can ask for price/location itself if needed.
    """
    if not llm_reply or llm_reply.startswith("["):
        return False
    # Keep only the 'what item?' clarifying question deterministic.
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
        # Use the LLM's conversational reply, but still carry over the
        # search_text from the deterministic fallback so downstream search
        # logic can trigger when all parameters are present.
        return {
            "reply": llm_reply,
            "search_text": fallback.get("search_text", ""),
            "search_results": None,
        }
    # Otherwise return the deterministic fallback.
    return fallback


def format_results_as_chat(results: list[dict], count: int) -> str:
    """Formatiert Suchergebnisse als Chat-Text."""
    if count == 0:
        return _NO_RESULTS
    text = _RESULTS_FOUND.format(count=count)
    for r in results[:5]:
        title = r.get("title", "\u2014")
        price = r.get("price") or (
            f"{r.get('price_value', '')}\u20ac" if r.get('price_value') else "\u2014"
        )
        loc = r.get("location", "")
        text += f"\n\n\U0001F4CC **{title}**"
        text += f"\n\U0001F4B0 {price}"
        if loc:
            text += f" \U0001F4CD {loc}"
    if len(results) > 5:
        text += f"\n\n... und {len(results) - 5} weitere Treffer"
    text += "\n\n\U0001F44D Mehr davon / \U0001F44E Nicht das - klick einfach auf die Buttons unter den Ergebnissen!"
    return text