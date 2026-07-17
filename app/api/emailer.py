"""Transactional email sending via SendGrid SMTP relay.

Only the API container sends email (verification links); the worker and beat
never import this module. Sending is synchronous and returns an explicit
(ok, error) result so callers can surface real failures to the user instead
of pretending the mail went out.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.api.config import settings

logger = logging.getLogger(__name__)

SENDGRID_USERNAME = "apikey"


def email_configured() -> bool:
    """True when a SendGrid API key is set and email can actually be sent."""
    return bool(settings.sendgrid_api_key)


def _send_smtp(from_addr: str, to_addrs: list[str], subject: str,
               html_body: str, text_body: str) -> tuple[bool, str]:
    """Send an email via SendGrid SMTP. Returns (ok, error_message)."""
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        server.starttls()
        server.login(SENDGRID_USERNAME, settings.sendgrid_api_key)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()
    except smtplib.SMTPException as exc:
        logger.error("SMTP send failed: %s", exc)
        return False, "Could not reach the email service"
    except Exception as exc:
        logger.error("SMTP send failed: %s", exc)
        return False, "Could not reach the email service"

    return True, ""


def send_verification_email(to_email: str, username: str, verify_url: str) -> tuple[bool, str]:
    """Send the verify-your-address email. Returns (ok, error_message).

    Never raises: network/SMTP failures are logged and returned so the caller
    can show an honest error and offer a resend.
    """
    if not email_configured():
        return False, "Email sending is not configured (SENDGRID_API_KEY is empty)"

    from_addr = f"kleinanzeigen-ai <{settings.email_from}>"
    html_body = (
        f"<p>Hi {username},</p>"
        "<p>Welcome to kleinanzeigen-ai! Please confirm your email address "
        "to activate searching on your account:</p>"
        f'<p><a href="{verify_url}">Verify my email</a></p>'
        "<p>Or open this link:</p>"
        f"<p>{verify_url}</p>"
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

    ok, error = _send_smtp(from_addr, [to_email],
                           "Verify your email address", html_body, text_body)
    if not ok:
        from app.shared.email_status import mark_email_failed
        mark_email_failed()
        return False, error

    return True, ""
