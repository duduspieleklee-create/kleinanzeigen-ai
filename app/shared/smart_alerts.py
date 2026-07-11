"""Smart Alerts — deterministic, no-LLM result summaries.

Turns a scrape run's already-computed deal data (see app/shared/pricing.py)
into one German sentence for the dashboard. Deliberately not LLM-generated:
no API key, no latency, no failure mode in the notification path — see
.claude/skills/sentry-deployment-security for why that trade-off was made.
"""
from typing import Optional


def build_smart_summary(
    new_count: int,
    keywords: str,
    deal_title: Optional[str] = None,
    best_price_str: Optional[str] = None,
) -> str:
    """One-line summary of a scrape run for ScrapeTask.last_summary.

    deal_title/best_price_str are only passed when the caller already found
    a below-market deal among the new results (Core/Pro only — see the
    deal_badges gate in app/worker/tasks.py) — Basic users get the plain count.
    """
    subject = f"„{keywords}“" if keywords else "deine Suche"
    count_str = "1 neuer Treffer" if new_count == 1 else f"{new_count} neue Treffer"

    if deal_title and best_price_str:
        return f"{count_str} für {subject} — Top-Deal: {deal_title} für {best_price_str}."
    return f"{count_str} für {subject}."


def build_push_notification(
    new_count: int,
    keywords: str = "",
    cheapest_price: Optional[str] = None,
    location: Optional[str] = None,
    deal: Optional[dict] = None,
) -> dict:
    """Baut Titel + Body einer Web-Push-Notification (Deutsch, deterministisch).

    Ziel: nur Inhalte mit echtem Mehrwert — Preis, Ersparnis, Ort — statt eines
    nackten Keywords.

    ``deal`` wird NUR übergeben, wenn der Nutzer konkret nach einem Gegenstand
    sucht (``keywords`` gesetzt) und ein Angebot unter Marktpreis gefunden wurde:
    ``{"title", "price", "saving_eur", "trust_score"}``. Bei reinem Kategorie-/
    Service-Stöbern ist ein „unter Marktpreis" sinnlos, also fällt die
    Notification auf „N neue Treffer + ab-Preis + Ort" zurück.

    Returns ``{"title": str, "body": str}``.
    """
    subject = f"„{keywords}“" if keywords else "deine Suche"

    if deal:
        saving = deal.get("saving_eur")
        title = f"🔥 {saving} € unter Marktpreis" if saving and saving > 0 \
            else "🔥 Top-Deal gefunden"
        headline = deal.get("title") or subject
        price = deal.get("price")
        first = f"{headline} – {price}" if price else headline
        meta = []
        if location:
            meta.append(f"📍 {location}")
        trust = deal.get("trust_score")
        if trust:
            meta.append(f"⭐ Verkäufer {trust}/100")
        body = first if not meta else f"{first}\n" + " · ".join(meta)
        return {"title": title, "body": body}

    count_str = "1 neuer Treffer" if new_count == 1 else f"{new_count} neue Treffer"
    title = f"🆕 {count_str} für {subject}" if keywords else f"🆕 {count_str}"
    meta = []
    if cheapest_price:
        meta.append(f"ab {cheapest_price}")
    if location:
        meta.append(f"📍 {location}")
    body = " · ".join(meta) if meta else "Jetzt ansehen"
    return {"title": title, "body": body}
