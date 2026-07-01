"""Rotating proxy support for the scraper.

Central helpers used by:
- the admin API, to live-test a proxy before adding it and to toggle the
  system-wide rotating-proxy feature, and
- the Celery worker, to pick an active proxy per scrape run.
"""
import ipaddress
import random
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from app.api.config import settings
from app.shared.models import Proxy, SystemSetting

ROTATING_KEY = "rotating_proxy_enabled"


def is_safe_proxy_url(url: str) -> tuple[bool, str]:
    """Reject proxy URLs that resolve to private/loopback/reserved addresses.

    The server makes outbound requests *through* admin-supplied proxy URLs, so
    an unvalidated URL turns the server into an SSRF pivot to internal hosts
    (e.g. cloud metadata endpoints). Returns (ok, reason).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "malformed URL"
    if parsed.scheme not in ("http", "https"):
        return False, "scheme must be http or https"
    host = parsed.hostname
    if not host:
        return False, "missing host"
    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, "host does not resolve"
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False, f"resolves to a non-public address ({ip})"
    return True, "ok"


def is_rotating_enabled(db: Session) -> bool:
    row = db.query(SystemSetting).filter(SystemSetting.key == ROTATING_KEY).first()
    return bool(row and row.value == "true")


def set_rotating_enabled(db: Session, enabled: bool) -> None:
    row = db.query(SystemSetting).filter(SystemSetting.key == ROTATING_KEY).first()
    if row is None:
        db.add(SystemSetting(key=ROTATING_KEY, value="true" if enabled else "false"))
    else:
        row.value = "true" if enabled else "false"
    db.commit()


def test_proxy(url: str) -> tuple[bool, str]:
    """Fetch the configured test URL through ``url``. Returns (ok, detail)."""
    proxies = {"http": url, "https": url}
    try:
        resp = requests.get(
            settings.proxy_test_url,
            proxies=proxies,
            timeout=settings.proxy_test_timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except Exception as e:  # connection errors, timeouts, bad proxy, etc.
        return False, str(e)[:200] or "connection failed"
    if resp.status_code == 200:
        return True, f"HTTP 200 from {settings.proxy_test_url}"
    return False, f"HTTP {resp.status_code}"


def mark_tested(db: Session, proxy: Proxy, ok: bool) -> None:
    proxy.last_status = "ok" if ok else "failed"
    proxy.is_active = ok
    proxy.last_tested_at = datetime.now(timezone.utc)
    db.commit()


def proxies_for_requests(db: Session):
    """A requests-style proxies dict when rotating is on and a proxy is active.

    Returns None otherwise, so callers can pass it straight to requests.get().
    """
    if not is_rotating_enabled(db):
        return None
    active = db.query(Proxy).filter(Proxy.is_active.is_(True)).all()
    if not active:
        return None
    url = random.choice(active).url
    return {"http": url, "https": url}
