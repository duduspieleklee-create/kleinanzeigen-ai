"""Regression tests for non-ASCII flash-cookie encoding (audit 2026-07-10).

A user-facing flash message written in German (e.g. "Konto erstellt – prüfe
dein Postfach") contains non-latin-1 bytes. Starlette encodes Set-Cookie as
latin-1, so an unsanitized value raised UnicodeEncodeError at response time
and turned a successful registration into a 500. These tests pin the fix.
"""
from unittest.mock import patch

import pytest
import time
from fastapi.testclient import TestClient

import app.api.main as m
from app.shared.cookies import ascii_cookie
from app.shared.database import Base, engine


def test_ascii_cookie_transliterates_german():
    s = "Konto erstellt – prüfe dein Postfach und klicke auf den Bestätigungslink."
    out = ascii_cookie(s)
    out.encode("latin-1")  # must not raise
    assert "–" not in out
    assert "ü" not in out and "ä" not in out
    assert "Konto erstellt - pruefe dein Postfach" in out


def test_ascii_cookie_drops_unmappable_bytes():
    assert ascii_cookie("emoji 🚀 boom") == "emoji  boom"


@pytest.fixture
def client():
    # Tables are created on the app's already-bound engine (in-memory test DB
    # from conftest). This is a self-contained, isolated test process.
    Base.metadata.create_all(bind=engine)
    return TestClient(m.app, follow_redirects=False)


def test_register_success_never_500_with_nonascii_flash(client):
    # Turnstile is enabled in the deployed .env; disable it for the happy path.
    # Unique username/email so the test is order-independent on the shared DB.
    uid = f"flashi{int(time.time() * 1000)}"
    with patch("app.api.routers.auth.turnstile_configured", return_value=False):
        resp = client.post(
            "/auth/register",
            data={
                "username": uid,
                "email": f"{uid}@example.com",
                "password": "password123",
                "confirm_password": "password123",
            },
            follow_redirects=False,
        )
    # Must redirect (303) with a session cookie — NOT a 500.
    assert resp.status_code == 303, resp.status_code
    assert resp.cookies.get("access_token")
    flash = resp.cookies.get("flash_success")
    if flash:
        flash.encode("latin-1")  # must not raise
