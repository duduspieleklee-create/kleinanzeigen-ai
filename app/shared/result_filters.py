"""Advanced result filters (Core/Pro): require / exclude keywords + exclude
locations, applied to scraped listings BEFORE they become results.

kleinanzeigen's search URL can't express "must NOT contain X" or "exclude town
Y" (see app/shared/url_builder.py — it only has keyword match, category code
and PLZ+radius). So these are our own post-scrape filters, run in the worker on
each parsed listing before it is deduped, saved, credited or notified — a
listing the user filtered out never costs a credit and never triggers an alert.

Semantics (locked with the product owner):
- "require": ALL terms must be present (AND), matched as WHOLE WORDS, case-
  insensitively, across the listing's title + description.
- "exclude": NONE of the terms may be present (same matching).
- "exclude_locations": drop the listing if its location contains any excluded
  place — substring match, so "Saarbrücken" or the PLZ "66111" both catch
  "66111 Saarbrücken".

Whole-word matching uses ``\b`` boundaries: "defekt" matches "defekt" but not
"defekte" — deliberately precise per the owner's choice (substring was the
alternative). Terms are pre-normalised to lowercase when stored, so callers pass
already-parsed lists; ``parse_terms`` produces them from raw form input.
"""
import re

# Split raw form input on commas, semicolons and newlines — the separators a
# user is likely to type between terms. Spaces are NOT separators, so a term
# may itself be multi-word (e.g. "neu ovp").
_SEPARATORS = re.compile(r"[,\n;]+")

# Bound how much a single search can carry, so the parameters JSON stays small
# and the per-listing filter loop stays cheap.
MAX_TERMS = 25
MAX_TERM_LEN = 60


def parse_terms(raw: str | None) -> list[str]:
    """Parse raw form input into a normalised (lowercase, trimmed) term list.

    Deduplicates while preserving order and caps count/length so a pasted wall
    of text can't bloat the stored parameters.
    """
    if not raw:
        return []
    seen: set[str] = set()
    terms: list[str] = []
    for part in _SEPARATORS.split(raw):
        term = part.strip().lower()[:MAX_TERM_LEN].strip()
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
        if len(terms) >= MAX_TERMS:
            break
    return terms


def _whole_word_present(term: str, text: str) -> bool:
    """True if ``term`` appears as a whole word in ``text`` (both lowercase)."""
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def passes_filters(
    title: str | None,
    description: str | None,
    location: str | None,
    *,
    require: list[str] | None = None,
    exclude: list[str] | None = None,
    exclude_locations: list[str] | None = None,
) -> bool:
    """Return True if a listing should be KEPT under the given filters.

    Terms are expected pre-normalised (lowercase) — see ``parse_terms``. Empty
    filter lists are no-ops, so a listing with no filters always passes.
    """
    text = f"{title or ''} {description or ''}".lower()

    for term in (require or []):
        if not _whole_word_present(term, text):
            return False

    for term in (exclude or []):
        if _whole_word_present(term, text):
            return False

    loc = (location or "").lower()
    for place in (exclude_locations or []):
        if place and place in loc:
            return False

    return True
