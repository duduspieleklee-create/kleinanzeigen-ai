FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app/shared ./app/shared
COPY app/beat ./app/beat

CMD ["celery", "-A", "app.beat.celery_app", "beat", "--loglevel=info"]
