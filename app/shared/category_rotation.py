"""Category batches for the automatic admin-search reference-data rotation.

Same category slugs as the search wizard's dropdown (app/api/templates/
dashboard.html), in the same order, except the three requested launch
categories are moved to the front. See app/worker/category_rotation_task.py
for the scheduler that activates one batch at a time.

"multimedia-elektronik" (the umbrella "Elektronik (allgemein)" slug) is
deliberately excluded: kleinanzeigen.de returns HTTP 200 with 0 listings when
it's combined with the s-anbieter:privat/ filter prefix that every rotation
search uses (confirmed 2026-07-06 — genuine leaf categories like
handy-telekom/notebooks/autos work fine with the same prefix). Since the
poster_type filter is fixed for the whole rotation, this slug would silently
yield nothing every time it came up, so "handy-telekom" stands in for
Elektronik instead.
"""

_PRIORITY_FIRST = ["dienstleistungen", "handy-telekom", "autos"]

_ALL_CATEGORIES = [
    "autos", "fahrraeder", "autoteile-reifen", "boote-bootszubehoer",
    "motorraeder-roller", "motorraeder-roller-teile", "anhaenger-nutzfahrzeuge",
    "wohnwagen-mobile",
    "wohnung-mieten", "wohnung-kaufen", "haus-mieten", "haus-kaufen",
    "auf-zeit-wg", "garage-lagerraum", "grundstuecke-garten",
    "gewerbeimmobilien", "ferienwohnung-ferienhaus",
    "kueche-esszimmer", "wohnzimmer", "schlafzimmer", "badezimmer",
    "bueromoebel", "dekoration", "garten-pflanzen", "heimtextilien",
    "heimwerken", "lampen-licht",
    "kleidung-damen", "kleidung-herren", "schuhe-damen", "schuhe-herren",
    "beauty-gesundheit", "accessoires-schmuck", "uhren-schmuck",
    "handy-telekom", "haushaltsgeraete", "audio-hifi",
    "foto", "tv-video", "notebooks", "pcs", "pc-zubehoer-software",
    "tablets-reader", "konsolen", "pc-videospiele", "wearables",
    "baby-kinderkleidung", "baby-kinderschuhe", "babyausstattung",
    "babyschalen-kindersitze", "kinderwagen-buggys", "kinderzimmermoebel",
    "spielzeug", "babysitter-kinderbetreuung", "altenpflege",
    "hunde", "katzen", "kleintiere", "voegel", "fische", "pferde",
    "nutztiere", "tierbetreuung-training", "zubehoer",
    "sammeln", "kunst", "sport-camping", "handarbeit-basteln-kunsthandwerk",
    "modellbau", "reise-eventservices", "freizeitaktivitaeten",
    "troedel-kistenweise", "esoterik-spirituelles", "verloren-gefunden",
    "buecher-zeitschriften", "fachbuecher-schule-studium", "film-dvd",
    "musik-cds", "musikinstrumente", "comics",
    "konzerte", "klassik-kultur", "comedy-kabarett", "gutscheine",
    "zu-verschenken", "zu-verschenken-tauschen", "verleihen",
    "jobs", "ausbildung", "praktika", "heimarbeit-mini-nebenjobs",
    "bueroarbeit-verwaltung", "gastronomie-tourismus",
    "bau-handwerk-produktion", "vertrieb-einkauf-verkauf",
    "dienstleistungen", "umzug-transport", "unterricht-kurse", "nachhilfe",
    "sprachkurse", "nachbarschaftshilfe",
]

_seen = set(_PRIORITY_FIRST)
_ORDERED_CATEGORIES = _PRIORITY_FIRST + [
    c for c in _ALL_CATEGORIES if c not in _seen and not _seen.add(c)
]

BATCH_SIZE = 3
CATEGORY_BATCHES = [
    _ORDERED_CATEGORIES[i:i + BATCH_SIZE]
    for i in range(0, len(_ORDERED_CATEGORIES), BATCH_SIZE)
]
