"""
Tests fuer den Chat-basierten Such-Assistenten (app/ai/ai_search_chat.py).
"""

from app.ai.ai_search_chat import build_chat_response, format_results_as_chat, GREETING


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


def test_format_results_no_results():
    text = format_results_as_chat([], 0)
    assert "nichts" in text.lower()


def test_format_results_with_results():
    results = [{"id": 1, "title": "Eichensofa", "price": "150 Euro", "location": "Berlin"}]
    text = format_results_as_chat(results, 1)
    assert "Eichensofa" in text
    assert "150" in text