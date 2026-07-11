"""
Tests für Smart Search Suggestions.
"""

from app.ai.smart_search_suggestions import smart_search


def test_get_synonyms():
    """Testet, ob Synonyme korrekt zurückgegeben werden."""
    synonyms = smart_search.get_synonyms("Auto")
    assert "PKW" in synonyms
    assert "Wagen" in synonyms
    assert "Fahrzeug" in synonyms


def test_get_related_terms():
    """Testet, ob verwandte Begriffe korrekt zurückgegeben werden."""
    terms = smart_search.get_related_terms("Auto")
    assert "Reifen" in terms
    assert "Motor" in terms
    assert "Fahrer" in terms


def test_get_suggestions():
    """Testet, ob Suchvorschläge korrekt generiert werden."""
    suggestions = smart_search.get_suggestions("Auto kaufen")
    assert "Synonyme für 'Auto'" in suggestions
    assert "Verwandte Begriffe für 'Auto'" in suggestions


def test_get_suggestions_cache():
    """Testet, ob der Cache funktioniert."""
    suggestions1 = smart_search.get_suggestions("Auto")
    suggestions2 = smart_search.get_suggestions("Auto")
    assert suggestions1 == suggestions2  # Cache sollte funktionieren
