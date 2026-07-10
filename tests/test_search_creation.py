"""Tests for search-creation hardening (issues #154-#162).

Drives the real routes through FastAPI's TestClient so Form(...) parsing,
redirects, and Set-Cookie flashes all behave exactly as in production.

The app's get_db / get_current_user dependencies are overridden with an
in-memory SQLite session and a fixture user, so no network or auth is needed.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.shared.database import Base, get_db
from app.api.dependencies import get_current_user
from app.shared.models import ScrapeTask, User, AdminSearch

import app.api.routers.scrapes as scrapes_router


@pytest.fixture
def client_and_db():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)

    user = User(username="tester", email="t@example.com", hashed_password="x",
                plan="basic", is_admin=False)
    user.credits = 50
    user.credits_reset_at = None
    user.email_verified = True
    admin = User(username="admin", email="a@example.com", hashed_password="x",
                 plan="pro", is_admin=True)
    admin.credits = 50
    admin.credits_reset_at = None
    admin.email_verified = True

    # No Redis/broker in the test environment — stub the Celery enqueue so
    # valid searches don't try to connect to localhost:6379.
    saved_delay = scrapes_router.scrape_kleinanzeigen.delay
    scrapes_router.scrape_kleinanzeigen.delay = lambda *a, **k: None

    with Session() as db:
        db.add_all([user, admin])
        db.commit()
        user_id = user.id
        admin_id = admin.id

    def _override_db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": user_id,
        "is_admin": False,
        "email": "t@example.com",
    }

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c, Session, user_id, admin_id

    scrapes_router.scrape_kleinanzeigen.delay = saved_delay
    app.dependency_overrides.clear()


def _flash_error(client):
    # Re-read the dashboard after a redirect; the flash_error cookie is set on
    # the redirect response. TestClient follows redirects, so check cookies.
    return client.cookies.get("flash_error")



# ── Validation (issue #157) ────────────────────────────────────────────────

def test_negative_price_rejected(client_and_db):
    c, Session, user_id, _ = client_and_db
    r = c.post("/scrapes/", data={"keywords": "sofa", "price_min": "-5"},
               follow_redirects=False)
    assert r.status_code == 303
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 0


def test_radius_without_location_rejected(client_and_db):
    c, Session, user_id, _ = client_and_db
    r = c.post("/scrapes/", data={"keywords": "sofa", "radius": "50"},
               follow_redirects=False)
    assert r.status_code == 303
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 0


def test_overlong_keywords_rejected(client_and_db):
    c, Session, user_id, _ = client_and_db
    r = c.post("/scrapes/", data={"keywords": "x" * 300}, follow_redirects=False)
    assert r.status_code == 303
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 0


def test_price_min_greater_than_max_rejected(client_and_db):
    c, Session, user_id, _ = client_and_db
    r = c.post("/scrapes/", data={"keywords": "sofa", "price_min": "100",
                                  "price_max": "50"}, follow_redirects=False)
    assert r.status_code == 303
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 0


def test_valid_search_creates_task(client_and_db):
    c, Session, user_id, _ = client_and_db
    r = c.post("/scrapes/", data={"keywords": "sofa", "location": "berlin",
                                  "location_id": "123", "interval_seconds": "3600"},
               follow_redirects=False)
    assert r.status_code == 303
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 1


def test_radius_with_location_id_succeeds(client_and_db):
    """Regression for the 'radius requires a selected location' rejection:
    when the wizard actually submits location_id (populated from the
    suggestion's `id` field), a radius is accepted and the search is created.
    This guards against the client silently dropping location_id (item.value
    bug)."""
    c, Session, user_id, _ = client_and_db
    r = c.post("/scrapes/", data={"keywords": "sofa", "location": "berlin",
                                  "location_id": "123", "radius": "50",
                                  "interval_seconds": "3600"},
               follow_redirects=False)
    assert r.status_code == 303
    assert not c.cookies.get("flash_error")
    with Session() as db:
        task = db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).first()
        assert task is not None
        assert task.parameters.get("radius") == 50
        assert task.parameters.get("location_id") == 123


def test_free_text_location_resolves_for_radius(client_and_db, monkeypatch):
    """Server-side hardening (issue #168): a user who types a location and
    sets a radius but never sends location_id must NOT be rejected with
    'A radius requires a selected location'. create_scrape resolves the
    free-text location via suggest_locations and stores the resolved id."""
    import app.shared.locations_client as loc_client

    monkeypatch.setattr(
        loc_client, "suggest_locations",
        lambda q, timeout=5.0: [{"id": "777", "label": "Berlin (Mitte)"}],
    )
    c, Session, user_id, _ = client_and_db
    r = c.post("/scrapes/", data={"keywords": "sofa", "location": "berlin",
                                  "radius": "50", "interval_seconds": "3600"},
               follow_redirects=False)
    assert r.status_code == 303
    assert not c.cookies.get("flash_error")
    with Session() as db:
        task = db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).first()
        assert task is not None
        assert task.parameters.get("radius") == 50
        assert task.parameters.get("location_id") == 777
        # canonical label preferred over the raw free text
        assert task.parameters.get("location") == "Berlin (Mitte)"


# ── Duplicate guard (issue #155) ───────────────────────────────────────────

def test_duplicate_user_search_blocked(client_and_db):
    c, Session, user_id, _ = client_and_db
    payload = {"keywords": "sofa", "location": "berlin", "location_id": "123",
               "interval_seconds": "3600"}
    c.post("/scrapes/", data=payload, follow_redirects=False)
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 1
    r2 = c.post("/scrapes/", data=payload, follow_redirects=False)
    assert r2.status_code == 303
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 1


def test_different_search_allowed(client_and_db):
    c, Session, user_id, _ = client_and_db
    c.post("/scrapes/", data={"keywords": "sofa", "interval_seconds": "3600"},
           follow_redirects=False)
    c.post("/scrapes/", data={"keywords": "tisch", "interval_seconds": "3600"},
           follow_redirects=False)
    with Session() as db:
        assert db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).count() == 2


# ── One-shot (issue #160): interval omitted → no interval_seconds ──────────

def test_oneshot_search_has_no_interval(client_and_db):
    c, Session, user_id, _ = client_and_db
    c.post("/scrapes/", data={"keywords": "sofa"}, follow_redirects=False)
    with Session() as db:
        task = db.query(ScrapeTask).filter(ScrapeTask.user_id == user_id).first()
        assert task is not None
        assert "interval_seconds" not in (task.parameters or {})


# ── Preview endpoint (issue #156) ──────────────────────────────────────────

def test_preview_returns_resolved_url(client_and_db):
    c, _, _, _ = client_and_db
    r = c.get("/scrapes/preview", params={"keywords": "sofa", "location": "berlin",
                                          "location_id": 123})
    assert r.status_code == 200
    body = r.json()
    assert "url" in body
    assert "berlin" in body["url"]
    assert "k0l123" in body["url"]


# ── Admin validation + duplicate guard (issue #159) ────────────────────────

def test_admin_interval_zero_rejected(client_and_db):
    c, Session, _, admin_id = client_and_db
    app = c.app
    app.dependency_overrides[get_current_user] = lambda: {
        "id": admin_id, "is_admin": True, "email": "a@example.com"
    }
    r = c.post("/admin/searches", data={"keywords": "werkzeug", "interval_minutes": "0"},
               follow_redirects=False)
    assert r.status_code == 303
    with Session() as db:
        assert db.query(AdminSearch).count() == 0


def test_admin_radius_without_location_rejected(client_and_db):
    c, Session, _, admin_id = client_and_db
    c.app.dependency_overrides[get_current_user] = lambda: {
        "id": admin_id, "is_admin": True, "email": "a@example.com"
    }
    r = c.post("/admin/searches", data={"keywords": "werkzeug", "radius": "50",
                                        "interval_minutes": "30"},
               follow_redirects=False)
    assert r.status_code == 303
    with Session() as db:
        assert db.query(AdminSearch).count() == 0


def test_admin_duplicate_blocked(client_and_db):
    c, Session, _, admin_id = client_and_db
    c.app.dependency_overrides[get_current_user] = lambda: {
        "id": admin_id, "is_admin": True, "email": "a@example.com"
    }
    payload = {"keywords": "werkzeug", "category": "handwerk", "interval_minutes": "30"}
    c.post("/admin/searches", data=payload, follow_redirects=False)
    with Session() as db:
        assert db.query(AdminSearch).count() == 1
    r2 = c.post("/admin/searches", data=payload, follow_redirects=False)
    assert r2.status_code == 303
    with Session() as db:
        assert db.query(AdminSearch).count() == 1
