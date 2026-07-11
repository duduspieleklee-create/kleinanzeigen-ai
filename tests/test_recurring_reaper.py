"""Tests for the recurring-search reaper (scrape.reap_stale_recurring_searches).

User recurring searches self-reschedule via an in-broker ETA task that a
worker restart drops, silently killing the chain. The reaper re-primes any
overdue recurring search. These tests assert:

- an overdue recurring search is re-enqueued (chain revived);
- a healthy (recently-run) recurring search is left alone;
- a one-shot search (no interval_seconds) is never touched;
- running/pending/cancelled tasks are ignored;
- re-priming bumps last_run_at so a second immediate pass is idempotent.
- orphaned running tasks with last_run_at=NULL are revived.

The Celery enqueue (scrape_kleinanzeigen.apply_async) is stubbed so no broker
is needed; we record its calls to assert which task_ids were revived.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.shared.database import Base
from app.shared.models import User, ScrapeTask
from app.worker import tasks as worker_tasks


@pytest.fixture
def db_and_stub(monkeypatch):
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)

    # The reaper opens its own session via SessionLocal(); point it at ours.
    monkeypatch.setattr(worker_tasks, "SessionLocal", Session)

    # Stub the Celery enqueue and record revived task_ids.
    calls = []
    monkeypatch.setattr(
        worker_tasks.scrape_kleinanzeigen,
        "apply_async",
        lambda *a, **k: calls.append(a[0] if a else k.get("args")),
    )

    with Session() as s:
        u = User(username="reaper", email="r@example.com", hashed_password="x",
                 plan="basic", email_verified=True)
        s.add(u)
        s.commit()
        uid = u.id

    yield Session, uid, calls
    eng.dispose()


def _mk(s, uid, *, status, interval, ago_seconds, last_run_at=None):
    """Create a ScrapeTask whose last_run_at is `ago_seconds` in the past."""
    params = {"keywords": "sofa"}
    if interval is not None:
        params["interval_seconds"] = interval
    t = ScrapeTask(
        user_id=uid, url="http://x", status=status, parameters=params,
        last_run_at=last_run_at or (datetime.now(timezone.utc) - timedelta(seconds=ago_seconds)),
        created_at=datetime.now(timezone.utc) - timedelta(seconds=ago_seconds),
    )
    s.add(t)
    s.commit()
    return t.id


def _revived_ids(calls):
    # apply_async(args=[params, task_id]) — task_id is the 2nd element.
    return {args[1] for args in calls if len(args) > 1}


def test_overdue_recurring_search_is_revived(db_and_stub):
    Session, uid, calls = db_and_stub
    with Session() as s:
        # interval 300s, last run 3000s ago -> well past interval + grace.
        tid = _mk(s, uid, status="completed", interval=300, ago_seconds=3000)

    worker_tasks.reap_stale_recurring_searches()

    assert tid in _revived_ids(calls)
    with Session() as s:
        # last_run_at was bumped, so an immediate second pass is a no-op.
        t = s.get(ScrapeTask, tid)
        assert (datetime.now(timezone.utc) - t.last_run_at.replace(
            tzinfo=timezone.utc)).total_seconds() < 60
    calls.clear()
    worker_tasks.reap_stale_recurring_searches()
    assert tid not in _revived_ids(calls)


def test_healthy_recurring_search_is_left_alone(db_and_stub):
    Session, uid, calls = db_and_stub
    with Session() as s:
        # ran 60s ago on a 300s interval -> inside interval + grace.
        tid = _mk(s, uid, status="completed", interval=300, ago_seconds=60)
    worker_tasks.reap_stale_recurring_searches()
    assert tid not in _revived_ids(calls)


def test_oneshot_search_never_revived(db_and_stub):
    Session, uid, calls = db_and_stub
    with Session() as s:
        tid = _mk(s, uid, status="completed", interval=None, ago_seconds=99999)
    worker_tasks.reap_stale_recurring_searches()
    assert tid not in _revived_ids(calls)


@pytest.mark.parametrize("status", ["running", "pending", "cancelled"])
def test_non_settled_status_ignored(db_and_stub, status):
    Session, uid, calls = db_and_stub
    with Session() as s:
        tid = _mk(s, uid, status=status, interval=300, ago_seconds=3000)
    worker_tasks.reap_stale_recurring_searches()
    assert tid not in _revived_ids(calls)


def test_orphaned_running_with_null_last_run_at_is_revived(db_and_stub):
    """Test that a running task with last_run_at=NULL is revived."""
    Session, uid, calls = db_and_stub
    with Session() as s:
        # Create a running task with last_run_at=NULL
        t = ScrapeTask(
            user_id=uid, url="http://x", status="running", parameters={"keywords": "sofa", "interval_seconds": 300},
            last_run_at=None,
        )
        s.add(t)
        s.commit()
        tid = t.id

    worker_tasks.reap_stale_recurring_searches()

    assert tid in _revived_ids(calls)
    with Session() as s:
        # last_run_at was bumped
        t = s.get(ScrapeTask, tid)
        assert t.last_run_at is not None


def test_orphaned_pending_with_null_last_run_at_is_revived(db_and_stub):
    """Test that a pending task with last_run_at=NULL and old created_at is revived."""
    Session, uid, calls = db_and_stub
    with Session() as s:
        # Create a pending task with last_run_at=NULL and old created_at
        t = ScrapeTask(
            user_id=uid, url="http://x", status="pending", parameters={"keywords": "sofa"},
            last_run_at=None,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=120),  # 120s old
        )
        s.add(t)
        s.commit()
        tid = t.id

    worker_tasks.reap_stale_recurring_searches()

    assert tid in _revived_ids(calls)
    with Session() as s:
        # last_run_at was bumped
        t = s.get(ScrapeTask, tid)
        assert t.last_run_at is not None
