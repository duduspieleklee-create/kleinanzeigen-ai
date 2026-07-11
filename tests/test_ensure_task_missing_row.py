"""Regression tests for the missing-ScrapeTask-row FK bug (Sentry #X / #Z).

Root cause: `_ensure_task` used to hand the stale `task_id` straight back even
when the `ScrapeTask` row no longer existed (user deleted the search between a
reaper claim and the worker run). The worker then bulk-inserted `ScrapeResult`
rows against a missing parent and the DB threw
`ForeignKeyViolation on scrape_results_task_id_fkey` (#X). Mid-run the stale ORM
object could also raise `ObjectDeletedError` (#Z).

These tests pin the two guards:
- `_ensure_task` returns (None, None) for a task_id whose row is gone, so the
  caller bails before any insert.
- `reap_stale_recurring_searches` does NOT re-enqueue a task whose row is gone
  (otherwise it would re-prime forever, every 120s producing a fresh #X).
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
    monkeypatch.setattr(worker_tasks, "SessionLocal", Session)

    calls = []
    monkeypatch.setattr(
        worker_tasks.scrape_kleinanzeigen,
        "apply_async",
        lambda *a, **k: calls.append(a[0] if a else k.get("args")),
    )

    with Session() as s:
        u = User(username="ensure", email="e@example.com", hashed_password="x",
                 plan="basic", email_verified=True)
        s.add(u)
        s.commit()
        uid = u.id

    yield Session, uid, calls
    eng.dispose()


def test_ensure_task_returns_none_for_missing_row(db_and_stub):
    Session, uid, _ = db_and_stub
    with Session() as s:
        # A task id that was never created (or was deleted).
        tid, task = worker_tasks._ensure_task(s, 999999, {"keywords": "sofa"})
    assert tid is None
    assert task is None


def test_ensure_task_returns_row_when_present(db_and_stub):
    Session, uid, _ = db_and_stub
    with Session() as s:
        t = ScrapeTask(user_id=uid, url="http://x", status="completed",
                       parameters={"keywords": "sofa"})
        s.add(t)
        s.commit()
        real_id = t.id
    with Session() as s:
        tid, task = worker_tasks._ensure_task(s, real_id, {})
    assert tid == real_id
    assert task is not None


def test_reaper_skips_deleted_task(db_and_stub):
    Session, uid, calls = db_and_stub
    with Session() as s:
        # Overdue recurring search...
        t = ScrapeTask(
            user_id=uid, url="http://x", status="completed",
            parameters={"keywords": "sofa", "interval_seconds": 300},
            last_run_at=datetime.now(timezone.utc) - timedelta(seconds=3000),
        )
        s.add(t)
        s.commit()
        tid = t.id

    # ...then the user deletes the search before the reaper runs.
    with Session() as s:
        s.delete(s.get(ScrapeTask, tid))
        s.commit()

    worker_tasks.reap_stale_recurring_searches()

    # Nothing should have been re-enqueued against the missing row.
    assert all(
        (len(args) < 2 or args[1] != tid) for args in calls if args
    ), f"reaper re-enqueued deleted task {tid}: {calls}"
