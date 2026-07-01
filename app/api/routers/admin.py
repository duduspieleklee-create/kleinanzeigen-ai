from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.models import AdminSearch

router = APIRouter()


def _require_admin(request: Request) -> dict:
    try:
        current_user = get_current_user(request, token=request.cookies.get("access_token") or "")
    except HTTPException:
        raise HTTPException(status_code=403, detail="Forbidden")

    if settings.allowed_emails:
        allowed = {e.strip().lower() for e in settings.allowed_emails.split(",") if e.strip()}
        if current_user.get("email", "").lower() not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
    return current_user


@router.post("/searches")
def create_admin_search(
    request: Request,
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
    _require_admin(request)
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
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    search = db.query(AdminSearch).filter(AdminSearch.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Not found")
    search.is_active = not search.is_active
    db.commit()
    return RedirectResponse(url="/dashboard#tab-admin", status_code=303)


@router.post("/searches/{search_id}/delete")
def delete_admin_search(
    search_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_admin(request)
    search = db.query(AdminSearch).filter(AdminSearch.id == search_id).first()
    if not search:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(search)
    db.commit()
    return RedirectResponse(url="/dashboard#tab-admin", status_code=303)
