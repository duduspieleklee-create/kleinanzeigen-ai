"""Shared email-service health signal for the temporary Resend outage.

Resend can suspend/rate-limit the account, leaving every email send failing
(verification + new-results). When that happens we don't want to silently drop
mail — we surface a non-blocking in-app banner ("E-Mail-Versand vorübergehend
nicht verfügbar") so users understand why no mail arrives and retries don't
look like bugs.

State is a single mtime-pinned marker file (cheap, shared by the worker that
writes failures and the API that renders pages). We deliberately use a *file*,
not the DB, because this is an ephemeral operational signal, not user data.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

# Marker path — lives next to the running app (writable in the container).
_MARKER = os.environ.get(
    "EMAIL_DEGRADED_MARKER",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", ".email_degraded"),
)

# How long a single send failure keeps the banner up. Short enough that a
# transient blip self-heals, long enough that the banner is actually visible
# between scrape cycles (the worker retries 3x on every failing run).
_DEGRADED_WINDOW_S = 6 * 60 * 60  # 6 hours


def mark_email_failed() -> None:
    """Record that an email send just failed (call from the worker)."""
    try:
        with open(_MARKER, "w") as fh:
            fh.write(str(time.time()))
    except OSError:
        # Banner is best-effort; never let a marker write crash the worker.
        pass


def clear_email_failed() -> None:
    """Explicitly clear the degraded marker (e.g. on a successful send)."""
    try:
        os.remove(_MARKER)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def email_degraded() -> bool:
    """True when email has been failing recently enough to warn the user."""
    try:
        mtime = os.path.getmtime(_MARKER)
    except OSError:
        return False
    return (time.time() - mtime) < _DEGRADED_WINDOW_S


def email_degraded_since() -> str | None:
    """Human-readable "seit HH:MM" label for the banner, or None."""
    try:
        mtime = os.path.getmtime(_MARKER)
    except OSError:
        return None
    if (time.time() - mtime) >= _DEGRADED_WINDOW_S:
        return None
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return dt.strftime("%H:%M")
