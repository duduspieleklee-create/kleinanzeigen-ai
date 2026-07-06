"""Smart Alerts — deterministic, no-LLM result summaries.

Turns a scrape run's already-computed deal data (see app/shared/pricing.py)
into one German sentence for the dashboard. Deliberately not LLM-generated:
no API key, no latency, no failure mode in the notification path — see
.claude/skills/sentry-deployment-security for why that trade-off was made.
"""
from typing import Optional


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
