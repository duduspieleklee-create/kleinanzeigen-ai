"""
Tests für den KI-gestützten Such-Assistenten (app/ai/ai_search.py).
"""

from app.ai.ai_search import parse_query, extract_keywords_for_search, generate_search_text, rank_results, feedback_to_refinement


def test_parse_simple_keywords():
    """Einfache Beschreibung → Keywords extrahiert."""
    result = parse_query("gebrauchtes Eichensofa")
    assert "eichensofa" in result["keywords"] or "sofa" in result["keywords"]
    assert result["category"] == "möbel"


def test_parse_with_price_max():
    """Preisangabe 'unter X' → price_max gesetzt."""
    result = parse_query("gebrauchtes sofa unter 200 euro in berlin")
    assert result["price_max"] == 200
    assert "berlin" in result["location"].lower()


def test_parse_with_price_range():
    """Preisangabe '50-100' → price_min + price_max."""
    result = parse_query("handy 50 bis 100 euro")
    assert result["price_min"] == 50
    assert result["price_max"] == 100


def test_parse_with_location():
    """Ortsangabe → location extrahiert."""
    result = parse_query("bike in München")
    assert "münchen" in result["location"].lower() or "muenchen" in result["location"].lower()


def test_parse_empty():
    """Leerer Text → leere Parameter."""
    result = parse_query("")
    assert result["keywords"] == []
    assert result["price_min"] is None


def test_parse_detects_category():
    """Kategorie-Hinweise werden erkannt."""
    assert parse_query("gebrauchtes iphone")["category"] == "elektronik"
    assert parse_query("gartenstuhl")["category"] == "garten"
    assert parse_query("gebrauchtes auto")["category"] == "fahrzeuge"


def test_extract_keywords():
    """extract_keywords_for_search erzeugt Suchtext."""
    parsed = {"keywords": ["sofa", "eiche"], "category": "möbel", "price_max": 200}
    kw = extract_keywords_for_search(parsed)
    assert "sofa" in kw


def test_generate_search_text():
    """generate_search_text erzeugt lesbaren Text."""
    parsed = {"keywords": ["sofa", "eiche"], "price_max": 200, "location": "Berlin"}
    text = generate_search_text(parsed)
    assert "200" in text
    assert "Berlin" in text


def test_rank_results_sorts_by_relevance():
    """Ergebnisse werden nach Relevanz sortiert (query-Terme in Title = höher)."""
    results = [
        {"id": 1, "title": "Alter Tisch", "description": "eiche", "price_value": 50},
        {"id": 2, "title": "Eichensofa gebraucht", "description": "schönes sofa aus eiche", "price_value": 150},
        {"id": 3, "title": "Sofa", "description": "nur sofa", "price_value": 100},
    ]
    ranked = rank_results(results, "gebrauchtes eichensofa")
    assert ranked[0]["id"] == 2  # Eichensofa should rank highest


def test_rank_results_boosts_liked():
    """Liked IDs werden bevorzugt."""
    results = [
        {"id": 1, "title": "Sofa", "description": "modern", "price_value": 100},
        {"id": 2, "title": "Couch", "description": "bequem", "price_value": 200},
        {"id": 3, "title": "Polstergarnitur", "description": "luxus", "price_value": 300},
    ]
    ranked = rank_results(results, "sofa", liked_ids={3})
    assert ranked[0]["id"] == 3  # liked item first


def test_parse_removes_stopwords():
    """Stopwörter werden aus Keywords entfernt."""
    result = parse_query("ich suche ein neues sofa")
    assert "ich" not in result["keywords"]
    assert "suche" not in result["keywords"]
    assert "sofa" in result["keywords"]
