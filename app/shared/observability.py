"""Zentrale Sentry/Observability-Schicht für kleinanzeigen-ai.

Bündelt, was vorher verstreut war:
- init_sentry(component): SDK-Init + globale Datenschutz-/Tag-Konventionen.
- SentryLogHandler: alle ERROR/Critical landen automatisch als Sentry-Event
  (inkl. exc_info) -> keine händischen capture_exception mehr nötig.
- track_job: Context-Manager UND Decorator für started/completed/failed/duration
  + automatischen Fehler-Context (task_id/user/keywords).
- metric / timing: dünne Wrapper, damit Attribute (component/env) nicht überall
  wiederholt werden.

Alles ist ein No-Op ohne SENTRY_DSN bzw. in dev ohne SENTRY_ENABLE_IN_DEV.
"""
import functools
import logging
import time
from contextlib import contextmanager
from typing import Optional

import sentry_sdk
import sentry_sdk.metrics as sentry_metrics

from app.api.config import settings
from app.shared.logging_config import logger
from app.shared.metrics_prom import prom_counter, job_duration

# Felder, die wir nie in Sentry-Events leaken wollen (DSGVO + Secret-Hygiene).
_REDACT_KEYS = (
    "dsn", "token", "api_key", "apikey", "secret", "password", "vapid",
    "client_secret", "access_token", "authorization", "private_key", "p256dh",
)


def _redact(value):
    """Rekursiv Secrets aus dicts/lists/strings entfernen."""
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if any(s in k.lower() for s in _REDACT_KEYS) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


def _before_send(event, hint):
    """Globaler Hook: Secrets aus extra/contexts/request redacten."""
    if event.get("extra"):
        event["extra"] = _redact(event["extra"])
    if event.get("contexts"):
        event["contexts"] = _redact(event["contexts"])
    req = event.get("request")
    if isinstance(req, dict):
        if req.get("data"):
            req["data"] = _redact(req["data"])
        if req.get("headers"):
            req["headers"] = _redact(req["headers"])
    return event


def init_sentry(component: str) -> None:
    """Initialise Sentry error tracking. No-op if SENTRY_DSN is unset, or in
    dev unless SENTRY_ENABLE_IN_DEV is also set (avoids noisy local events).

    Sets shared tags (component/env/git_sha) once and installs a before_send
    that redacts secrets globally — so no caller has to sanitize by hand.
    """
    if not settings.sentry_dsn:
        return
    if settings.environment == "dev" and not settings.sentry_enable_in_dev:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.git_sha,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        send_default_pii=False,  # DSGVO: keine IPs/Emails automatisch mitsenden
        before_send=_before_send,
    )
    sentry_sdk.set_tag("component", component)
    sentry_sdk.set_tag("env", settings.environment)
    if settings.git_sha:
        sentry_sdk.set_tag("git_sha", settings.git_sha)
    logger.info(f"Sentry error tracking enabled for component={component}")


class SentryLogHandler(logging.Handler):
    """Bridge: ab level ERROR automatisch an Sentry (inkl. exc_info).

    Erlaubt es, logger.error(...) ohne extra capture_exception() zu nutzen.
    ERROR- und CRITICAL-Logs werden als Sentry-Event gereicht; lower levels
    werden ignoriert, damit INFO/DEBUG nicht das Quota fluten.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < self.level:
            return
        if not settings.sentry_dsn:
            return
        if settings.environment == "dev" and not settings.sentry_enable_in_dev:
            return
        if not sentry_sdk.get_client().options.get("dsn"):
            return
        # Wenn exc_info bereits am Logger hängt, übernimmt capture_exception
        # den Traceback sauber; sonst reicht capture_message mit dem Text.
        if record.exc_info:
            sentry_sdk.capture_exception(record.exc_info[1])
        else:
            sentry_sdk.capture_message(record.getMessage(), level="error")


def install_log_bridge() -> None:
    """Hängt den SentryLogHandler an den Root-Logger an (idempotent)."""
    for h in logging.getLogger().handlers:
        if isinstance(h, SentryLogHandler):
            return
    sentry_handler = SentryLogHandler()
    sentry_handler.setLevel(logging.ERROR)
    logging.getLogger().addHandler(sentry_handler)


@contextmanager
def track_job(job_name: str, tags: Optional[dict] = None):
    """Emit started/completed/failed counters and a duration distribution for one job run.

    job.started / job.completed / job.failed (counters, tag: job)
    job.duration_ms (distribution, tag: job)
    Spiegelt dieselben Metriken nach Prometheus (job_started_total etc.).

    On failure, captures the exception with the supplied tags as context.
    """
    sentry_metrics.count("job.started", 1, attributes={"job": job_name})
    prom_counter("job.started", task=job_name)
    start = time.monotonic()
    failed = False
    try:
        yield
    except Exception:
        failed = True
        if tags:
            sentry_sdk.set_context("job", tags)
        sentry_sdk.capture_exception()
        raise
    finally:
        sentry_metrics.count(
            "job.failed" if failed else "job.completed", 1, attributes={"job": job_name}
        )
        prom_counter("job.failed" if failed else "job.completed", task=job_name)
        duration_s = time.monotonic() - start
        sentry_metrics.distribution(
            "job.duration_ms",
            duration_s * 1000,
            unit="millisecond",
            attributes={"job": job_name},
        )
        job_duration.labels(task=job_name).observe(duration_s)


def track_job_decorator(job_name: Optional[str] = None, *, tags_fn=None):
    """Decorator-Variante von track_job für Funktionen/Beat-Tasks.

    job_name default = ``func.__module__ + "." + func.__name__``.
    tags_fn(func, args, kwargs) -> dict optional für zusätzlichen Context.
    """
    def decorator(func):
        name = job_name or f"{func.__module__}.{func.__name__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ctx = tags_fn(func, args, kwargs) if tags_fn else None
            with track_job(name, ctx):
                return func(*args, **kwargs)

        return wrapper
    return decorator


def set_request_context(user_id: Optional[int], path: str, method: str) -> None:
    """Setzt User/Route-Context für API-Requests (Filterbarkeit in Sentry)."""
    if user_id is not None:
        sentry_sdk.set_user({"id": str(user_id)})  # nur id, keine E-Mail (DSGVO)
    sentry_sdk.set_tag("path", path)
    sentry_sdk.set_tag("method", method)


def metric(name: str, value: float = 1, unit: Optional[str] = None, **tags) -> None:
    """Dünner Counter-Wrapper mit automatischem component/env-Tag.

    Spiegelt nach Prometheus, falls der Name gemappt ist.
    """
    attrs = {"component": settings.environment}
    attrs.update(tags)
    if unit:
        sentry_metrics.distribution(name, value, unit=unit, attributes=attrs)
    else:
        sentry_metrics.count(name, value, attributes=attrs)
    prom_counter(name, value, **tags)


@contextmanager
def timing(name: str, **tags):
    """Misst Dauer einer Code-Strecke als distribution ``name`` (ms)."""
    start = time.monotonic()
    try:
        yield
    finally:
        attrs = {"component": settings.environment}
        attrs.update(tags)
        sentry_metrics.distribution(name, (time.monotonic() - start) * 1000,
                                     unit="millisecond", attributes=attrs)
