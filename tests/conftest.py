"""Shared pytest fixtures for the kleinanzeigen-ai test suite.

Ensures the dashboard (and any other) templates render with the same globals
the real app registers (build_info, turnstile_site_key), so template-render
tests mirror production.
"""
import os

# Keep tests hermetic: never read the real .env, and avoid touching a live DB.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite:///file::memory:?cache=shared")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import app.api.main  # noqa: E402  (registers templates at import)
from app.api.version import register_globals  # noqa: E402

register_globals(app.api.main.templates)
