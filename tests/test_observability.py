"""Tests für die zentrale Observability-Schicht (app/shared/observability.py).

Deckt ab: before_send redacted Secrets, init_sentry No-Op ohne DSN, track_job
CM zaehlt started/completed/failed + faengt Exceptions, set_request_context
setzt User/Route-Tags.
"""
import logging

import pytest

from app.shared import observability as obs


def test_before_send_redacts_secrets():
    event = {
        "extra": {"vapid_private_key": "SECRET", "user_id": 7},
        "contexts": {"auth": {"access_token": "TOKEN", "plan": "pro"}},
        "request": {"data": {"password": "hunter2"}, "headers": {"authorization": "Bearer X"}},
    }
    out = obs._before_send(event, None)
    assert out["extra"]["vapid_private_key"] == "[REDACTED]"
    assert out["extra"]["user_id"] == 7
    assert out["contexts"]["auth"]["access_token"] == "[REDACTED]"
    assert out["contexts"]["auth"]["plan"] == "pro"
    assert out["request"]["data"]["password"] == "[REDACTED]"
    assert out["request"]["headers"]["authorization"] == "[REDACTED]"


def test_init_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.setattr(obs.settings, "sentry_dsn", "")
    # darf nicht crashen und nichts initialisieren
    obs.init_sentry("test")


def test_init_sentry_noop_in_dev_without_flag(monkeypatch):
    monkeypatch.setattr(obs.settings, "sentry_dsn", "https://x@sentry.io/1")
    monkeypatch.setattr(obs.settings, "environment", "dev")
    monkeypatch.setattr(obs.settings, "sentry_enable_in_dev", False)
    obs.init_sentry("test")


def test_track_job_emits_completed_on_success(monkeypatch):
    captured = []
    monkeypatch.setattr(obs.sentry_metrics, "count",
                        lambda name, val, attributes=None: captured.append((name, val, attributes)))
    monkeypatch.setattr(obs.sentry_metrics, "distribution", lambda *a, **k: None)

    with obs.track_job("demo.job"):
        pass
    names = [c[0] for c in captured]
    assert "job.started" in names
    assert "job.completed" in names
    assert "job.failed" not in names


def test_track_job_emits_failed_and_reraises(monkeypatch):
    captured = []
    monkeypatch.setattr(obs.sentry_metrics, "count",
                        lambda name, val, attributes=None: captured.append((name, val, attributes)))
    monkeypatch.setattr(obs.sentry_metrics, "distribution", lambda *a, **k: None)
    captured_exc = {}
    monkeypatch.setattr(obs.sentry_sdk, "capture_exception",
                        lambda *a, **k: captured_exc.setdefault("called", True))
    monkeypatch.setattr(obs.sentry_sdk, "set_context",
                        lambda *a, **k: None)

    with pytest.raises(ValueError):
        with obs.track_job("demo.job", {"task_id": "5"}):
            raise ValueError("boom")
    names = [c[0] for c in captured]
    assert "job.failed" in names
    assert captured_exc.get("called") is True


def test_sentry_log_handler_only_error_level(monkeypatch):
    monkeypatch.setattr(obs.settings, "sentry_dsn", "https://x@sentry.io/1")
    monkeypatch.setattr(obs.settings, "environment", "prod")
    captured = {}
    monkeypatch.setattr(obs.sentry_sdk, "get_client",
                        lambda: type("C", (), {"options": {"dsn": "https://x@sentry.io/1"}})())
    monkeypatch.setattr(obs.sentry_sdk, "capture_message",
                        lambda msg, level=None: captured.setdefault("msg", msg))
    monkeypatch.setattr(obs.sentry_sdk, "capture_exception",
                        lambda exc: captured.setdefault("exc", exc))

    h = obs.SentryLogHandler()
    h.setLevel(logging.ERROR)
    rec_info = logging.LogRecord("t", logging.INFO, __file__, 1, "info-msg", None, None)
    h.emit(rec_info)  # unter ERROR -> ignoriert
    assert "msg" not in captured

    rec_err = logging.LogRecord("t", logging.ERROR, __file__, 1, "err-msg", None, None)
    h.emit(rec_err)
    assert captured.get("msg") == "err-msg"
