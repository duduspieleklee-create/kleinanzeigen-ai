"""
Google Trends Integration für Smart Search Suggestions.

Holt aktuelle Trend-Daten von Google Trends zu einem Keyword.
Ergebnisse werden gecached (10 Min TTL) um Rate-Limits zu vermeiden.
Fallback: leere Liste bei Fehlern.
"""

import logging
from datetime import datetime, timedelta
from pytrends.request import TrendReq

logger = logging.getLogger("kleinanzeigen-ai")

# Cache: keyword -> (data, timestamp)
_cache: dict[str, tuple[list[str], datetime]] = {}

# TTL: 10 Minuten
_CACHE_TTL = timedelta(minutes=10)

# Maximale Versuche bevor wir aufgeben
_MAX_RETRIES = 2


def get_trending_searches(keyword: str, geo: str = "DE") -> list[str]:
    """
    Holt Trending-Searches zu einem Keyword von Google Trends.

    Parameter:
        keyword: Das Such-Keyword
        geo: Ländercode (DE = Deutschland)

    Rückgabe:
        Liste von Trending-Strings (max 10), leere Liste bei Fehler
    """
    now = datetime.now()

    # Cache prüfen
    if keyword in _cache:
        cached_data, cached_at = _cache[keyword]
        if now - cached_at < _CACHE_TTL:
            logger.debug("Trends cache HIT for '%s'", keyword)
            return cached_data

    logger.info("Trends cache MISS for '%s' — fetching from Google Trends", keyword)

    try:
        data = _fetch_trends(keyword, geo)
        if data:
            _cache[keyword] = (data, now)
        return data
    except Exception as e:
        logger.warning("Google Trends fetch error for '%s': %s", keyword, e)
        # Bei Fehler: falls Cache existiert, alten Cache zurückgeben
        if keyword in _cache:
            stale_data, _ = _cache[keyword]
            logger.info("Returning stale cache for '%s' (%d items)", keyword, len(stale_data))
            return stale_data
        return []


def _fetch_trends(keyword: str, geo: str = "DE") -> list[str]:
    """Führt den eigentlichen Google Trends API Call aus."""
    if not keyword or len(keyword) < 2:
        return []

    # Verwandte Suchanfragen (related queries) liefern Trending-Vorschläge
    pytrends = TrendReq(hl="de-DE", tz=360, timeout=5)

    # Ersten Versuch: related queries für das Keyword
    pytrends.build_payload([keyword], cat=0, timeframe="now 7-d", geo=geo)
    related = pytrends.related_queries()

    results: list[str] = []

    if keyword in related:
        item = related[keyword]
        # "top" = meistgesuchte verwandte Queries
        if item.get("top") is not None:
            top_df = item["top"]
            if not top_df.empty:
                top_queries = top_df["query"].tolist()[:10]
                results.extend(q for q in top_queries if q.lower() != keyword.lower())

        # "rising" = am stärksten steigende Queries
        if item.get("rising") is not None:
            rising_df = item["rising"]
            if not rising_df.empty:
                rising_queries = rising_df["query"].tolist()[:5]
                results.extend(q for q in rising_queries if q.lower() not in (r.lower() for r in results))

    # fallback: trending_searches (tagesaktuelle Trends)
    if not results:
        try:
            trending_df = pytrends.trending_searches(pn="germany")
            if trending_df is not None and not trending_df.empty:
                results.extend(trending_df.iloc[:, 0].tolist()[:5])
        except Exception:
            pass

    return results[:10]


def get_trending_searches_batch(keywords: list[str], geo: str = "DE") -> dict[str, list[str]]:
    """Batch-Variante: Holt Trends für mehrere Keywords auf einmal."""
    result = {}
    for kw in keywords:
        result[kw] = get_trending_searches(kw, geo)
    return result


def clear_cache():
    """Leert den Cache (für Tests)."""
    _cache.clear()
