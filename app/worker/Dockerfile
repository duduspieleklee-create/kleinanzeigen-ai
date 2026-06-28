FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app/shared ./app/shared
COPY app/worker ./app/worker

CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=info"]
