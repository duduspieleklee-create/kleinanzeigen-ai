"""Email notification system for new search results.

Sends via SendGrid HTTP API using the same credentials
(`settings.sendgrid_api_key`) already used for verification emails in
app/api/emailer.py.
"""
import html
import logging
from typing import Optional, List
from dataclasses import dataclass

import requests

from app.api.config import settings

logger = logging.getLogger("kleinanzeigen-ai")

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


@dataclass
class EmailNotification:
    """Email notification payload."""
    recipient: str
    subject: str
    body_html: str
    body_text: Optional[str] = None


def email_configured() -> bool:
    """True when a SendGrid API key is set and email can actually be sent."""
    return bool(settings.sendgrid_api_key)


def send_email_notification(notification: EmailNotification) -> bool:
    """Send an email notification via SendGrid HTTP API. Never raises.

    Returns True if sent successfully, False otherwise (and logs why).
    """
    if not email_configured():
        logger.warning(
            "Skipping email to %s: SENDGRID_API_KEY is not configured",
            notification.recipient,
        )
        return False

    payload = {
        "personalizations": [{"to": [{"email": notification.recipient}]}],
        "from": {"email": settings.email_from, "name": "kleinanzeigen-ai"},
        "subject": notification.subject,
        "content": [
            {"type": "text/plain", "value": notification.body_text or ""},
            {"type": "text/html", "value": notification.body_html},
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
        logger.error("New-results email to %s failed: %s",
                     notification.recipient, exc)
        return False

    if resp.status_code >= 400:
        logger.error("New-results email to %s rejected (%s): %s",
                     notification.recipient, resp.status_code, resp.text[:500])
        return False

    logger.info("New-results email sent to %s", notification.recipient)
    return True


def create_new_results_email(
    user_email: str,
    keywords: str,
    result_count: int,
    results: List[dict],
    highlight: Optional[str] = None,
) -> EmailNotification:
    """Create an email notification for new search results.
    
    Args:
        user_email: Recipient email address
        keywords: Search keywords
        result_count: Number of new results
        results: List of result dicts with keys: title, price, url, trust_score
        highlight: Optional highlight message (e.g., for deals)
    
    Returns:
        EmailNotification object ready to send
    """
    safe_keywords = html.escape(keywords)
    subject = f"[kleinanzeigen-ai] {result_count} neue Angebote für '{keywords}'"
    dashboard_url = f"{(settings.public_base_url or '').rstrip('/')}/dashboard#tab-my-results"

    # Build HTML body — all fields below come from scraped, attacker-influenced
    # listing data and must be escaped before interpolation into body_html.
    results_html = ""
    for i, result in enumerate(results[:10], 1):  # Limit to 10 results per email
        trust_score = result.get("trust_score") if result.get("show_trust", True) else None
        trust_badge = _get_trust_badge_html(trust_score)
        safe_title = html.escape(str(result.get("title", "N/A")))
        safe_price = html.escape(str(result.get("price", "N/A")))
        safe_location = html.escape(str(result.get("location", "N/A")))
        safe_url = html.escape(str(result.get("url", "#")), quote=True)
        results_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">
                <strong>{i}. {safe_title}</strong><br>
                Preis: {safe_price}<br>
                Ort: {safe_location}<br>
                {trust_badge}
                <a href="{safe_url}" style="color: #0066cc;">Anzeige ansehen →</a>
            </td>
        </tr>
        """

    highlight_section = ""
    if highlight:
        safe_highlight = html.escape(highlight)
        highlight_section = f"""
        <div style="background-color: #fff3cd; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
            <strong style="color: #856404;">🎯 Deal Alert:</strong> {safe_highlight}
        </div>
        """
    
    body_html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            table {{ width: 100%; border-collapse: collapse; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>kleinanzeigen-ai</h1>
                <p>{result_count} neue Angebote für: <strong>{safe_keywords}</strong></p>
            </div>
            <div class="content">
                {highlight_section}
                <h2>Neue Angebote:</h2>
                <table>
                    {results_html}
                </table>
                <p style="margin-top: 20px; text-align: center;">
                    <a href="{dashboard_url}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                        Dashboard öffnen
                    </a>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    body_text = f"""
    kleinanzeigen-ai: {result_count} neue Angebote für '{keywords}'
    
    {highlight or ''}
    
    Neue Angebote:
    """ + "\n".join([
        f"{i}. {r.get('title')} - {r.get('price')} - {r.get('url')}"
        for i, r in enumerate(results[:10], 1)
    ])
    
    return EmailNotification(
        recipient=user_email,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
    )


def _get_trust_badge_html(trust_score: Optional[int]) -> str:
    """Generate HTML badge for trust score."""
    import html as html_module
    if trust_score is None:
        return ""
    
    if trust_score >= 80:
        color = "#4CAF50"
        label = "Sehr zuverlässig"
    elif trust_score >= 60:
        color = "#FFC107"
        label = "Zuverlässig"
    elif trust_score >= 40:
        color = "#FF9800"
        label = "Bedingt zuverlässig"
    else:
        color = "#F44336"
        label = "Warnung"
    
    safe_label = html_module.escape(label)
    return f"""
    <span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px;">
        Trust Score: {trust_score}/100 ({safe_label})
    </span><br>
    """
