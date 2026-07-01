"""Rotating proxy support for the scraper.

Central helpers used by:
- the admin API, to live-test a proxy before adding it and to toggle the
  system-wide rotating-proxy feature, and
- the Celery worker, to pick an active proxy per scrape run.
"""
import random
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from app.api.config import settings
from app.shared.models import Proxy, SystemSetting

ROTATING_KEY = "rotating_proxy_enabled"


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
