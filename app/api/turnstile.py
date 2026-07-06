"""Cloudflare Turnstile server-side verification.

Turnstile guards the public, unauthenticated forms (login, register) against
bots, credential-stuffing and automated signups. The browser widget produces a
token in the ``cf-turnstile-response`` form field; this module validates that
token against Cloudflare's siteverify API before the request is trusted.

Docs: https://developers.cloudflare.com/turnstile/get-started/server-side-validation/

Verification fails closed when Turnstile is enabled: a missing, reused or
invalid token is rejected. When Turnstile is not configured (both keys empty),
``turnstile_configured`` is False and callers skip the check so local/dev
setups keep working without keys.
"""
import httpx

from app.api.config import settings
from app.shared.logging_config import logger

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
FORM_FIELD = "cf-turnstile-response"
_TIMEOUT = 10.0


def turnstile_configured() -> bool:
    """True when Turnstile is enabled and tokens should be validated."""
    return settings.turnstile_enabled


async def verify_turnstile(token: str, remoteip: str | None = None) -> bool:
    """Validate a Turnstile token via the siteverify API.

    Returns True only when Cloudflare confirms the token is valid. An empty
    token, a network/API error, or any unsuccessful response returns False so
    the caller rejects the submission. Never raises.
    """
    if not token:
        return False

    payload = {"secret": settings.turnstile_secret_key, "response": token}
    # The visitor's IP is an optional extra signal Cloudflare can cross-check.
    if remoteip:
        payload["remoteip"] = remoteip

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(SITEVERIFY_URL, data=payload)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # network error, timeout, bad JSON
        logger.warning("Turnstile siteverify request failed: %s", exc)
        return False

    if not data.get("success"):
        logger.info(
            "Turnstile verification rejected: %s", data.get("error-codes")
        )
        return False
    return True


def client_ip(request) -> str | None:
    """Best-effort client IP for the optional ``remoteip`` siteverify field.

    Behind Cloudflare the real visitor IP arrives in ``CF-Connecting-IP``;
    fall back to the direct socket peer otherwise.
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    return request.client.host if request.client else None
