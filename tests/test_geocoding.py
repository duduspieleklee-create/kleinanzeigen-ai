"""
Tests für das Geocoding-Modul (app/shared/geocoding.py).
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import requests

from app.shared.database import Base
from app.shared.models import GeocodeCache
from app.shared import geocoding


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    return Session()


def test_normalize_location_lowercases_and_collapses_whitespace():
    assert geocoding.normalize_location("  10115   Berlin ") == "10115 berlin"
    assert geocoding.normalize_location("München") == "münchen"
    assert geocoding.normalize_location("") == ""
    assert geocoding.normalize_location(None) == ""


def test_geocode_miss_then_cache_hit(db, monkeypatch):
    calls = []

    def fake_query(location, timeout):
        calls.append(location)
        return (52.52, 13.4)

    monkeypatch.setattr(geocoding, "_query_nominatim", fake_query)

    first = geocoding.geocode("Berlin", db)
    assert first == {"lat": 52.52, "lon": 13.4}
    assert calls == ["berlin"]  # normalised key
    # Row persisted.
    assert db.query(GeocodeCache).filter(GeocodeCache.location == "berlin").count() == 1

    # Second call — served from cache, no new network lookup. Different casing/
    # spacing must hit the SAME cache row.
    second = geocoding.geocode("  BERLIN ", db)
    assert second == {"lat": 52.52, "lon": 13.4}
    assert calls == ["berlin"]  # unchanged → no extra lookup


def test_geocode_not_found_is_negatively_cached(db, monkeypatch):
    calls = []

    def fake_query(location, timeout):
        calls.append(location)
        return None  # Nominatim returned no hit

    monkeypatch.setattr(geocoding, "_query_nominatim", fake_query)

    assert geocoding.geocode("Nirgendwo XYZ", db) is None
    # A negative row (lat/lon NULL) was stored.
    row = db.query(GeocodeCache).filter(GeocodeCache.location == "nirgendwo xyz").first()
    assert row is not None and row.lat is None and row.lon is None

    # Second call must NOT re-query — the negative cache answers it.
    assert geocoding.geocode("Nirgendwo XYZ", db) is None
    assert calls == ["nirgendwo xyz"]


def test_geocode_network_error_returns_none_without_caching(db, monkeypatch):
    def boom(location, timeout):
        raise requests.RequestException("nominatim down")

    monkeypatch.setattr(geocoding, "_query_nominatim", boom)

    assert geocoding.geocode("Hamburg", db) is None
    # Nothing cached, so a later (recovered) call can still succeed.
    assert db.query(GeocodeCache).filter(GeocodeCache.location == "hamburg").count() == 0


def test_geocode_empty_location_returns_none_without_query(db, monkeypatch):
    def fail(location, timeout):
        raise AssertionError("should not query for empty location")

    monkeypatch.setattr(geocoding, "_query_nominatim", fail)
    assert geocoding.geocode("   ", db) is None
