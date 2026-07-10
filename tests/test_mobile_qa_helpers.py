"""Regression tests for mobile-first QA helpers (audit 2026-07-10).

Covers the dev-only quick-login route used to screenshot the authenticated
dashboard on mobile without solving the Cloudflare Turnstile challenge.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.api.main as m
from app.shared.database import Base, engine


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    return TestClient(m.app, follow_redirects=False)


def test_dev_login_as_forbidden_in_prod(client):
    with patch("app.api.routers.auth.settings") as s:
        s.environment = "production"
        s.turnstile_enabled = True
        resp = client.get("/auth/dev/login-as/1", follow_redirects=False)
    assert resp.status_code == 404


def test_dev_login_as_works_in_dev(client):
    import time

    uid = f"devqa{int(time.time() * 1000)}"
    # Create a user directly via the engine-bound session.
    from app.shared.database import SessionLocal
    from app.shared.models import User

    db = SessionLocal()
    u = User(
        username=uid,
        email=f"{uid}@example.com",
        hashed_password="x",
        is_active=1,
        email_verified=1,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    uid_pk = u.id
    db.close()

    with patch("app.api.routers.auth.settings") as s:
        s.environment = "dev"
        s.turnstile_enabled = True
        resp = client.get(f"/auth/dev/login-as/{uid_pk}", follow_redirects=False)

    assert resp.status_code == 303, resp.status_code
    assert resp.cookies.get("access_token")
    assert resp.headers["location"] == "/dashboard"
