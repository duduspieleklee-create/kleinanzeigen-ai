import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.dependencies import get_current_user
from app.api.version import register_globals
from app.shared.database import get_db
from app.shared.models import Favorite, ScrapeResult, ScrapeTask, User
from app.shared.plans import plan_config

# Exact confirmation phrase the user must type to delete their account —
# German to match the rest of the dashboard's localization.
_DELETE_CONFIRMATION_PHRASE = "LÖSCHEN"

router = APIRouter(prefix="", tags=["Settings"])
templates = Jinja2Templates(directory="app/api/templates")
register_globals(templates)


class NotificationSettingsPayload(BaseModel):
    # Optional: when omitted, the server must NOT touch the push flag — this
    # prevents unrelated settings saves from force-enabling push (issue #187).
    push_enabled: bool | None = None
    email_enabled: bool = False


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
            "is_admin": bool(db_user.is_admin),
            "plan_name": plan_name,
            "plan_label": cfg.get("label", "Basic") if cfg else "Basic",
            "max_active_searches": cfg.get("max_active_searches", 5) if cfg else 5,
            "min_interval_seconds": cfg.get("min_interval_seconds", 300) if cfg else 300,
            "show_deals": show_deals,
            "show_trust_scores": show_trust_scores,
            "max_credits": cfg.get("credits_per_week", 0) if cfg else 0,
            "credits": getattr(db_user, 'credits', 0),
            "user_settings": {
                "push_notifications_enabled": db_user.push_notifications_enabled,
                "email_notifications_enabled": db_user.email_notifications_enabled,
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

    # push_enabled is optional: only update the DB flag when the client
    # explicitly sends it (issue #187). This makes the settings POST a
    # single source of truth that the push toggle drives (issue #186).
    if payload.push_enabled is not None:
        db_user.push_notifications_enabled = payload.push_enabled
    db_user.email_notifications_enabled = payload.email_enabled
    db.commit()
    return {"status": "saved"}


@router.post("/settings/tutorial-complete")
def complete_tutorial(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    db_user = db.query(User).filter(User.id == current_user["id"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.has_completed_tutorial = True
    db.commit()
    return {"status": "saved"}


@router.get("/settings/export")
def export_account_data(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Download everything the app has stored about the caller, as JSON.

    Covers the account record, notification preferences, searches, results,
    and favorites — every user-owned table (GDPR Art. 20 data portability).
    """
    db_user = db.query(User).filter(User.id == current_user["id"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    tasks = db.query(ScrapeTask).filter(ScrapeTask.user_id == db_user.id).all()
    task_ids = [t.id for t in tasks]
    results = (
        db.query(ScrapeResult).filter(ScrapeResult.task_id.in_(task_ids)).all()
        if task_ids else []
    )
    favorites = db.query(Favorite).filter(Favorite.user_id == db_user.id).all()

    def _iso(dt):
        return dt.isoformat() if dt else None

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "username": db_user.username,
            "email": db_user.email,
            "plan": db_user.plan,
            "credits": db_user.credits,
            "email_verified": bool(db_user.email_verified),
            "created_at": _iso(db_user.created_at),
        },
        "notification_settings": {
            "push_notifications_enabled": db_user.push_notifications_enabled,
            "email_notifications_enabled": db_user.email_notifications_enabled,
        },
        "searches": [
            {
                "id": t.id,
                "status": t.status,
                "parameters": t.parameters,
                "created_at": _iso(t.created_at),
                "completed_at": _iso(t.completed_at),
            }
            for t in tasks
        ],
        "results": [
            {
                "id": r.id,
                "search_id": r.task_id,
                "title": r.title,
                "price": r.price,
                "location": r.location,
                "url": r.url,
                "trust_score": r.trust_score,
                "created_at": _iso(r.created_at),
            }
            for r in results
        ],
        "favorites": [
            {"result_id": f.result_id, "created_at": _iso(f.created_at)}
            for f in favorites
        ],
    }

    filename = f"kleinanzeigen-ai-export-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class DeleteAccountPayload(BaseModel):
    confirmation: str


@router.post("/settings/delete-account")
def delete_account(
    payload: DeleteAccountPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Permanently delete the caller's account and everything tied to it
    (searches, results, favorites, push subscriptions, token usage).

    Requires typing the exact German confirmation phrase, since neither
    password nor Google-OAuth re-auth works uniformly across both login
    methods this app supports.
    """
    if payload.confirmation.strip() != _DELETE_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'Type "{_DELETE_CONFIRMATION_PHRASE}" exactly to confirm deletion.',
        )

    db_user = db.query(User).filter(User.id == current_user["id"]).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # The system user owns Beat-scheduled admin searches (settings.system_user_id)
    # and must keep existing — deleting it would break the FK on future
    # AdminSearch-dispatched ScrapeTask rows.
    if db_user.id == settings.system_user_id:
        raise HTTPException(status_code=400, detail="This account cannot be deleted.")

    # ScrapeTask.user_id has no ON DELETE CASCADE at the DB level, so each
    # task is deleted explicitly via the ORM — this cascades (via the
    # relationship `cascade="all, delete-orphan"` on ScrapeTask.results and
    # ScrapeResult.favorited_by) to that task's results and their favorites.
    tasks = db.query(ScrapeTask).filter(ScrapeTask.user_id == db_user.id).all()
    for task in tasks:
        db.delete(task)
    db.flush()

    # Remaining user-owned rows (push subscriptions, any leftover favorites/
    # token usage) cascade from the User relationships / ON DELETE CASCADE FKs.
    db.delete(db_user)
    db.commit()
    return {"status": "deleted"}
