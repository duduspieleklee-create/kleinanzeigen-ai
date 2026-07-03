from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.models import User
from app.shared.plans import plan_config

router = APIRouter(prefix="", tags=["Settings"])
templates = Jinja2Templates(directory="app/api/templates")


@router.get("/settings")
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
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
                "push_notifications_enabled": getattr(db_user, 'push_notifications_enabled', True),
                "email_notifications_enabled": getattr(db_user, 'email_notifications_enabled', False),
                "deals_only_enabled": getattr(db_user, 'deals_only_enabled', False),
                "quiet_start": getattr(db_user, 'quiet_start', "22:00"),
                "quiet_end": getattr(db_user, 'quiet_end', "08:00"),
            },
        },
    )
