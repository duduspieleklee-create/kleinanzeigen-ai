"""Maps a dashboard category slug to its kleinanzeigen.de numeric category id.

Why this exists: kleinanzeigen scopes a search to a category via a ``c{id}``
code inside the URL's ``k`` token (e.g. ``…/k0c208`` for "Häuser zum Kauf"),
*not* via the ``s-{slug}`` path segment — that segment is display/SEO text
only, exactly like the location slug (see ``build_kleinanzeigen_url`` in
``app/shared/url_builder.py``). Without the ``c{id}`` the ``k0`` token means
"all categories", so the URL degrades to a full-text search for the slug word
and returns listings from every category (a "haus-kaufen" search would surface
job ads, electronics, …). This module is the missing slug→id lookup.

The dashboard's own slugs (``category_options`` in ``dashboard.html``) are a
custom naming scheme that does *not* map 1:1 onto kleinanzeigen's URL slugs,
so the ids below were resolved against kleinanzeigen's live category tree and
grouped to match the dashboard's ``optgroup`` the slug lives under — several
slugs (e.g. ``umzug-transport``, ``beauty-gesundheit``, ``altenpflege``)
exist under more than one branch of kleinanzeigen's tree with different ids,
and the dashboard grouping is what disambiguates which one is meant.

If you add/rename a category in ``dashboard.html``, add its id here too — an
unmapped slug falls back to the old (broken) behaviour: no category filter.
"""

# Slug → kleinanzeigen category id. Grouped by the dashboard optgroup the slug
# belongs to (comments mirror the <optgroup label> text in dashboard.html).
CATEGORY_CODES: dict[str, int] = {
    # Auto, Rad & Boot (root c210)
    "autos": 216,
    "fahrraeder": 217,
    "autoteile-reifen": 223,
    "boote-bootszubehoer": 211,
    "motorraeder-roller": 305,
    "motorraeder-roller-teile": 306,
    "anhaenger-nutzfahrzeuge": 276,
    "wohnwagen-mobile": 220,
    # Immobilien (root c195)
    "wohnung-mieten": 203,
    "wohnung-kaufen": 196,
    "haus-mieten": 205,
    "haus-kaufen": 208,
    "auf-zeit-wg": 199,
    "garage-lagerraum": 197,
    "grundstuecke-garten": 207,
    "gewerbeimmobilien": 277,
    "ferienwohnung-ferienhaus": 275,
    # Haus & Garten (root c80)
    "kueche-esszimmer": 86,
    "wohnzimmer": 88,
    "schlafzimmer": 81,
    "badezimmer": 91,
    "bueromoebel": 93,
    "dekoration": 246,
    "garten-pflanzen": 89,
    "heimtextilien": 90,
    "heimwerken": 84,
    "lampen-licht": 82,
    # Mode & Beauty (root c153)
    "kleidung-damen": 154,
    "kleidung-herren": 160,
    "schuhe-damen": 159,
    "schuhe-herren": 158,
    "beauty-gesundheit": 224,  # Mode&Beauty branch (not the c269 Unterricht one)
    "accessoires-schmuck": 156,
    "uhren-schmuck": 157,
    # Elektronik (root c161) — "Elektronik (allgemein)" is the root itself
    "multimedia-elektronik": 161,  # root (not c293 Dienstleistungen>Elektronik)
    "handy-telekom": 173,
    "haushaltsgeraete": 176,
    "audio-hifi": 172,
    "foto": 245,
    "tv-video": 175,
    "notebooks": 278,
    "pcs": 228,
    "pc-zubehoer-software": 225,
    "tablets-reader": 285,
    "konsolen": 279,
    "pc-videospiele": 227,
    "wearables": 405,
    # Familie, Kind & Baby (root c17)
    "baby-kinderkleidung": 22,
    "baby-kinderschuhe": 19,
    "babyausstattung": 258,
    "babyschalen-kindersitze": 21,
    "kinderwagen-buggys": 25,
    "kinderzimmermoebel": 20,
    "spielzeug": 23,
    "babysitter-kinderbetreuung": 237,  # Familie branch (not c290 Dienstleistungen)
    "altenpflege": 236,  # Familie branch (not c288 Dienstleistungen)
    # Tiere (root c130)
    "hunde": 134,
    "katzen": 136,
    "kleintiere": 132,
    "voegel": 243,  # kleinanzeigen slug is "vogel"
    "fische": 138,
    "pferde": 139,
    "nutztiere": 135,
    "tierbetreuung-training": 133,  # Tiere branch (not c295 Dienstleistungen)
    "zubehoer": 313,  # Tierzubehör
    # Freizeit, Hobby & Nachbarschaft (root c185)
    "sammeln": 234,
    "kunst": 240,
    "sport-camping": 230,
    "handarbeit-basteln-kunsthandwerk": 282,
    "modellbau": 249,
    "reise-eventservices": 233,
    "freizeitaktivitaeten": 187,
    "troedel-kistenweise": 250,
    "esoterik-spirituelles": 232,  # Freizeit branch (not c265 Unterricht)
    "verloren-gefunden": 189,
    # Musik, Filme & Bücher (root c73)
    "buecher-zeitschriften": 76,
    "fachbuecher-schule-studium": 77,
    "film-dvd": 79,
    "musik-cds": 78,
    "musikinstrumente": 74,
    "comics": 284,
    # Eintrittskarten & Tickets (root c231)
    "konzerte": 255,
    "klassik-kultur": 251,
    "comedy-kabarett": 254,
    "gutscheine": 287,
    # Verschenken & Tauschen (root c272)
    "zu-verschenken": 192,  # "Verschenken" leaf
    "zu-verschenken-tauschen": 272,  # root "Zu Verschenken & Tauschen"
    "verleihen": 274,
    # Jobs (root c102) — "Jobs (allgemein)" is the root itself
    "jobs": 102,
    "ausbildung": 118,
    "praktika": 125,
    "heimarbeit-mini-nebenjobs": 107,
    "bueroarbeit-verwaltung": 114,
    "gastronomie-tourismus": 110,
    "bau-handwerk-produktion": 111,
    "vertrieb-einkauf-verkauf": 117,
    # Dienstleistungen & Unterricht (roots c297 Dienstleistungen / c235 Unterricht)
    "dienstleistungen": 297,  # root "Dienstleistungen (allgemein)"
    "umzug-transport": 296,  # Dienstleistungen branch (not c238 Immobilien)
    "unterricht-kurse": 235,  # root "Unterricht & Kurse"
    "nachhilfe": 268,
    "sprachkurse": 271,
    "nachbarschaftshilfe": 400,  # its own root
}


def category_code(category: str | None) -> int | None:
    """Return the kleinanzeigen numeric category id for a dashboard slug.

    Returns ``None`` for an unmapped/empty slug — the caller then builds a URL
    without a category filter (the pre-existing behaviour) rather than guessing
    a wrong category, which would be worse than no filter.
    """
    if not category:
        return None
    return CATEGORY_CODES.get(category)
