import ssl
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Redis connection from environment variable
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# rediss:// (Azure Cache for Redis) requires SSL — disable cert verification
# because Azure uses a certificate that may not be in the default CA bundle.
_USE_SSL = REDIS_URL.startswith("rediss://")
_SSL_OPTS = {"ssl_cert_reqs": ssl.CERT_NONE} if _USE_SSL else {}

celery_app = Celery(
    "kleinanzeigen-ai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    broker_use_ssl=_SSL_OPTS or None,
    redis_backend_use_ssl=_SSL_OPTS or None,
)
