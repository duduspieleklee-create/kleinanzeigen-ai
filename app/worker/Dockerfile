FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Drop root privileges — run the worker as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Cloud Run requires the container to accept connections on $PORT even for
# a non-HTTP background service — health_shim opens a no-op listener for it.
CMD ["sh", "-c", "python -m app.shared.health_shim & exec celery -A app.worker.celery_app worker --loglevel=info"]
