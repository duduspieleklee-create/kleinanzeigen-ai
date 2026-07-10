"""Helpers for Set-Cookie values.

Starlette encodes the Set-Cookie header as latin-1, so any non-ASCII byte
(e.g. German `ü`, `ä`, or an en-dash `–`) raises UnicodeEncodeError at
response time and turns a 200 into a 500. User-facing flash messages are
written in German, so every cookie that carries such a message must be
sanitized first.
"""


def ascii_cookie(value: str) -> str:
    """Return ``value`` safe to put in a Set-Cookie header.

    Transliterates common German characters (ä→ae, ö→oe, ü→ue, ß→ss,
    en/em dash → hyphen), strips control characters (newlines, tabs — which
    the stdlib cookie module rejects with CookieError), then drops any
    remaining non-latin-1 bytes. This keeps the message readable in the
    browser while guaranteeing the cookie never raises at response time.
    """
    if value is None:
        return ""
    repl = {
        "ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae",
        "Ö": "Oe", "Ü": "Ue", "ß": "ss",
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00b7": "-",
    }
    for k, v in repl.items():
        value = value.replace(k, v)
    # Collapse any control character (newline, tab, CR, etc.) to a space —
    # http.cookies raises CookieError on these even though they are valid
    # latin-1 bytes.
    value = "".join(" " if ord(c) < 0x20 or ord(c) == 0x7f else c for c in value)
    return value.encode("latin-1", "ignore").decode("latin-1")
