"""Backwards-compatible re-export of init_sentry.

New code should import from app.shared.observability directly.
"""
from app.shared.observability import init_sentry  # noqa: F401

__all__ = ["init_sentry"]
