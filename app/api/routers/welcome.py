"""Welcome-task endpoints — the client reports task completions that can't be
detected server-side (PWA install, leaving a review)."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.entitlements import (
    REQUIRED_TASK_KEYS,
    completed_task_keys,
    is_premium,
    mark_task,
    premium_days_left,
)
from app.shared.models import User

router = APIRouter()


@router.post("/pwa-installed")
def pwa_installed(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Sent by the dashboard when it detects it's running as an installed PWA.
    mark_task(db, current_user["id"], "install_pwa")
    return JSONResponse({"status": "ok"})


@router.post("/review-done")
def review_done(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Honor-system: user confirms after clicking through to the review page.
    mark_task(db, current_user["id"], "leave_review")
    return JSONResponse({"status": "ok"})


@router.get("/status")
def status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    done = completed_task_keys(db, current_user["id"])
    user = db.query(User).filter(User.id == current_user["id"]).first()
    return JSONResponse({
        "required": REQUIRED_TASK_KEYS,
        "completed": sorted(done),
        "all_done": all(k in done for k in REQUIRED_TASK_KEYS),
        "is_premium": is_premium(user),
        "premium_days_left": premium_days_left(user),
    })
