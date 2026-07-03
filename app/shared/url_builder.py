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
    location_id: Optional[int] = None,
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

    When location_id is provided the canonical URL is used:
      /s-{location_slug}/{keywords}/k0l{locationId}[r{radius}][+global.zustand:{condition}]

    Without location_id (backward-compat / text-only location):
      /[filter-prefixes/]s-{category}/{location-slug}/{keywords}/k0[+condition]
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

    # ── Category + keywords path ────────────────────────────────────────────
    # kleinanzeigen URL shapes:
    #   category only       → /s-{category}/k0
    #   category + keywords → /s-{category}/{keywords}/k0        ✓ accepted
    #   keyword only        → /s-{keyword}/k0                    ✓ accepted
    #   neither             → /s-anzeigen/k0
    # /s-anzeigen/{keyword}/k0 is REJECTED (400) by kleinanzeigen — do not use.
    if category:
        path_parts.append(f"s-{_sanitize_path_segment(category)}")
    elif keywords:
        # Keyword-only: fold keyword into the leading s- segment so we avoid
        # the rejected /s-anzeigen/{keyword}/k0 shape.
        path_parts.append(f"s-{_sanitize_path_segment(keywords)}")
    else:
        path_parts.append("s-anzeigen")

    # ── Location slug (display / SEO only — the real scoping is via locationId) ──
    if location:
        path_parts.append(_sanitize_path_segment(location))

    # ── Keywords ─────────────────────────────────────────────────────────────
    if keywords:
    # ── Keywords in path (only when a category is also set) ──────────────────
    # When keyword-only, the keyword already lives in the s- segment above.
    if keywords and category:
        path_parts.append(_sanitize_path_segment(keywords))

    # ── k0 token: locationId + radius go here when locationId is known ───────
    k0 = "k0"
    if location_id:
        k0 += f"l{int(location_id)}"
        if radius and int(radius) in _VALID_RADII:
            k0 += f"r{int(radius)}"
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
    # Radius falls back to query param only when locationId is absent (old tasks)
    if radius and int(radius) in _VALID_RADII and not location_id:
        query["radius"] = int(radius)

    if query:
        return f"{base}{path}?{urlencode(query)}"
    return f"{base}{path}"
