"""Tests for the shared rate limiter configuration (#128).

Verifies the slowapi Limiter is backed by Redis (so the rate-limit window is
shared across API replicas, not per-process) and that the in-memory fallback is
enabled so a brief Redis outage degrades gracefully instead of 500-ing every
request.
"""
from app.api.config import settings
from app.api.security import limiter


def test_limiter_uses_redis_storage_uri():
    """The limiter must be configured with the configured Redis URL."""
    assert limiter._storage_uri == settings.redis_url
    assert str(settings.redis_url).startswith("redis://")


def test_limiter_in_memory_fallback_enabled():
    """A Redis outage must fall back to in-memory limiting, not crash."""
    assert limiter._in_memory_fallback_enabled is True
