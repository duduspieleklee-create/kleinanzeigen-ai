"""Application security helpers.

The same-origin (CSRF) check and security-response-headers live as HTTP
middleware in ``app.api.main``. The shared rate limiter lives here so that both
the app (for the 429 error handler) and the auth router (for per-route
decorators) import a single instance.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.config import settings

# Fixed-window limiter keyed by client IP, throttling brute-force /
# credential-stuffing against the auth endpoints. Backed by Redis
# (``settings.redis_url``) so the window is shared across API replicas —
# an in-memory limiter would let an attacker get N attempts *per process*.
#
# ``in_memory_fallback_enabled`` keeps the app serving (degraded to per-process
# limiting) if Redis is briefly unreachable, rather than 500-ing every request.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    in_memory_fallback_enabled=True,
)
