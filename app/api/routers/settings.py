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
async def settings_page(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        current_user = get_current_user(
            request, token=request.cookies.get("access_token") or "", db=db
        )
    except HTTPException:
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
            "plan_label": cfg["label"] if cfg else "Basic",
            "max_active_searches": cfg["max_active_searches"] if cfg else 5,
            "min_interval_seconds": cfg["min_interval_seconds"] if cfg else 300,
            "show_deals": show_deals,
            "show_trust_scores": show_trust_scores,
            "max_credits": cfg["weekly_credits"] if cfg else 0,
            "credits": db_user.credits if hasattr(db_user, 'credits') else 0,
            "user_settings": {
                "push_notifications_enabled": True,  # Default to True
                "email_notifications_enabled": False,
            },
        },
    )
