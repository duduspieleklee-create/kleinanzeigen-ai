import re
from typing import Optional
from urllib.parse import urlencode


def _sanitize_path_segment(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\-]", "", value.replace(" ", "-").lower())


# Valid enum values — anything outside these is silently ignored so old DB rows
# with missing/None fields degrade gracefully to "no filter applied".
_VALID_AD_TYPES = {"angebote", "gesuche"}
_VALID_POSTER_TYPES = {"privat", "gewerblich"}
_VALID_CONDITIONS = {"new_with_tag", "new", "like_new", "ok", "alright", "defect"}
_VALID_SHIPPING = {"ja", "nein"}
_VALID_SORTS = {"SORTING_DATE", "SORTING_PRICE_ASC", "SORTING_PRICE_DESC", "SORTING_RELEVANCE"}
_VALID_RADII = {5, 10, 20, 30, 50, 100, 150, 200}


def build_kleinanzeigen_url(
    keywords: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    radius: Optional[int] = None,
    sort: Optional[str] = "SORTING_DATE",
    ad_type: Optional[str] = None,
    poster_type: Optional[str] = None,
    condition: Optional[str] = None,
    shipping: Optional[str] = None,
    # Scheduling-only key stored in parameters JSON — not a URL param
    interval_seconds: Optional[int] = None,  # noqa: ARG001
) -> str:
    """
    Build a kleinanzeigen.de search URL from structured parameters.

    URL shape (reverse-engineered from live site):
      /[anzeige:{angebote|gesuche}/]
      /[anbieter:{privat|gewerblich}/]
      /[versand:{ja|nein}/]
      /s-{category}/
      /{location}/          (omitted when no location)
      /{keyword-slug}/      (omitted when no keywords)
      /k0[+global.zustand:{condition}]
      ?minPrice=&maxPrice=&sortingField=&radius=
    """
    base = "https://www.kleinanzeigen.de"
    path_parts = []

    # ── Filter prefix segments (each carries its own s- prefix) ─────────────
    if ad_type in _VALID_AD_TYPES:
        path_parts.append(f"s-anzeige:{ad_type}")
    if poster_type in _VALID_POSTER_TYPES:
        path_parts.append(f"s-anbieter:{poster_type}")
    if shipping in _VALID_SHIPPING:
        path_parts.append(f"s-versand:{shipping}")

    # ── Category ────────────────────────────────────────────────────────────
    if category:
        path_parts.append(f"s-{_sanitize_path_segment(category)}")
    else:
        path_parts.append("s-anzeigen")

    # ── Location ────────────────────────────────────────────────────────────
    if location:
        path_parts.append(_sanitize_path_segment(location))

    # ── Keywords + condition ─────────────────────────────────────────────────
    if keywords:
        path_parts.append(_sanitize_path_segment(keywords))

    k0 = "k0"
    if condition in _VALID_CONDITIONS:
        k0 += f"+global.zustand:{condition}"
    path_parts.append(k0)

    path = "/" + "/".join(path_parts)

    # ── Query parameters ─────────────────────────────────────────────────────
    query: dict = {}
    if price_min is not None:
        query["minPrice"] = int(price_min)
    if price_max is not None:
        query["maxPrice"] = int(price_max)
    if sort and sort in _VALID_SORTS and sort != "SORTING_DATE":
        query["sortingField"] = sort
    if radius and int(radius) in _VALID_RADII:
        query["radius"] = int(radius)

    if query:
        return f"{base}{path}?{urlencode(query)}"
    return f"{base}{path}"
