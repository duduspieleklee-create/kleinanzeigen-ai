from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.models import AdminSearch, Proxy
from app.shared.proxy import (
    is_rotating_enabled,
    mark_tested,
    set_rotating_enabled,
    test_proxy,
)

router = APIRouter()


@router.post("/searches")
def create_admin_search(
    keywords: str = Form(...),
    category: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    location_id: Optional[int] = Form(None),
    price_min: Optional[int] = Form(None),
    price_max: Optional[int] = Form(None),
    radius: Optional[int] = Form(None),
    interval_minutes: int = Form(30),
    db: Session = Depends(get_db),
):
    search = AdminSearch(
        keywords=keywords,
        category=category or None,
        location=location or None,
        location_id=location_id,
        price_min=price_min,
        price_max=price_max,
        radius=radius,
        interval_minutes=interval_minutes,
    )
    db.add(search)
    db.commit()
    response = RedirectResponse(url="/dashboard#tab-admin", status_code=303)
    response.set_cookie("flash_success", f"Admin search '{keywords}' created", max_age=10)
    return response


@router.post("/searches/{search_id}/toggle")
def toggle_admin_search(
    search_id: int,
    db: Session = Depends(get_db),
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
    _: dict = Depends(get_current_user),
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
    _: dict = Depends(get_current_user),
):
    url = (url or "").strip()
    if not url:
        return _proxy_redirect("flash_error", "Proxy URL is required")
    if db.query(Proxy).filter(Proxy.url == url).first():
        return _proxy_redirect("flash_error", "That proxy is already in the list")

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
    _: dict = Depends(get_current_user),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status_code=404, detail="Not found")
    ok, detail = test_proxy(proxy.url)
    mark_tested(db, proxy, ok)
    key = "flash_success" if ok else "flash_error"
    return _proxy_redirect(key, f"Proxy re-test {'passed' if ok else 'failed'} ({detail})")


@router.post("/proxies/{proxy_id}/delete")
def delete_proxy(
    proxy_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(proxy)
    db.commit()
    return _proxy_redirect("flash_success", "Proxy removed")
