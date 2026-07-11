"""
Tests für Google Trends Integration (app/ai/smart_search_trends.py).
"""

from unittest.mock import MagicMock, patch
from app.ai.smart_search_trends import get_trending_searches, clear_cache


def test_get_trending_searches_empty_keyword():
    """Leeres Keyword → leere Liste."""
    assert get_trending_searches("") == []
    assert get_trending_searches("a") == []


def test_get_trending_searches_network_error_returns_empty(monkeypatch):
    """Netzwerkfehler → leere Liste."""
    def mock_fetch(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.ai.smart_search_trends._fetch_trends", mock_fetch)
    clear_cache()
    assert get_trending_searches("sofa") == []


def test_get_trending_searches_returns_stale_cache_on_error(monkeypatch):
    """Nach erfolgreichem Fetch → bei Fehler alter Cache."""
    data = ["Ledersofa", "Ecksofa", "Schlafsofa"]
    cache_hit = False
    call_count = [0]

    def mock_fetch_first(keyword, geo="DE"):
        call_count[0] += 1
        if call_count[0] == 1:
            return data
        raise RuntimeError("network down")

    monkeypatch.setattr("app.ai.smart_search_trends._fetch_trends", mock_fetch_first)
    clear_cache()

    # Erster Aufruf → Daten von Google Trends
    result1 = get_trending_searches("sofa")
    assert result1 == data

    # Zweiter Aufruf → Cache (kein fetch)
    result2 = get_trending_searches("sofa")
    assert result2 == data
    assert call_count[0] == 1  # kein zweiter Fetch


def test_get_trending_searches_cache_returns_quickly(monkeypatch):
    """Cache-Treffer → kein Google-Trends-Aufruf."""
    fetch_calls = [0]

    def mock_fetch(keyword, geo="DE"):
        fetch_calls[0] += 1
        return ["Trend1", "Trend2"]

    monkeypatch.setattr("app.ai.smart_search_trends._fetch_trends", mock_fetch)
    clear_cache()

    get_trending_searches("auto")
    get_trending_searches("auto")
    get_trending_searches("auto")

    assert fetch_calls[0] == 1  # nur einmal gefetched, 2x Cache
