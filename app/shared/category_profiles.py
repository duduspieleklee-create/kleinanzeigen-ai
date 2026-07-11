"""Maps a search's kleinanzeigen.de category (and ad type) to a notification
*profile* — the piece of context that decides whether "X € unter Marktpreis"
framing makes sense in a push/email notification, or whether something else
(urgency, trust score, plain count) serves the user better.

Background: ``build_push_notification`` (see ``app/shared/smart_alerts.py``)
used to treat every search the same way once a keyword was set — a job
posting and an iPhone listing produced structurally identical notifications.
That's wrong: a price-comparison badge is meaningless for a job ad and mildly
tasteless for a puppy listing (price there is a "Schutzgebühr", not a market
price). This module is the single place that decides which category slug
maps to which behaviour, mirroring how ``category_options`` in
``dashboard.html`` is the single place the ~100 category slugs themselves are
defined — if that list changes, update the mapping here too.

Slugs not listed here (generic item categories: Elektronik, Mode, Auto,
Haus & Garten, Freizeit, Musik/Filme/Bücher, Sammeln, Auto/Rad/Boot, Tickets,
etc., or no category at all) fall back to ``"item"`` — the existing
price-comparison behaviour — since those are exactly the cases it was
designed for.
"""

# Slugs sourced from the `category_options` Jinja macro in
# app/api/templates/dashboard.html — keep in sync with that list.
CATEGORY_PROFILES: dict[str, str] = {
    # Jobs — no comparable "price" at all.
    "jobs": "job",
    "ausbildung": "job",
    "praktika": "job",
    "heimarbeit-mini-nebenjobs": "job",
    "bueroarbeit-verwaltung": "job",
    "gastronomie-tourismus": "job",
    "bau-handwerk-produktion": "job",
    "vertrieb-einkauf-verkauf": "job",
    # Immobilien — price is central but incomparable without size/room count,
    # which isn't scraped, so no "% below market" framing (yet).
    "wohnung-mieten": "real_estate",
    "wohnung-kaufen": "real_estate",
    "haus-mieten": "real_estate",
    "haus-kaufen": "real_estate",
    "auf-zeit-wg": "real_estate",
    "garage-lagerraum": "real_estate",
    "grundstuecke-garten": "real_estate",
    "gewerbeimmobilien": "real_estate",
    "ferienwohnung-ferienhaus": "real_estate",
    # Dienstleistungen & Unterricht — usually "VB"/hourly, no fixed price;
    # provider trust score matters more than any price comparison.
    "dienstleistungen": "service",
    "umzug-transport": "service",
    "unterricht-kurse": "service",
    "nachhilfe": "service",
    "sprachkurse": "service",
    "nachbarschaftshilfe": "service",
    # Verschenken & Tauschen — price is always 0/trade, so "€ saved" is
    # meaningless; what matters is that free listings disappear fast.
    "zu-verschenken": "giveaway",
    "zu-verschenken-tauschen": "giveaway",
    # Tiere — price is a "Schutzgebühr", not a market price; "deal" framing
    # is tasteless for a living animal.
    "hunde": "animal",
    "katzen": "animal",
    "kleintiere": "animal",
    "voegel": "animal",
    "fische": "animal",
    "pferde": "animal",
    "nutztiere": "animal",
    "tierbetreuung-training": "animal",
    "zubehoer": "animal",
}

# Profiles that never get price/"deal" framing, regardless of plan — see the
# module docstring for why. Anything not in this set (including the default
# "item" profile and category-less searches) keeps the existing
# price-comparison behaviour in build_push_notification.
NO_PRICE_PROFILES = {"job", "real_estate", "service", "giveaway", "animal", "gesuche"}

DEFAULT_PROFILE = "item"


def resolve_profile(category: str | None, ad_type: str | None = None) -> str:
    """Return the notification profile for a search's category + ad type.

    ``ad_type == "gesuche"`` (the user is watching for *want-ads* — someone
    looking for something, not offering it) always wins over the category:
    there is no "market price" concept for demand, whatever category it's
    filed under.
    """
    if ad_type == "gesuche":
        return "gesuche"
    if not category:
        return DEFAULT_PROFILE
    return CATEGORY_PROFILES.get(category, DEFAULT_PROFILE)
