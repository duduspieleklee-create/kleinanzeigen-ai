"""
AI-Assisted Search – KI-gestützte Suchassistent für kleinanzeigen-ai

Der User beschreibt auf Deutsch was er sucht. Das Modul parst die Beschreibung,
extrahiert Suchparameter, führt die Suche aus und erlaubt iteratives Verfeinern
per Feedback ("mehr davon", "weniger davon").

Abhängigkeiten:
- Custom Model Endpoint (optional): Für semantisches Parsing und Ranking
- Fallback: Regex-basierte Extraktion + Standard-Suche
"""

import logging
import re
from typing import Optional

logger = logging.getLogger("kleinanzeigen-ai")

# Pattern: Preis-Angaben (range zuerst, sonst frisst "max" den "bis"-Range)
_PRICE_PATTERNS = [
    (r"(\d+)\s*[–\-]+\s*(\d+)\s*(€|eur|euro)?", "range"),
    (r"(\d+)\s+bis\s+(\d+)\s*(€|eur|euro)?", "range"),
    (r"(?:bis|max|maximal|unter|höchstens)\s*(\d+)\s*(€|eur|euro)?", "max"),
    (r"(?:ab|min|mindestens|über)\s*(\d+)\s*(€|eur|euro)?", "min"),
    (r"(\d+)\s*(€|eur|euro)", "exact"),
]

# Pattern: Orts-Angaben
_LOCATION_PATTERNS = [
    r"(?:in|bei|um|nahe|aus)\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s[A-ZÄÖÜ][a-zäöüß]+)*)",
]

# Common German cities so bare follow-up answers like "Berlin" still count
# as a location in multi-turn chat (no "in ..." prefix required).
_KNOWN_CITIES = {
    "berlin", "hamburg", "münchen", "muenchen", "köln", "koeln", "frankfurt",
    "stuttgart", "düsseldorf", "duesseldorf", "leipzig", "dortmund", "essen",
    "bremen", "dresden", "hannover", "nürnberg", "nuernberg", "duisburg",
    "bochum", "wuppertal", "bielefeld", "bonn", "münster", "muenster",
    "karlsruhe", "mannheim", "augsburg", "wiesbaden", "gelsenkirchen",
    "mönchengladbach", "moenchengladbach", "braunschweig", "chemnitz",
    "kiel", "aachen", "halle", "magdeburg", "freiburg", "krefeld", "lübeck",
    "luebeck", "oberhausen", "erfurt", "mainz", "rostock", "kassel",
    "hagen", "hamm", "saarbrücken", "saarbruecken", "mülheim", "muelheim",
    "potsdam", "ludwigshafen", "oldenburg", "leverkusen", "osnabrück",
    "osnabrueck", "solingen", "heidelberg", "herne", "neuss", "darmstadt",
    "paderborn", "regensburg", "ingolstadt", "würzburg", "wuerzburg",
    "fürth", "fuerth", "wolfsburg", "offenbach", "ulm", "heilbronn",
    "pforzheim", "göttingen", "goettingen", "bottrop", "trier", "reutlingen",
    "koblenz", "remscheid", "bergisch", "jena", "reutlingen", "erlangen",
    "moers", "siegen", "hildesheim", "salzgitter",
}

# Stopwörter für Keyword-Extraktion
_STOPWORDS = {
    "der", "die", "das", "ein", "eine", "einen", "einer", "eines",
    "ich", "suche", "möchte", "will", "hätte", "gerne", "bitte",
    "und", "oder", "aber", "auch", "noch", "schon", "mal",
    "für", "auf", "mit", "von", "aus", "bei", "nach", "in",
    "ist", "hat", "habe", "wird", "kann", "soll", "muss",
    "nicht", "kein", "keine", "einen", "dem", "den", "des",
    "dass", "weil", "wenn", "dann", "dort", "hier", "da",
    "neu", "gebraucht", "zu", "zum", "zur",
    "hallo", "hi", "hey", "guten", "tag", "moin", "servus", "tschüss", "hallo", "danke",
}

# Wörter die nach Preis-Extraktion aus Keywords entfernt werden
_PRICE_CONSUMED = {"unter", "bis", "max", "ab", "über", "unter", "maximal", "mindestens", "höchstens"}

# Wörter die auf eine Kategorie hindeuten
_CATEGORY_HINTS: dict[str, list[str]] = {
    "möbel": ["sofa", "tisch", "schrank", "regal", "bett", "stuhl", "kommode",
              "couch", "sessel", "vitrine", "sideboard", "matratze"],
    "elektronik": ["handy", "smartphone", "iphone", "laptop", "tablet", "fernseher", "tv",
                   "kamera", "kopfhörer", "lautsprecher", "computer", "notebook",
                   "monitor", "drucker", "konsole", "playstation", "xbox"],
    "fahrzeuge": ["auto", "wagen", "motorrad", "roller", "fahrrad", "e-bike",
                  "pkw", "kombi", "cabrio", "suv", "transporter", "anhänger"],
    "garten": ["pflanze", "baum", "rasen", "blume", "gartenhaus", "pool",
               "grill", "gartengeräte", "rasenmäher", "gartenstuhl"],
    "kleidung": ["jacke", "hose", "schuhe", "pullover", "hemd", "kleid",
                 "t-shirt", "jeans", "stiefel", "sneaker"],
}

# Wunsch-Keywords (User-Feedback für "mehr davon")
_POSITIVE_KEYWORDS = ["mehr", "davon", "ähnlich", "genau", "ja", "gut", "passt", "super", "gefällt"]
_NEGATIVE_KEYWORDS = ["weniger", "anderes", "nicht", "nein", "schlecht", "falsch"]


def parse_query(text: str) -> dict:
    """Parst einen natürlichsprachlichen Suchtext in strukturierte Parameter.

    Rückgabe:
        dict mit keys: keywords, category, price_min, price_max, location
    """
    result: dict = {
        "keywords": [],
        "category": "",
        "price_min": None,
        "price_max": None,
        "location": "",
        "raw": text,
    }

    if not text:
        return result

    cleaned = text.strip().lower()

    # Preis extrahieren
    for pattern, kind in _PRICE_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            if kind == "max":
                result["price_max"] = int(match.group(1))
            elif kind == "min":
                result["price_min"] = int(match.group(1))
            elif kind == "range":
                result["price_min"] = int(match.group(1))
                result["price_max"] = int(match.group(2))
            elif kind == "exact":
                result["price_max"] = int(match.group(1)) * 1.2  # +/-20%
                result["price_min"] = int(match.group(1)) * 0.8
            break

    # Location extrahieren (darf keine Preis-Wörter enthalten)
    for pattern in _LOCATION_PATTERNS:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            loc = match.group(1)
            # Verwerfen falls Preis-Wörter enthalten sind
            price_words = {"unter", "bis", "ab", "über", "max", "min"}
            loc_tokens = set(re.findall(r"[a-zäöüß]+", loc.lower()))
            if not price_words & loc_tokens:
                result["location"] = loc
                break
    # Simple fallback: look for " in <city>" at the end of the string
    if not result["location"]:
        fallback_match = re.search(r"\bin\s+([a-zäöüß]+)\b", cleaned)
        if fallback_match:
            result["location"] = fallback_match.group(1).title()
    # Bare city / PLZ (multi-turn chat: user replies just "Berlin" or "10115")
    if not result["location"]:
        plz_match = re.search(r"\b(\d{5})\b", cleaned)
        if plz_match:
            result["location"] = plz_match.group(1)
        else:
            tokens = re.findall(r"[a-zäöüß]+", cleaned)
            for t in tokens:
                if t in _KNOWN_CITIES:
                    result["location"] = t.title()
                    break
            # Single-token follow-up that looks like a place name (not a known item)
            if not result["location"] and len(tokens) == 1:
                token = tokens[0]
                known_items = {h for hints in _CATEGORY_HINTS.values() for h in hints}
                if (
                    token not in _STOPWORDS
                    and token not in _PRICE_CONSUMED
                    and token not in known_items
                    and len(token) >= 3
                ):
                    result["location"] = token.title()

    # Keywords extrahieren (remove stopwords, filter meaningful words)
    tokens = re.findall(r"[a-zäöüß]+", cleaned)
    keywords = [
        t for t in tokens
        if t not in _STOPWORDS
        and len(t) > 2
        and t not in _PRICE_CONSUMED
        and t not in _KNOWN_CITIES
        and not re.fullmatch(r"\d{5}", t)
    ]

    # Kategorie erkennen (exakte Token-Matches + Compound-Substrings)
    token_set = set(re.findall(r"[a-zäöüß]+", cleaned))
    best_cat = ""
    best_count = 0
    for cat, hints in _CATEGORY_HINTS.items():
        count = 0
        for h in hints:
            # Exakter Treffer
            if h in token_set:
                count += 2
            # Compound-Treffer (z.B. "eichensofa" enthält "sofa")
            elif any(h in t for t in token_set):
                count += 1
        if count > best_count:
            best_count = count
            best_cat = cat
    if best_cat:
        result["category"] = best_cat

    result["keywords"] = keywords[:6]  # max 6 keywords
    return result


def generate_search_text(parsed: dict) -> str:
    """Erzeugt einen lesbaren Suchtext aus den geparsten Parametern."""
    parts = []
    if parsed.get("keywords"):
        parts.append(" ".join(parsed["keywords"][:3]))
    if parsed.get("category"):
        parts.append(f"({parsed['category']})")
    if parsed.get("price_min") or parsed.get("price_max"):
        price_str = ""
        if parsed.get("price_min") and parsed.get("price_max"):
            price_str = f"{parsed['price_min']}€–{parsed['price_max']}€"
        elif parsed.get("price_min"):
            price_str = f"ab {parsed['price_min']}€"
        elif parsed.get("price_max"):
            price_str = f"bis {parsed['price_max']}€"
        parts.append(price_str)
    if parsed.get("location"):
        parts.append(f"in {parsed['location']}")
    return " ".join(parts)


def extract_keywords_for_search(parsed: dict) -> str:
    """Erzeugt den Keyword-String für die eigentliche Suche auf kleinanzeigen."""
    kw = parsed.get("keywords", [])
    cat = parsed.get("category", "")
    search_terms = list(kw)
    if cat and not any(cat in str(k) for k in kw):
        search_terms.append(cat)
    return " ".join(search_terms[:4]) if search_terms else parsed.get("raw", "")


def rank_results(results: list[dict], query: str, liked_ids: Optional[set[int]] = None) -> list[dict]:
    """Rankt Ergebnisse nach Relevanz zum Original-Query.
    
    Aktuell: einfaches Keyword-Matching.
    Mit Custom Model: semantisches Ranking via Embeddings/LLM.
    """
    liked_ids = liked_ids or set()
    query_lower = query.lower()
    query_tokens = set(re.findall(r"[a-zäöüß]+", query_lower))

    scored = []
    for r in results:
        score = 0
        title = (r.get("title") or "").lower()
        desc = (r.get("description") or "").lower()
        text = title + " " + desc

        # Boost: liked IDs priorisieren
        if r.get("id") in liked_ids:
            score += 50

        # Keyword-Matching
        for token in query_tokens:
            if token in title:
                score += 10
            elif token in text:
                score += 3

        # Preis-Nähe zum Query (falls Preismentioned)
        price = r.get("price_value")
        if price:
            price_matches = re.findall(r"(\d+)", query)
            for pm in price_matches:
                target = int(pm)
                diff = abs(price - target)
                if diff < 50:
                    score += 5
                elif diff < 200:
                    score += 2

        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored]


def feedback_to_refinement(feedback: list[dict], liked_ids: set[int], disliked_ids: set[int]) -> str:
    """Erzeugt aus User-Feedback einen verfeinerten Suchtext.
    
    feedback: Liste von {result_id, action: "like"|"dislike"}
    """
    hints = []
    if liked_ids:
        hints.append(f"zeige mehr ähnlich wie Anzeigen #{','.join(str(i) for i in liked_ids)}")
    if disliked_ids:
        hints.append(f"weniger wie Anzeigen #{','.join(str(i) for i in disliked_ids)}")
    return ". ".join(hints)
