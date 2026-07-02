"""Transactional email sending via the Resend HTTP API.

Only the API container sends email (verification links); the worker and beat
never import this module. Sending is synchronous and returns an explicit
(ok, error) result so callers can surface real failures to the user instead
of pretending the mail went out.
"""
import logging

import requests

from app.api.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def email_configured() -> bool:
    """True when a Resend API key is set and email can actually be sent."""
    return bool(settings.resend_api_key)


def send_verification_email(to_email: str, username: str, verify_url: str) -> tuple[bool, str]:
    """Send the verify-your-address email. Returns (ok, error_message).

    Never raises: network/API failures are logged and returned so the caller
    can show an honest error and offer a resend.
    """
    if not email_configured():
        return False, "Email sending is not configured (RESEND_API_KEY is empty)"

    payload = {
        "from": f"kleinanzeigen-ai <{settings.email_from}>",
        "to": [to_email],
        "subject": "Verify your email address",
        "html": (
            f"<p>Hi {username},</p>"
            "<p>Welcome to kleinanzeigen-ai! Please confirm your email address "
            "to activate searching on your account:</p>"
            f'<p><a href="{verify_url}">Verify my email</a></p>'
            "<p>Or open this link:</p>"
            f"<p>{verify_url}</p>"
            "<p>The link is valid for 24 hours. If you did not create this "
            "account, you can ignore this email.</p>"
        ),
        "text": (
            f"Hi {username},\n\n"
            "Welcome to kleinanzeigen-ai! Please confirm your email address to "
            "activate searching on your account by opening this link:\n\n"
            f"{verify_url}\n\n"
            "The link is valid for 24 hours. If you did not create this "
            "account, you can ignore this email.\n"
        ),
    }

    try:
        resp = requests.post(
            RESEND_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.error("Verification email to %s failed: %s", to_email, exc)
        return False, "Could not reach the email service"

    if resp.status_code >= 400:
        # Resend returns a JSON body with a message; log it but keep the
        # user-facing error generic (no provider internals in the UI).
        logger.error(
            "Verification email to %s rejected (%s): %s",
            to_email, resp.status_code, resp.text[:500],
        )
        return False, "The email service rejected the message"

    return True, ""
