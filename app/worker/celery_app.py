import ssl
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Prometheus multiprocess-dir (prefork-Worker) vor dem metrics_prom-Import
# vorbereiten: Verzeichnis anlegen und Altbestände leeren, damit tote PIDs
# keine Geister-Serien hinterlassen.
_PROM_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
if _PROM_DIR:
    import glob
    os.makedirs(_PROM_DIR, exist_ok=True)
    for _f in glob.glob(os.path.join(_PROM_DIR, "*.db")):
        try:
            os.remove(_f)
        except OSError:
            pass

from app.shared.sentry import init_sentry  # noqa: E402 — must follow load_dotenv()
from app.shared.observability import install_log_bridge  # noqa: E402
from app.shared.metrics_prom import start_exporter  # noqa: E402

init_sentry("worker")
install_log_bridge()
# Prometheus exporter für diesen Prozess (scrape target worker:8001).
start_exporter(8001)

# Redis connection from environment variable
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# rediss:// (Memorystore in-transit encryption, if enabled) requires SSL —
# disable cert verification since the certificate may not be in the default
# CA bundle. Plain redis:// (Memorystore's default, private-IP-only) skips this.
_USE_SSL = REDIS_URL.startswith("rediss://")
_SSL_OPTS = {"ssl_cert_reqs": ssl.CERT_NONE} if _USE_SSL else {}

celery_app = Celery(
    "kleinanzeigen-ai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.worker.tasks",
        "app.worker.archival_task",
        "app.worker.category_rotation_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # Hard timeout: 30 minutes
    task_soft_time_limit=25 * 60,  # Soft timeout: 25 minutes (allows graceful cleanup)
    broker_use_ssl=_SSL_OPTS or None,
    redis_backend_use_ssl=_SSL_OPTS or None,
)

# Prometheus multiprocess: wenn ein prefork-Child recycelt wird, seine mmap-
# Counter-Dateien für die Aggregation markieren (sonst verschwinden die Werte).
if _PROM_DIR:
    from celery.signals import worker_process_shutdown

    @worker_process_shutdown.connect
    def _prom_mark_dead(pid=None, **_):
        from prometheus_client import multiprocess
        multiprocess.mark_process_dead(pid or os.getpid())
