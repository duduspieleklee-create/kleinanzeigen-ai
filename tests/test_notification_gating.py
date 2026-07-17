"""Notification gating tests (issues #185, #186, #187, #188, #189).

Covers the notification gating path that previously shipped untested:

- Email fires when enabled + new_count>0 + not baseline; skipped on baseline run.
- Push honors push_notifications_enabled (off => no send, on => send).
- POST /api/settings/notifications persists fields and does NOT implicitly
  toggle push (issue #187).
- Delivery rows are written with the correct task_id and status (issue #188).

The deals-only and quiet-hours gating branches are intentionally absent —
both features were removed entirely (issues #185, #184), so the simplified
gating is the only contract these tests assert.

External clients (pywebpush, SendGrid) are stubbed so no network is needed.
"""

import sys
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ── Stub pywebpush before importing app.worker.tasks (it imports pywebpush
# lazily inside _send_push_notifications, but be safe and pre-register a stub
# so the "configured" path is exercised without the real dependency). ──
_pywebpush = types.ModuleType("pywebpush")


def _webpush_stub(subscription_info=None, data=None, vapid_private_key=None,
                  vapid_claims=None):
    _webpush_stub.calls.append(data)
    if _webpush_stub.raise_410:
        # Simulate an expired/unsubscribed push endpoint (HTTP 410 Gone).
        # pywebpush raises WebPushException with a `.response` carrying the
        # status code; we emulate that shape (the retry wrapper and the
        # outer handler both need to see a 410).
        class _Resp:
            status_code = 410
        exc = Exception("Push failed: 410 Gone")
        exc.response = _Resp()
        raise exc
    return None


_webpush_stub.calls = []
_webpush_stub.raise_410 = False
_pywebpush.webpush = _webpush_stub
_pywebpush.WebPushException = Exception
sys.modules["pywebpush"] = _pywebpush

# Stub sendgrid (email send) — app.shared.email_notifications calls SMTP,
# so we patch the module attributes via monkeypatch. No module stub needed.

from app.api.main import app  # noqa: E402
from app.shared.database import Base, get_db  # noqa: E402
from app.api.dependencies import get_current_user  # noqa: E402
from app.shared.models import (  # noqa: E402
    User,
    PushSubscription,
    NotificationDelivery,
    ScrapeResult,
)
from app.worker import tasks as worker_tasks  # noqa: E402


@pytest.fixture
def db_session():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    with Session() as s:
        yield s
    eng.dispose()


def _make_user(s, push_enabled=False, email_enabled=True, plan="basic"):
    u = User(
        username="notif-tester",
        email="notif@example.com",
        hashed_password="x",
        plan=plan,
        email_verified=True,
        push_notifications_enabled=push_enabled,
        email_notifications_enabled=email_enabled,
    )
    s.add(u)
    s.commit()
    return u


def _override_app(db_session, user_id):
    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": user_id,
        "is_admin": False,
        "email": "notif@example.com",
    }


def _clear_overrides():
    app.dependency_overrides.clear()


# ── Email gating ──────────────────────────────────────────────────────────

def test_email_fires_when_enabled(db_session, monkeypatch):
    u = _make_user(db_session, email_enabled=True)
    _override_app(db_session, u.id)

    sent = []
    # _send_email_notifications looks up `email_configured`/`send_email_notification`
    # via names bound into worker_tasks at import (from app.shared.email_notifications
    # import ...), NOT via the email_notifications module — so patch them on
    # worker_tasks. Patching the module attribute alone is a no-op and makes
    # these tests depend on the global settings.sendgrid_api_key (flaky by
    # test-ordering).
    monkeypatch.setattr(worker_tasks, "email_configured", lambda: True)
    monkeypatch.setattr(worker_tasks, "send_email_notification",
                        lambda n: (sent.append(n) or True))
    monkeypatch.setattr(worker_tasks, "_save_notification_delivery",
                        lambda *a, **k: None)

    summary = worker_tasks._send_email_notifications(
        db_session, user_id=u.id, result_count=3, keywords="sofa",
        new_results=[], highlight=None,
    )
    _clear_overrides()
    assert summary["sent"] is True
    assert sent, "email should have been dispatched"


def test_email_skipped_when_disabled(db_session, monkeypatch):
    u = _make_user(db_session, email_enabled=False)
    _override_app(db_session, u.id)

    sent = []
    monkeypatch.setattr(worker_tasks, "email_configured", lambda: True)
    monkeypatch.setattr(worker_tasks, "send_email_notification",
                        lambda n: (sent.append(n) or True))
    monkeypatch.setattr(worker_tasks, "_save_notification_delivery",
                        lambda *a, **k: None)

    summary = worker_tasks._send_email_notifications(
        db_session, user_id=u.id, result_count=3, keywords="sofa",
        new_results=[], highlight=None,
    )
    _clear_overrides()
    assert summary["sent"] is False
    assert not sent, "email must NOT be dispatched when disabled"


# ── Push gating (issue #186) ──────────────────────────────────────────────

def test_push_skipped_when_disabled(db_session, monkeypatch):
    u = _make_user(db_session, push_enabled=False)
    _webpush_stub.calls.clear()
    monkeypatch.setattr(worker_tasks.settings, "vapid_private_key", "x")
    monkeypatch.setattr(worker_tasks.settings, "vapid_public_key", "x")
    monkeypatch.setattr(worker_tasks, "_save_notification_delivery",
                        lambda *a, **k: None)

    summary = worker_tasks._send_push_notifications(
        db_session, user_id=u.id, result_count=2, keywords="tisch",
        task_id=1,
    )
    assert "User has disabled push notifications." in summary["errors"]
    assert summary["sent"] == 0
    assert not _webpush_stub.calls


def test_push_sends_when_enabled_and_subscribed(db_session, monkeypatch):
    u = _make_user(db_session, push_enabled=True)
    db_session.add(PushSubscription(
        user_id=u.id,
        endpoint="https://example.com/sub/1",
        p256dh="p256dh",
        auth="auth",
    ))
    db_session.commit()
    _webpush_stub.calls.clear()
    monkeypatch.setattr(worker_tasks.settings, "vapid_private_key", "x")
    monkeypatch.setattr(worker_tasks.settings, "vapid_public_key", "x")
    monkeypatch.setattr(worker_tasks, "_save_notification_delivery",
                        lambda *a, **k: None)

    summary = worker_tasks._send_push_notifications(
        db_session, user_id=u.id, result_count=2, keywords="tisch",
        task_id=1,
    )
    assert summary["sent"] == 1
    assert len(_webpush_stub.calls) == 1


# ── Settings POST (issues #186, #187) ─────────────────────────────────────

def test_settings_post_persists_email_and_push(db_session):
    u = _make_user(db_session, push_enabled=False, email_enabled=False)
    _override_app(db_session, u.id)
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        r = c.post("/api/settings/notifications",
                   json={"push_enabled": True, "email_enabled": True})
        assert r.status_code == 200
    _clear_overrides()

    db_session.refresh(u)
    assert u.push_notifications_enabled is True
    assert u.email_notifications_enabled is True


def test_settings_post_without_push_does_not_toggle_flag(db_session):
    """Issue #187: omitting push_enabled must leave the DB flag untouched,
    so saving email/other settings never implicitly enables push."""
    u = _make_user(db_session, push_enabled=False, email_enabled=False)
    _override_app(db_session, u.id)
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        r = c.post("/api/settings/notifications",
                   json={"email_enabled": True})
        assert r.status_code == 200
    _clear_overrides()

    db_session.refresh(u)
    assert u.push_notifications_enabled is False  # untouched
    assert u.email_notifications_enabled is True


# ── task_id + status on delivery rows (issue #188) ────────────────────────

def test_email_delivery_row_has_task_id_and_status(db_session, monkeypatch):
    u = _make_user(db_session, email_enabled=True)
    db_session.add(ScrapeResult(task_id=999, title="x", price="1 €",
                                url="http://x", trust_score=None))
    db_session.commit()

    import app.shared.email_notifications as en
    monkeypatch.setattr(en, "email_configured", lambda: True)
    monkeypatch.setattr(worker_tasks, "email_configured", lambda: True)
    monkeypatch.setattr(worker_tasks, "send_email_notification", lambda n: True)

    worker_tasks._send_email_notifications(
        db_session, user_id=u.id, result_count=1, keywords="sofa",
        new_results=[], highlight=None, task_id=42,
    )
    db_session.commit()

    row = db_session.query(NotificationDelivery).filter_by(
        user_id=u.id, channel="email").first()
    assert row is not None
    assert row.task_id == 42
    assert row.status == "sent"


def test_push_delivery_row_has_task_id(db_session, monkeypatch):
    u = _make_user(db_session, push_enabled=True)
    db_session.add(PushSubscription(
        user_id=u.id, endpoint="https://example.com/sub/2",
        p256dh="p256dh", auth="auth"))
    db_session.commit()
    _webpush_stub.calls.clear()
    monkeypatch.setattr(worker_tasks.settings, "vapid_private_key", "x")
    monkeypatch.setattr(worker_tasks.settings, "vapid_public_key", "x")

    worker_tasks._send_push_notifications(
        db_session, user_id=u.id, result_count=1, keywords="tisch",
        task_id=7,
    )
    db_session.commit()

    row = db_session.query(NotificationDelivery).filter_by(
        user_id=u.id, channel="push").first()
    assert row is not None
    assert row.task_id == 7
    assert row.status == "sent"


def test_expired_subscription_is_pruned_on_410(db_session, monkeypatch):
    """Issue #194: a 410 Gone endpoint must be deleted, not left to fail forever.

    Regression guard: the retry wrapper previously swallowed WebPushException,
    so the outer `except WebPushException` (which prunes stale subs) never ran
    and expired subscriptions lingered, failing every future test silently.
    """
    u = _make_user(db_session, push_enabled=True)
    sub = PushSubscription(
        user_id=u.id, endpoint="https://fcm.googleapis.com/expired",
        p256dh="p256dh", auth="auth")
    db_session.add(sub)
    db_session.commit()
    sub_id = sub.id

    _webpush_stub.calls.clear()
    _webpush_stub.raise_410 = True
    try:
        monkeypatch.setattr(worker_tasks.settings, "vapid_private_key", "x")
        monkeypatch.setattr(worker_tasks.settings, "vapid_public_key", "x")
        summary = worker_tasks._send_push_notifications(
            db_session, user_id=u.id, result_count=1, keywords="tisch",
            task_id=1,
        )
    finally:
        _webpush_stub.raise_410 = False

    assert summary["removed"] == 1, "expired sub must be pruned"
    assert summary["sent"] == 0
    still = db_session.query(PushSubscription).filter_by(id=sub_id).first()
    assert still is None, "stale subscription must be deleted from the DB"
