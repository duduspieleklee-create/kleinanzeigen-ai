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
SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


def email_configured() -> bool:
    """True when a Resend API key **or** a LambdaFunctionURL endpoint is set.
    The lambda endpoint can be used as a free fallback for verification emails.
    """
    # Primary: Resend key
    if settings.resend_api_key:
        return True
    # SendGrid key
    if settings.sendgrid_api_key:
        return True
    # Fallback: LambdaFunctionURL endpoint
    return bool(settings.lambda_email_url)


def send_verification_email(to_email: str, username: str, verify_url: str) -> tuple[bool, str]:
    """Send the verify‑your‑address email. Returns (ok, error_message).

    Uses Resend if `RESEND_API_KEY` is set, otherwise falls back to the
    `LAMBDA_EMAIL_URL` HTTP endpoint (if configured). Both payload formats are
    compatible with Resend JSON, so the lambda can simply forward the request to
    any email provider.
    """
    if not email_configured():
        return False, "Email sending is not configured (no RESEND_API_KEY or LAMBDA_EMAIL_URL)"

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

    # Choose endpoint
    if settings.resend_api_key:
        # Resend flow – include Authorization header
        try:
            resp = requests.post(
                RESEND_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.error("Verification email to %s failed (Resend): %s", to_email, exc)
            return False, "Could not reach the email service"
    elif settings.sendgrid_api_key:
        # SendGrid flow – Authorization header with Bearer token
        try:
            resp = requests.post(
                SENDGRID_API_URL,
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": settings.sendgrid_email_from},
                    "subject": payload["subject"],
                    "content": [
                        {"type": "text/plain", "value": payload["text"]},
                        {"type": "text/html", "value": payload["html"]},
                    ],
                },
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.error("Verification email to %s failed (SendGrid): %s", to_email, exc)
            return False, "Could not reach the email service"
    else:
        # LambdaFunctionURL fallback – simple POST, no auth header needed
        try:
            resp = requests.post(
                settings.lambda_email_url,
                json=payload,
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.error("Verification email to %s failed (Lambda URL): %s", to_email, exc)
            return False, "Could not reach the email service"

    if resp.status_code >= 400:
        # Log detailed error – Resend includes JSON, lambda may forward that as well
        logger.error(
            "Verification email to %s rejected (%s): %s",
            to_email, resp.status_code, resp.text[:500],
        )
        from app.shared.email_status import mark_email_failed
        mark_email_failed()
        return False, "The email service rejected the message"

    return True, ""
