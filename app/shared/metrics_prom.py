"""Prometheus-Export-Schicht für kleinanzeigen-ai.

Jeder Prozess (api/worker/beat) hat eine eigene Registry und exportiert seine
Metriken lokal; Prometheus scraped pro Target:
  - api:8000   (/metrics, FastAPI-Endpoint)
  - worker:8001 (start_http_server im celery_app)
  - beat:8002   (start_http_server im celery_beat)

Metriken werden einmalig hier als Module-Level Objekte definiert, damit sie
von allen Callern wiederverwendt werden (Prometheus-Regeln: ein Metric = ein
Objekt, nie pro Call neu erzeugt).

Wrapper (prom_counter/prom_histogram/prom_gauge) erlauben es, denselben
Aufruf wie bei Sentry zu nutzen, ohne die Caller zu ändern.
"""
import os

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.exposition import CONTENT_TYPE_LATEST

# Multiprocess-Mode für prefork-Worker: Fork-Children schreiben Metriken in
# mmap-Dateien unter PROMETHEUS_MULTIPROC_DIR, der Exporter aggregiert beim
# Scrape. Ohne das würde der Exporter (MainProcess) nur Import-Zeit-Werte der
# in Fork-Children inkrementierten Counter zeigen. API/Beat (single-process)
# setzen die Env nicht und laufen im Normal-Mode.
_MULTIPROC = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

# Prozess-lokale Registry (kein Multi-Process-Mode nötig: api = single uvicorn
# worker, worker/beat = je eigener Prozess mit eigenem HTTP-Exporter).
REGISTRY = CollectorRegistry()

# ── Jobs ────────────────────────────────────────────────────────────────────
job_started = Counter("job_started_total", "Jobs started", ["task"], registry=REGISTRY)
job_completed = Counter("job_completed_total", "Jobs completed", ["task"], registry=REGISTRY)
job_failed = Counter("job_failed_total", "Jobs failed", ["task"], registry=REGISTRY)
job_duration = Histogram(
    "job_duration_seconds", "Job duration", ["task"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600), registry=REGISTRY,
)

# ── Scraping ──────────────────────────────────────────────────────────────
scrape_listings = Counter(
    "scrape_listings_found_total", "New listings found", ["baseline"], registry=REGISTRY
)
admin_search_dispatched = Counter(
    "admin_search_dispatched_total", "Admin searches dispatched", registry=REGISTRY
)
recurring_reaped = Counter(
    "scrape_recurring_reaped_total", "Stale recurring searches reaped", registry=REGISTRY
)

# ── Notifications ──────────────────────────────────────────────────────────
push_sent = Counter("notifications_push_sent_total", "Push notifications sent", registry=REGISTRY)
push_failed = Counter("notifications_push_failed_total", "Push notifications failed", registry=REGISTRY)
email_sent = Counter("notifications_email_sent_total", "Emails sent", registry=REGISTRY)
email_failed = Counter("notifications_email_failed_total", "Emails failed", registry=REGISTRY)

# ── Seller / Trust extraction ─────────────────────────────────────────────
seller_req = Counter(
    "seller_extraction_requests_total", "Seller extractions", ["cached"], registry=REGISTRY
)

# ── Archival ─────────────────────────────────────────────────────────────
archival_results = Counter(
    "archival_results_purged_total", "Old results purged", registry=REGISTRY
)
archival_token = Counter(
    "archival_token_usage_purged_total", "Token usage rows purged", registry=REGISTRY
)

# ── System (DB-pollende Gauges, von API collector befüllt) ──────────────────
searches_active = Gauge(
    "searches_active", "Active user searches", registry=REGISTRY,
    multiprocess_mode="livesum",
)
worker_heartbeat = Gauge(
    "worker_heartbeat", "1 if worker processed a beat tick recently", registry=REGISTRY,
    multiprocess_mode="livesum",
)


def prom_counter(name: str, value: float = 1, **labels) -> None:
    """Dünner Wrapper: mappt unsere Sentry-ähnlichen Namen auf die Registry-Objekte.

    Erlaubt es Callern, Prometheus ohne Kenntnis der Objekte zu nutzen; wir
    routen über die vordefinierten Metriken, da Prometheus keine dynamischen
    Metriknamen zur Laufzeit mag (jeder Name = ein Objekt).
    """
    mapping = {
        "job.started": (job_started,),
        "job.completed": (job_completed,),
        "job.failed": (job_failed,),
        "scrape.listings_found": (scrape_listings,),
        "admin_search.dispatched": (admin_search_dispatched,),
        "scrape.recurring_reaped": (recurring_reaped,),
        "notifications.push_sent": (push_sent,),
        "notifications.push_failed": (push_failed,),
        "notifications.email_sent": (email_sent,),
        "notifications.email_failed": (email_failed,),
        "seller_extraction.request": (seller_req,),
        "archival.results_purged": (archival_results,),
        "archival.token_usage_purged": (archival_token,),
    }
    target = mapping.get(name)
    if not target:
        return
    metric_obj = target[0]
    if labels:
        metric_obj.labels(**labels).inc(value)
    else:
        metric_obj.inc(value)


def _exposition_registry() -> CollectorRegistry:
    """Registry für die Ausgabe — im Multiprocess-Mode über alle Prozesse aggregiert."""
    if _MULTIPROC:
        from prometheus_client import multiprocess
        reg = CollectorRegistry()
        multiprocess.MultiProcessCollector(reg)
        return reg
    return REGISTRY


def start_exporter(port: int) -> None:
    """Startet den Prometheus-HTTP-Exporter idempotent.

    Mehrere Prozesse teilen sich denselben Code (die API importiert z.B. tasks
    und damit celery_app); ein bereits gebundener Port darf den Import nicht
    crashen lassen.
    """
    from prometheus_client import start_http_server
    try:
        start_http_server(port, registry=_exposition_registry())
    except OSError:
        pass


def render_metrics() -> tuple[str, str]:
    """Liefert (body, content_type) für den FastAPI /metrics Endpoint."""
    return generate_latest(_exposition_registry()).decode("utf-8"), CONTENT_TYPE_LATEST


def start_db_collector(interval: int = 60) -> None:
    """Hintergrund-Thread: pollt DB-Metriken in Gauges (nur in der API).

    Setzt ``searches_active`` periodisch. Worker/Beat erkennt Prometheus via
    ``up{job=...}`` (Exporter erreichbar?), kein separater Heartbeat nötig.
    """
    import threading
    from app.shared.database import SessionLocal
    from app.shared.models import ScrapeTask

    def _loop() -> None:
        while True:
            try:
                db = SessionLocal()
                try:
                    active = (
                        db.query(ScrapeTask)
                        .filter(ScrapeTask.status.in_(["running", "completed", "pending"]))
                        .count()
                    )
                    searches_active.set(active)
                finally:
                    db.close()
            except Exception:
                pass
            threading.Event().wait(interval)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
