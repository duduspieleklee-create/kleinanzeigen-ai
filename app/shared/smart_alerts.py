"""Smart Alerts — deterministic, no-LLM result summaries.

Turns a scrape run's already-computed deal data (see app/shared/pricing.py)
into one German sentence for the dashboard. Deliberately not LLM-generated:
no API key, no latency, no failure mode in the notification path — see
.claude/skills/sentry-deployment-security for why that trade-off was made.
"""
from typing import Optional

# Category-specific copy for searches where price-comparison framing doesn't
# apply (see app/shared/category_profiles.py for which categories map here).
# Deliberately no "price"/"trust" keys with data the caller hasn't gated —
# build_push_notification only shows what it's given, so plan-gating
# (e.g. trust_score being a Core/Pro feature) is the caller's responsibility.
_PROFILE_COPY: dict[str, dict] = {
    "job": {
        "emoji": "🧑‍💼",
        "singular": "neues Stellenangebot",
        "plural": "neue Stellenangebote",
        "urgency": "Jetzt ansehen, bevor sie weg sind",
        "show_trust": False,
        "trust_label": "Anbieter",
    },
    "real_estate": {
        "emoji": "🏠",
        "singular": "neue Immobilie",
        "plural": "neue Immobilien",
        "urgency": "Schnell sein — Wohnungen gehen oft in Minuten weg",
        "show_trust": False,
        "trust_label": "Anbieter",
    },
    "service": {
        "emoji": "🧰",
        "singular": "neues Angebot",
        "plural": "neue Angebote",
        "urgency": None,
        "show_trust": True,
        "trust_label": "Anbieter",
    },
    "giveaway": {
        "emoji": "🎁",
        "singular": "neuer Artikel",
        "plural": "neue Artikel",
        "urgency": "Kostenlose Sachen sind sehr schnell weg",
        "show_trust": False,
        "trust_label": "Anbieter",
    },
    "animal": {
        "emoji": "🐾",
        "singular": "neuer Treffer",
        "plural": "neue Treffer",
        "urgency": None,
        "show_trust": True,
        "trust_label": "Anbieter",
    },
    "gesuche": {
        "emoji": "🔎",
        "singular": "neues Gesuch",
        "plural": "neue Gesuche",
        "urgency": None,
        "show_trust": False,
        "trust_label": "Anbieter",
    },
}


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
    profile: str = "item",
    trust_score: Optional[int] = None,
    sample_title: Optional[str] = None,
) -> dict:
    """Baut Titel + Body einer Web-Push-Notification (Deutsch, deterministisch).

    Ziel: nur Inhalte mit echtem Mehrwert statt eines nackten Keywords — was
    das im Detail heißt, hängt vom ``profile`` ab (siehe
    app/shared/category_profiles.py):

    - ``"item"`` (Default, auch für ``"ticket"``/``"vehicle"``-Suchen mit
      Keyword): Preisvergleich ist sinnvoll. ``deal`` wird NUR übergeben, wenn
      der Nutzer konkret nach einem Gegenstand sucht (``keywords`` gesetzt)
      und ein Angebot unter Marktpreis gefunden wurde — Format
      ``{"title", "price", "saving_eur", "trust_score"}``. Ohne ``deal``
      fällt die Notification auf „N neue Treffer + ab-Preis + Ort" zurück.
    - Jobs/Immobilien/Dienstleistungen/Verschenken/Tiere/Gesuche (siehe
      ``_PROFILE_COPY``): kein Preisvergleich — stattdessen kategorie-passende
      Formulierung + Dringlichkeit, wo sinnvoll (z. B. Wohnungen, kostenlose
      Artikel), + Trust-Score nur bei Profilen, wo ein Anbieter-Vertrauen
      wirklich hilft (Dienstleistungen, Tiere). ``trust_score`` und
      ``sample_title`` sind Caller-gated: dieser Funktion ist es egal, ob der
      Aufrufer den Trust-Score aus Plan-Gründen weggelassen hat — sie zeigt
      nur, was sie bekommt.

    Returns ``{"title": str, "body": str}``.
    """
    subject = f"„{keywords}“" if keywords else "deine Suche"

    if profile in _PROFILE_COPY:
        profile_copy = _PROFILE_COPY[profile]
        noun = profile_copy["singular"] if new_count == 1 else profile_copy["plural"]
        title = f"{profile_copy['emoji']} {new_count} {noun} für {subject}" if keywords \
            else f"{profile_copy['emoji']} {new_count} {noun}"

        has_headline = new_count == 1 and bool(sample_title)
        meta = []
        if has_headline:
            meta.append(sample_title)
        if cheapest_price:
            meta.append(cheapest_price if has_headline else f"ab {cheapest_price}")
        if location:
            meta.append(f"📍 {location}")
        if profile_copy["show_trust"] and trust_score:
            meta.append(f"⭐ {profile_copy['trust_label']} {trust_score}/100")
        if profile_copy["urgency"]:
            meta.append(profile_copy["urgency"])

        body = " · ".join(meta) if meta else "Jetzt ansehen"
        return {"title": title, "body": body}

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
