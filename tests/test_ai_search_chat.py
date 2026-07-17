"""
Tests fuer den Chat-basierten Such-Assistenten (app/ai/ai_search_chat.py).
"""

from app.ai.ai_search_chat import (
    build_chat_response,
    format_results_as_chat,
    GREETING,
    _user_messages_text,
    _sanitize_messages,
    _use_llm_reply,
    _fetch_trending_suggestions,
    _trending_explanation_for,
    _MISSING_KEYWORDS,
    _MISSING_PRICE,
)


def test_trending_suggestions_fahrrad():
    """Fahrrad -> E-Bike etc as trending cousins."""
    out = _fetch_trending_suggestions("Fahrrad")
    assert "E-Bike" in out


def test_trending_suggestions_empty_query():
    """Empty query returns empty list."""
    assert _fetch_trending_suggestions("") == []
    assert _fetch_trending_suggestions("xyzzy-nonsense") == []


def test_trending_explanation_for_fahrrad():
    """Explanation builds a German hint line."""
    hint = _trending_explanation_for("Fahrrad")
    assert "Fahrrad" in hint
    assert "E-Bike" in hint


def test_trending_explanation_for_unknown_returns_empty():
    """Unknown topic -> empty hint."""
    assert _trending_explanation_for("xyzzy-nonsense") == ""


def test_greeting_non_empty():
    assert len(GREETING) > 50


def test_empty_conversation_asks_keywords():
    """Keine Keywords -> KI fragt nach."""
    conv = [{"role": "user", "content": "Hallo"}]
    r = build_chat_response(conv)
    assert "suchst" in r["reply"] or "Artikel" in r["reply"] or "Was" in r["reply"]


def test_keyword_triggers_price_question():
    """User nennt Artikel -> KI fragt nach Preis (fallback) oder per LLM."""
    conv = [
        {"role": "assistant", "content": GREETING},
        {"role": "user", "content": "Ich suche ein gebrauchtes Sofa"},
    ]
    r = build_chat_response(conv)
    # Accept deterministic fallback ("Preis") or LLM paraphrase
    assert any(w in r["reply"] for w in ["Preis", "preis", "ausgeben", "Kosten", "kosten", "Budget", "budget"])


def test_keyword_and_price_triggers_location():
    """User nennt Artikel + Preis -> KI fragt nach Ort."""
    conv = [
        {"role": "assistant", "content": "Was moechtest du ausgeben?"},
        {"role": "user", "content": "Ein Sofa unter 200 Euro"},
    ]
    r = build_chat_response(conv)
    # Accept both deterministic fallback and LLM paraphrases
    assert any(w in r["reply"] for w in ["Stadt", "Region", "PLZ", "Umkreis", "Wo ", "wo ", "Ort"])


def test_all_params_triggers_search():
    """User nennt alles Noetige -> KI sucht."""
    conv = [
        {"role": "assistant", "content": "In welcher Stadt?"},
        {"role": "user", "content": "Ein gebrauchtes Sofa unter 200 Euro in Berlin"},
    ]
    r = build_chat_response(conv)
    assert r["search_text"] and len(r["search_text"]) > 3


def test_multi_turn_accumulates_params():
    """Multi-step answers must accumulate (Sofa → bis 200 → Berlin)."""
    conv = [
        {"role": "assistant", "content": GREETING},
        {"role": "user", "content": "Ich suche ein Sofa"},
        {"role": "assistant", "content": "Hast du einen Preisrahmen im Kopf?"},
        {"role": "user", "content": "bis 200 Euro"},
        {"role": "assistant", "content": "In welcher Stadt?"},
        {"role": "user", "content": "Berlin"},
    ]
    r = build_chat_response(conv)
    assert r["search_text"], "expected search to fire after multi-turn funnel"
    assert "sofa" in r["search_text"].lower() or "möbel" in r["search_text"].lower() or "moebel" in r["search_text"].lower()
    assert "200" in r["search_text"] or "berlin" in r["search_text"].lower()


def test_user_messages_text_merges_turns():
    conv = [
        {"role": "user", "content": "Sofa"},
        {"role": "assistant", "content": "Preis?"},
        {"role": "user", "content": "bis 100"},
        {"role": "user", "content": " in München"},
    ]
    assert _user_messages_text(conv) == "Sofa bis 100 in München"


def test_sanitize_messages_drops_empty_and_caps():
    msgs = [{"role": "user", "content": ""}] + [
        {"role": "user", "content": f"m{i}"} for i in range(20)
    ]
    cleaned = _sanitize_messages(msgs)
    assert all(m["content"] for m in cleaned)
    assert len(cleaned) <= 12


def test_use_llm_reply_defers_to_funnel_when_search_ready():
    assert _use_llm_reply("Ich suche jetzt ...", {"reply": "ok", "search_text": "sofa"}) is False
    assert _use_llm_reply("Wonach suchst du?", {"reply": _MISSING_KEYWORDS, "search_text": ""}) is False
    assert _use_llm_reply("Hast du Budget?", {"reply": _MISSING_PRICE, "search_text": ""}) is False
    assert _use_llm_reply("[Error contacting LLM]", {"reply": "x", "search_text": ""}) is False
    # Healthy LLM with non-funnel fallback can still be preferred
    assert _use_llm_reply("Klar, gerne!", {"reply": "custom freeform", "search_text": ""}) is True


def test_format_results_no_results():
    text = format_results_as_chat([], 0)
    assert "nichts" in text.lower()


def test_format_results_with_results():
    results = [{"id": 1, "title": "Eichensofa", "price": "150 Euro", "location": "Berlin"}]
    text = format_results_as_chat(results, 1)
    assert "Eichensofa" in text
    assert "150" in text
