import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.version import register_globals
from app.shared.database import get_db
from app.shared.models import User
from app.shared.plans import plan_config

router = APIRouter(prefix="", tags=["Settings"])
templates = Jinja2Templates(directory="app/api/templates")
register_globals(templates)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class NotificationSettingsPayload(BaseModel):
    push_enabled: bool = True
    deals_only: bool = False
    email_enabled: bool = False
    quiet_start: str | None = None
    quiet_end: str | None = None


@router.get("/settings")
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        current_user = get_current_user(
            request, token=request.cookies.get("access_token") or "", db=db
        )
    except Exception:
        return RedirectResponse(url="/")

    db_user = db.query(User).filter(User.id == current_user["id"]).first()
    if not db_user:
        return RedirectResponse(url="/")

    plan_name = db_user.plan or "basic"
    cfg = plan_config(plan_name)
    show_deals = bool(cfg and cfg.get("deal_badges"))
    show_trust_scores = bool(cfg and cfg.get("trust_scores", False))

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user_email": db_user.email,
            "email_verified": bool(db_user.email_verified),
            "plan_name": plan_name,
            "plan_label": cfg.get("label", "Basic") if cfg else "Basic",
            "max_active_searches": cfg.get("max_active_searches", 5) if cfg else 5,
            "min_interval_seconds": cfg.get("min_interval_seconds", 300) if cfg else 300,
            "show_deals": show_deals,
            "show_trust_scores": show_trust_scores,
            "max_credits": cfg.get("weekly_credits", 0) if cfg else 0,
            "credits": getattr(db_user, 'credits', 0),
            "user_settings": {
                "push_notifications_enabled": db_user.push_notifications_enabled,
                "email_notifications_enabled": db_user.email_notifications_enabled,
                "deals_only_enabled": db_user.deals_only_enabled,
                "quiet_start": db_user.quiet_start,
                "quiet_end": db_user.quiet_end,
            },
        },
    )


@router.post("/api/settings/notifications")
def update_notification_settings(
    payload: NotificationSettingsPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    db_user = db.query(User).filter(User.id == current_user["id"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    for value in (payload.quiet_start, payload.quiet_end):
        if value and not _TIME_RE.match(value):
            raise HTTPException(status_code=422, detail="quiet_start/quiet_end must be HH:MM")

    db_user.push_notifications_enabled = payload.push_enabled
    db_user.deals_only_enabled = payload.deals_only
    db_user.email_notifications_enabled = payload.email_enabled
    db_user.quiet_start = payload.quiet_start or None
    db_user.quiet_end = payload.quiet_end or None
    db.commit()
    return {"status": "saved"}
