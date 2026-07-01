"""Price parsing + deal scoring — the market-intelligence layer.

kleinanzeigen shows a raw price string per listing but never any market
context. These helpers turn the string into a number, compute the median
across a search's results, and classify each listing as below / at / above
market so the UI and notifications can surface "good deals".
"""
import re
import statistics
from typing import Optional

# Matches a German-formatted number: 1.200  or  1.234,56  or  120
_NUM_RE = re.compile(r"\d[\d.\s]*(?:,\d+)?")


def parse_price(text: Optional[str]) -> Optional[int]:
    """Parse a listing price string to whole euros. None if not a number.

    Handles German formatting ("1.200 €" -> 1200, "1.234,56 €" -> 1235),
    negotiable suffixes ("120 € VB"), and free items ("Zu verschenken" -> 0).
    """
    if not text:
        return None
    if "verschenken" in text.lower():  # "Zu verschenken" == free
        return 0
    m = _NUM_RE.search(text)
    if not m:
        return None
    # '.' and spaces are thousands separators; ',' is the decimal point.
    raw = m.group(0).replace(".", "").replace(" ", "").replace(",", ".")
    try:
        return int(round(float(raw)))
    except ValueError:
        return None


def median_price(values) -> Optional[float]:
    """Median of the positive numeric prices in ``values`` (ignores None/0)."""
    nums = [v for v in values if v is not None and v > 0]
    if not nums:
        return None
    return statistics.median(nums)


def deal_badge(value: Optional[int], median: Optional[float]) -> Optional[dict]:
    """Classify a listing price against the search median.

    Returns {"label", "cls", "pct"} or None when there isn't enough info.
    Threshold is ±15% around the median.
    """
    if value is None or median is None or median <= 0:
        return None
    if value == 0:
        return {"label": "Free", "cls": "deal-great", "pct": -100.0}
    pct = (value - median) / median * 100.0
    if pct <= -15:
        return {"label": f"{abs(round(pct))}% below market", "cls": "deal-great", "pct": pct}
    if pct >= 15:
        return {"label": f"{round(pct)}% above market", "cls": "deal-high", "pct": pct}
    return {"label": "Fair price", "cls": "deal-fair", "pct": pct}
