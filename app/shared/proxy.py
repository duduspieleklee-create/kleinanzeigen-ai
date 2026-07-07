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
from app.shared.logging_config import logger

ROTATING_KEY = "rotating_proxy_enabled"


def _is_public_url(url: str) -> tuple[bool, str]:
    """Return (ok, reason) for whether ``url`` resolves to a public address.

    Shared by is_safe_proxy_url (the proxy side) and the proxy_test_url guard
    (the test-target side). Both ends of a proxied request need to land on
    public addresses; checking only one side still allows a private host to
    be reached through a public proxy. (Issue #90.)
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


def is_safe_proxy_url(url: str) -> tuple[bool, str]:
    """Reject proxy URLs that resolve to private/loopback/reserved addresses.

    The server makes outbound requests *through* admin-supplied proxy URLs, so
    an unvalidated URL turns the server into an SSRF pivot to internal hosts
    (e.g. cloud metadata endpoints). Returns (ok, reason).
    """
    return _is_public_url(url)


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
    # The test target itself must resolve to a public address — otherwise a
    # misconfigured `proxy_test_url` (e.g. pointing at an internal endpoint)
    # could be reached through an admin-supplied proxy even when the proxy
    # passes is_safe_proxy_url. (Issue #90.)
    target_safe, target_reason = _is_public_url(settings.proxy_test_url)
    if not target_safe:
        detail = f"proxy_test_url is not a public address ({target_reason})"
        logger.warning("Refusing proxy test for %s: %s", url, detail)
        return False, detail
    try:
        resp = requests.get(
            settings.proxy_test_url,
            proxies=proxies,
            timeout=settings.proxy_test_timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except Exception as e:  # connection errors, timeouts, bad proxy, etc.
        detail = str(e)[:200] or "connection failed"
        logger.info("Proxy test failed for %s: %s", url, detail)
        return False, detail
    if resp.status_code == 200:
        logger.info("Proxy test ok for %s", url)
        return True, f"HTTP 200 from {settings.proxy_test_url}"
    detail = f"HTTP {resp.status_code}"
    logger.info("Proxy test failed for %s: %s", url, detail)
    return False, detail


def mark_tested(db: Session, proxy: Proxy, ok: bool) -> None:
    proxy.last_status = "ok" if ok else "failed"
    proxy.is_active = ok
    proxy.last_tested_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Marked proxy %s tested", proxy.url)


def proxies_for_requests(db: Session):
    """A requests-style proxies dict when rotating is on and a proxy is active.

    Returns None otherwise, so callers can pass it straight to requests.get().
    Each successful pick of a proxy is audit-logged so the worker *use* path
    is observable, not just the admin *test* path. (Issue #90.)
    """
    if not is_rotating_enabled(db):
        return None
    active = db.query(Proxy).filter(Proxy.is_active.is_(True)).all()
    if not active:
        return None
    chosen = random.choice(active)
    logger.info(
        "Using rotating proxy for outbound request: proxy_id=%s url=%s last_tested_at=%s",
        chosen.id, chosen.url, chosen.last_tested_at,
    )
    return {"http": chosen.url, "https": chosen.url}
