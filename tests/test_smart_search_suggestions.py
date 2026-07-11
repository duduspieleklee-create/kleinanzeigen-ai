"""
Tests für Smart Search Suggestions.

Die Synonym-/Verwandten-Suche läuft live gegen externe APIs (Datamuse,
Wikipedia). Für deterministische Unit-Tests mocken wir `requests.get`,
sodass der dokumentierte Fallback auf die deutschen Mock-Daten geprüft wird.
"""

from unittest.mock import patch, MagicMock

from app.ai.smart_search_suggestions import smart_search


def _mock_requests_get(payload):
    """Baut einen gefakten requests.get, der payload zurückliefert."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_get_synonyms():
    """Synonyme kommen aus dem Fallback, wenn die API nicht erreichbar ist."""
    with patch("app.ai.smart_search_suggestions.requests.get") as mock_get:
        mock_get.side_effect = RuntimeError("offline")
        synonyms = smart_search.get_synonyms("Auto")
    assert "PKW" in synonyms
    assert "Wagen" in synonyms
    assert "Fahrzeug" in synonyms


def test_get_related_terms():
    """Verwandte Begriffe kommen aus dem Fallback bei API-Fehler."""
    with patch("app.ai.smart_search_suggestions.requests.get") as mock_get:
        mock_get.side_effect = RuntimeError("offline")
        terms = smart_search.get_related_terms("Auto")
    assert "Reifen" in terms
    assert "Motor" in terms
    assert "Fahrer" in terms


def test_get_synonyms_live_shape():
    """Bei erreichbarer API liefert get_synonyms eine Liste von Wörtern."""
    with patch("app.ai.smart_search_suggestions.requests.get") as mock_get:
        mock_get.return_value = _mock_requests_get(
            [{"word": "automobile"}, {"word": "car"}]
        )
        synonyms = smart_search.get_synonyms("Auto")
    assert synonyms == ["automobile", "car"]


def test_get_suggestions():
    """Generiert Suchvorschläge für eine Nutzeranfrage (Fallback-Pfad)."""
    with patch("app.ai.smart_search_suggestions.requests.get") as mock_get:
        mock_get.side_effect = RuntimeError("offline")
        suggestions = smart_search.get_suggestions("Auto kaufen")
    assert "Synonyme für 'Auto'" in suggestions
    assert "Verwandte Begriffe für 'Auto'" in suggestions


def test_get_suggestions_cache():
    """Der Cache funktioniert."""
    with patch("app.ai.smart_search_suggestions.requests.get") as mock_get:
        mock_get.side_effect = RuntimeError("offline")
        suggestions1 = smart_search.get_suggestions("Auto")
        suggestions2 = smart_search.get_suggestions("Auto")
    assert suggestions1 == suggestions2  # Cache sollte funktionieren
