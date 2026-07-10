import logging
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.dependencies import get_current_user
from app.shared.database import get_db
from app.shared.models import PushSubscription

logger = logging.getLogger(__name__)

router = APIRouter()


def _label_for_endpoint(endpoint: str) -> str:
    """Best-effort human label from the push service's host.

    Browsers don't expose a device name to the server, but the push
    service host (fcm.googleapis.com, Mozilla's autopush, etc.) is enough
    to tell a user's subscriptions apart in a management list.
    """
    host = urlparse(endpoint).netloc
    if "googleapis.com" in host:
        return "Chrome / Android"
    if "mozilla.com" in host:
        return "Firefox"
    if "apple.com" in host:
        return "Safari / iOS"
    if "notify.windows.com" in host:
        return "Edge / Windows"
    return host or "Unbekanntes Gerät"


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


@router.get("/subscriptions")
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List the caller's push subscriptions, for the settings page's device
    management list — distinct from the browser-derived on/off toggle, which
    only reflects the current device's own subscription state.
    """
    subs = (
        db.query(PushSubscription)
        .filter(PushSubscription.user_id == current_user["id"])
        .order_by(PushSubscription.created_at.desc())
        .all()
    )
    return {
        "subscriptions": [
            {
                "id": s.id,
                "endpoint": s.endpoint,
                "label": _label_for_endpoint(s.endpoint),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in subs
        ]
    }


@router.post("/subscriptions/{subscription_id}/revoke")
def revoke_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Revoke a single subscription by id — e.g. a lost or old device the
    user can no longer unsubscribe from locally via the browser."""
    sub = db.query(PushSubscription).filter(
        PushSubscription.id == subscription_id,
        PushSubscription.user_id == current_user["id"],
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(sub)
    db.commit()
    return {"status": "revoked"}


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
        task_id=None,
        bypass_preferences=True,
        tag=f"test-{int(time.time() * 1000)}",
        title="TEST - kleeblatt.space",
    )
    return {
        "status": "success" if summary["sent"] > 0 else "no_subscriptions",
        "summary": summary,
    }
