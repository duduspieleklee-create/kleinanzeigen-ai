from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.shared.database import get_db
from app.shared.models import AdminSearch, Proxy
from app.shared.proxy import (
    is_rotating_enabled,
    is_safe_proxy_url,
    mark_tested,
    set_rotating_enabled,
    test_proxy,
)
from app.worker.tasks import run_test_push

router = APIRouter()


@router.post("/test-notification")
def send_test_notification(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """Send a test push to the current admin's own devices, synchronously.

    Sending inline (not via Celery) lets us report the real outcome — sent, no
    subscription, or the actual delivery error — instead of a fire-and-forget
    that always looks successful even when every push silently fails.
    """
    response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)

    def _flash(key: str, message: str) -> RedirectResponse:
        # Cookie headers are latin-1 only; webpush errors can contain anything.
        safe = message.encode("latin-1", "replace").decode("latin-1")
        response.set_cookie(key, safe, max_age=15)
        return response

    result = run_test_push(db, current_user["id"])

    if not result["configured"]:
        return _flash(
            "flash_error",
            "Push is not configured on the server: " + "; ".join(result["errors"]),
        )
    if result["total"] == 0:
        return _flash(
            "flash_error",
            "No active push subscription on this account. Enable notifications "
            "on the dashboard first, then try the test again.",
        )
    if result["sent"] > 0:
        extra = f" ({result['removed']} expired removed)" if result["removed"] else ""
        return _flash(
            "flash_success",
            f"Test notification sent to {result['sent']} device(s){extra}. "
            "Check your device now.",
        )
    if result["removed"] > 0:
        return _flash(
            "flash_error",
            "Your saved subscription had expired and was removed. Re-enable "
            "notifications on the dashboard, then try again.",
        )
    detail = "; ".join(result["errors"][:2]) or "unknown error"
    return _flash("flash_error", f"Push failed: {detail}")


@router.post("/searches")
def create_admin_search(
    keywords: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    location_id: Optional[int] = Form(None),
    price_min: Optional[int] = Form(None),
    price_max: Optional[int] = Form(None),
    radius: Optional[int] = Form(None),
    ad_type: Optional[str] = Form(None),
    poster_type: Optional[str] = Form(None),
    condition: Optional[str] = Form(None),
    shipping: Optional[str] = Form(None),
    interval_minutes: int = Form(30),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    keywords = keywords or None
    category = category or None
    if not keywords and not category:
        response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
        response.set_cookie(
            "flash_error", "Bitte Stichwörter oder Kategorie angeben", max_age=10
        )
        return response

    # ── Input hardening (mirrors the user-facing flow) ──────────────────────
    if keywords and len(keywords) > 255:
        response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
        response.set_cookie(
            "flash_error", "Stichwörter zu lang (max. 255 Zeichen)", max_age=10
        )
        return response
    if category and len(category) > 100:
        response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
        response.set_cookie(
            "flash_error", "Kategorie zu lang (max. 100 Zeichen)", max_age=10
        )
        return response
    if radius is not None and radius > 0 and not location_id:
        response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
        response.set_cookie(
            "flash_error", "Ein Umkreis erfordert einen ausgewählten Ort", max_age=10
        )
        return response
    if interval_minutes is not None and interval_minutes <= 0:
        response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
        response.set_cookie(
            "flash_error", "Intervall muss größer als 0 sein", max_age=10
        )
        return response

    # ── Duplicate guard (admin) ─────────────────────────────────────────────
    dup = (
        db.query(AdminSearch)
        .filter(
            AdminSearch.keywords == (keywords or None),
            AdminSearch.category == (category or None),
            AdminSearch.location_id == location_id,
            AdminSearch.price_min == price_min,
            AdminSearch.price_max == price_max,
            AdminSearch.radius == radius,
            AdminSearch.ad_type == (ad_type or None),
            AdminSearch.poster_type == (poster_type or None),
            AdminSearch.condition == (condition or None),
            AdminSearch.shipping == (shipping or None),
        )
        .first()
    )
    if dup:
        response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
        response.set_cookie(
            "flash_error",
            f"Diese Hintergrundsuche existiert bereits (#{dup.id})",
            max_age=10,
        )
        return response

    search = AdminSearch(
        keywords=keywords,
        category=category,
        location=location or None,
        location_id=location_id,
        price_min=price_min,
        price_max=price_max,
        radius=radius,
        ad_type=ad_type or None,
        poster_type=poster_type or None,
        condition=condition or None,
        shipping=shipping or None,
        interval_minutes=interval_minutes,
    )
    db.add(search)
    db.commit()
    response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
    response.set_cookie(
        "flash_success", f"Admin search '{keywords or category}' created", max_age=10
    )
    return response


@router.post("/searches/{search_id}/toggle")
def toggle_admin_search(
    search_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    search = db.query(AdminSearch).filter(AdminSearch.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Not found")
    search.is_active = not search.is_active
    db.commit()
    return RedirectResponse(url="/dashboard#tab-admin", status_code=303)


@router.post("/searches/{search_id}/delete")
def delete_admin_search(
    search_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    search = db.query(AdminSearch).filter(AdminSearch.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(search)
    db.commit()
    return RedirectResponse(url="/dashboard#tab-admin", status_code=303)


# ── Rotating proxy management ─────────────────────────────────────────────────

def _proxy_redirect(flash_key: str = None, message: str = None) -> RedirectResponse:
    response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
    if flash_key and message:
        # Cookie headers are latin-1 only; proxy error details come from
        # arbitrary exceptions, so make the value safe before setting it.
        safe = message.encode("latin-1", "replace").decode("latin-1")
        response.set_cookie(flash_key, safe, max_age=10)
    return response


@router.post("/proxy/toggle")
def toggle_rotating_proxy(
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    new_state = not is_rotating_enabled(db)
    set_rotating_enabled(db, new_state)
    return _proxy_redirect(
        "flash_success",
        f"Rotating proxy {'enabled' if new_state else 'disabled'}",
    )


@router.post("/proxies")
def add_proxy(
    url: str = Form(...),
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    url = (url or "").strip()
    if not url:
        return _proxy_redirect("flash_error", "Proxy URL is required")
    if db.query(Proxy).filter(Proxy.url == url).first():
        return _proxy_redirect("flash_error", "That proxy is already in the list")

    # SSRF guard — refuse proxies pointing at internal/reserved addresses.
    safe, reason = is_safe_proxy_url(url)
    if not safe:
        return _proxy_redirect("flash_error", f"Proxy URL rejected: {reason}")

    # Live test — only add the proxy if it can actually reach the target.
    ok, detail = test_proxy(url)
    if not ok:
        return _proxy_redirect("flash_error", f"Proxy failed the live test - not added ({detail})")

    proxy = Proxy(
        url=url,
        is_active=True,
        last_status="ok",
        last_tested_at=datetime.now(timezone.utc),
    )
    db.add(proxy)
    db.commit()
    return _proxy_redirect("flash_success", "Proxy passed the live test and was added")


@router.post("/proxies/{proxy_id}/retest")
def retest_proxy(
    proxy_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status_code=404, detail="Not found")

    # SSRF guard — a stored URL could have been added before this check existed.
    safe, reason = is_safe_proxy_url(proxy.url)
    if not safe:
        mark_tested(db, proxy, False)
        return _proxy_redirect("flash_error", f"Proxy URL rejected: {reason}")

    ok, detail = test_proxy(proxy.url)
    mark_tested(db, proxy, ok)
    key = "flash_success" if ok else "flash_error"
    return _proxy_redirect(key, f"Proxy re-test {'passed' if ok else 'failed'} ({detail})")


@router.post("/proxies/{proxy_id}/delete")
def delete_proxy(
    proxy_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_admin),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(proxy)
    db.commit()
    return _proxy_redirect("flash_success", "Proxy removed")
