import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.models import PushSubscription

logger = logging.getLogger(__name__)

router = APIRouter()


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionPayload(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    if not settings.vapid_public_key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"publicKey": settings.vapid_public_key}


@router.post("/subscribe", status_code=201)
def subscribe(
    payload: SubscriptionPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint
    ).first()
    if existing:
        # Update keys in case they rotated
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
        db.commit()
        return {"status": "updated"}

    sub = PushSubscription(
        user_id=current_user["id"],
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    db.add(sub)
    db.commit()
    return {"status": "subscribed"}


@router.post("/unsubscribe")
def unsubscribe(
    payload: SubscriptionPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint,
        PushSubscription.user_id == current_user["id"],
    ).delete()
    db.commit()
    return {"status": "unsubscribed"}


@router.post("/test")
def send_test_push(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.worker.tasks import _send_push_notifications

    summary = _send_push_notifications(
        db,
        user_id=current_user["id"],
        result_count=1,
        keywords="Test Search",
        highlight="✓ Test notification working!",
        location="Everywhere",
        task_id=0,
    )
    return {
        "status": "success" if summary["sent"] > 0 else "no_subscriptions",
        "summary": summary,
    }
