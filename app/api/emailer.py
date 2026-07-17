"""Transactional email sending via SendGrid HTTP API.

Only the API container sends email (verification links); the worker and beat
never import this module. Sending is synchronous and returns an explicit
(ok, error) result so callers can surface real failures to the user instead
of pretending the mail went out.
"""
import logging

import requests

from app.api.config import settings

logger = logging.getLogger(__name__)

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


def email_configured() -> bool:
    """True when a SendGrid API key is set and email can actually be sent."""
    return bool(settings.sendgrid_api_key)


def _send_via_api(from_addr: str, to_addrs: list[str], subject: str,
                  html_body: str, text_body: str) -> tuple[bool, str]:
    """Send an email via SendGrid HTTP API. Returns (ok, error_message)."""
    payload = {
        "personalizations": [{"to": [{"email": addr} for addr in to_addrs]}],
        "from": {"email": settings.email_from, "name": "kleinanzeigen-ai"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html", "value": html_body},
        ],
    }

    try:
        resp = requests.post(
            SENDGRID_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.error("SendGrid API request failed: %s", exc)
        return False, "Could not reach the email service"

    if resp.status_code >= 400:
        logger.error("SendGrid API rejected (%s): %s",
                     resp.status_code, resp.text[:500])
        return False, "The email service rejected the message"

    return True, ""


def send_verification_email(to_email: str, username: str, verify_url: str) -> tuple[bool, str]:
    """Send the verify-your-address email. Returns (ok, error_message).

    Never raises: network/API failures are logged and returned so the caller
    can show an honest error and offer a resend.
    """
    import html as html_module
    if not email_configured():
        return False, "Email sending is not configured (SENDGRID_API_KEY is empty)"

    safe_username = html_module.escape(username)
    safe_url = html_module.escape(verify_url)

    html_body = (
        f"<p>Hi {safe_username},</p>"
        "<p>Welcome to kleinanzeigen-ai! Please confirm your email address "
        "to activate searching on your account:</p>"
        f'<p><a href="{safe_url}">Verify my email</a></p>'
        "<p>Or open this link:</p>"
        f"<p>{safe_url}</p>"
        "<p>The link is valid for 24 hours. If you did not create this "
        "account, you can ignore this email.</p>"
    )
    text_body = (
        f"Hi {username},\n\n"
        "Welcome to kleinanzeigen-ai! Please confirm your email address to "
        "activate searching on your account by opening this link:\n\n"
        f"{verify_url}\n\n"
        "The link is valid for 24 hours. If you did not create this "
        "account, you can ignore this email.\n"
    )

    ok, error = _send_via_api(
        settings.email_from, [to_email],
        "Verify your email address", html_body, text_body,
    )
    if not ok:
        from app.shared.email_status import mark_email_failed
        mark_email_failed()
        return False, error

    return True, ""
