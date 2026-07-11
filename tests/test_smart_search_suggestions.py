"""
Tests für Smart Search Suggestions (app/ai/smart_search_suggestions.py).

Alle externen Aufrufe (Datamuse, Wikipedia, Custom Model Endpoint) werden
gemockt, damit die Tests ohne Netz laufen und deterministisch sind.
Konvention des Repos: monkeypatch auf das externe Call-Target.
"""

import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def sss():
    """Frische Instanz mit geleertem Cache pro Test."""
    from app.ai import smart_search_suggestions as mod

    inst = mod.SmartSearchSuggestions()
    inst.cache = {}
    return inst


# ── Synonyme (Datamuse) ────────────────────────────────────────────────────
def test_get_synonyms_uses_datamuse(sss, monkeypatch):
    fake = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: [
            {"word": "PKW"},
            {"word": "Wagen"},
            {"word": "Fahrzeug"},
        ],
    )
    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", lambda *a, **k: fake)
    assert sss.get_synonyms("Auto") == ["PKW", "Wagen", "Fahrzeug"]


def test_get_synonyms_falls_back_to_mock_on_error(sss, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", boom)
    assert sss.get_synonyms("Auto") == ["PKW", "Wagen", "Fahrzeug", "Pkw", "Kfz"]
    # Unbekanntes Wort → leere Liste, kein Crash
    assert sss.get_synonyms("UnbekanntesWort123") == []


def test_get_synonyms_retries_transient_failures_then_succeeds(sss, monkeypatch):
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        calls["n"] += 1
        if "datamuse" not in str(url):
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: [],
            )
        if calls["n"] < 3:
            raise RuntimeError("transient datamuse failure")
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{"word": "PKW"}, {"word": "Wagen"}],
        )

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", fake_get)
    result = sss.get_synonyms("Auto")
    assert result == ["PKW", "Wagen"]
    assert calls["n"] == 3


# ── Verwandte Begriffe (Wikipedia) ────────────────────────────────────────
def test_get_related_terms_uses_wikipedia(sss, monkeypatch):
    fake = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "query": {
                "search": [
                    {"title": "Reifen – Wikipedia"},
                    {"title": "Motor"},
                    {"title": "Fahrer"},
                ]
            }
        },
    )
    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", lambda *a, **k: fake)
    result = sss.get_related_terms("Auto")
    assert "Reifen" in result
    assert "Motor" in result
    assert "Fahrer" in result


def test_get_related_terms_falls_back_to_mock_on_error(sss, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", boom)
    assert sss.get_related_terms("Auto") == ["Reifen", "Motor", "Fahrer", "Bremse", "Getriebe"]


def test_get_related_terms_retries_transient_failures_then_succeeds(sss, monkeypatch):
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        calls["n"] += 1
        if "wikipedia" not in str(url):
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: [],
            )
        if calls["n"] < 3:
            raise RuntimeError("transient wikipedia failure")
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "query": {
                    "search": [
                        {"title": "Reifen – Wikipedia"},
                        {"title": "Motor"},
                    ]
                }
            },
        )

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", fake_get)
    result = sss.get_related_terms("Auto")
    assert result[:2] == ["Reifen", "Motor"]
    assert calls["n"] == 3


# ── Lokale Trends ──────────────────────────────────────────────────────────
def test_get_local_trends_known_keyword(sss):
    assert "IKEA" in sss.get_local_trends("Gartenmöbel")


def test_get_local_trends_unknown_keyword_empty(sss):
    assert sss.get_local_trends("UnbekanntesWort123") == []


# ── Custom Model Endpoint (OpenAI-kompatibel) ─────────────────────────────
def test_custom_model_disabled_returns_empty(sss, monkeypatch):
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_endpoint", "")
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_provider", "")
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_name", "")
    assert sss.get_custom_model_suggestions("Auto kaufen") == []


def test_provider_preset_resolves_endpoint_and_enables(monkeypatch):
    """CUSTOM_MODEL_PROVIDER=ollama füllt Endpoint automatisch, kein Key nötig."""
    from app.api import config as cfg

    monkeypatch.setattr(cfg.settings, "custom_model_provider", "ollama")
    monkeypatch.setattr(cfg.settings, "custom_model_endpoint", "")
    monkeypatch.setattr(cfg.settings, "custom_model_name", "qwen2.5:1.5b")
    assert cfg.settings.custom_model_endpoint_resolved == "http://localhost:11434/v1"
    assert cfg.settings.custom_model_api_key_resolved == ""
    assert cfg.settings.custom_model_enabled is True


def test_provider_preset_openai_requires_explicit_key(monkeypatch):
    from app.api import config as cfg

    monkeypatch.setattr(cfg.settings, "custom_model_provider", "openai")
    monkeypatch.setattr(cfg.settings, "custom_model_name", "gpt-4o-mini")
    # Preset liefert Endpoint, aber keinen Key → nur sinnvoll mit explizitem Key
    assert cfg.settings.custom_model_endpoint_resolved == "https://api.openai.com/v1"
    monkeypatch.setattr(cfg.settings, "custom_model_api_key", "sk-test")
    assert cfg.settings.custom_model_api_key_resolved == "sk-test"
    assert cfg.settings.custom_model_enabled is True


def test_explicit_endpoint_overrides_provider(monkeypatch):
    from app.api import config as cfg

    monkeypatch.setattr(cfg.settings, "custom_model_provider", "openai")
    monkeypatch.setattr(cfg.settings, "custom_model_endpoint", "http://localhost:8000/v1")
    monkeypatch.setattr(cfg.settings, "custom_model_name", "local-model")
    assert cfg.settings.custom_model_endpoint_resolved == "http://localhost:8000/v1"


def test_custom_model_enabled_returns_parsed_lines(sss, monkeypatch):
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_endpoint", "http://localhost:11434/v1")
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_name", "llama3")
    # health-check property
    from app.api import config as cfg

    assert cfg.settings.custom_model_enabled is True

    fake_resp = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "choices": [
                {"message": {"content": "Gebrauchtwagen\nPKW\nWagen\nKfz"}}
            ]
        },
    )
    monkeypatch.setattr(
        "app.ai.smart_search_suggestions.requests.post", lambda *a, **k: fake_resp
    )
    result = sss.get_custom_model_suggestions("Auto kaufen")
    assert result == ["Gebrauchtwagen", "PKW", "Wagen", "Kfz"]


def test_custom_model_handles_network_error(sss, monkeypatch):
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_endpoint", "http://localhost:11434/v1")
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_name", "llama3")

    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.post", boom)
    assert sss.get_custom_model_suggestions("Auto kaufen") == []


def test_custom_model_strips_numbering_and_bullets(sss, monkeypatch):
    """Kleine LLMs nummerieren gern — der Parser muss '1. X' -> 'X' machen."""
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_endpoint", "http://localhost:11434/v1")
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_name", "llama3")

    fake_resp = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "choices": [
                {"message": {"content": "1. Gebrauchtwagen\n2) PKW kaufen\n3 - Auto gebraucht\n• Wagen\nKfz"}}
            ]
        },
    )
    monkeypatch.setattr(
        "app.ai.smart_search_suggestions.requests.post", lambda *a, **k: fake_resp
    )
    result = sss.get_custom_model_suggestions("Auto kaufen")
    assert result == ["Gebrauchtwagen", "PKW kaufen", "Auto gebraucht", "Wagen", "Kfz"]


@pytest.mark.skipif(
    not __import__("os").environ.get("CUSTOM_MODEL_ENDPOINT"),
    reason="echtes Custom Model nur mit CUSTOM_MODEL_ENDPOINT gesetzt (z.B. Ollama)",
)
def test_custom_model_smoke_against_real_endpoint(monkeypatch):
    """Smoke-Test gegen ein laufendes OpenAI-kompatibles Modell (z.B. Ollama)."""
    from app.ai import smart_search_suggestions as mod

    inst = mod.SmartSearchSuggestions()
    inst.cache = {}
    result = inst.get_custom_model_suggestions("Auto kaufen")
    assert isinstance(result, list)
    assert all(not t[0].isdigit() for t in result), "Nummerierung sollte bereinigt sein"
    assert len(result) >= 1, "Modell sollte mindestens einen Vorschlag liefern"


# ── get_suggestions (Kombination) ─────────────────────────────────────────
def test_get_suggestions_combines_sources(sss, monkeypatch):
    datamuse = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: [{"word": "PKW"}, {"word": "Wagen"}],
    )

    def fake_get(url, *a, **k):
        if "datamuse" in url:
            return datamuse
        # Wikipedia
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"query": {"search": [{"title": "Reifen"}, {"title": "Motor"}]}},
        )

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", fake_get)

    result = sss.get_suggestions("Auto kaufen")
    assert "Synonyme für 'Auto'" in result
    assert "Verwandte Begriffe für 'Auto'" in result
    assert "Verwandte Begriffe für 'kaufen'" in result
    assert "Aktuelle Trends für 'Auto'" in result  # aus data/trends.json


def test_get_suggestions_includes_custom_model_when_enabled(sss, monkeypatch):
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_endpoint", "http://localhost:11434/v1")
    monkeypatch.setattr("app.ai.smart_search_suggestions.settings.custom_model_name", "llama3")

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: []
    ))
    monkeypatch.setattr(
        "app.ai.smart_search_suggestions.requests.post",
        lambda *a, **k: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": "E-Auto\nGebrauchtwagen"}}]},
        ),
    )
    result = sss.get_suggestions("Auto")
    assert "KI-Vorschläge (Custom Model)" in result
    assert result["KI-Vorschläge (Custom Model)"] == ["E-Auto", "Gebrauchtwagen"]


# ── Cache ──────────────────────────────────────────────────────────────────
def test_get_suggestions_cache_hit(sss, monkeypatch):
    calls = {"n": 0}

    def fake_get(url, *a, **k):
        calls["n"] += 1
        if "datamuse" in url:
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: [{"word": "PKW"}])
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"query": {"search": [{"title": "Reifen"}]}},
        )

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", fake_get)
    # Google Trends mocken (damit kein extra Call)
    monkeypatch.setattr("app.ai.smart_search_trends.get_trending_searches_batch", lambda *a, **k: {})

    first = sss.get_suggestions("Auto")
    second = sss.get_suggestions("Auto")
    assert first == second
    # Zweiter Aufruf darf keinen neuen Netz-Call auslösen
    assert calls["n"] == 2  # exakt die Calls des ersten Aufrufs (Auto → synonym + related)


# ── API-Endpoint ───────────────────────────────────────────────────────────
def test_api_endpoint_returns_suggestions(monkeypatch):
    from app.api.routers.smart_search import get_search_suggestions

    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: []
    ))
    resp = get_search_suggestions("Auto kaufen")
    assert resp["query"] == "Auto kaufen"
    assert isinstance(resp["suggestions"], dict)
    # data/trends.json liefert Trends für "Auto" ohne Netz
    assert "Aktuelle Trends für 'Auto'" in resp["suggestions"]


# ── Persistenz (search_suggestions DB) ─────────────────────────────────────
def test_persist_suggestions_creates_and_increments(monkeypatch):
    """Vorschläge werden in der DB gespeichert und bei Wiederholung hochgezählt."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.shared.database import Base
    from app.shared.models import SearchSuggestion
    from app.api.routers.smart_search import _persist_suggestions

    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)

    # Mock external calls
    monkeypatch.setattr("app.ai.smart_search_suggestions.requests.get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: []
    ))

    db = Session()
    suggestions = {
        "Synonyme für 'Auto'": ["PKW", "Wagen"],
        "Verwandte Begriffe für 'Auto'": ["Reifen"],
    }

    # First call → creates rows
    _persist_suggestions("Auto", suggestions, db)
    rows = db.query(SearchSuggestion).filter(SearchSuggestion.keyword == "Auto").all()
    assert len(rows) == 3
    assert all(r.usage_count == 1 for r in rows)

    # Second call → increments
    _persist_suggestions("Auto", suggestions, db)
    rows = db.query(SearchSuggestion).filter(SearchSuggestion.keyword == "Auto").all()
    assert len(rows) == 3
    assert all(r.usage_count == 2 for r in rows)

    db.close()
