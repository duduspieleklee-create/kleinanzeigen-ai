"""Email notification system for search results and alerts.

Supports both SMTP (standard email) and Resend API (modern email service).
Configuration via environment variables.
"""
import logging
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("kleinanzeigen-ai")


@dataclass
class EmailNotification:
    """Email notification payload."""
    recipient: str
    subject: str
    body_html: str
    body_text: Optional[str] = None


def send_email_notification(
    notification: EmailNotification,
    use_resend: bool = False,
) -> bool:
    """Send an email notification.
    
    Args:
        notification: EmailNotification object
        use_resend: If True, use Resend API; otherwise use SMTP
    
    Returns:
        True if sent successfully, False otherwise
    """
    if use_resend:
        return _send_via_resend(notification)
    else:
        return _send_via_smtp(notification)


def _send_via_resend(notification: EmailNotification) -> bool:
    """Send email via Resend API.
    
    Requires RESEND_API_KEY environment variable.
    """
    try:
        import os
        from resend import Resend
    except ImportError:
        logger.warning("Resend library not installed. Install with: pip install resend")
        return False
    
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY not configured")
        return False
    
    try:
        client = Resend(api_key=api_key)
        response = client.emails.send({
            "from": "noreply@kleinanzeigen-ai.de",
            "to": notification.recipient,
            "subject": notification.subject,
            "html": notification.body_html,
            "text": notification.body_text or "",
        })
        logger.info(f"Email sent via Resend to {notification.recipient}: {response}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email via Resend: {e}")
        return False


def _send_via_smtp(notification: EmailNotification) -> bool:
    """Send email via SMTP.
    
    Requires SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD environment variables.
    """
    import os
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    
    if not all([smtp_host, smtp_user, smtp_password]):
        logger.warning("SMTP credentials not fully configured")
        return False
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = notification.subject
        msg["From"] = smtp_user
        msg["To"] = notification.recipient
        
        if notification.body_text:
            msg.attach(MIMEText(notification.body_text, "plain"))
        msg.attach(MIMEText(notification.body_html, "html"))
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, notification.recipient, msg.as_string())
        
        logger.info(f"Email sent via SMTP to {notification.recipient}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {e}")
        return False


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
    subject = f"[kleinanzeigen-ai] {result_count} neue Angebote für '{keywords}'"
    
    # Build HTML body
    results_html = ""
    for i, result in enumerate(results[:10], 1):  # Limit to 10 results per email
        trust_score = result.get("trust_score", 0)
        trust_badge = _get_trust_badge_html(trust_score)
        results_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">
                <strong>{i}. {result.get('title', 'N/A')}</strong><br>
                Preis: {result.get('price', 'N/A')}<br>
                Ort: {result.get('location', 'N/A')}<br>
                {trust_badge}
                <a href="{result.get('url', '#')}" style="color: #0066cc;">Anzeige ansehen →</a>
            </td>
        </tr>
        """
    
    highlight_section = ""
    if highlight:
        highlight_section = f"""
        <div style="background-color: #fff3cd; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
            <strong style="color: #856404;">🎯 Deal Alert:</strong> {highlight}
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
                <p>{result_count} neue Angebote für: <strong>{keywords}</strong></p>
            </div>
            <div class="content">
                {highlight_section}
                <h2>Neue Angebote:</h2>
                <table>
                    {results_html}
                </table>
                <p style="margin-top: 20px; text-align: center;">
                    <a href="https://kleinanzeigen-ai.de/dashboard" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
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
    
    return f"""
    <span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px;">
        Trust Score: {trust_score}/100 ({label})
    </span><br>
    """
