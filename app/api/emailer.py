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

def email_configured() -> bool:
    """True when any email backend is properly configured.

    Supported backends:
    - Resend (RESEND_API_KEY)
    - SendGrid via SMTP (SMTP host/user/password + valid FROM address)
    - LambdaFunctionURL fallback
    """
    if settings.resend_api_key:
        return True
    # SendGrid SMTP backend
    if (
        settings.sendgrid_smtp_host
        and settings.sendgrid_smtp_user
        and settings.sendgrid_smtp_password
        and settings.sendgrid_email_from
    ):
        return True
    return bool(settings.lambda_email_url)


def send_verification_email(to_email: str, username: str, verify_url: str) -> tuple[bool, str]:
    def send_verification_email(to_email: str, username: str, verify_url: str) -> tuple[bool, str]:
        """Send verification email.

        Preferred method: SendGrid via SMTP relay (requires SMTP host/port/user/password).
        If any of those SMTP settings are missing, fall back to the existing Resend / SendGrid API / Lambda flow.
        """
        # If SMTP settings are configured, use them
        if settings.sendgrid_smtp_host and settings.sendgrid_smtp_user and settings.sendgrid_smtp_password:
            try:
                # Build email message
                from email.message import EmailMessage
                msg = EmailMessage()
                msg["Subject"] = "Verify your email address"
                msg["From"] = settings.sendgrid_email_from
                msg["To"] = to_email
                # Plain‑text body
                text_body = (
                    f"Hi {username},\n\n"
                    "Welcome to kleinanzeigen‑ai! Please confirm your email address to activate searching on your account by opening this link:\n\n"
                    f"{verify_url}\n\n"
                    "The link is valid for 24 hours. If you did not create this account, you can ignore this email."
                )
                # HTML body
                html_body = (
                    f"<p>Hi {username},</p>"
                    "<p>Welcome to kleinanzeigen‑ai! Please confirm your email address to activate searching on your account:</p>"
                    f"<p><a href='{verify_url}'>Verify my email</a></p>"
                    f"<p>{verify_url}</p>"
                    "<p>The link is valid for 24 hours. If you did not create this account, you can ignore this email.</p>"
                )
                msg.set_content(text_body)
                msg.add_alternative(html_body, subtype='html')

                # Connect to SMTP server
                import smtplib
                with smtplib.SMTP(settings.sendgrid_smtp_host, settings.sendgrid_smtp_port, timeout=15) as server:
                    server.starttls()
                    server.login(settings.sendgrid_smtp_user, settings.sendgrid_smtp_password)
                    server.send_message(msg)
                return True, ""
            except Exception as exc:
                logger.error("Verification email to %s failed (SMTP): %s", to_email, exc)
                return False, "Could not send email via SMTP"
        # Existing flows (Resend, SendGrid API, Lambda) remain unchanged
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
        if settings.resend_api_key:
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
                logger.error("Verification email to %s failed (SendGrid API): %s", to_email, exc)
                return False, "Could not reach the email service"
        else:
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
            logger.error(
                "Verification email to %s rejected (%s): %s",
                to_email, resp.status_code, resp.text[:500],
            )
            from app.shared.email_status import mark_email_failed
            mark_email_failed()
            return False, "The email service rejected the message"
        return True, ""

    return True, ""
