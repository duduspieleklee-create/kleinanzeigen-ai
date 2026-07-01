"""Application security helpers.

The same-origin (CSRF) check and security-response-headers live as HTTP
middleware in ``app.api.main``. The shared rate limiter lives here so that both
the app (for the 429 error handler) and the auth router (for per-route
decorators) import a single instance.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory fixed-window limiter keyed by client IP. This throttles
# brute-force / credential-stuffing against the auth endpoints. It is
# per-process; for multi-replica deployments back it with Redis by passing
# ``storage_uri=settings.redis_url``.
limiter = Limiter(key_func=get_remote_address)
